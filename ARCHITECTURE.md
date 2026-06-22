# CookedCommute — Architecture (a worked example)

CookedCommute has **two data planes**:

1. **Warehouse plane (batch ELT)** — the data the app *owns and models*: NDW traffic
   sensors + RDW parking facilities. Flows Functions → ADLS → Snowflake → dbt → serving views.
2. **Live vendor plane (real-time proxy)** — data that is only useful fresh and that TomTom
   already serves rendered: flow tiles + incidents. The API proxies these straight through;
   they never touch the warehouse.

This document follows **one traffic reading from a roadside sensor all the way to a pixel on
the map**, then does the same (briefly) for parking, then covers the live plane and the
design rationale.

---

## Worked example: one traffic reading, sensor → screen

### 0. The sensor
NDW (*Nationaal Dataportaal Wegverkeer*) aggregates hundreds of inductive-loop and camera
sensors across Dutch motorways and main roads. A sensor on the A10 ring reports a vehicle
flow and average speed roughly once a minute. NDW publishes the whole network as two
gzipped **DATEX II** XML files:

- `measurement.xml.gz` — static-ish **config**: each site's id, coordinates, road name.
- `trafficspeed.xml.gz` — live **measurements**: flow + speed per site, ~1/min.

### 1. The timer fires (Azure Function)
`azure_functions/TrafficTimer` has a timer trigger (`0 */5 * * * *`). On the consumption
plan, Azure's scheduler wakes the app and calls `ingest_traffic(load_settings())`. Settings
come from the Function App's **app settings** (set by Terraform) — NDW URLs, the ADLS
account, the Amsterdam bounding box — so there is no `.env` in the cloud.

### 2. Fetch + parse (the "E")
`ingestion/sources/ndw_traffic.py`:
- Downloads and gunzips both files.
- Parses with **lxml `iterparse` (streaming)** rather than a full DOM — the measurement file
  is ~11 MB and a naive `//xpath` blows libxml2's limits; streaming keeps memory flat.
- Builds `{site_id → {lat, lon, road}}` from config and `{site_id → {flow, speed}}` from the
  live file (carefully *not* double-counting the nested `measuredValue` wrappers — there's a
  unit test for exactly that).
- **Joins** on `site_id` and **clips** to the Amsterdam bbox, discarding the rest of the country.

Result: one dict per Amsterdam site —
```json
{"site_id": "...A10...", "lat": 52.37, "lon": 4.85, "road": "A10",
 "flow_veh_h": 1200, "speed_kmh": 42, "measured_at": "2026-06-21T21:10:00Z"}
```

### 3. Enrich
`ingestion/pipeline.py::enrich_traffic` adds a derived `congestion_level`
(`free`/`moderate`/`heavy`) from speed/flow — deterministic, unit-tested logic.

### 4. Land raw to the lake (the "L")
`ingestion/sinks.py::land` writes the rows as **NDJSON** to a date-partitioned path:
```
raw/traffic/dt=2026-06-21/20260621T211013.jsonl
```
It keeps a local copy in `/tmp/lake` (writable in Functions) and uploads to **ADLS Gen2**
with `DataLakeServiceClient` authenticated by **`DefaultAzureCredential`** — which, inside
the Function, resolves to the app's **system-assigned managed identity**. Terraform granted
that identity *Storage Blob Data Contributor* on the lake, so the upload needs **no keys**.
This is the ELT boundary: raw, unmodelled JSON now sits in cheap object storage.

### 5. Snowflake pulls it in (the COPY task)
Snowflake reads the lake through a **storage integration** (a one-time trust: Snowflake's
managed app in your Azure AD, granted *Storage Blob Data Reader* on the account) and an
**external stage** over `azure://…/raw/`. A scheduled **TASK** (`RAW.LOAD_RAW`, every 5 min)
calls a stored procedure running `COPY INTO RAW.TRAFFIC_MEASUREMENTS FROM @RAW.ADLS_STAGE/traffic/`.
`COPY` is **idempotent** — Snowflake tracks already-loaded files and skips them, so
overlapping runs never double-load. The reading is now an append-only row in
`RAW.TRAFFIC_MEASUREMENTS` with an `ingested_at`.

