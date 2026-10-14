"""
Дашборд «Метрики интернет-магазина» в Metabase — как код, через REST API.

    cd bi && docker compose up -d
    python bi/setup_metabase.py

Скрипт идемпотентен: при повторном запуске старая коллекция архивируется и всё создаётся заново.
Локальный администратор берётся из bi/.env (создаётся при первом запуске, в git не попадает).
"""

import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MB = "http://localhost:3030"
HERE = Path(__file__).resolve().parent
ENV = HERE / ".env"
TITLE = "Метрики интернет-магазина"
GREY, BLUE, GREEN, RED = "#9CA3AF", "#2563EB", "#16A34A", "#DC2626"
FULL = "period in ('Год 1', 'Год 2')"     # декабрь 2011 неполный — в сравнения не входит


# ---------- HTTP ----------
def call(method, path, body=None, session=None):
    req = urllib.request.Request(MB + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"X-Metabase-Session": session} if session else {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode()[:500]}") from None


def env():
    if not ENV.exists():
        ENV.write_text(f"MB_ADMIN_EMAIL=admin@retail.local\nMB_ADMIN_PASSWORD={secrets.token_urlsafe(18)}\n",
                       encoding="utf-8")
    return dict(line.split("=", 1) for line in ENV.read_text(encoding="utf-8").split())


def wait_ready():
    for _ in range(90):
        try:
            if call("GET", "/api/health")["status"] == "ok":
                return
        except Exception:  # noqa: BLE001 — Metabase ещё стартует
            pass
        time.sleep(5)
    sys.exit("Metabase не поднялся за 7,5 минут")


def login(e):
    props = call("GET", "/api/session/properties")
    if props.get("setup-token") and not props.get("has-user-setup"):
        call("POST", "/api/setup", {
            "token": props["setup-token"],
            "user": {"email": e["MB_ADMIN_EMAIL"], "password": e["MB_ADMIN_PASSWORD"],
                     "first_name": "Admin", "last_name": "Retail", "site_name": TITLE},
            "prefs": {"site_name": TITLE, "site_locale": "ru", "allow_tracking": False}})
    return call("POST", "/api/session", {"username": e["MB_ADMIN_EMAIL"], "password": e["MB_ADMIN_PASSWORD"]})["id"]


def database(s):
    dbs = call("GET", "/api/database", session=s)["data"]
    db = next((d for d in dbs if d["name"] == "Retail"), None)
    if db is None:
        db = call("POST", "/api/database", {
            "engine": "postgres", "name": "Retail",
            "details": {"host": "warehouse", "port": 5432, "dbname": "retail", "user": "retail",
                        "password": "retail", "schema-filters-type": "inclusion",
                        "schema-filters-patterns": "mart"}}, session=s)
    call("POST", f"/api/database/{db['id']}/sync_schema", {}, session=s)
    return db["id"]


# ---------- карточки ----------
TAGS = {"period": {"id": "tag-period", "name": "period", "display-name": "Период", "type": "text"},
        "region": {"id": "tag-region", "name": "region", "display-name": "Регион", "type": "text"}}
WHERE = "[[and period = {{period}}]] [[and region = {{region}}]]"


def card(s, db, coll, name, sql, display, viz=None, filtered=False, description=None):
    body = {"name": name, "display": display, "collection_id": coll, "description": description,
            "visualization_settings": viz or {},
            "dataset_query": {"type": "native", "database": db,
                              "native": {"query": sql, "template-tags": TAGS if filtered else {}}}}
    return call("POST", "/api/card", body, session=s)["id"]


def money(col, decimals=0):
    return {json.dumps(["name", col], ensure_ascii=False): {"prefix": "£", "decimals": decimals}}


