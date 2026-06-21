-- Cleaned, typed traffic measurements (one row per site per poll).
with src as (
    select * from {{ source('raw', 'traffic_measurements') }}
)

select
    site_id,
    lat,
    lon,
    road,
    flow_veh_h,
    speed_kmh,
    measured_at,
    ingested_at
from src
where measured_at is not null
  and (flow_veh_h is not null or speed_kmh is not null)
