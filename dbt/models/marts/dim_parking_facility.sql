-- One row per off-street parking facility with its latest attributes.
-- Facilities are a static catalog, so this dedups to the most recent snapshot.
select
    garage_id,
    name,
    lat,
    lon,
    capacity,
    measured_at
from {{ ref('stg_parking') }}
qualify row_number() over (partition by garage_id order by measured_at desc) = 1
