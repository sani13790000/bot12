"""Galaxy Vast AI Trading Platform — Streamlit Institutional Dashboard."""
import streamlit as st

st.set_page_config(
    page_title="Galaxy Vast Institutional",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🌌 Galaxy Vast AI Trading Platform")
st.subheader("Institutional-Grade Trading Framework")

st.markdown(
    """
    Welcome to the institutional dashboard. Use the sidebar to navigate:

    - **Market Replay** — Candle-by-candle playback with trade markers
    - **Backtest** — Tick-level multi-symbol backtesting
    - **Portfolio** — Allocation and position sizing
    - **Correlation** — Cross-asset correlation analysis
    - **Explainability** — Understand AI trade decisions
    - **RL Agent** — Train and predict with reinforcement learning
    """
)

from api_client import APIClient
client = APIClient()
health = client.health()
color = "green" if health.get("status") == "healthy" else "red"
st.markdown(f"API status: <span style='color:{color};font-weight:bold'>{health.get('status', 'unknown')}</span>", unsafe_allow_html=True)
