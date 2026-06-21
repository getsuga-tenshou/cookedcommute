"""Typed configuration loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional at runtime (e.g. Azure Functions app settings)
    pass


def _f(name: str, default: str) -> float:
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class BBox:
    """A lat/lon bounding box used to clip the national NDW feed to Amsterdam."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, lat: float | None, lon: float | None) -> bool:
        if lat is None or lon is None:
            return False
        return self.min_lat <= lat <= self.max_lat and self.min_lon <= lon <= self.max_lon


@dataclass(frozen=True)
class Settings:
    # sources
    ndw_trafficspeed_url: str
    ndw_measurement_url: str
    ams_parking_url: str
    tomtom_api_key: str
    # ingestion behaviour
    poll_traffic_seconds: int
    poll_parking_seconds: int
    lake_dir: str
    use_synthetic: bool
    bbox: BBox
    # ADLS Gen2 raw landing (ELT). If unset, ingestion lands to local lake_dir.
    adls_account: str
    adls_filesystem: str
    adls_connection_string: str
    # Snowflake warehouse
    sf_account: str
    sf_user: str
    sf_password: str
    sf_role: str
    sf_warehouse: str
    sf_database: str
    sf_schema: str
    sf_private_key_path: str
    sf_private_key_passphrase: str

    @property
    def adls_enabled(self) -> bool:
        return bool(self.adls_connection_string or self.adls_account)

    @property
    def snowflake_config(self) -> dict:
        cfg = {
            "account": self.sf_account,
            "user": self.sf_user,
            "role": self.sf_role or None,
            "warehouse": self.sf_warehouse or None,
            "database": self.sf_database or None,
            "schema": self.sf_schema or None,
        }
        # Snowflake blocks password for programmatic access -> prefer key-pair auth.
        if self.sf_private_key_path:
            cfg["private_key_file"] = self.sf_private_key_path
            if self.sf_private_key_passphrase:
                cfg["private_key_file_pwd"] = self.sf_private_key_passphrase
        else:
            cfg["password"] = self.sf_password
        return cfg


def load_settings() -> Settings:
    return Settings(
        ndw_trafficspeed_url=os.getenv(
            "NDW_TRAFFICSPEED_URL", "https://opendata.ndw.nu/trafficspeed.xml.gz"
        ),
        ndw_measurement_url=os.getenv(
            "NDW_MEASUREMENT_URL", "https://opendata.ndw.nu/measurement.xml.gz"
        ),
        ams_parking_url=os.getenv(
            "AMS_PARKING_URL", "https://npropendata.rdw.nl/parkingdata/v2"
        ),
        tomtom_api_key=os.getenv("TOMTOM_API_KEY", ""),
        poll_traffic_seconds=int(os.getenv("POLL_TRAFFIC_SECONDS", "60")),
        poll_parking_seconds=int(os.getenv("POLL_PARKING_SECONDS", "300")),
        lake_dir=os.getenv("LAKE_DIR", "./lake"),
        use_synthetic=os.getenv("USE_SYNTHETIC", "false").lower() == "true",
        bbox=BBox(
            _f("AMS_BBOX_MIN_LAT", "52.30"),
            _f("AMS_BBOX_MAX_LAT", "52.42"),
            _f("AMS_BBOX_MIN_LON", "4.78"),
            _f("AMS_BBOX_MAX_LON", "5.02"),
        ),
        adls_account=os.getenv("ADLS_ACCOUNT", ""),
        adls_filesystem=os.getenv("ADLS_FILESYSTEM", "raw"),
        adls_connection_string=os.getenv("ADLS_CONNECTION_STRING", ""),
        sf_account=os.getenv("SNOWFLAKE_ACCOUNT", ""),
        sf_user=os.getenv("SNOWFLAKE_USER", ""),
        sf_password=os.getenv("SNOWFLAKE_PASSWORD", ""),
        sf_role=os.getenv("SNOWFLAKE_ROLE", "PARKPULSE_ROLE"),
        sf_warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "PARKPULSE_WH"),
        sf_database=os.getenv("SNOWFLAKE_DATABASE", "PARKPULSE"),
        sf_schema=os.getenv("SNOWFLAKE_SCHEMA", "RAW"),
        sf_private_key_path=os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH", ""),
        sf_private_key_passphrase=os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", ""),
    )
