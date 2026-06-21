"""Shared map helpers (Folium): clean basemap, TomTom overlay, colour scales."""
from __future__ import annotations

import os

import folium

AMS_CENTER = [52.3676, 4.9041]

# "Your location" presets for the parking view.
LOCATIONS = {
    "Amsterdam Centraal": (52.3791, 4.9003),
    "Dam Square": (52.3731, 4.8926),
    "Museumplein": (52.3580, 4.8810),
    "Vondelpark": (52.3580, 4.8686),
    "Johan Cruijff ArenA": (52.3144, 4.9419),
    "Sloterdijk": (52.3889, 4.8378),
}

CONGESTION_HEX = {
    "free": "#22c55e",
    "moderate": "#f59e0b",
    "heavy": "#ef4444",
    "unknown": "#9ca3af",
}

_TOMTOM_KEY = os.getenv("TOMTOM_API_KEY", "")


def base_map(center=None, zoom: int = 12) -> folium.Map:
    """A clean light Leaflet map (CartoDB Positron) — pannable/zoomable."""
    return folium.Map(
        location=center or AMS_CENTER,
        zoom_start=zoom,
        tiles="CartoDB positron",
        control_scale=True,
    )


def add_tomtom_flow(m: folium.Map) -> None:
    """Overlay TomTom's live traffic-flow tiles (toggle in the layer control)."""
    if not _TOMTOM_KEY:
        return
    folium.TileLayer(
        tiles=(
            "https://api.tomtom.com/traffic/map/4/tile/flow/relative/"
            "{z}/{x}/{y}.png?key=" + _TOMTOM_KEY
        ),
        attr="TomTom",
        name="Live traffic flow (TomTom)",
        overlay=True,
        control=True,
        opacity=0.75,
    ).add_to(m)


def congestion_hex(level: str) -> str:
    return CONGESTION_HEX.get(level or "unknown", CONGESTION_HEX["unknown"])


def congestion_weight(level: str) -> float:
    return {"heavy": 1.0, "moderate": 0.6, "free": 0.25}.get(level or "unknown", 0.1)


def capacity_radius(capacity) -> float:
    """Marker radius scaled by capacity (sqrt so big lots don't dominate)."""
    try:
        return 5 + (float(capacity) ** 0.5) * 0.8
    except (TypeError, ValueError):
        return 5.0


def near_amsterdam(lat: float, lon: float) -> bool:
    """Rough check that a point falls in the greater-Amsterdam area."""
    return 52.0 <= lat <= 52.6 and 4.5 <= lon <= 5.3
