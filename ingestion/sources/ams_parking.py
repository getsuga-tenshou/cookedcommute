"""Amsterdam off-street parking *facilities* from RDW NPR open data (static).

Scope: we surface *where the parking facilities are* — name, location, capacity,
and type — not live free-space counts (that scope was dropped; Amsterdam's dynamic
feed host is offline anyway).

NPR is a national catalog. Flow:
  1. GET the catalog (base URL) -> list of facilities with a per-facility staticDataUrl.
  2. Keep Amsterdam off-street facilities (name contains "(Amsterdam…)", excluding
     on-street zones / bike parking).
  3. GET each facility's static record -> coordinates (accessPoints) + capacity
     (specifications) + usage type.
Facilities rarely change, so the resolved set is cached to the lake for a day.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from ..config import Settings

log = logging.getLogger("parkpulse.ingest")

_TIMEOUT = 30
_CACHE = "parking_facilities.json"
_CACHE_TTL_SECONDS = 24 * 3600


def _get_json(session: requests.Session, url: str):
    resp = session.get(url, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def is_amsterdam_offstreet(name: str | None) -> bool:
    """True for Amsterdam car-parking facilities; drops on-street and bike parking."""
    n = (name or "").lower()
    if "(amsterdam" not in n:  # the municipality appears in parentheses in the name
        return False
    if n.startswith("straatparkeren") or "fietsparkeren" in n or "fietsenstalling" in n:
        return False
    return True


def extract_facility(info: dict) -> Optional[dict]:
    """Map an NPR ``parkingFacilityInformation`` block to a flat facility row."""
    specs = info.get("specifications") or []
    capacity = specs[0].get("capacity") if specs else None
    usage = specs[0].get("usage") if specs else None

    lat = lon = None
    for ap in info.get("accessPoints") or []:
        for loc in ap.get("accessPointLocation") or []:
            la, lo = loc.get("latitude"), loc.get("longitude")
            if la and lo:
                lat, lon = float(la), float(lo)
                break
        if lat is not None:
            break
    if lat is None or lon is None:
        return None

    return {
        "garage_id": info.get("identifier"),
        "name": info.get("name"),
        "lat": lat,
        "lon": lon,
        "free_spaces": None,  # facilities only; no live count in scope
        "capacity": int(capacity) if capacity else None,
        "state": usage or "facility",
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }


def _resolve_facilities(settings: Settings) -> list[dict]:
    session = requests.Session()
    catalog = _get_json(session, settings.ams_parking_url.rstrip("/"))
    facilities = catalog.get("ParkingFacilities", []) if isinstance(catalog, dict) else []
    ams = [f for f in facilities if is_amsterdam_offstreet(f.get("name"))]
    log.info("NPR catalog: %d facilities; Amsterdam off-street: %d", len(facilities), len(ams))

    rows: list[dict] = []
    for f in ams:
        url = f.get("staticDataUrl")
        if not url:
            continue
        try:
            info = (_get_json(session, url) or {}).get("parkingFacilityInformation") or {}
            row = extract_facility(info)
            if row and row["garage_id"]:
                rows.append(row)
        except Exception as exc:  # noqa: BLE001 - skip one bad facility, keep the rest
            log.warning("static fetch failed for %s (%s)", f.get("name"), exc)
    log.info("resolved %d Amsterdam parking facilities", len(rows))
    return rows


def get_parking(settings: Settings) -> list[dict]:
    """Return Amsterdam parking facilities, using a daily on-disk cache."""
    os.makedirs(settings.lake_dir, exist_ok=True)
    cache_path = os.path.join(settings.lake_dir, _CACHE)

    if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path)) < _CACHE_TTL_SECONDS:
        with open(cache_path, "r", encoding="utf-8") as fh:
            rows = json.load(fh)
    else:
        rows = _resolve_facilities(settings)
        if rows:
            with open(cache_path, "w", encoding="utf-8") as fh:
                json.dump(rows, fh)

    # Stamp each row with the current cycle time so the "latest" view is fresh.
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        r["measured_at"] = now
    return rows
