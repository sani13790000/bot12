"""Galaxy Vast Institutional Dashboard — Streamlit v2.0."""
import importlib
import sys
import os

import streamlit as st

st.set_page_config(
    page_title="Galaxy Vast Institutional",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/sani13790000/bot12',
        'About': 'Galaxy Vast AI Trading Platform v2.0.0 — Institutional Grade'
    }
)

# Custom CSS
st.markdown("""
<style>
    .main { background-color: #0E1117; }
    .stMetric { background-color: #1E2329; border-radius: 8px; padding: 8px; }
    .stMetric label { color: #848E9C !important; font-size: 0.75rem !important; }
    div[data-testid="stSidebarContent"] { background-color: #1E2329; }
    .galaxy-header { color: #FFD700; font-size: 2rem; font-weight: bold; }
    .status-live { color: #0ECB81; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.markdown('<h2 style="color:#FFD700">🌌 Galaxy Vast</h2>', unsafe_allow_html=True)
st.sidebar.markdown('<span style="color:#848E9C">Institutional Trading Platform v2.0</span>', unsafe_allow_html=True)
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    [
        "📉 Market Replay",
        "📈 Backtest",
        "📉 Walk-Forward",
        "💼 Portfolio",
        "🧠 AI Explainability",
        "🎲 Monte Carlo",
    ],
    label_visibility="collapsed"
)

st.sidebar.divider()
st.sidebar.markdown('<span class="status-live">⚫ LIVE</span> Connected to API', unsafe_allow_html=True)
st.sidebar.caption("API: http://localhost:8000")

# Add pages directory to sys.path so imports work in Streamlit context
_pages_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pages")
if _pages_dir not in sys.path:
    sys.path.insert(0, _pages_dir)

# Route to correct page module
_page_map = {
    "📉 Market Replay": "replay",
    "📈 Backtest": "backtest",
    "📉 Walk-Forward": "walk_forward",
    "💼 Portfolio": "portfolio",
    "🧠 AI Explainability": "explainability",
    "🎲 Monte Carlo": "monte_carlo",
}

_module_name = _page_map.get(page, "replay")
try:
    _mod = importlib.import_module(_module_name)
    if hasattr(_mod, "render"):
        _mod.render()
except Exception as _e:
    st.error(f"Failed to load page '{_module_name}': {_e}")
    st.exception(_e)
