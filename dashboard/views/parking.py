"""View 2 — Parking facilities near you (GPS-first interactive map)."""
from __future__ import annotations

import folium
import streamlit as st
from streamlit_folium import st_folium

import db
from components import maps


def _resolve_location():
    """GPS first; fall back to an Amsterdam picker (the data is Amsterdam-only)."""
    st.caption("📍 Click the location pin to use your device GPS, or pick a spot in Amsterdam.")
    try:
        from streamlit_geolocation import streamlit_geolocation

        gps = streamlit_geolocation()
        if gps and gps.get("latitude") and gps.get("longitude"):
            glat, glon = float(gps["latitude"]), float(gps["longitude"])
            if maps.near_amsterdam(glat, glon):
                st.success(f"Using your location · {glat:.4f}, {glon:.4f}")
                return glat, glon
            st.warning(
                "You're outside Amsterdam — this demo's parking data is Amsterdam-only, "
                "so choose a spot below."
            )
    except Exception:
        pass

    name = st.selectbox("Location in Amsterdam", list(maps.LOCATIONS))
    return maps.LOCATIONS[name]


def render() -> None:
    lat, lon = _resolve_location()

    df = db.nearest_parking(lat, lon, 200)
    if df.empty:
        st.info("No parking facilities yet — run ingestion + load, then refresh.")
        return
    df = df.copy()
    df["dist_km"] = (df["dist_m"] / 1000).round(2)

    c1, c2, c3 = st.columns(3)
    c1.metric("Facilities nearby", f"{len(df):,}")
    c2.metric("Total spaces", f"{int(df['capacity'].fillna(0).sum()):,}")
    c3.metric("Closest", f"{df.iloc[0]['dist_km']} km")

    m = maps.base_map([lat, lon], zoom=13)
    folium.Marker(
        [lat, lon],
        tooltip="You are here",
        icon=folium.Icon(color="red", icon="user", prefix="fa"),
    ).add_to(m)
    for r in df.itertuples():
        cap = int(r.capacity) if r.capacity == r.capacity else "?"
        folium.CircleMarker(
            location=[r.lat, r.lon],
            radius=maps.capacity_radius(r.capacity),
            color="#0e7490",
            fill=True,
            fill_color="#0891b2",
            fill_opacity=0.7,
            weight=1,
            popup=folium.Popup(
                f"<b>{r.name or r.garage_id}</b><br>Capacity: {cap}<br>"
                f"Type: {r.state}<br>{r.dist_km} km away",
                max_width=240,
            ),
            tooltip=r.name,
        ).add_to(m)
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

    st.markdown("**Nearest facilities**")
    show = df[["name", "capacity", "state", "dist_km"]].head(10).rename(
        columns={"state": "type", "dist_km": "km"}
    )
    st.dataframe(show, use_container_width=True, hide_index=True)
