"""Portfolio Management Dashboard Page"""
from __future__ import annotations

import random
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from plotly.subplots import make_subplots

st.set_page_config(page_title="Portfolio Management", layout="wide")

st.title("💼 Portfolio Management")
st.markdown("*Multi-symbol allocation with correlation analysis and risk-adjusted sizing*")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Portfolio Settings")
    available_symbols = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD"]
    selected_symbols = st.multiselect("Active Symbols", available_symbols,
                                      default=["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])
    capital = st.number_input("Total Capital ($)", min_value=1000, value=50000, step=1000)
    max_risk_per_symbol = st.slider("Max Risk per Symbol (%)", 0.5, 5.0, 1.0, 0.1)
    method = st.selectbox("Allocation Method", ["Risk Parity", "Equal Weight", "Kelly Criterion", "Min Variance"])
    st.divider()
    recalc = st.button("🔄 Recalculate", type="primary", use_container_width=True)

if not selected_symbols:
    st.warning("Select at least one symbol.")
    st.stop()

# ── Generate demo data ─────────────────────────────────────────────────────
def gen_portfolio_data(symbols):
    np.random.seed(42)
    n = len(symbols)
    returns = {s: np.random.normal(0.0008, 0.012, 252) for s in symbols}
    returns_df = pd.DataFrame(returns)
    vols = returns_df.std() * np.sqrt(252)
    sharpes = returns_df.mean() / returns_df.std() * np.sqrt(252)
    corr = returns_df.corr()
    if method == "Risk Parity":
        raw = 1.0 / vols
        weights = (raw / raw.sum()).to_dict()
    elif method == "Kelly Criterion":
        raw = sharpes.clip(lower=0)
        weights = (raw / raw.sum()).to_dict() if raw.sum() > 0 else {s: 1/n for s in symbols}
    elif method == "Min Variance":
        raw = 1.0 / (vols ** 2)
        weights = (raw / raw.sum()).to_dict()
    else:
        weights = {s: 1.0 / n for s in symbols}
    rows = []
    for s in symbols:
        rows.append({
            "Symbol": s,
            "Weight": round(weights[s], 4),
            "Allocation ($)": round(weights[s] * capital, 2),
            "Annual Vol": round(float(vols[s]), 4),
            "Sharpe": round(float(sharpes[s]), 3),
            "Win Rate": round(random.uniform(0.52, 0.70), 3),
            "Profit Factor": round(random.uniform(1.1, 2.2), 3),
            "Max DD": round(random.uniform(0.03, 0.15), 3),
            "Open Trades": random.randint(0, 2),
            "Total Trades": random.randint(20, 150),
        })
    return pd.DataFrame(rows), corr, returns_df

if "port_df" not in st.session_state or recalc:
    st.session_state.port_df, st.session_state.corr, st.session_state.ret_df = gen_portfolio_data(selected_symbols)

port_df = st.session_state.port_df
corr = st.session_state.corr
ret_df = st.session_state.ret_df

# ── KPIs ───────────────────────────────────────────────────────────────────────
st.subheader("📊 Portfolio Summary")
port_sharpe = (port_df["Sharpe"] * port_df["Weight"]).sum()
port_vol = (port_df["Annual Vol"] * port_df["Weight"]).sum()
port_dd = (port_df["Max DD"] * port_df["Weight"]).sum()
total_trades = port_df["Total Trades"].sum()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Portfolio Sharpe", f"{port_sharpe:.3f}")
c2.metric("Portfolio Volatility", f"{port_vol*100:.2f}%")
c3.metric("Avg Max Drawdown", f"{port_dd*100:.2f}%")
c4.metric("Total Trades", f"{total_trades:,}")
c5.metric("Active Symbols", len(selected_symbols))

st.divider()

# ── Charts ─────────────────────────────────────────────────────────────────────
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("🥧 Allocation")
    fig_pie = px.pie(
        port_df, values="Weight", names="Symbol",
        color_discrete_sequence=px.colors.sequential.Plasma,
        hole=0.4,
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    fig_pie.update_layout(template="plotly_dark", height=380,
                          legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig_pie, use_container_width=True)

with col_r:
    st.subheader("🔥 Correlation Heatmap")
    fig_heat = px.imshow(
        corr,
        color_continuous_scale="RdBu_r",
        zmin=-1, zmax=1,
        text_auto=".2f",
        aspect="auto",
    )
    fig_heat.update_layout(template="plotly_dark", height=380)
    st.plotly_chart(fig_heat, use_container_width=True)

# ── Cumulative equity curves per symbol ───────────────────────────────────
st.subheader("📈 Equity Curves")
fig_eq = go.Figure()
colors = px.colors.qualitative.Plotly
for idx, sym in enumerate(selected_symbols):
    cum = (1 + ret_df[sym]).cumprod() * 10000
    fig_eq.add_trace(go.Scatter(
        x=list(range(len(cum))), y=cum.values,
        name=sym, line=dict(color=colors[idx % len(colors)], width=2),
    ))
fig_eq.update_layout(template="plotly_dark", xaxis_title="Day",
                      yaxis_title="Equity ($, starting 10k)", height=350,
                      legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig_eq, use_container_width=True)

# ── Table ──────────────────────────────────────────────────────────────────────
st.subheader("📝 Position Details")
st.dataframe(
    port_df.style.background_gradient(subset=["Sharpe", "Weight"], cmap="YlGn")
                 .format({
                     "Weight": "{:.2%}",
                     "Allocation ($)": "${:,.0f}",
                     "Annual Vol": "{:.2%}",
                     "Sharpe": "{:.3f}",
                     "Win Rate": "{:.1%}",
                     "Profit Factor": "{:.3f}",
                     "Max DD": "{:.2%}",
                 }),
    use_container_width=True,
    height=280,
)
