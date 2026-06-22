"""Timer-triggered parking ingestion (daily 06:00 UTC; facilities are static)."""
import logging
import os
import sys

import azure.functions as func

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # function-app root

from ingestion.config import load_settings  # noqa: E402
from ingestion.pipeline import ingest_parking  # noqa: E402


def main(timer: func.TimerRequest) -> None:
    count = ingest_parking(load_settings())
    logging.info("ParkingTimer landed %d rows", count)
