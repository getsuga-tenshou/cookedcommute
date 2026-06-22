"""CookedCommute API — serves live Snowflake data to the frontend.

Run from the repo root:
    uvicorn backend.api:app --reload
then open http://localhost:8000

Endpoints (GeoJSON FeatureCollections):
    GET /api/traffic   NDW sensor congestion points (heat + speed/heavy stats)
    GET /api/parking   off-street parking facilities
    GET /api/flow      proxied TomTom live flow tiles (every street)
    GET /api/incidents proxied TomTom incidents (closures / jams / roadworks)
The same server also serves frontend/index.html, so there's no CORS to wire.
"""
from __future__ import annotations

import os
import time

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

DB = os.getenv("SNOWFLAKE_DATABASE", "PARKPULSE")
FRONTEND = os.path.join(ROOT, "frontend")

app = FastAPI(title="CookedCommute API")


def _connect():
    import snowflake.connector

    cfg = dict(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        role=os.getenv("SNOWFLAKE_ROLE", "PARKPULSE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "PARKPULSE_WH"),
        database=DB,
    )
    key = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH", "")
    if key:
        cfg["private_key_file"] = key
        if os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"):
            cfg["private_key_file_pwd"] = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    else:
        cfg["password"] = os.getenv("SNOWFLAKE_PASSWORD")
    return snowflake.connector.connect(**cfg)


def _query(sql: str) -> list[dict]:
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(sql)
        cols = [c[0].lower() for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


_cache: dict[str, tuple[float, dict]] = {}


def _cached(key: str, ttl: int, fn):
    now = time.time()
    if key in _cache and now - _cache[key][0] < ttl:
        return _cache[key][1]
    val = fn()
    _cache[key] = (now, val)
    return val


def _fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _pt(lon, lat, props) -> dict:
    return {"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [lon, lat]}}


def _traffic() -> dict:
    feats = []
    ndw = _query(
        f"select lat::float lat, lon::float lon, congestion_level, speed_kmh::float speed "
        f"from {DB}.SERVING.LIVE_TRAFFIC where lat is not null and lon is not null"
    )
    weights = {"heavy": 1.0, "moderate": 0.6, "free": 0.25}
    for r in ndw:
        feats.append(_pt(r["lon"], r["lat"], {
            "kind": "ndw",
            "congestion": weights.get(r["congestion_level"], 0.1),
            "speed": r["speed"],
        }))
    return _fc(feats)


def _parking() -> dict:
    rows = _query(
        f"select name, lat::float lat, lon::float lon, capacity::int capacity "
        f"from {DB}.SERVING.LIVE_PARKING where lat is not null and lon is not null"
    )
    return _fc([_pt(r["lon"], r["lat"], {"name": r["name"], "capacity": r["capacity"]}) for r in rows])


@app.get("/api/traffic")
def traffic():
    try:
        return _cached("traffic", 20, _traffic)
    except Exception:
        return _fc([])


@app.get("/api/parking")
def parking():
    try:
        return _cached("parking", 300, _parking)
    except Exception:
        return _fc([])


# --- TomTom raster traffic-flow tiles, proxied so the API key stays server-side ---
TOMTOM_KEY = os.getenv("TOMTOM_API_KEY", "")
_FLOW_STYLES = {"relative0", "relative0-dark"}
_tiles: dict[str, tuple[float, bytes]] = {}


@app.get("/api/flow/{style}/{z}/{x}/{y}")
def flow_tile(style: str, z: int, x: int, y: int):
    """Colour every road by live speed-vs-free-flow. Tiles are cached ~60s
    (flow refreshes about once a minute) to spare the daily TomTom quota."""
    if not TOMTOM_KEY or style not in _FLOW_STYLES:
        return Response(status_code=404)
    ck = f"{style}/{z}/{x}/{y}"
    now = time.time()
    hit = _tiles.get(ck)
    if hit and now - hit[0] < 60:
        png = hit[1]
    else:
        import requests

        url = (f"https://api.tomtom.com/traffic/map/4/tile/flow/{style}/{z}/{x}/{y}.png"
               f"?key={TOMTOM_KEY}&tileSize=512")
        try:
            resp = requests.get(url, timeout=10)
        except Exception:
            return Response(status_code=502)
        if resp.status_code != 200:
            return Response(status_code=resp.status_code)
        png = resp.content
        if len(_tiles) > 3000:
            _tiles.clear()
        _tiles[ck] = (now, png)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=60"})


# --- TomTom live incidents (closures / jams / roadworks) for the Amsterdam bbox ---
_INC_FIELDS = ("{incidents{type,geometry{type,coordinates},properties{iconCategory,"
               "magnitudeOfDelay,delay,from,to,roadNumbers,events{description}}}}")
_ICON = {0: "Unknown", 1: "Accident", 2: "Fog", 3: "Dangerous conditions", 4: "Rain",
         5: "Ice", 6: "Jam", 7: "Lane closed", 8: "Road closed", 9: "Roadworks",
         10: "Wind", 11: "Flooding", 14: "Broken-down vehicle"}


def _incidents() -> dict:
    if not TOMTOM_KEY:
        return _fc([])
    import requests

    bbox = (f'{os.getenv("AMS_BBOX_MIN_LON", "4.78")},{os.getenv("AMS_BBOX_MIN_LAT", "52.30")},'
            f'{os.getenv("AMS_BBOX_MAX_LON", "5.02")},{os.getenv("AMS_BBOX_MAX_LAT", "52.42")}')
    url = ("https://api.tomtom.com/traffic/services/5/incidentDetails"
           f"?key={TOMTOM_KEY}&bbox={bbox}&fields={_INC_FIELDS}"
           "&language=en-GB&timeValidityFilter=present")
    resp = requests.get(url, timeout=12)
    if resp.status_code != 200:
        return _fc([])
    feats = []
    for inc in (resp.json() or {}).get("incidents", []):
        props = inc.get("properties") or {}
        cat = props.get("iconCategory", 0)
        events = props.get("events") or []
        desc = (events[0].get("description") if events else "") or _ICON.get(cat, "Incident")
        feats.append({
            "type": "Feature",
            "geometry": inc.get("geometry"),
            "properties": {
                "category": _ICON.get(cat, "Incident"),
                "closed": 1 if cat in (7, 8) else 0,
                "delay": props.get("delay"),
                "desc": desc,
                "road": ", ".join(props.get("roadNumbers") or []),
            },
        })
    return _fc(feats)


@app.get("/api/incidents")
def incidents():
    try:
        return _cached("incidents", 60, _incidents)
    except Exception:
        return _fc([])


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
