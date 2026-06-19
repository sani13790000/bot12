"""Galaxy Vast Institutional Dashboard — Streamlit (6 pages)."""

import streamlit as st

st.set_page_config(
    page_title="Galaxy Vast Institutional",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("🌌 Galaxy Vast")
st.sidebar.markdown("**Institutional Trading Platform**")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    [
        "🎥 Market Replay",
        "📈 Backtest",
        "🔍 Walk-Forward",
        "💼 Portfolio",
        "🧠 AI Explainability",
        "🎲 Monte Carlo",
    ],
)

if page == "🎥 Market Replay":
    from dashboard.pages import replay
    replay.render()
elif page == "📈 Backtest":
    from dashboard.pages import backtest
    backtest.render()
elif page == "🔍 Walk-Forward":
    from dashboard.pages import walk_forward
    walk_forward.render()
elif page == "💼 Portfolio":
    from dashboard.pages import portfolio
    portfolio.render()
elif page == "🧠 AI Explainability":
    from dashboard.pages import explainability
    explainability.render()
elif page == "🎲 Monte Carlo":
    from dashboard.pages import monte_carlo
    monte_carlo.render()
