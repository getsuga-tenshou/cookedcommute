"""Read-only data access for the dashboard (Snowflake live views + dbt marts)."""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

DB = os.getenv("SNOWFLAKE_DATABASE", "PARKPULSE")


@st.cache_resource
def _connection():
    import snowflake.connector

    cfg = dict(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        role=os.getenv("SNOWFLAKE_ROLE", "PARKPULSE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "PARKPULSE_WH"),
        database=DB,
    )
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH", "")
    if key_path:  # key-pair auth (password is blocked for programmatic access)
        cfg["private_key_file"] = key_path
        passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", "")
        if passphrase:
            cfg["private_key_file_pwd"] = passphrase
    else:
        cfg["password"] = os.getenv("SNOWFLAKE_PASSWORD")
    return snowflake.connector.connect(**cfg)


def _read(sql: str, params: dict | None = None) -> pd.DataFrame:
    try:
        cur = _connection().cursor()
        cur.execute(sql, params or {})
        df = cur.fetch_pandas_all()
    except Exception:
        _connection.clear()  # drop a possibly-expired session and retry once
        cur = _connection().cursor()
        cur.execute(sql, params or {})
        df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


def _read_safe(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Marts may not exist until dbt has run; never crash the UI over it."""
    try:
        return _read(sql, params)
    except Exception:
        return pd.DataFrame()


# --- Live serving views (latest row per entity) -------------------------- #
@st.cache_data(ttl=15)
def live_traffic() -> pd.DataFrame:
    return _read(
        f"""
        select site_id, lat::float lat, lon::float lon, road,
               flow_veh_h::float flow_veh_h, speed_kmh::float speed_kmh,
               congestion_level, measured_at
        from {DB}.SERVING.LIVE_TRAFFIC
        where lat is not null and lon is not null
        """
    )


@st.cache_data(ttl=15)
def live_city_traffic() -> pd.DataFrame:
    return _read_safe(
        f"""
        select lat::float lat, lon::float lon, congestion_ratio::float congestion_ratio,
               congestion_level, current_speed::float current_speed, frc
        from {DB}.SERVING.LIVE_CITY_TRAFFIC
        where lat is not null and lon is not null
        """
    )


@st.cache_data(ttl=15)
def live_parking() -> pd.DataFrame:
    return _read(
        f"""
        select garage_id, name, lat::float lat, lon::float lon,
               free_spaces::float free_spaces, capacity::float capacity,
               occupancy_pct::float occupancy_pct, state, measured_at
        from {DB}.SERVING.LIVE_PARKING
        where lat is not null and lon is not null
        """
    )


@st.cache_data(ttl=15)
def nearest_parking(lat: float, lon: float, k: int = 8) -> pd.DataFrame:
    return _read(
        f"""
        select garage_id, name, lat::float lat, lon::float lon,
               free_spaces::float free_spaces, capacity::float capacity,
               occupancy_pct::float occupancy_pct, state, measured_at,
               ST_DISTANCE(geom, ST_MAKEPOINT(%(lon)s, %(lat)s))::float as dist_m
        from {DB}.SERVING.LIVE_PARKING
        where geom is not null
        order by dist_m asc
        limit %(k)s
        """,
        {"lat": lat, "lon": lon, "k": k},
    )
