"""CookedCommute — Streamlit dashboard entrypoint.

    streamlit run dashboard/app.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

from views import live_traffic, parking  # noqa: E402

st.set_page_config(page_title="CookedCommute — Amsterdam", page_icon="🚗", layout="wide")

PAGES = {
    "Live Traffic": live_traffic,
    "Parking Near You": parking,
}

with st.sidebar:
    st.title("🚗 CookedCommute")
    st.caption("How cooked is your commute, and where do you park? · Amsterdam")
    choice = st.radio("View", list(PAGES), label_visibility="collapsed")
    st.divider()
    st.caption("Live data: NDW (traffic) · RDW NPR (parking facilities)")

st.title(choice)
PAGES[choice].render()
