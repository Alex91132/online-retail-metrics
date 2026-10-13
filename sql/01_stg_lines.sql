-- Строки чеков после очистки. Каждое правило — отдельный флаг, его влияние считается в cleaning_impact.
create or replace table stg_lines as
with flagged as (
    select
        *,
        quantity * price                                        as amount,
        starts_with(invoice, 'C')                               as is_cancellation,
        not regexp_matches(stock_code, '^[0-9]{5}')             as is_service_code,  -- почта, комиссии, корректировки
        starts_with(invoice, 'A')                               as is_bad_debt,      -- списание долга (код B — тоже служебный)
        price <= 0                                              as is_zero_price,
        row_number() over (partition by invoice, stock_code, description, quantity, invoice_date, price,
                                        customer_id, country) > 1 as is_duplicate
    from raw
)
select
    invoice,
    stock_code,
    description,
    quantity,
    price,
    amount,
    invoice_date,
    date_trunc('month', invoice_date)::date                     as month,
    case when invoice_date < date '2010-12-01' then 'Год 1'
         when invoice_date < date '2011-12-01' then 'Год 2'
         else 'Дек 2011 (неполный)' end                          as period,
    cast(customer_id as bigint)                                 as customer_id,
    country,
    case when country = 'United Kingdom' then 'Великобритания'
         when country in ('EIRE', 'Germany', 'France', 'Netherlands', 'Spain', 'Belgium', 'Switzerland',
                          'Portugal', 'Italy', 'Norway', 'Sweden', 'Denmark', 'Finland', 'Austria',
                          'Poland', 'Cyprus', 'Channel Islands', 'Greece', 'Iceland', 'Lithuania',
                          'Malta', 'Czech Republic', 'European Community') then 'Европа'
         else 'Остальной мир' end                               as region,
    is_cancellation
from flagged
where not (is_service_code or is_bad_debt or is_zero_price or is_duplicate);

-- Сколько строк и выручки убирает каждое правило (по порядку применения)
create or replace table cleaning_impact as
with f as (
    select
        quantity * price as amount,
        not regexp_matches(stock_code, '^[0-9]{5}') as svc,
        starts_with(invoice, 'A') as bad,
        price <= 0 as zero,
        row_number() over (partition by invoice, stock_code, description, quantity, invoice_date, price,
                                        customer_id, country) > 1 as dup
    from raw
)
select 'Служебные коды (почта, комиссии, корректировки, списания долга)' as rule, count(*) filter (where svc) as lines,
       sum(amount) filter (where svc) as amount from f
union all
select 'Нулевая или отрицательная цена', count(*) filter (where zero and not (svc or bad)),
       sum(amount) filter (where zero and not (svc or bad)) from f
union all
select 'Точные дубли строк', count(*) filter (where dup and not (svc or bad or zero)),
       sum(amount) filter (where dup and not (svc or bad or zero)) from f;
