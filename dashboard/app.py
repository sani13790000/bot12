"""Galaxy Vast Institutional Dashboard — Streamlit v2.0."""
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
    .stMetric [data-testid="metric-container"] > div:nth-child(2) { font-size: 1.4rem !important; }
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
        "📊 Market Replay",
        "📈 Backtest",
        "📉 Walk-Forward",
        "💼 Portfolio",
        "🧠 AI Explainability",
        "🎲 Monte Carlo",
    ],
    label_visibility="collapsed"
)

st.sidebar.divider()
st.sidebar.markdown('<span class="status-live">● LIVE</span> Connected to API', unsafe_allow_html=True)
st.sidebar.caption("API: http://localhost:8000")

if page == "📊 Market Replay":
    from dashboard.pages import replay; replay.render()
elif page == "📈 Backtest":
    from dashboard.pages import backtest; backtest.render()
elif page == "📉 Walk-Forward":
    from dashboard.pages import walk_forward; walk_forward.render()
elif page == "💼 Portfolio":
    from dashboard.pages import portfolio; portfolio.render()
elif page == "🧠 AI Explainability":
    from dashboard.pages import explainability; explainability.render()
elif page == "🎲 Monte Carlo":
    from dashboard.pages import monte_carlo; monte_carlo.render()
