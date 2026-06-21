"""TomTom Traffic Flow -> city-road congestion samples (covers all roads).

NDW only sensors motorways + main roads. To get *city-street* intensity we sample
a grid of points across Amsterdam and ask TomTom's Flow Segment API for the nearest
road segment's current vs free-flow speed; congestion_ratio = 1 - current/freeflow.

Free tier = 2,500 non-tile calls/day, so the grid is kept small (default 10x10 =
100 calls per run). Queried concurrently to stay fast.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from ..config import Settings

log = logging.getLogger("parkpulse.ingest")

_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/12/json"
_TIMEOUT = 15


def _grid(bbox, n: int) -> list[tuple[float, float]]:
    if n < 2:
        n = 2
    lats = [bbox.min_lat + (bbox.max_lat - bbox.min_lat) * i / (n - 1) for i in range(n)]
    lons = [bbox.min_lon + (bbox.max_lon - bbox.min_lon) * j / (n - 1) for j in range(n)]
    return [(la, lo) for la in lats for lo in lons]


def _fetch_point(key: str, lat: float, lon: float):
    try:
        resp = requests.get(
            _URL, params={"point": f"{lat},{lon}", "key": key}, timeout=_TIMEOUT
        )
        if resp.status_code != 200:
            return None
        fsd = (resp.json() or {}).get("flowSegmentData")
        if not fsd:
            return None
        cur, free = fsd.get("currentSpeed"), fsd.get("freeFlowSpeed")
        if cur is None or not free:
            return None
        ratio = max(0.0, min(1.0, 1 - cur / free))
        return {
            "point_id": f"{round(lat, 4)}_{round(lon, 4)}",
            "lat": lat,
            "lon": lon,
            "current_speed": float(cur),
            "freeflow_speed": float(free),
            "congestion_ratio": round(ratio, 3),
            "frc": fsd.get("frc"),
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:  # noqa: BLE001 - one bad point shouldn't sink the batch
        return None


def get_city_traffic(settings: Settings, n: int = 10) -> list[dict]:
    key = settings.tomtom_api_key
    if not key:
        log.warning("No TOMTOM_API_KEY set; skipping city-traffic.")
        return []
    points = _grid(settings.bbox, n)
    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = [r for r in ex.map(lambda p: _fetch_point(key, p[0], p[1]), points) if r]
    log.info("TomTom city-flow: %d/%d segments", len(rows), len(points))
    return rows