def build_cards(s, db, coll):
    c = {}
    kpi = {
        "Выручка": ("sum(revenue) / 1e6", {json.dumps(["name", "Выручка"], ensure_ascii=False):
                                                {"prefix": "£", "suffix": " млн", "decimals": 2}}),
        "Заказы": ("count(distinct invoice) filter (where is_cancellation = 0)", {}),
        "Клиенты с ID": ("count(distinct customer_id) filter (where is_cancellation = 0)", {}),
        "Средний чек (все заказы)": ("sum(revenue) / nullif(count(distinct invoice) filter (where is_cancellation = 0), 0)",
                                     money("Средний чек (все заказы)")),
        "Доля отмен": ("-sum(revenue) filter (where is_cancellation = 1) / "
                       "nullif(sum(revenue) filter (where is_cancellation = 0), 0)", {}),
    }
    for name, (expr, cols) in kpi.items():
        viz = {"scalar.compact_primary_number": False, "column_settings": cols}
        if name == "Доля отмен":
            viz["column_settings"] = {json.dumps(["name", name], ensure_ascii=False):
                                      {"number_style": "percent", "decimals": 1}}
        c[name] = card(s, db, coll, name, f'select {expr} as "{name}" from mart.orders where {FULL} {WHERE}',
                       "scalar", viz, filtered=True)

    c["monthly"] = card(s, db, coll, "Рост выручки дали заказы без ID и новые клиенты", f"""
        select month as "Месяц", customer_type as "Тип клиента", sum(revenue) as "Выручка"
        from mart.orders where {FULL} {WHERE}
        group by 1, 2 order by 1""", "area", {
        "graph.dimensions": ["Месяц", "Тип клиента"], "graph.metrics": ["Выручка"],
        "stackable.stack_type": "stacked", "graph.x_axis.title_text": "", "graph.y_axis.title_text": "£",
        "series_settings": {"Вернувшийся": {"color": BLUE}, "Новый": {"color": GREEN}, "Без ID": {"color": GREY}}},
        filtered=True)

    c["regions"] = card(s, db, coll, "Великобритания на месте, растут Европа и Австралия", f"""
        select region as "Регион", period as "Период", sum(revenue) as "Выручка"
        from mart.orders where {FULL} group by 1, 2 order by 3 desc""", "bar", {
        "graph.dimensions": ["Регион", "Период"], "graph.metrics": ["Выручка"],
        "series_settings": {"Год 1": {"color": GREY}, "Год 2": {"color": BLUE}},
        "graph.show_values": True, "graph.label_value_formatting": "compact"})

    c["seasonal"] = card(s, db, coll, "Сезонность: ноябрь почти втрое выше февраля", f"""
        select date_part('month', month)::int % 12 + 1 as "Месяц периода",
               period as "Период", sum(revenue) as "Выручка"
        from mart.orders where {FULL} group by 1, 2 order by 1""", "line", {
        "graph.dimensions": ["Месяц периода", "Период"], "graph.metrics": ["Выручка"],
        "graph.x_axis.scale": "ordinal", "graph.x_axis.title_text": "Месяц периода (1 = декабрь)",
        "series_settings": {"Год 1": {"color": GREY}, "Год 2": {"color": BLUE}}})

    c["bridge"] = card(s, db, coll, "Год 1 £9,16 млн → год 2 £9,33 млн: потери перекрыли новые клиенты", """
        select step as "Шаг",
               case when value >= 0 then value end as "Рост",
               case when value < 0 then value end as "Падение"
        from mart.bridge where kind = 'step' and abs(value) > 10000 order by step_order""", "bar", {
        "graph.dimensions": ["Шаг"], "graph.metrics": ["Рост", "Падение"], "stackable.stack_type": "stacked",
        "series_settings": {"Рост": {"color": GREEN}, "Падение": {"color": RED}},
        "graph.show_values": True, "graph.label_value_formatting": "compact",
        "graph.x_axis.title_text": "", "graph.y_axis.title_text": "Изменение выручки, £"},
        description="Клиент «ушёл», если покупал в году 1 и ни разу в году 2. Шаги в сумме дают +£175 тыс.; "
                    "клиенты только с отменами (+£1 тыс.) не показаны.")

    c["factors"] = card(s, db, coll, "Главный фактор падения — частота покупок", """
        select factor as "Фактор", round(before, 2) as "Год 1", round(after, 2) as "Год 2",
               round(change_pct * 100, 1) as "Изменение, %", round(contribution) as "Вклад в выручку, £"
        from mart.factors""", "table", {
        "table.column_formatting": [{"columns": ["Вклад в выручку, £"], "type": "range",
                                     "colors": [RED, "#FFFFFF", GREEN], "min_type": None, "max_type": None,
                                     "operator": "=", "highlight_row": False}]},
        description="Выручка клиентов с ID = клиенты × заказов на клиента × средний чек; вклады по методу LMDI.")

    months = ", ".join(f'round(100 * max(retention) filter (where month_number = {n}), 0) as "{n}"'
                       for n in range(1, 13))
    c["cohorts"] = card(s, db, coll, "Через месяц возвращается каждый пятый новый клиент", f"""
        select to_char(cohort_month, 'YYYY-MM') as "Когорта", max(cohort_size) as "Клиентов", {months}
        from mart.cohorts where cohort_month > date '2009-12-01'
        group by cohort_month order by cohort_month""", "table", {
        "table.column_formatting": [{"columns": [str(n) for n in range(1, 13)], "type": "range",
                                     "colors": ["#FFFFFF", BLUE], "min_type": "custom", "min_value": 0,
                                     "max_type": "custom", "max_value": 40, "operator": "=",
                                     "highlight_row": False}]},
        description="Доля клиентов когорты (%), купивших через N месяцев после первой покупки. "
                    "Первая когорта (дек 2009) — вся накопленная база, поэтому исключена.")

    c["segments"] = card(s, db, coll, "27 % клиентов дают 74 % выручки", """
        select segment as "Сегмент",
               round(100.0 * count(*) / sum(count(*)) over (), 1) as "Доля клиентов, %",
               round(100.0 * sum(revenue) / sum(sum(revenue)) over (), 1) as "Доля выручки, %"
        from mart.customers group by 1 order by 3 desc""", "bar", {
        "graph.dimensions": ["Сегмент"], "graph.metrics": ["Доля клиентов, %", "Доля выручки, %"],
        "series_settings": {"Доля клиентов, %": {"color": GREY}, "Доля выручки, %": {"color": BLUE}},
        "graph.show_values": True},
        description="RFM на 10.12.2011: давность ≤30/90/180/365 дней, заказы 1/2/3–4/5–9/10+.")

    c["reactivate"] = card(s, db, coll, "Список на реактивацию: 737 клиентов «Нельзя потерять» и «Под угрозой»", """
        select customer_id::text as "Клиент", country as "Страна", segment as "Сегмент", orders as "Заказов",
               revenue_y1 as "Выручка год 1, £", revenue_y2 as "Выручка год 2, £",
               to_char(last_purchase, 'DD.MM.YYYY') as "Последняя покупка", recency_days as "Дней без покупок"
        from mart.customers where segment in ('Нельзя потерять', 'Под угрозой')
        order by revenue desc""", "table")
    return c


