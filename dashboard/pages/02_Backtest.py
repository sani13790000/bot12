"""Backtest page."""
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import APIClient

st.set_page_config(page_title="Backtest", layout="wide")
st.title("📊 Tick-Level Backtest")

client = APIClient()

with st.sidebar:
    st.header("Parameters")
    symbols = st.multiselect("Symbols", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"], default=["XAUUSD"])
    timeframe = st.selectbox("Timeframe", ["M1", "M5", "M15", "H1", "H4", "D1"], index=2)
    initial_balance = st.number_input("Initial Balance", value=100_000.0, step=10_000.0)
    risk_per_trade = st.slider("Risk per trade %", 0.1, 5.0, 1.0)
    slippage = st.slider("Slippage (pips)", 0.0, 2.0, 0.3)
    commission = st.slider("Commission per lot", 0.0, 10.0, 3.5)

# Generate synthetic candle data for demo
def make_candles(symbol="XAUUSD", n=300):
    np.random.seed(hash(symbol) % 2**31)
    now = pd.Timestamp.utcnow() - pd.Timedelta(days=n)
    price = 2350.0 if "XAU" in symbol else 1.08
    candles = []
    for i in range(n):
        o = price
        h = price * (1 + abs(np.random.normal(0, 0.003)))
        l = price * (1 - abs(np.random.normal(0, 0.003)))
        c = l + (h - l) * np.random.random()
        candles.append({"timestamp": (now + pd.Timedelta(hours=i)).isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": 100})
        price = c
    return candles

if st.button("🚀 Run Backtest"):
    payload = {
        "symbols": symbols,
        "timeframe": timeframe,
        "initial_balance": initial_balance,
        "risk_per_trade_pct": risk_per_trade,
        "slippage_pips": slippage,
        "commission_per_lot": commission,
        "candles_by_symbol": {sym: make_candles(sym) for sym in symbols},
    }
    with st.spinner("Running tick-level backtest..."):
        result = client.run_backtest(payload)

    if "error" in result:
        st.error(result["error"])
    else:
        metrics = result.get("metrics", {})
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Return %", metrics.get("total_return_pct", 0))
        col2.metric("Win Rate %", metrics.get("win_rate", 0))
        col3.metric("Profit Factor", metrics.get("profit_factor", 0))
        col4.metric("Sharpe", metrics.get("sharpe_ratio", 0))
        col5.metric("Max DD %", metrics.get("max_drawdown_pct", 0))

        equity = result.get("equity_curve", [])
        if equity:
            eq_df = pd.DataFrame(equity, columns=["timestamp", "equity"])
            fig = go.Figure(go.Scatter(x=eq_df["timestamp"], y=eq_df["equity"], mode="lines", name="Equity"))
            fig.update_layout(title="Equity Curve", height=400)
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Performance Metrics")
        st.json(metrics)

        st.subheader("Trade History")
        trades = result.get("trades", [])
        if trades:
            st.dataframe(pd.DataFrame(trades).head(50))
