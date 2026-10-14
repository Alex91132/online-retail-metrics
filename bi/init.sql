-- Витрины из marts/*.csv в схему mart. Выполняется один раз при первом старте контейнера.
create schema mart;

create table mart.orders (
    invoice text, invoice_date timestamp, month date, period text, customer_id bigint, country text,
    region text, is_cancellation int, customer_type text, cohort_month date, revenue numeric(14, 2),
    items int, lines int
);
copy mart.orders from '/marts/orders.csv' with (format csv, header true);

create table mart.customers (
    customer_id bigint primary key, country text, region text, orders int, revenue numeric(14, 2),
    last_purchase date, revenue_y1 numeric(14, 2), revenue_y2 numeric(14, 2), first_purchase date,
    cohort_month date, recency_days int, r int, f int, m int, segment text
);
copy mart.customers from '/marts/customers.csv' with (format csv, header true);

create table mart.cohorts (
    cohort_month date, month_number int, cohort_size int, active_customers int, retention numeric(6, 4),
    revenue numeric(14, 2), revenue_per_customer numeric(12, 2)
);
copy mart.cohorts from '/marts/cohorts.csv' with (format csv, header true);

create table mart.bridge (step_order int, step text, value numeric(14, 2), kind text, sign text);
copy mart.bridge from '/marts/bridge.csv' with (format csv, header true);

create table mart.factors (factor text, before numeric, after numeric, change_pct numeric, contribution numeric);
copy mart.factors from '/marts/factors.csv' with (format csv, header true);

create index on mart.orders (period, region);
