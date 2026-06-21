"""Continuous local ingestion loop (the local stand-in for the timer Functions).

Lands raw to the lake/ADLS on each cycle. Load into Snowflake separately with
`python -m ingestion.warehouse` (or the scheduled COPY task in the cloud).

    python -m ingestion.run_local
"""
from __future__ import annotations

import logging
import time

from .config import load_settings
from .pipeline import ingest_parking, ingest_traffic

log = logging.getLogger("parkpulse.ingest")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    log.info(
        "Starting ingestion loop (traffic=%ss, parking=%ss, synthetic=%s, adls=%s)",
        settings.poll_traffic_seconds,
        settings.poll_parking_seconds,
        settings.use_synthetic,
        settings.adls_enabled,
    )

    next_parking = 0.0
    while True:
        start = time.time()
        try:
            log.info("traffic: landed %d rows", ingest_traffic(settings))
        except Exception:  # noqa: BLE001
            log.exception("traffic cycle failed")

        if time.time() >= next_parking:
            try:
                log.info("parking: landed %d rows", ingest_parking(settings))
            except Exception:  # noqa: BLE001
                log.exception("parking cycle failed")
            next_parking = time.time() + settings.poll_parking_seconds

        time.sleep(max(1.0, settings.poll_traffic_seconds - (time.time() - start)))


if __name__ == "__main__":
    main()
