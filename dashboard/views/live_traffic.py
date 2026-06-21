"""View 1 — Live traffic intensity (NDW main roads + TomTom city roads)."""
from __future__ import annotations

import folium
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium

import db
from components import maps


def render() -> None:
    df = db.live_traffic()
    city = db.live_city_traffic()
    if df.empty and city.empty:
        st.info("No live traffic yet — run ingestion + load, then refresh.")
        return

    avg_speed = df["speed_kmh"].dropna().mean() if not df.empty else float("nan")
    pct_heavy = df["congestion_level"].eq("heavy").mean() * 100 if len(df) else 0
    last_update = str(df["measured_at"].max())[11:16] if not df.empty else "n/a"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg speed (main roads)", f"{avg_speed:.0f} km/h" if avg_speed == avg_speed else "n/a")
    c2.metric("Corridors heavy", f"{pct_heavy:.0f}%")
    c3.metric("Main-road sites", f"{len(df):,}")
    c4.metric("City segments", f"{len(city):,}")

    st.caption(
        f"Heatmap = congestion intensity (green free → red jammed). Main roads from NDW, "
        f"city streets from TomTom. Last NDW update {last_update} UTC. "
        "Toggle the TomTom live-flow tiles top-right."
    )

    m = maps.base_map(maps.AMS_CENTER, zoom=12)
    heat = []
    for r in df.itertuples():
        if r.lat is not None and r.lon is not None:
            heat.append([r.lat, r.lon, maps.congestion_weight(r.congestion_level)])
    for r in city.itertuples():
        if r.lat is not None and r.lon is not None:
            heat.append([r.lat, r.lon, float(r.congestion_ratio or 0)])
    HeatMap(heat, radius=15, blur=22, min_opacity=0.35, max_zoom=15).add_to(m)
    maps.add_tomtom_flow(m)
    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, height=560, use_container_width=True, returned_objects=[])

    if not df.empty:
        with st.expander("Most congested main-road sites"):
            worst = df.sort_values("speed_kmh", na_position="last").head(15)
            st.dataframe(
                worst[["road", "speed_kmh", "flow_veh_h", "congestion_level"]],
                use_container_width=True,
                hide_index=True,
            )
