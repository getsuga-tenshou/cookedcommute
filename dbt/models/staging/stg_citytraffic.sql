-- Cleaned TomTom city-road congestion samples, with a derived congestion level.
with src as (
    select * from {{ source('raw', 'city_traffic') }}
)

select
    point_id,
    lat,
    lon,
    current_speed,
    freeflow_speed,
    congestion_ratio,
    frc,
    case
        when congestion_ratio >= 0.5  then 'heavy'
        when congestion_ratio >= 0.25 then 'moderate'
        when congestion_ratio is not null then 'free'
        else 'unknown'
    end as congestion_level,
    measured_at
from src
where lat is not null and lon is not null
