"""Snowflake helpers + a local-dev loader (PUT lake files to an internal stage,
then COPY INTO RAW). In the cloud the equivalent COPY runs as a scheduled TASK
over the ADLS external stage (see snowflake/02_azure_stage_and_load.sql).

    python -m ingestion.warehouse        # load ./lake/* into Snowflake RAW
"""
from __future__ import annotations

import glob
import logging
import os
import shutil
import tempfile

from .config import Settings, load_settings

log = logging.getLogger("parkpulse.ingest")

# dataset -> (target table, column list, VARIANT->typed projection)
_DATASETS = {
    "traffic": (
        "RAW.TRAFFIC_MEASUREMENTS",
        "(site_id, lat, lon, road, flow_veh_h, speed_kmh, measured_at)",
        "SELECT $1:site_id::string, $1:lat::float, $1:lon::float, $1:road::string, "
        "$1:flow_veh_h::float, $1:speed_kmh::float, $1:measured_at::timestamp_tz",
    ),
    "parking": (
        "RAW.PARKING_SNAPSHOTS",
        "(garage_id, name, lat, lon, free_spaces, capacity, state, measured_at)",
        "SELECT $1:garage_id::string, $1:name::string, $1:lat::float, $1:lon::float, "
        "$1:free_spaces::number, $1:capacity::number, $1:state::string, $1:measured_at::timestamp_tz",
    ),
}


def connect(settings: Settings):
    import snowflake.connector

    cfg = {k: v for k, v in settings.snowflake_config.items() if v}
    return snowflake.connector.connect(**cfg)


def dev_load(settings: Settings) -> None:
    """Load local lake JSONL into Snowflake RAW via the internal stage.

    Files are first copied into a space-free temp directory because Snowflake's
    PUT command mishandles spaces in local paths (and repo paths often have them).
    """
    lake = os.path.abspath(settings.lake_dir)
    con = connect(settings)
    try:
        cur = con.cursor()
        for dataset, (table, cols, select) in _DATASETS.items():
            files = glob.glob(os.path.join(lake, dataset, "**", "*.jsonl"), recursive=True)
            if not files:
                log.info("%s: no local files to load", dataset)
                continue

            staging = os.path.join(tempfile.gettempdir(), "parkpulse_put", dataset)
            shutil.rmtree(staging, ignore_errors=True)
            os.makedirs(staging, exist_ok=True)
            for i, f in enumerate(files):
                # prefix keeps basenames unique across dt= partitions
                shutil.copy(f, os.path.join(staging, f"{i:05d}_{os.path.basename(f)}"))

            put_uri = ("file://" + os.path.join(staging, "*.jsonl")).replace("\\", "/")
            try:
                cur.execute(f"PUT '{put_uri}' @RAW.LOCAL_STAGE/{dataset}/ OVERWRITE=TRUE AUTO_COMPRESS=TRUE")
                cur.execute(
                    f"COPY INTO {table} {cols} FROM ( {select} FROM @RAW.LOCAL_STAGE/{dataset}/ ) "
                    f"FILE_FORMAT=(FORMAT_NAME=RAW.JSON_NDJSON) PATTERN='.*\\.jsonl.*' ON_ERROR=CONTINUE"
                )
                log.info("%s: COPY INTO %s from %d file(s)", dataset, table, len(files))
            except Exception as exc:  # noqa: BLE001 - keep loading the other datasets
                log.warning("%s: load failed (%s) — has %s been created? (run snowflake/03_*.sql)",
                            dataset, exc, table)
    finally:
        con.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    dev_load(load_settings())


if __name__ == "__main__":
    main()
