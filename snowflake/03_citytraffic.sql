-- ParkPulse — add the city-road traffic source (TomTom Flow).
-- Run once in Snowsight (role PARKPULSE_ROLE), after 01_bootstrap.sql.

USE ROLE PARKPULSE_ROLE;
USE WAREHOUSE PARKPULSE_WH;
USE DATABASE PARKPULSE;

CREATE TABLE IF NOT EXISTS RAW.CITY_TRAFFIC (
    point_id          STRING,
    lat               FLOAT,
    lon               FLOAT,
    current_speed     FLOAT,
    freeflow_speed    FLOAT,
    congestion_ratio  FLOAT,        -- 0 free-flowing ... 1 jammed
    frc               STRING,       -- TomTom functional road class (FRC0=motorway ... FRC6=local)
    measured_at       TIMESTAMP_TZ,
    ingested_at       TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
);

-- Latest reading per sampled point, with a derived congestion level + geo point.
CREATE OR REPLACE VIEW SERVING.LIVE_CITY_TRAFFIC AS
SELECT
    point_id, lat, lon, current_speed, freeflow_speed, congestion_ratio, frc,
    CASE
        WHEN congestion_ratio >= 0.5  THEN 'heavy'
        WHEN congestion_ratio >= 0.25 THEN 'moderate'
        WHEN congestion_ratio IS NOT NULL THEN 'free'
        ELSE 'unknown'
    END AS congestion_level,
    measured_at,
    ST_MAKEPOINT(lon, lat) AS geom
FROM RAW.CITY_TRAFFIC
WHERE lat IS NOT NULL AND lon IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY point_id ORDER BY measured_at DESC) = 1;
