"""
Полная сборка: сырые данные → SQL-витрины (DuckDB) → аналитика → CSV для DataLens и results/.

    python scripts/build.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402

from retail import analysis as A  # noqa: E402
from retail.data import load_raw  # noqa: E402

MARTS = ROOT / "marts"          # выгрузки для DataLens (коммитятся)
RESULTS = ROOT / "results"


def build(con=None):
    con = con or duckdb.connect()
    con.register("raw", load_raw())
    for f in sorted((ROOT / "sql").glob("*.sql")):
        con.execute(f.read_text(encoding="utf-8"))
    return con


def main():
    con = build()
    MARTS.mkdir(exist_ok=True)
    RESULTS.mkdir(exist_ok=True)
    # для DataLens: флаги 0/1, даты без времени там, где время не нужно
    exports = {
        "orders": "select * replace (is_cancellation::int as is_cancellation) from mart_orders order by invoice_date",
        "customers": "select * replace (first_purchase::date as first_purchase, last_purchase::date as last_purchase) "
                     "from mart_customers order by revenue desc",
        "cohorts": "select * from mart_cohorts order by cohort_month, month_number",
    }
    for name, sql in exports.items():
        con.execute(f"copy ({sql}) to '{(MARTS / (name + '.csv')).as_posix()}' (header, delimiter ',')")

    orders = con.execute("select * from mart_orders").df()
    customers = con.execute("select * from mart_customers").df()
    bridge, counts = A.revenue_bridge(orders)
    factors = A.factor_decomposition(orders)
    years = A.year_summary(orders)
    segments = A.segment_summary(customers)
    cleaning = con.execute("select * from cleaning_impact").df()
    raw_total = con.execute("select count(*), sum(quantity * price) from raw").fetchone()

    # порядок шагов и знак — DataLens сортирует и красит столбцы по полям, а не по положению строки
    bridge.insert(0, "step_order", range(1, len(bridge) + 1))
    bridge["sign"] = [("Итог" if k == "total" else "Рост" if v >= 0 else "Падение")
                      for k, v in zip(bridge.kind, bridge.value)]
    bridge.round(2).to_csv(MARTS / "bridge.csv", index=False)
    factors.round(4).to_csv(MARTS / "factors.csv", index=False)
    years.to_csv(RESULTS / "years.csv")
    segments.to_csv(RESULTS / "segments.csv", index=False)
    cleaning.to_csv(RESULTS / "cleaning.csv", index=False)

    region = (orders[orders.period.isin(["Год 1", "Год 2"])]
              .pivot_table(index="region", columns="period", values="revenue", aggfunc="sum"))
    summary = {
        "raw_lines": int(raw_total[0]), "raw_amount": float(raw_total[1]),
        "clean_lines": int(con.execute("select count(*) from stg_lines").fetchone()[0]),
        "bridge_counts": counts,
        "concentration_y2": A.concentration(customers),
        "region": {r: {"y1": float(v["Год 1"]), "y2": float(v["Год 2"])} for r, v in region.iterrows()},
        "cancel_rate": {p: float(-g[g.revenue < 0].revenue.sum() / g[g.revenue > 0].revenue.sum())
                        for p, g in orders[orders.period.isin(["Год 1", "Год 2"])].groupby("period")},
    }
    (RESULTS / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    print(years.round(2).to_string(), "\n")
    print(bridge.round(0).to_string(index=False), "\n", counts, "\n")
    print(factors.round(3).to_string(index=False), "\n")
    print(segments.round(3).to_string(index=False), "\n")
    print(cleaning.round(0).to_string(index=False))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for f in sorted(MARTS.glob("*.csv")):
        print(f"marts/{f.name}: {f.stat().st_size / 1e6:.1f} МБ")


if __name__ == "__main__":
    main()