### 6. The serving view (read model)
The dashboard never reads `RAW` directly. `SERVING.LIVE_TRAFFIC` returns the **latest row per
site** via `QUALIFY ROW_NUMBER() OVER (PARTITION BY site_id ORDER BY measured_at DESC) = 1`
— a window-function "upsert" with no `MERGE` and no separate "current" table. It also derives
`congestion_level` and a `GEOGRAPHY` point (`ST_MAKEPOINT`) for distance queries.

### 7. (Parallel) dbt models the analytics
Separately, **dbt** turns `RAW` into clean **staging views** (`stg_traffic`) and **marts**
(`fct_traffic_intensity` — 5-minute intensity buckets per site) with **data-quality tests**
(accepted ranges, not-null, accepted values). The live dashboard uses the serving views;
dbt is the cold-path analytics. Both read the same `RAW`.

### 8. The API
`backend/api.py` (FastAPI) exposes `GET /api/traffic`, which queries `SERVING.LIVE_TRAFFIC`,
weights each point by congestion, and returns a **GeoJSON FeatureCollection**. A 20 s TTL
cache keeps repeat hits off Snowflake. The connection uses **key-pair auth** (Snowflake
blocks password auth for programmatic access under MFA).

### 9. The pixel
`frontend/index.html` (MapLibre GL) fetches `/api/traffic`, renders the NDW points as a
congestion **heatmap**, and computes the "avg speed / % heavy" card. It re-fetches every 30 s.
Our A10 reading is now a warm patch on the ring road — at **~5-minute end-to-end freshness**,
zero manual steps.

---

## Worked example: parking (briefer)
- `ParkingTimer` runs **daily** — facilities are a static catalog, not live occupancy.
- `ingestion/sources/ams_parking.py` calls the **RDW NPR** open API, filters to Amsterdam
  off-street facilities, extracts `{garage_id, name, lat, lon, capacity}`.
- Same land → COPY → `RAW.PARKING_SNAPSHOTS` path.
- `SERVING.LIVE_PARKING` and dbt's `dim_parking_facility` dedup to one row per facility.
- `GET /api/parking` returns the facilities; the frontend uses the browser's geolocation and
  a **haversine** sort to rank "nearest to you".

---

## The live vendor plane (no warehouse)
Two layers are real-time-only and TomTom already serves them rendered, so warehousing them
would add latency for no benefit:

- **Flow tiles** — `GET /api/flow/{style}/{z}/{x}/{y}` proxies TomTom raster traffic tiles,
  keeping the **API key server-side** and caching ~60 s. This colours *every* street (the
  NDW sensors only cover the major network).
- **Incidents** — `GET /api/incidents` proxies TomTom Incident Details for the bbox, reshaped
  to GeoJSON; the frontend draws clickable warning markers.

Splitting the planes is deliberate: **own + model** the data that's yours (NDW/RDW); **proxy**
the data that's vendor-rendered and only useful live (TomTom).

---

## Why these choices
- **ELT, not ETL** — land raw first, transform in-warehouse. Cheap storage, replayable
  (re-run dbt without re-fetching), transforms in version-controlled SQL.
- **Managed identity + key-pair auth** — no secrets in code or config. The Function never
  holds a storage key; Snowflake never holds a password.
- **`QUALIFY` serving views** — a latest-row read model with no `MERGE` and no "current"
  table; trivial and fast over append-only raw.
- **Idempotent `COPY` + native task** — at-least-once landing is fine because load is
  dedup-by-file; the scheduler is Snowflake-native, so no extra orchestrator to run.
- **Tile proxy** — full-street coverage + incidents on the free tier without leaking the key.
- **Terraform** — the whole Azure footprint (lake, Function App, identity, observability) is
  reproducible from code.

## Operational notes
- **Cadence / cost** — traffic + COPY every 5 min, parking daily; the XS warehouse
  auto-suspends after 60 s and the task can be suspended entirely when idle.
- **Free tiers** — Azure Functions consumption (1M exec/mo), ADLS (pennies), Snowflake trial,
  TomTom Freemium (50k tile + 2.5k non-tile requests/day).
- **CI** — GitHub Actions runs ruff, pytest (parsers + logic), and `dbt parse` on every push.
