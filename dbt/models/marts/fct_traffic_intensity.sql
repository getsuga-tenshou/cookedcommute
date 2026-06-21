-- 5-minute traffic intensity per site (the cold-path aggregate behind trends).
select
    site_id,
    road,
    dateadd(minute, floor(minute(measured_at) / 5) * 5, date_trunc('hour', measured_at))
        as bucket_5min,
    avg(speed_kmh)                              as avg_speed_kmh,
    avg(flow_veh_h)                             as avg_flow_veh_h,
    case
        when avg(speed_kmh) >= 50 then 'free'
        when avg(speed_kmh) >= 30 then 'moderate'
        when avg(speed_kmh) is not null then 'heavy'
        else 'unknown'
    end                                         as congestion_level,
    count(*)                                    as n_obs
from {{ ref('stg_traffic') }}
group by 1, 2, 3
