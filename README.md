# CookedCommute

*How cooked is your commute — and where can you park it?*

A real-time mobility dashboard for **Amsterdam**: see live traffic intensity across
every road, and the parking facilities nearby.

## What it does

- **Live Traffic** — a congestion heatmap over the whole city, combining motorway &
  main-road sensors (NDW) with city-street flow (TomTom), plus a live TomTom flow overlay.
- **Parking Near You** — a GPS-first interactive map of off-street parking facilities
  (RDW NPR), ranked by distance from where you are.

## How it works

A small **ELT** pipeline: Python ingests three live open-data feeds and lands raw
JSON → loads into **Snowflake** → **dbt** builds tested marts → geospatial serving
views → a **Streamlit + Folium** dashboard reads them live.

## Tech

| Area | Tools |
|---|---|
| Ingestion | Python (requests, lxml / DATEX II parsing, threaded fetch) |
| Data sources | NDW (traffic), TomTom Traffic Flow (city roads), RDW NPR (parking) |
| Warehouse | Snowflake — key-pair auth, `GEOGRAPHY` / `ST_DISTANCE`, `QUALIFY` live views |
| Transform | dbt (dbt-snowflake) — staging → marts + data tests |
| Dashboard | Streamlit + Folium (Leaflet) + TomTom map tiles |
| Quality / CI | pytest, ruff, GitHub Actions |

## License

MIT — see `LICENSE`.
