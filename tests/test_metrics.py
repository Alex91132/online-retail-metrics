import math
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from retail import analysis as A  # noqa: E402


def _raw():
    """Маленький набор строк со всеми ловушками настоящих данных."""
    rows = [
        # invoice, stock, desc, qty, date, price, customer, country
        ("100", "10001", "MUG", 10, "2010-01-05 10:00", 2.0, 1.0, "United Kingdom"),
        ("100", "10001", "MUG", 10, "2010-01-05 10:00", 2.0, 1.0, "United Kingdom"),     # точный дубль
        ("100", "POST", "POSTAGE", 1, "2010-01-05 10:00", 15.0, 1.0, "United Kingdom"),  # служебный код
        ("101", "10002", "BAG", 5, "2010-02-10 11:00", 4.0, 2.0, "France"),
        ("102", "10003", "FREE", 3, "2010-02-11 11:00", 0.0, 2.0, "France"),           # нулевая цена
        ("C103", "10002", "BAG", -2, "2010-02-12 12:00", 4.0, 2.0, "France"),           # отмена
        ("104", "10001", "MUG", 4, "2011-01-07 09:00", 2.5, 1.0, "United Kingdom"),     # клиент 1 вернулся
        ("105", "10004", "LAMP", 1, "2011-03-01 09:00", 30.0, 3.0, "Australia"),        # новый в год 2
        ("106", "10004", "LAMP", 2, "2011-04-01 09:00", 30.0, None, "United Kingdom"),  # без ID
        ("107", "10001", "MUG", 1, "2010-05-01 09:00", 2.0, None, "United Kingdom"),    # без ID, год 1
    ]
    df = pd.DataFrame(rows, columns=["invoice", "stock_code", "description", "quantity", "invoice_date",
                                     "price", "customer_id", "country"])
    df["invoice_date"] = pd.to_datetime(df.invoice_date)
    return df


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect()
    c.register("raw", _raw())
    for f in sorted((ROOT / "sql").glob("*.sql")):
        c.execute(f.read_text(encoding="utf-8"))
    return c


def test_cleaning_rules(con):
    lines = con.execute("select * from stg_lines").df()
    assert len(lines) == 7                                   # 10 − дубль − служебный − нулевая цена
    assert not lines.stock_code.eq("POST").any()
    assert lines.is_cancellation.sum() == 1
    impact = con.execute("select * from cleaning_impact").df().set_index("rule").lines
    assert impact.sum() == 3


def test_orders_mart_types(con):
    o = con.execute("select * from mart_orders").df().set_index("invoice")
    assert o.loc["100", "revenue"] == 20                     # дубль не задвоил выручку
    assert o.loc["100", "customer_type"] == "Новый"
    assert o.loc["104", "customer_type"] == "Вернувшийся"
    assert o.loc["106", "customer_type"] == "Без ID"
    assert o.loc["C103", "revenue"] == -8
    assert o.loc["105", "region"] == "Остальной мир"


def test_bridge_sums_to_total_change(con):
    o = con.execute("select * from mart_orders").df()
    bridge, counts = A.revenue_bridge(o)
    start, end = bridge.value.iloc[0], bridge.value.iloc[-1]
    assert start + bridge[bridge.kind == "step"].value.sum() == pytest.approx(end)
    assert counts == {"lost": 1, "retained": 1, "new": 1, "y1": 2}


def test_lmdi_is_exact():
    before = {"c": 100, "f": 4.0, "a": 50.0}
    after = {"c": 110, "f": 3.5, "a": 55.0}
    parts = A.lmdi(before, after)
    assert sum(parts.values()) == pytest.approx(math.prod(after.values()) - math.prod(before.values()))
    assert parts["f"] < 0 < parts["c"]
    assert A.lmdi(before, before) == {"c": 0, "f": 0, "a": 0}


def test_factor_decomposition_matches_revenue(con):
    o = con.execute("select * from mart_orders").df()
    f = A.factor_decomposition(o)
    y = A.year_summary(o)
    assert f.contribution.sum() == pytest.approx(y.loc["Год 2", "revenue"] - y.loc["Год 1", "revenue"])


def test_cohort_month_zero_is_full_retention(con):
    c = con.execute("select * from mart_cohorts").df()
    assert (c[c.month_number == 0].retention == 1).all()


def test_rfm_segments_cover_all_customers(con):
    c = con.execute("select * from mart_customers").df()
    assert c.segment.notna().all()
    assert set(c.r).issubset({1, 2, 3, 4, 5}) and set(c.f).issubset({1, 2, 3, 4, 5})
    assert c.set_index("customer_id").loc[3, "segment"] in {"Перспективные", "Новые", "Спящие", "Под угрозой"}


def test_concentration_monotonic():
    c = pd.DataFrame({"revenue_y2": np.arange(1, 101, dtype=float)})
    k = A.concentration(c)
    assert k["top1"] < k["top10"] < k["top20"] < 1
