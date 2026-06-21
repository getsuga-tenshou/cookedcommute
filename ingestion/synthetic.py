"""Synthetic data generator: a graceful fallback for offline demos / feed outages.

Produces plausible Amsterdam traffic points and real garage locations with
randomised-but-stable-per-minute values, so the dashboard always has something
live-looking to show (e.g. in an interview on hotel wifi). Clearly distinct from
real data: rows carry no claim of authenticity and the README documents the flag.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

from .config import Settings

# A handful of real Amsterdam off-street garages (approx. coordinates).
_GARAGES = [
    ("syn-bijenkorf", "Q-Park De Bijenkorf", 52.3731, 4.8926, 700),
    ("syn-europarking", "Q-Park Europarking", 52.3596, 4.8783, 1100),
    ("syn-byzantium", "Q-Park Byzantium", 52.3636, 4.8810, 400),
    ("syn-museumplein", "Q-Park Museumplein", 52.3580, 4.8810, 600),
    ("syn-waterlooplein", "Q-Park Waterlooplein", 52.3673, 4.9020, 550),
    ("syn-arena", "P+R Johan Cruijff ArenA", 52.3144, 4.9419, 2500),
    ("syn-sloterdijk", "P+R Sloterdijk", 52.3889, 4.8378, 1200),
    ("syn-olympisch", "P+R Olympisch Stadion", 52.3433, 4.8556, 900),
]


def _rng(settings: Settings) -> random.Random:
    # Stable within a minute, varies across minutes.
    minute_bucket = int(datetime.now(timezone.utc).timestamp() // 60)
    return random.Random(minute_bucket)


def traffic_rows(settings: Settings, n: int = 45) -> list[dict]:
    rng = _rng(settings)
    bb = settings.bbox
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(n):
        lat = rng.uniform(bb.min_lat, bb.max_lat)
        lon = rng.uniform(bb.min_lon, bb.max_lon)
        speed = round(rng.triangular(5, 100, 75), 1)
        flow = round(rng.uniform(200, 2200), 0)
        rows.append(
            {
                "site_id": f"syn-traffic-{i:03d}",
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "road": rng.choice(["A10", "A2", "S100", "S114", "N200"]),
                "flow_veh_h": flow,
                "speed_kmh": speed,
                "measured_at": now,
            }
        )
    return rows


def parking_rows(settings: Settings) -> list[dict]:
    rng = _rng(settings)
    now = datetime.now(timezone.utc)
    rows = []
    for gid, name, lat, lon, cap in _GARAGES:
        free = rng.randint(0, cap)
        rows.append(
            {
                "garage_id": gid,
                "name": name,
                "lat": lat,
                "lon": lon,
                "free_spaces": free,
                "capacity": cap,
                "state": "open",
                "measured_at": now,
            }
        )
    return rows
