-- Витрины для дашборда. Зерно у каждой своё — так COUNT DISTINCT в BI считается верно.

-- Первая покупка клиента (по заказам, не по отменам)
create or replace table customer_first as
select customer_id, min(invoice_date) as first_purchase, date_trunc('month', min(invoice_date))::date as cohort_month
from stg_lines
where customer_id is not null and not is_cancellation
group by customer_id;

-- 1. Заказы: строка = чек (заказ или отмена)
create or replace table mart_orders as
select
    l.invoice,
    min(l.invoice_date)                                         as invoice_date,
    any_value(l.month)                                          as month,
    any_value(l.period)                                         as period,
    l.customer_id,
    any_value(l.country)                                        as country,
    any_value(l.region)                                         as region,
    any_value(l.is_cancellation)                                as is_cancellation,
    case when l.customer_id is null then 'Без ID'
         when any_value(l.month) = any_value(f.cohort_month) then 'Новый'
         else 'Вернувшийся' end                                 as customer_type,
    any_value(f.cohort_month)                                   as cohort_month,
    round(sum(l.amount), 2)                                     as revenue,
    sum(l.quantity)                                             as items,
    count(*)                                                    as lines
from stg_lines l
left join customer_first f using (customer_id)
group by l.invoice, l.customer_id;

-- 2. Клиенты: строка = клиент, RFM на дату конца данных (10.12.2011)
create or replace table mart_customers as
with c as (
    select
        customer_id,
        any_value(country)                                      as country,
        any_value(region)                                       as region,
        count(*) filter (where not is_cancellation)             as orders,
        round(sum(revenue), 2)                                  as revenue,
        max(invoice_date) filter (where not is_cancellation)    as last_purchase,
        round(sum(revenue) filter (where period = 'Год 1'), 2)  as revenue_y1,
        round(sum(revenue) filter (where period = 'Год 2'), 2)  as revenue_y2
    from mart_orders
    where customer_id is not null
    group by customer_id
),
s as (
    select
        c.*, f.first_purchase, f.cohort_month,
        date_diff('day', c.last_purchase, timestamp '2011-12-10') as recency_days
    from c join customer_first f using (customer_id)
    where c.orders > 0
),
scored as (
    -- Пороги, а не квантили: у тысяч клиентов один заказ, и квантиль делил бы их случайным образом
    select
        *,
        case when recency_days <= 30 then 5 when recency_days <= 90 then 4 when recency_days <= 180 then 3
             when recency_days <= 365 then 2 else 1 end           as r,
        case when orders >= 10 then 5 when orders >= 5 then 4 when orders >= 3 then 3
             when orders = 2 then 2 else 1 end                    as f,
        ntile(5) over (order by revenue)                          as m
    from s
)
select
    *,
    case
        when first_purchase >= timestamp '2011-09-11' then 'Новые'           -- первая покупка за 90 дней
        when r >= 4 and f >= 4                      then 'Чемпионы'
        when r >= 3 and f >= 3                      then 'Лояльные'
        when r >= 3                                 then 'Перспективные'
        when f >= 4                                 then 'Нельзя потерять'
        when f = 3                                  then 'Под угрозой'
        else 'Спящие' end                                       as segment
from scored;

-- 3. Когорты: строка = когорта × месяц жизни
create or replace table mart_cohorts as
with a as (
    select o.cohort_month, o.month, o.customer_id, sum(o.revenue) as revenue
    from mart_orders o
    where o.customer_id is not null and o.period <> 'Дек 2011 (неполный)'
    group by all
),
sz as (select cohort_month, count(*) as cohort_size from customer_first
       where cohort_month < date '2011-12-01' group by 1)
select
    a.cohort_month,
    date_diff('month', a.cohort_month, a.month)                 as month_number,
    sz.cohort_size,
    count(distinct a.customer_id) filter (where a.revenue > 0)  as active_customers,
    round(count(distinct a.customer_id) filter (where a.revenue > 0) / sz.cohort_size, 4) as retention,
    round(sum(a.revenue), 2)                                    as revenue,
    round(sum(a.revenue) / sz.cohort_size, 2)                   as revenue_per_customer
from a join sz using (cohort_month)
group by a.cohort_month, a.month, sz.cohort_size;
