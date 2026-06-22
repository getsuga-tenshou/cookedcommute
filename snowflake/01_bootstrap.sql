-- CookedCommute — Snowflake bootstrap (run once, as ACCOUNTADMIN on the trial).
-- Creates role, warehouse, database, schemas, RAW tables, an internal stage for
-- local dev, and the GEOGRAPHY-backed "live" views the dashboard reads.
-- (Objects use the internal PARKPULSE_ prefix — the project's original codename.)
--
-- Substitute <YOUR_SNOWFLAKE_USER> below (the login you signed up with).

-- ---------------------------------------------------------------------------
-- Role, warehouse, database, schemas
-- ---------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS PARKPULSE_ROLE;
GRANT ROLE PARKPULSE_ROLE TO USER <YOUR_SNOWFLAKE_USER>;
GRANT ROLE PARKPULSE_ROLE TO ROLE SYSADMIN;

CREATE WAREHOUSE IF NOT EXISTS PARKPULSE_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60            -- protect the $400 trial: suspend after 60s idle
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE;
GRANT USAGE ON WAREHOUSE PARKPULSE_WH TO ROLE PARKPULSE_ROLE;

CREATE DATABASE IF NOT EXISTS PARKPULSE;
GRANT USAGE ON DATABASE PARKPULSE TO ROLE PARKPULSE_ROLE;

CREATE SCHEMA IF NOT EXISTS PARKPULSE.RAW;       -- landing (loaded from ADLS/lake)
CREATE SCHEMA IF NOT EXISTS PARKPULSE.STAGING;   -- dbt views
CREATE SCHEMA IF NOT EXISTS PARKPULSE.ANALYTICS; -- dbt marts
CREATE SCHEMA IF NOT EXISTS PARKPULSE.SERVING;   -- live views (this file)

GRANT ALL ON SCHEMA PARKPULSE.RAW       TO ROLE PARKPULSE_ROLE;
GRANT ALL ON SCHEMA PARKPULSE.STAGING   TO ROLE PARKPULSE_ROLE;
GRANT ALL ON SCHEMA PARKPULSE.ANALYTICS TO ROLE PARKPULSE_ROLE;
GRANT ALL ON SCHEMA PARKPULSE.SERVING   TO ROLE PARKPULSE_ROLE;

USE ROLE PARKPULSE_ROLE;
USE WAREHOUSE PARKPULSE_WH;
USE DATABASE PARKPULSE;

-- ---------------------------------------------------------------------------
-- RAW landing tables (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS RAW.TRAFFIC_MEASUREMENTS (
    site_id      STRING,
    lat          FLOAT,
    lon          FLOAT,
    road         STRING,
    flow_veh_h   FLOAT,
    speed_kmh    FLOAT,
    measured_at  TIMESTAMP_TZ,
    ingested_at  TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS RAW.PARKING_SNAPSHOTS (
    garage_id    STRING,
    name         STRING,
    lat          FLOAT,
    lon          FLOAT,
    free_spaces  NUMBER,
    capacity     NUMBER,
    state        STRING,
    measured_at  TIMESTAMP_TZ,
    ingested_at  TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
);

-- JSON file format + an internal stage for local-dev loading (PUT + COPY).
CREATE FILE FORMAT IF NOT EXISTS RAW.JSON_NDJSON TYPE = JSON STRIP_OUTER_ARRAY = FALSE;
CREATE STAGE IF NOT EXISTS RAW.LOCAL_STAGE FILE_FORMAT = RAW.JSON_NDJSON;

-- ---------------------------------------------------------------------------
-- SERVING live views: latest row per entity (warehouse-friendly, no MERGE),
-- with a GEOGRAPHY point for nearest-garage distance queries.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW SERVING.LIVE_TRAFFIC AS
SELECT
    site_id, lat, lon, road, flow_veh_h, speed_kmh,
    CASE
        WHEN speed_kmh >= 50 THEN 'free'
        WHEN speed_kmh >= 30 THEN 'moderate'
        WHEN speed_kmh IS NOT NULL THEN 'heavy'
        ELSE 'unknown'
    END AS congestion_level,
    measured_at,
    ST_MAKEPOINT(lon, lat) AS geom
FROM RAW.TRAFFIC_MEASUREMENTS
WHERE lat IS NOT NULL AND lon IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY site_id ORDER BY measured_at DESC) = 1;

CREATE OR REPLACE VIEW SERVING.LIVE_PARKING AS
SELECT
    garage_id, name, lat, lon, free_spaces, capacity,
    CASE
        WHEN capacity > 0 AND free_spaces IS NOT NULL
        THEN ROUND((capacity - free_spaces) / capacity * 100, 1)
    END AS occupancy_pct,
    state, measured_at,
    ST_MAKEPOINT(lon, lat) AS geom
FROM RAW.PARKING_SNAPSHOTS
WHERE lat IS NOT NULL AND lon IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY garage_id ORDER BY measured_at DESC) = 1;
