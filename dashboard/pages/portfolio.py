"""Portfolio Management Dashboard Page."""
from __future__ import annotations

import random

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


def render() -> None:
    st.title("💼 Portfolio Management")
    st.markdown("*Multi-symbol allocation with correlation analysis and risk-adjusted sizing*")

    with st.sidebar:
        st.header("⚙️ Portfolio Settings")
        available = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD"]
        selected = st.multiselect("Active Symbols", available,
                                  default=["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])
        capital = st.number_input("Total Capital ($)", 1000, 1_000_000, 50_000, 1000)
        method = st.selectbox("Allocation Method",
                              ["Risk Parity", "Equal Weight", "Kelly Criterion", "Min Variance"])
        st.divider()
        recalc = st.button("🔄 Recalculate", type="primary", use_container_width=True)

    if not selected:
        st.warning("Select at least one symbol.")
        return

    def gen_data(symbols):
        np.random.seed(42)
        n = len(symbols)
        returns = {s: np.random.normal(0.0008, 0.012, 252) for s in symbols}
        ret_df = pd.DataFrame(returns)
        vols = ret_df.std() * np.sqrt(252)
        sharpes = ret_df.mean() / ret_df.std() * np.sqrt(252)
        corr = ret_df.corr()
        if method == "Risk Parity":
            raw = 1.0 / vols
        elif method == "Kelly Criterion":
            raw = sharpes.clip(lower=0)
            if raw.sum() == 0:
                raw = pd.Series([1.0/n]*n, index=symbols)
        elif method == "Min Variance":
            raw = 1.0 / (vols ** 2)
        else:
            raw = pd.Series([1.0]*n, index=symbols)
        weights = raw / raw.sum()
        rows = []
        for s in symbols:
            rows.append({
                "Symbol": s, "Weight": round(float(weights[s]), 4),
                "Allocation ($)": round(float(weights[s]) * capital, 2),
                "Annual Vol": round(float(vols[s]), 4),
                "Sharpe": round(float(sharpes[s]), 3),
                "Win Rate": round(random.uniform(0.52, 0.70), 3),
                "Max DD": round(random.uniform(0.03, 0.15), 3),
                "Open Trades": random.randint(0, 2),
            })
        return pd.DataFrame(rows), corr, ret_df

    if "port_df" not in st.session_state or recalc:
        st.session_state.port_df, st.session_state.corr, st.session_state.ret_df = gen_data(selected)

    port_df = st.session_state.port_df
    corr = st.session_state.corr

    # KPIs
    st.subheader("📊 Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Capital", f"${capital:,.0f}")
    c2.metric("Symbols", len(selected))
    c3.metric("Avg Sharpe", f"{port_df['Sharpe'].mean():.3f}")
    c4.metric("Avg Win Rate", f"{port_df['Win Rate'].mean()*100:.1f}%")

    st.divider()
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("🧩 Allocation")
        fig_pie = px.pie(port_df, values="Weight", names="Symbol",
                         color_discrete_sequence=px.colors.qualitative.Set2)
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(template="plotly_dark", height=340,
                              margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_r:
        st.subheader("🔗 Correlation Heatmap")
        fig_corr = go.Figure(go.Heatmap(
            z=corr.values, x=corr.columns.tolist(), y=corr.index.tolist(),
            colorscale="RdBu", zmin=-1, zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in corr.values],
            texttemplate="%{text}"
        ))
        fig_corr.update_layout(template="plotly_dark", height=340,
                               margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_corr, use_container_width=True)

    st.subheader("📝 Allocation Table")
    st.dataframe(
        port_df.style.background_gradient(subset=["Sharpe", "Weight"], cmap="RdYlGn")
               .format({"Weight": "{:.2%}", "Allocation ($)": "${:,.2f}",
                        "Annual Vol": "{:.2%}", "Sharpe": "{:.3f}",
                        "Win Rate": "{:.1%}", "Max DD": "{:.1%}"}),
        use_container_width=True, height=260
    )
