"""Galaxy Vast AI Trading Dashboard — Phase I: Live Data."""
from __future__ import annotations
import os
from typing import Any, Callable, Dict, Optional
import streamlit as st
import requests

API_BASE_URL: str = os.getenv("API_BASE_URL", "http://api:8000")
IS_DEV: bool = os.getenv("ENVIRONMENT", "production").lower() in ("dev", "development", "local")
_REFRESH_MS: int = int(os.getenv("DASHBOARD_REFRESH_MS", "5000"))

st.set_page_config(page_title="Galaxy Vast AI Trading", page_icon="🌌", layout="wide", initial_sidebar_state="expanded")

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=_REFRESH_MS, key="live_refresh")
except ImportError:
    st.sidebar.caption("Install streamlit-autorefresh for auto-refresh")


def _get(path: str, params: Optional[Dict] = None, timeout: int = 8) -> Optional[Any]:
    """GET from API — returns parsed JSON or None on error."""
    try:
        r = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.sidebar.error(f"API offline: {API_BASE_URL}")
        return None
    except requests.exceptions.Timeout:
        st.sidebar.warning(f"Timeout: {path}")
        return None
    except Exception as exc:  # noqa: BLE001
        if IS_DEV:
            st.exception(exc)
        return None


def _post(path: str, payload: Dict, timeout: int = 15) -> Optional[Any]:
    """POST to API — returns parsed JSON or None on error."""
    try:
        r = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        if IS_DEV:
            st.exception(exc)
        return None


with st.sidebar:
    st.markdown("### 🌌 Galaxy Vast AI")
    st.markdown("---")
    page = st.radio("Navigation", ["📊 Overview", "💹 Live Trades", "📈 Analytics", "🤖 AI Model", "⚙️ Settings"], key="nav")
    st.markdown("---")
    health = _get("/health/live")
    if health and health.get("status") == "ok":
        st.success("🟢 API Online")
    else:
        st.error("🔴 API Offline")
    st.caption(f"Refresh: {_REFRESH_MS // 1000}s | {API_BASE_URL}")

if page == "📊 Overview":
    st.title("📊 System Overview")
    ready = _get("/health/ready")
    if ready:
        st.json(ready)
    col1, col2, col3 = st.columns(3)
    account = _get("/metrics/account")
    if account:
        col1.metric("Equity", f"${account.get('equity', 0):,.2f}")
        col2.metric("Balance", f"${account.get('balance', 0):,.2f}")
        col3.metric("Free Margin", f"${account.get('free_margin', 0):,.2f}")

elif page == "💹 Live Trades":
    from dashboard.pages import live_trading
    live_trading.render(api_get=_get, api_base=API_BASE_URL)

elif page == "📈 Analytics":
    from dashboard.pages import portfolio
    portfolio.render(api_get=_get)

elif page == "🤖 AI Model":
    from dashboard.pages import explainability
    explainability.render(api_get=_get)

elif page == "⚙️ Settings":
    st.title("⚙️ Settings")
    cfg = _get("/admin/config")
    if cfg:
        st.json(cfg)
    else:
        st.info("Settings managed via .env file")
