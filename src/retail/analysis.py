"""Аналитика поверх витрин: мост выручки, факторное разложение, концентрация."""

import math

import pandas as pd


def log_mean(a, b):
    """Логарифмическое среднее L(a, b) — вес в разложении LMDI; L(a, a) = a."""
    if a == b:
        return a
    return (a - b) / (math.log(a) - math.log(b))


def lmdi(before, after):
    """
    Разложение изменения произведения факторов на вклады (LMDI-I):
    ΔV = Σ L(V₁, V₀) · ln(xᵢ₁ / xᵢ₀). Вклады в сумме дают ровно ΔV — без остатка «на взаимодействие».
    before, after — словари {фактор: значение}, V = произведение факторов.
    """
    v0 = math.prod(before.values())
    v1 = math.prod(after.values())
    w = log_mean(v1, v0)
    return {k: w * math.log(after[k] / before[k]) for k in before}


def year_summary(orders):
    """Клиенты, частота, средний чек и выручка по годам — для клиентов с ID и без."""
    o = orders[orders.period.isin(["Год 1", "Год 2"])]
    known = o[o.customer_id.notna()]
    rows = []
    for p, g in known.groupby("period"):
        purchases = g[~g.is_cancellation]
        customers = purchases.customer_id.nunique()
        n_orders = len(purchases)
        revenue = g.revenue.sum()
        rows.append({"period": p, "customers": customers, "orders": n_orders,
                     "frequency": n_orders / customers, "aov": revenue / n_orders, "revenue": revenue,
                     "revenue_no_id": o[(o.period == p) & o.customer_id.isna()].revenue.sum()})
    return pd.DataFrame(rows).set_index("period")


def factor_decomposition(orders):
    """Вклад числа клиентов, частоты и среднего чека в изменение выручки клиентов с ID (Год 1 → Год 2)."""
    s = year_summary(orders)
    b, a = s.loc["Год 1"], s.loc["Год 2"]
    f = ("customers", "frequency", "aov")
    parts = lmdi({k: b[k] for k in f}, {k: a[k] for k in f})
    names = {"customers": "Число клиентов", "frequency": "Частота покупок", "aov": "Средний чек"}
    return pd.DataFrame([{"factor": names[k], "before": b[k], "after": a[k],
                          "change_pct": a[k] / b[k] - 1, "contribution": v} for k, v in parts.items()])


def revenue_bridge(orders):
    """
    Мост выручки Год 1 → Год 2 по клиентам: ушедшие, изменение у оставшихся, новые, продажи без ID.
    Шаги в сумме дают ровно изменение выручки.
    """
    o = orders[orders.period.isin(["Год 1", "Год 2"])]
    known = o[o.customer_id.notna()]
    by = known.pivot_table(index="customer_id", columns="period", values="revenue", aggfunc="sum")
    bought = known[~known.is_cancellation].pivot_table(index="customer_id", columns="period",
                                                       values="invoice", aggfunc="count")
    y1 = bought["Год 1"].notna().reindex(by.index, fill_value=False)
    y2 = bought["Год 2"].notna().reindex(by.index, fill_value=False)
    r1, r2 = by["Год 1"].fillna(0), by["Год 2"].fillna(0)
    no_id = o[o.customer_id.isna()].groupby("period").revenue.sum()
    total1 = r1.sum() + no_id["Год 1"]
    steps = [
        ("Выручка, год 1", total1, "total"),
        ("Ушли клиенты", -r1[y1 & ~y2].sum() + r2[y1 & ~y2].sum(), "step"),
        ("Оставшиеся купили меньше", r2[y1 & y2].sum() - r1[y1 & y2].sum(), "step"),
        ("Новые клиенты", r2[~y1 & y2].sum() - r1[~y1 & y2].sum(), "step"),
        ("Продажи без ID клиента", no_id["Год 2"] - no_id["Год 1"], "step"),
    ]
    other = (r2[~y1 & ~y2].sum() - r1[~y1 & ~y2].sum())        # только отмены без покупок в обоих годах
    if abs(other) > 0.5:
        steps.append(("Прочее: только отмены", other, "step"))
    steps.append(("Выручка, год 2", r2.sum() + no_id["Год 2"], "total"))
    counts = {"lost": int((y1 & ~y2).sum()), "retained": int((y1 & y2).sum()), "new": int((~y1 & y2).sum()),
              "y1": int(y1.sum())}
    return pd.DataFrame(steps, columns=["step", "value", "kind"]), counts


def concentration(customers, col="revenue_y2"):
    """Доля выручки у топ-1/10/20 % клиентов."""
    r = customers[col].dropna()
    r = r[r > 0].sort_values(ascending=False)
    n, tot = len(r), r.sum()
    return {f"top{q}": float(r.iloc[:max(1, int(n * q / 100))].sum() / tot) for q in (1, 10, 20)}


def segment_summary(customers):
    s = customers.groupby("segment").agg(customers=("customer_id", "size"), revenue=("revenue", "sum"),
                                         revenue_y2=("revenue_y2", "sum"), recency=("recency_days", "median"),
                                         orders=("orders", "median"))
    s["share_customers"] = s.customers / s.customers.sum()
    s["share_revenue"] = s.revenue / s.revenue.sum()
    return s.sort_values("revenue", ascending=False).reset_index()
