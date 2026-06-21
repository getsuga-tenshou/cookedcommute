"""NDW national traffic feed (DATEX II) -> normalized Amsterdam traffic rows.

NDW publishes two gzipped XML files we care about:

* ``measurement.xml.gz``  - static config: one record per measurement site with
  its coordinates. Fetched at most once a day and cached to the lake.
* ``trafficspeed.xml.gz``  - live values, refreshed ~every minute: per site a
  ``vehicleFlowRate`` (intensity, veh/h) and an ``averageVehicleSpeed`` (km/h).

These files are large (measurement.xml is ~50 MB uncompressed), so we parse them
by **streaming** with ``iterparse`` rather than building a DOM and running broad
``//`` XPath queries (which blow libxml2's node-set limit on a file this size).
Parsing is namespace-agnostic (matches on local tag names) and degrades
gracefully: a record we cannot read is skipped, never crashing the cycle.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import time
from datetime import datetime, timezone

import requests
from lxml import etree

from ..config import Settings

_TIMEOUT = 60
_MEASUREMENT_CACHE = "measurement_config.json"
_CACHE_TTL_SECONDS = 24 * 3600


def _fetch_gz(url: str) -> bytes:
    resp = requests.get(url, timeout=_TIMEOUT)
    resp.raise_for_status()
    raw = resp.content
    # Some endpoints already decompress transparently; sniff the gzip magic bytes.
    if raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    return raw


def _localname(tag) -> str:
    """Local name of an element tag, ignoring namespace ('{ns}foo' -> 'foo')."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _to_float(text: str | None):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _parse_iso(text: str | None):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _iter_records(xml_bytes: bytes, target: str):
    """Yield each element whose local name == target, freeing memory as we go."""
    context = etree.iterparse(io.BytesIO(xml_bytes), events=("end",), huge_tree=True, recover=True)
    for _, el in context:
        if _localname(el.tag) == target:
            yield el
            el.clear()
            # Drop already-processed siblings so memory stays flat on huge files.
            while el.getprevious() is not None:
                parent = el.getparent()
                if parent is None:
                    break
                del parent[0]


# --------------------------------------------------------------------------- #
# Static measurement-site config (id -> lat/lon/road)
# --------------------------------------------------------------------------- #
def parse_measurement_config(xml_bytes: bytes) -> dict[str, dict]:
    sites: dict[str, dict] = {}
    for rec in _iter_records(xml_bytes, "measurementSiteRecord"):
        site_id = rec.get("id")
        lat = lon = road = None
        for node in rec.iter():
            ln = _localname(node.tag)
            text = (node.text or "").strip()
            if not text:
                continue
            if ln == "latitude" and lat is None:
                lat = _to_float(text)
            elif ln == "longitude" and lon is None:
                lon = _to_float(text)
            elif road is None and ln in ("carriagewayCode", "roadNumber", "measurementSiteName"):
                road = text
        if site_id:
            sites[site_id] = {"lat": lat, "lon": lon, "road": road}
    return sites


def load_measurement_config(settings: Settings) -> dict[str, dict]:
    """Return id->config, using a daily on-disk cache to avoid refetching ~50MB."""
    os.makedirs(settings.lake_dir, exist_ok=True)
    cache_path = os.path.join(settings.lake_dir, _MEASUREMENT_CACHE)
    if os.path.exists(cache_path) and (time.time() - os.path.getmtime(cache_path)) < _CACHE_TTL_SECONDS:
        with open(cache_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    config = parse_measurement_config(_fetch_gz(settings.ndw_measurement_url))
    if config:
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(config, fh)
    return config


# --------------------------------------------------------------------------- #
# Live values
# --------------------------------------------------------------------------- #
def parse_trafficspeed(xml_bytes: bytes) -> dict[str, dict]:
    """Return id -> {flow_veh_h, speed_kmh, measured_at} from the live feed."""
    out: dict[str, dict] = {}
    for sm in _iter_records(xml_bytes, "siteMeasurements"):
        site_id = None
        flows: list[float] = []
        speeds: list[float] = []
        measured_at = None
        for node in sm.iter():
            ln = _localname(node.tag)
            if ln == "measurementSiteReference":
                site_id = node.get("id") or (node.text or "").strip() or site_id
            elif ln in ("measurementOrCalculatedTime", "measurementTimeDefault"):
                measured_at = _parse_iso(node.text) or measured_at
            elif ln == "vehicleFlowRate":
                v = _to_float((node.text or "").strip())
                if v is not None:
                    flows.append(v)
            elif ln == "speed":
                v = _to_float((node.text or "").strip())
                if v is not None:
                    speeds.append(v)
        if site_id:
            out[site_id] = {
                "flow_veh_h": sum(flows) if flows else None,
                "speed_kmh": (sum(speeds) / len(speeds)) if speeds else None,
                "measured_at": measured_at or datetime.now(timezone.utc),
            }
    return out


def get_traffic(settings: Settings) -> list[dict]:
    """Fetch + join + clip to Amsterdam. Returns rows ready for the pipeline."""
    config = load_measurement_config(settings)
    live = parse_trafficspeed(_fetch_gz(settings.ndw_trafficspeed_url))
    rows: list[dict] = []
    for site_id, vals in live.items():
        cfg = config.get(site_id, {})
        lat, lon = cfg.get("lat"), cfg.get("lon")
        if not settings.bbox.contains(lat, lon):
            continue
        rows.append(
            {
                "site_id": site_id,
                "lat": lat,
                "lon": lon,
                "road": cfg.get("road"),
                "flow_veh_h": vals["flow_veh_h"],
                "speed_kmh": vals["speed_kmh"],
                "measured_at": vals["measured_at"],
            }
        )
    return rows
