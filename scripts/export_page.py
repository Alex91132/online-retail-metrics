"""
Данные для страницы-записки docs/ из витрин marts/ и results/.

    python scripts/export_page.py
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
M, R = ROOT / "marts", ROOT / "results"
DATALENS_URL = ""          # публичная ссылка на дашборд — после публикации


def main():
    orders = pd.read_csv(M / "orders.csv", parse_dates=["month"])
    cohorts = pd.read_csv(M / "cohorts.csv", parse_dates=["cohort_month"])
    years = pd.read_csv(R / "years.csv").set_index("period")
    summary = json.loads((R / "summary.json").read_text(encoding="utf-8"))
    full = orders[orders.period.isin(["Год 1", "Год 2"])]

    monthly = (full.groupby(["period", "month"]).revenue.sum().reset_index()
               .assign(m=lambda d: d.month.dt.month))
    by_type = full.groupby(["period", "customer_type"]).revenue.sum().unstack()
    total = {p: float(full[full.period == p].revenue.sum()) for p in ("Год 1", "Год 2")}
    coh = cohorts[(cohorts.cohort_month > "2009-12-01") & (cohorts.month_number <= 12)]

    out = {
        "datalens": DATALENS_URL,
        "total": total,
        "years": years.reset_index().to_dict("records"),
        "by_type": {p: {k: float(v) for k, v in r.items()} for p, r in by_type.iterrows()},
        "bridge": pd.read_csv(M / "bridge.csv").to_dict("records"),
        "factors": pd.read_csv(M / "factors.csv").to_dict("records"),
        "monthly": [{"period": r.period, "m": int(r.m), "revenue": round(float(r.revenue))}
                    for r in monthly.itertuples()],
        "cohorts": [{"cohort": r.cohort_month.strftime("%Y-%m"), "n": int(r.month_number),
                     "retention": float(r.retention), "size": int(r.cohort_size)} for r in coh.itertuples()],
        "segments": pd.read_csv(R / "segments.csv").to_dict("records"),
        "cleaning": pd.read_csv(R / "cleaning.csv").fillna(0).to_dict("records"),
        **summary,
    }
    js = "window.DATA = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "data.js").write_text(js, encoding="utf-8")
    print(f"docs/data.js — {len(js) / 1e3:.0f} КБ")


if __name__ == "__main__":
    main()
