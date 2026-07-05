"""فاز E — dashboard/app.py
FIX-E13: API_BASE_URL از os.getenv — نه hardcode
FIX-E14: st.exception فقط در development
FIX-E15: unsafe_allow_html فقط برای رشته hardcode CSS (نه user input)
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import streamlit as st

# ───────────────────────────────────────────────────────────────────────────── #
# Config
# ───────────────────────────────────────────────────────────────────────────── #
_ENVIRONMENT   = os.getenv("ENVIRONMENT", "development")
_IS_DEV        = _ENVIRONMENT != "production"
_API_BASE_URL  = os.getenv("API_BASE_URL", "http://api:8000")

st.set_page_config(
    page_title="Galaxy Vast AI",
    page_icon="\U0001f980",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ───────────────────────────────────────────────────────────────────────────── #
# Custom CSS — hardcoded string, NOT user input — safe for html=True
# ───────────────────────────────────────────────────────────────────────────── #
_CUSTOM_CSS = """
<style>
    .main-header { font-size: 2rem; font-weight: 700; color: #00d4ff; }
    .metric-card { background: #1e1e2e; border-radius: 8px; padding: 1rem; }
    .stSelectbox label { color: #a0a0b0; }
    [data-testid="stSidebar"] { background: #13131f; }
</style>
"""
st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)  # safe: hardcoded HTML

# ───────────────────────────────────────────────────────────────────────────── #
# Sidebar navigation
# ───────────────────────────────────────────────────────────────────────────── #
st.sidebar.markdown("## \U0001f980 Galaxy Vast AI")  # no unsafe_allow_html needed
st.sidebar.markdown("---")

_PAGES = {
    "\U0001f504 Market Replay":     "replay",
    "\U0001f4c8 Backtest Results":  "backtest",
    "\u23f9 Walk-Forward":          "walk_forward",
    "\U0001f4bc Portfolio":         "portfolio",
    "\U0001f9a0 Explainability":    "explainability",
    "\U0001f0b2 Monte Carlo":       "monte_carlo",
}

_selected_label = st.sidebar.radio("Navigation", list(_PAGES.keys()))
_module_name    = _PAGES[_selected_label]

st.sidebar.markdown("---")
# Read API URL from env — not hardcoded
st.sidebar.caption(f"API: {_API_BASE_URL}")
st.sidebar.caption(f"Env: {_ENVIRONMENT}")

# ───────────────────────────────────────────────────────────────────────────── #
# Page loader
# ───────────────────────────────────────────────────────────────────────────── #
_pages_dir = str(Path(__file__).parent / "pages")
if _pages_dir not in sys.path:
    sys.path.insert(0, _pages_dir)

try:
    _mod = importlib.import_module(_module_name)
    if hasattr(_mod, "render"):
        _mod.render()
    else:
        st.error(f"Page '{_module_name}' has no render() function.")
except Exception as _e:
    st.error(f"Failed to load page '{_module_name}': {_e}")
    if _IS_DEV:
        st.exception(_e)  # full traceback only in development
    else:
        st.info("\U0001f527 Please contact support or check server logs.")
