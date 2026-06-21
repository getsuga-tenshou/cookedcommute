-- City-road congestion fact: latest reading per sampled point.
select
    point_id,
    lat,
    lon,
    current_speed,
    freeflow_speed,
    congestion_ratio,
    frc,
    congestion_level,
    measured_at
from {{ ref('stg_citytraffic') }}
qualify row_number() over (partition by point_id order by measured_at desc) = 1
