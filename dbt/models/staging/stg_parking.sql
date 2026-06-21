-- Cleaned parking snapshots with a derived occupancy percentage.
with src as (
    select * from {{ source('raw', 'parking_snapshots') }}
)

select
    garage_id,
    name,
    lat,
    lon,
    free_spaces,
    capacity,
    state,
    case
        when capacity > 0 and free_spaces is not null
        then round((capacity - free_spaces) / nullif(capacity, 0) * 100, 1)
    end as occupancy_pct,
    measured_at,
    ingested_at
from src
where measured_at is not null
