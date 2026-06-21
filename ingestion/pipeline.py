"""Ingestion pipeline (ELT): fetch -> parse -> enrich -> land raw to lake/ADLS.

Snowflake pulls the landed files into RAW via COPY (scheduled TASK in the cloud,
or `python -m ingestion.warehouse` locally). Run a single cycle:

    python -m ingestion.pipeline --once
"""
from __future__ import annotations

import argparse
import logging
from typing import Optional

from . import sinks, synthetic
from .config import Settings, load_settings
from .sources import ams_parking, ndw_traffic, tomtom_flow

log = logging.getLogger("parkpulse.ingest")


# --------------------------------------------------------------------------- #
# Derived fields
# --------------------------------------------------------------------------- #
def congestion_level(speed: Optional[float], flow: Optional[float]) -> str:
    if speed is not None:
        if speed >= 50:
            return "free"
        if speed >= 30:
            return "moderate"
        return "heavy"
    if flow is not None:
        if flow >= 1500:
            return "heavy"
        if flow >= 800:
            return "moderate"
        return "free"
    return "unknown"


def occupancy_pct(free: Optional[int], cap: Optional[int]) -> Optional[float]:
    if free is None or not cap:
        return None
    return round(max(0.0, min(100.0, (cap - free) / cap * 100)), 1)


def enrich_traffic(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["congestion_level"] = congestion_level(r.get("speed_kmh"), r.get("flow_veh_h"))
    return rows


def enrich_parking(rows: list[dict]) -> list[dict]:
    for r in rows:
        r["occupancy_pct"] = occupancy_pct(r.get("free_spaces"), r.get("capacity"))
    return rows


# --------------------------------------------------------------------------- #
# Per-source fetch with graceful fallback
# --------------------------------------------------------------------------- #
def _traffic_rows(settings: Settings) -> list[dict]:
    if settings.use_synthetic:
        return synthetic.traffic_rows(settings)
    try:
        rows = ndw_traffic.get_traffic(settings)
        if rows:
            return rows
        log.warning("NDW returned 0 Amsterdam rows; using synthetic fallback")
    except Exception as exc:  # noqa: BLE001 - degrade, never crash the loop
        log.warning("NDW fetch/parse failed (%s); using synthetic fallback", exc)
    return synthetic.traffic_rows(settings)


def _parking_rows(settings: Settings) -> list[dict]:
    if settings.use_synthetic:
        return synthetic.parking_rows(settings)
    try:
        rows = ams_parking.get_parking(settings)
        if rows:
            return rows
        log.warning("Amsterdam parking returned 0 rows; using synthetic fallback")
    except Exception as exc:  # noqa: BLE001
        log.warning("Parking fetch/parse failed (%s); using synthetic fallback", exc)
    return synthetic.parking_rows(settings)


def ingest_traffic(settings: Settings) -> int:
    rows = enrich_traffic(_traffic_rows(settings))
    sinks.land(settings, "traffic", rows)
    return len(rows)


def ingest_parking(settings: Settings) -> int:
    rows = enrich_parking(_parking_rows(settings))
    sinks.land(settings, "parking", rows)
    return len(rows)


def ingest_citytraffic(settings: Settings) -> int:
    """City-road congestion from TomTom (rate-limited: ~100 calls per run)."""
    if settings.use_synthetic:
        return 0
    try:
        rows = tomtom_flow.get_city_traffic(settings)
    except Exception as exc:  # noqa: BLE001
        log.warning("TomTom city-flow failed (%s)", exc)
        rows = []
    sinks.land(settings, "citytraffic", rows)
    return len(rows)


def run_once(settings: Settings, traffic: bool = True, parking: bool = True) -> None:
    if traffic:
        log.info("traffic: landed %d rows", ingest_traffic(settings))
        log.info("city-traffic: landed %d rows", ingest_citytraffic(settings))
    if parking:
        log.info("parking: landed %d rows", ingest_parking(settings))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="CookedCommute ingestion (ELT land step)")
    ap.add_argument("--once", action="store_true", help="run a single cycle and exit")
    ap.add_argument("--traffic-only", action="store_true")
    ap.add_argument("--parking-only", action="store_true")
    args = ap.parse_args()

    settings = load_settings()
    run_once(settings, traffic=not args.parking_only, parking=not args.traffic_only)


if __name__ == "__main__":
    main()
