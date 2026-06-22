"""Timer-triggered traffic ingestion (every 5 min): lands raw to ADLS.

Deploy note: copy the repo-root ``ingestion/`` package into this function-app
folder before publishing (see runbook), so it ships alongside.
"""
import logging
import os
import sys

import azure.functions as func

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # function-app root

from ingestion.config import load_settings  # noqa: E402
from ingestion.pipeline import ingest_traffic  # noqa: E402


def main(timer: func.TimerRequest) -> None:
    count = ingest_traffic(load_settings())
    logging.info("TrafficTimer landed %d rows", count)
