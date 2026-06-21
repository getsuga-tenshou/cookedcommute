-- Typical occupancy by day-of-week x hour per garage.
-- Seed of the "predictive availability" product: given when you plan to arrive,
-- how full is this garage usually?
select
    garage_id,
    dayofweekiso(measured_at)  as day_of_week,   -- 1=Mon ... 7=Sun
    hour(measured_at)          as hour_of_day,
    round(avg(occupancy_pct), 1) as avg_occupancy_pct,
    count(*)                   as n_obs
from {{ ref('stg_parking') }}
where occupancy_pct is not null
group by 1, 2, 3