# ---------- дашборд ----------
def text(dcid, row, col, w, h, md, tab):
    return {"id": dcid, "card_id": None, "dashboard_tab_id": tab,
            "row": row, "col": col, "size_x": w, "size_y": h, "parameter_mappings": [],
            "visualization_settings": {"virtual_card": {"display": "text", "name": None, "dataset_query": {},
                                                        "visualization_settings": {}, "archived": False},
                                       "text": md, "dashcard.background": False}}


def build_dashboard(s, coll, c):
    params = [
        {"id": "p_period", "name": "Период", "slug": "period", "type": "string/=", "sectionId": "string",
         "default": ["Год 2"], "values_query_type": "list", "values_source_type": "static-list",
         "values_source_config": {"values": ["Год 1", "Год 2"]}},
        {"id": "p_region", "name": "Регион", "slug": "region", "type": "string/=", "sectionId": "string",
         "values_query_type": "list", "values_source_type": "static-list",
         "values_source_config": {"values": ["Великобритания", "Европа", "Остальной мир"]}},
    ]
    d = call("POST", "/api/dashboard", {"name": TITLE, "collection_id": coll, "parameters": params,
                                        "description": "Online Retail II (UCI, CC BY 4.0): год 1 — дек 2009 — ноя 2010, "
                                                       "год 2 — дек 2010 — ноя 2011."}, session=s)
    filt = lambda cid: [{"parameter_id": p, "card_id": cid, "target": ["variable", ["template-tag", t]]}  # noqa: E731
                        for p, t in (("p_period", "period"), ("p_region", "region"))]
    n = [0]

    def dc(cid, row, col, w, h, tab, filtered=False):
        n[0] += 1
        return {"id": -n[0], "card_id": cid, "dashboard_tab_id": tab, "row": row, "col": col,
                "size_x": w, "size_y": h, "parameter_mappings": filt(cid) if filtered else [],
                "visualization_settings": {}}

    def txt(*a):
        n[0] += 1
        return text(-n[0], *a)

    t1, t2, t3 = -1, -2, -3
    cards = [
        txt(0, 0, 24, 2, "**Выручка года 2 выросла на 1,9 %, но выручка клиентов с ID упала на 2,0 %:** рост дали "
                          "заказы без ID и заграница. Фильтры «Период» и «Регион» действуют на этой вкладке.", t1),
        dc(c["Выручка"], 2, 0, 5, 3, t1, True), dc(c["Заказы"], 2, 5, 5, 3, t1, True),
        dc(c["Клиенты с ID"], 2, 10, 5, 3, t1, True), dc(c["Средний чек (все заказы)"], 2, 15, 5, 3, t1, True),
        dc(c["Доля отмен"], 2, 20, 4, 3, t1, True),
        dc(c["monthly"], 5, 0, 24, 7, t1, True),
        dc(c["regions"], 12, 0, 12, 7, t1), dc(c["seasonal"], 12, 12, 12, 7, t1),
        txt(0, 0, 24, 2, "**Из 4 239 клиентов года 1 ушёл 1 531**, оставшиеся сделали на 8 % меньше заказов. "
                          "Новые клиенты и заказы без ID перекрыли потери.", t2),
        dc(c["bridge"], 2, 0, 24, 8, t2), dc(c["factors"], 10, 0, 24, 5, t2),
        txt(0, 0, 24, 2, "**Новые клиенты удерживаются не хуже прежнего — теряем частоту в старой базе.** "
                          "Ниже — когорты, RFM-сегменты и список клиентов для реактивации.", t3),
        dc(c["cohorts"], 2, 0, 24, 19, t3), dc(c["segments"], 21, 0, 24, 6, t3),
        dc(c["reactivate"], 27, 0, 24, 9, t3),
    ]
    call("PUT", f"/api/dashboard/{d['id']}", {
        "tabs": [{"id": t1, "name": "Обзор"}, {"id": t2, "name": "Почему изменилась выручка"},
                 {"id": t3, "name": "Клиенты"}],
        "dashcards": cards}, session=s)
    return d["id"]


def main():
    e = env()
    wait_ready()
    s = login(e)
    db = database(s)
    time.sleep(10)                                      # дать синхронизации схемы закончиться
    call("PUT", "/api/setting/enable-public-sharing", {"value": True}, session=s)
    call("PUT", "/api/setting/custom-formatting", {"value": {"type/Number": {"number_separators": ", "}}},
         session=s)                                     # запятая — десятичный разделитель, пробел — разряды
    for coll in call("GET", "/api/collection", session=s):
        if coll.get("name") == TITLE and not coll.get("archived"):
            call("PUT", f"/api/collection/{coll['id']}", {"archived": True}, session=s)
    coll = call("POST", "/api/collection", {"name": TITLE, "color": BLUE}, session=s)["id"]
    cards = build_cards(s, db, coll)
    dash = build_dashboard(s, coll, cards)
    uuid = call("POST", f"/api/dashboard/{dash}/public_link", {}, session=s)["uuid"]
    print(f"дашборд: {MB}/dashboard/{dash}\nпубличная ссылка (локально): {MB}/public/dashboard/{uuid}")
    (HERE / "public_dashboard.txt").write_text(f"{MB}/public/dashboard/{uuid}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
