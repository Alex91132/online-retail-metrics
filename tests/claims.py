"""Числа, которые цитируют README и записка, — пересчёт из витрин `marts/`.

Здесь единственный список того, что мы обещаем читателю. `tests/test_claims.py` падает,
если хотя бы одно число разошлось, и печатает какое именно: это защита от дрейфа
между текстом и данными (текст записки в `docs/app.js` статичный).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MARTS = ROOT / "marts"
Y1, Y2 = "Год 1", "Год 2"

# то, что написано в README и на странице записки
EXPECTED = {
    "выручка, год 1, £": 9_155_346,
    "выручка, год 2, £": 9_330_523,
    "рост выручки, %": 1.91,
    "выручка клиентов с ID, изменение, %": -2.07,
    "прирост выручки без ID, £": 340_990,
    "оставшихся клиентов": 2_708,
    "заказы оставшихся, изменение, %": -8.4,
    "средний чек без ID, год 1, £": 686,
    "средний чек без ID, год 2, £": 1_057,
    "средний чек с ID, год 2, £": 467,
    "«Чемпионы», доля клиентов, %": 27.0,
    "«Чемпионы», доля выручки, %": 74.3,
    "737 клиентов на реактивацию, год 1, £": 1_160_955,
    "737 клиентов на реактивацию, год 2, £": 281_406,
    "Австралия, год 1, £": 29_360,
    "Австралия, год 2, £": 136_922,
    "доля Великобритании, %": 85.3,
    "удержание янв–авг 2010, %": 18.6,
    "удержание янв–авг 2011, %": 20.7,
}

TOL = {"£": 1.0, "%": 0.05, "клиентов": 0.0}          # деньги — до фунта, проценты — до 0.05 п.п.


def _tol(key: str) -> float:
    """Допуск по единице в конце названия: деньги в фунтах, проценты в п.п., клиенты — точно."""
    if key.endswith("£"):
        return TOL["£"]
    if key.endswith("%"):
        return TOL["%"]
    return TOL["клиентов"]


def computed(marts: Path = MARTS) -> dict[str, float]:
    """Пересчитывает всё, что цитируется, из витрин."""
    o = pd.read_csv(marts / "orders.csv", parse_dates=["invoice_date"])
    o = o[o.period.isin([Y1, Y2])]                    # декабрь 2011 неполный — вне сравнений
    c = pd.read_csv(marts / "customers.csv")
    pos = o[o.revenue > 0]                            # заказы = чеки без отмен (METRICS.md)

    rev = o.groupby("period").revenue.sum()
    piv = o.pivot_table(index="period", columns="customer_type", values="revenue", aggfunc="sum")
    with_id = piv.drop(columns="Без ID").sum(axis=1)

    n = pos.dropna(subset=["customer_id"]).groupby(["customer_id", "period"]).size().unstack(fill_value=0)
    ret = n[(n[Y1] > 0) & (n[Y2] > 0)]

    noid = pos[pos.customer_type == "Без ID"]
    aov_noid = noid.groupby("period").revenue.sum() / noid.groupby("period").size()
    wid2 = pos[(pos.customer_type != "Без ID") & (pos.period == Y2)]

    seg = c.groupby("segment").agg(customers=("customer_id", "size"), revenue_all=("revenue", "sum"),
                                   revenue_y1=("revenue_y1", "sum"), revenue_y2=("revenue_y2", "sum"))
    risky = c[c.segment.isin(["Нельзя потерять", "Под угрозой"])]
    au = o[o.country == "Australia"].groupby("period").revenue.sum()

    co = pd.read_csv(marts / "cohorts.csv", parse_dates=["cohort_month"])
    m1 = co[co.month_number == 1]

    def retention(year: int) -> float:
        g = m1[(m1.cohort_month.dt.year == year) & (m1.cohort_month.dt.month <= 8)]
        return float(g.retention.mean() * 100)

    return {
        "выручка, год 1, £": float(rev[Y1]),
        "выручка, год 2, £": float(rev[Y2]),
        "рост выручки, %": float((rev[Y2] / rev[Y1] - 1) * 100),
        "выручка клиентов с ID, изменение, %": float((with_id[Y2] / with_id[Y1] - 1) * 100),
        "прирост выручки без ID, £": float(piv.loc[Y2, "Без ID"] - piv.loc[Y1, "Без ID"]),
        "оставшихся клиентов": float(len(ret)),
        "заказы оставшихся, изменение, %": float((ret[Y2].sum() / ret[Y1].sum() - 1) * 100),
        "средний чек без ID, год 1, £": float(aov_noid[Y1]),
        "средний чек без ID, год 2, £": float(aov_noid[Y2]),
        "средний чек с ID, год 2, £": float(wid2.revenue.sum() / len(wid2)),
        "«Чемпионы», доля клиентов, %": float(seg.loc["Чемпионы", "customers"] / seg.customers.sum() * 100),
        "«Чемпионы», доля выручки, %": float(seg.loc["Чемпионы", "revenue_all"] / seg.revenue_all.sum() * 100),
        "737 клиентов на реактивацию, год 1, £": float(risky.revenue_y1.sum()),
        "737 клиентов на реактивацию, год 2, £": float(risky.revenue_y2.sum()),
        "Австралия, год 1, £": float(au[Y1]),
        "Австралия, год 2, £": float(au[Y2]),
        "доля Великобритании, %": float(o[o.country == "United Kingdom"].revenue.sum() / o.revenue.sum() * 100),
        "удержание янв–авг 2010, %": retention(2010),
        "удержание янв–авг 2011, %": retention(2011),
    }


def check(marts: Path = MARTS) -> list[str]:
    """Список расхождений: пусто — текст и данные совпадают."""
    got = computed(marts)
    out = []
    for key, want in EXPECTED.items():
        if key not in got:
            out.append(f"{key}: нет в пересчёте")
            continue
        tol = _tol(key)
        if abs(got[key] - want) > tol:
            out.append(f"{key}: в тексте {want:,.3f}, в витринах {got[key]:,.3f}")
    extra = sorted(set(got) - set(EXPECTED))
    out += [f"{k}: считается, но не заявлено" for k in extra]
    return out
