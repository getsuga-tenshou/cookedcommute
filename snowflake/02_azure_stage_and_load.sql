-- CookedCommute — connect Snowflake to ADLS Gen2 and load RAW (the "EL" of ELT).
-- Run after 01_bootstrap.sql. Fill the placeholders from `terraform output`:
--   <AZURE_TENANT_ID>  ->  az account show --query tenantId -o tsv
--   <ADLS_ACCOUNT>     ->  terraform output storage_account

-- ---------------------------------------------------------------------------
-- 1) Storage integration (ACCOUNTADMIN) — grants Snowflake access to ADLS.
-- ---------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;

CREATE STORAGE INTEGRATION IF NOT EXISTS PARKPULSE_AZURE_INT
    TYPE = EXTERNAL_STAGE
    STORAGE_PROVIDER = 'AZURE'
    ENABLED = TRUE
    AZURE_TENANT_ID = '<AZURE_TENANT_ID>'
    STORAGE_ALLOWED_LOCATIONS =
        ('azure://<ADLS_ACCOUNT>.blob.core.windows.net/raw/');

GRANT USAGE ON INTEGRATION PARKPULSE_AZURE_INT TO ROLE PARKPULSE_ROLE;
-- Tasks (scheduled COPY) need this account-level privilege:
GRANT EXECUTE TASK ON ACCOUNT TO ROLE PARKPULSE_ROLE;

-- >>> CONSENT STEP (one-time) <<<
--   DESC INTEGRATION PARKPULSE_AZURE_INT;
-- Open AZURE_CONSENT_URL in a browser and accept. Then, in the Azure portal,
-- grant the shown AZURE_MULTI_TENANT_APP_NAME the role
-- "Storage Blob Data Reader" on the storage account (see runbook).

-- ---------------------------------------------------------------------------
-- 2) External stage over ADLS
-- ---------------------------------------------------------------------------
USE ROLE PARKPULSE_ROLE;
USE WAREHOUSE PARKPULSE_WH;
USE DATABASE PARKPULSE;

CREATE OR REPLACE STAGE RAW.ADLS_STAGE
    STORAGE_INTEGRATION = PARKPULSE_AZURE_INT
    URL = 'azure://<ADLS_ACCOUNT>.blob.core.windows.net/raw/'
    FILE_FORMAT = RAW.JSON_NDJSON;

-- ---------------------------------------------------------------------------
-- 3) COPY templates (idempotent: Snowflake skips already-loaded files)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE RAW.LOAD_NOW() RETURNS STRING LANGUAGE SQL AS
$$
BEGIN
    COPY INTO RAW.TRAFFIC_MEASUREMENTS (site_id, lat, lon, road, flow_veh_h, speed_kmh, measured_at)
    FROM (
        SELECT $1:site_id::string, $1:lat::float, $1:lon::float, $1:road::string,
               $1:flow_veh_h::float, $1:speed_kmh::float, $1:measured_at::timestamp_tz
        FROM @RAW.ADLS_STAGE/traffic/
    )
    FILE_FORMAT = (FORMAT_NAME = RAW.JSON_NDJSON) PATTERN = '.*\\.jsonl' ON_ERROR = CONTINUE;

    COPY INTO RAW.PARKING_SNAPSHOTS (garage_id, name, lat, lon, free_spaces, capacity, state, measured_at)
    FROM (
        SELECT $1:garage_id::string, $1:name::string, $1:lat::float, $1:lon::float,
               $1:free_spaces::number, $1:capacity::number, $1:state::string,
               $1:measured_at::timestamp_tz
        FROM @RAW.ADLS_STAGE/parking/
    )
    FILE_FORMAT = (FORMAT_NAME = RAW.JSON_NDJSON) PATTERN = '.*\\.jsonl' ON_ERROR = CONTINUE;

    RETURN 'loaded';
END;
$$;

-- ---------------------------------------------------------------------------
-- 4) Automated loading: a scheduled TASK (simplest, fully Snowflake-native).
--    Suspend with ALTER TASK ... SUSPEND to stop credit use.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TASK RAW.LOAD_RAW
    WAREHOUSE = PARKPULSE_WH
    SCHEDULE = '5 MINUTE'   -- gentle on trial credits; lower to '1 MINUTE' for fresher data
AS
    CALL RAW.LOAD_NOW();

-- Created SUSPENDED (the default). Resume only once the Functions are landing
-- files in ADLS, so we don't wake the warehouse every 5 min over an empty lake:
--   ALTER TASK RAW.LOAD_RAW RESUME;

-- ---------------------------------------------------------------------------
-- 5) (Optional, advanced) Snowpipe auto-ingest instead of a polling task:
--    requires a NOTIFICATION INTEGRATION wired to an Azure Event Grid topic on
--    the storage account. See docs/SNOWFLAKE_SETUP.md. Sketch:
--
--    CREATE PIPE RAW.TRAFFIC_PIPE AUTO_INGEST = TRUE
--      INTEGRATION = 'PARKPULSE_EVENTGRID_INT' AS
--      COPY INTO RAW.TRAFFIC_MEASUREMENTS FROM ( ... ) ;
