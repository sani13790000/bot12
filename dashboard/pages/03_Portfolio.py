"""Portfolio management page."""
import pandas as pd
import streamlit as st

from api_client import APIClient

st.set_page_config(page_title="Portfolio", layout="wide")
st.title("💼 Portfolio Manager")

client = APIClient()

strategy = st.selectbox("Allocation Strategy", ["EQUAL_WEIGHT", "RISK_PARITY", "MINIMUM_VARIANCE", "KELLY_CRITERION"])
total_capital = st.number_input("Total Capital", value=100_000.0, step=10_000.0)
max_risk = st.slider("Max Risk %", 1.0, 20.0, 5.0)

signals = [
    {"symbol": "XAUUSD", "direction": "BUY", "entry_price": 2350.0, "stop_loss": 2340.0, "take_profit": 2370.0, "confidence": 78, "win_rate": 0.55, "avg_win": 120, "avg_loss": 60},
    {"symbol": "EURUSD", "direction": "SELL", "entry_price": 1.0850, "stop_loss": 1.0900, "take_profit": 1.0750, "confidence": 65, "win_rate": 0.52, "avg_win": 80, "avg_loss": 50},
    {"symbol": "GBPUSD", "direction": "BUY", "entry_price": 1.2650, "stop_loss": 1.2600, "take_profit": 1.2750, "confidence": 72, "win_rate": 0.50, "avg_win": 90, "avg_loss": 55},
]

if st.button("⚖️ Build Portfolio"):
    payload = {
        "strategy": strategy,
        "total_capital": total_capital,
        "max_risk_pct": max_risk,
        "signals": signals,
    }
    result = client.portfolio(payload)
    if "error" in result:
        st.error(result["error"])
    else:
        st.metric("Cash", round(result.get("cash", 0), 2))
        st.metric("Total Value", round(result.get("total_value", 0), 2))
        positions = result.get("positions", [])
        if positions:
            st.dataframe(pd.DataFrame(positions))
        st.json(result.get("allocation", {}))
