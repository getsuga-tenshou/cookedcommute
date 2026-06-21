"""Raw landing sink for ELT: write NDJSON to the local lake and/or ADLS Gen2.

Partition layout (mirrors the Snowflake stage paths used by COPY INTO):
    <dataset>/dt=YYYY-MM-DD/YYYYMMDDThhmmss.jsonl
Always writes a local copy under LAKE_DIR; additionally uploads to ADLS when
ADLS_* is configured (the real landing zone in the cloud).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from .config import Settings

log = logging.getLogger("parkpulse.ingest")


def _ndjson(rows: list[dict]) -> str:
    return "\n".join(json.dumps(r, default=str) for r in rows) + "\n"


def land(settings: Settings, dataset: str, rows: list[dict]) -> str | None:
    if not rows:
        return None
    now = datetime.now(timezone.utc)
    rel = f"{dataset}/dt={now:%Y-%m-%d}/{now:%Y%m%dT%H%M%S}.jsonl"
    data = _ndjson(rows)

    local_path = os.path.join(settings.lake_dir, rel)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "w", encoding="utf-8") as fh:
        fh.write(data)

    if settings.adls_enabled:
        try:
            _upload_adls(settings, rel, data)
        except Exception as exc:  # noqa: BLE001 - lake copy already written; don't crash
            log.warning("ADLS upload failed for %s (%s); kept local copy", rel, exc)
    return rel


def _upload_adls(settings: Settings, rel: str, data: str) -> None:
    from azure.storage.filedatalake import DataLakeServiceClient

    if settings.adls_connection_string:
        svc = DataLakeServiceClient.from_connection_string(settings.adls_connection_string)
    else:
        from azure.identity import DefaultAzureCredential

        svc = DataLakeServiceClient(
            account_url=f"https://{settings.adls_account}.dfs.core.windows.net",
            credential=DefaultAzureCredential(),
        )
    fs = svc.get_file_system_client(settings.adls_filesystem)
    fs.get_file_client(rel).upload_data(data, overwrite=True)
