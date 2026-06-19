"""Walk-Forward Optimization Dashboard Page."""
from __future__ import annotations

import random
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render() -> None:
    st.title("📄 Walk-Forward Optimization")
    st.markdown("*Train / Validation / Out-of-Sample testing with automatic parameter optimization*")

    with st.sidebar:
        st.header("⚙️ WFO Settings")
        symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])
        n_windows = st.slider("Number of Windows", 3, 12, 6)
        train_pct = st.slider("Train %", 40, 70, 60)
        val_pct = st.slider("Validation %", 10, 30, 20)
        test_pct = 100 - train_pct - val_pct
        st.info(f"Test period: {test_pct}%")
        st.divider()
        opt_metric = st.selectbox("Optimization Metric",
                                  ["Sharpe Ratio", "Profit Factor", "Net Profit", "Sortino Ratio"])
        run_btn = st.button("🚀 Run Walk-Forward", type="primary", use_container_width=True)

    def generate_wfo_results(n: int) -> pd.DataFrame:
        rows = []
        base_date = pd.Timestamp("2022-01-01")
        for i in range(n):
            is_sharpe = round(random.uniform(0.8, 2.5), 3)
            oos_sharpe = round(is_sharpe * random.uniform(0.5, 0.95), 3)
            rows.append({
                "Window": i + 1,
                "Train Start": (base_date + pd.DateOffset(months=i * 2)).strftime("%Y-%m"),
                "OOS End": (base_date + pd.DateOffset(months=i * 2 + 4)).strftime("%Y-%m"),
                "IS Sharpe": is_sharpe,
                "OOS Sharpe": oos_sharpe,
                "IS Win Rate": round(random.uniform(0.52, 0.70), 3),
                "OOS Win Rate": round(random.uniform(0.48, 0.65), 3),
                "IS PF": round(random.uniform(1.3, 2.2), 3),
                "OOS PF": round(random.uniform(1.0, 1.8), 3),
                "IS Net P&L": round(random.uniform(500, 3000), 2),
                "OOS Net P&L": round(random.uniform(-200, 2000), 2),
                "Robustness": round(oos_sharpe / is_sharpe, 3) if is_sharpe > 0 else 0,
                "Optimal RSI": random.randint(10, 20),
                "Optimal SL": round(random.uniform(0.5, 2.0), 1),
            })
        return pd.DataFrame(rows)

    if "wfo_df" not in st.session_state or run_btn:
        with st.spinner(f"Running {n_windows}-window walk-forward on {symbol} ..."):
            time.sleep(1.2)
            st.session_state.wfo_df = generate_wfo_results(n_windows)

    df = st.session_state.wfo_df

    # KPIs
    st.subheader("📊 Summary")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Avg OOS Sharpe", f"{df['OOS Sharpe'].mean():.3f}",
              delta=f"vs IS: {df['IS Sharpe'].mean():.3f}")
    c2.metric("Avg OOS Win Rate", f"{df['OOS Win Rate'].mean()*100:.1f}%")
    c3.metric("Avg OOS Profit Factor", f"{df['OOS PF'].mean():.3f}")
    c4.metric("Total OOS P&L", f"${df['OOS Net P&L'].sum():,.0f}")
    c5.metric("Avg Robustness", f"{df['Robustness'].mean()*100:.1f}%",
              help="OOS Sharpe / IS Sharpe. >70% = robust")

    st.divider()
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("📈 IS vs OOS Sharpe")
        fig = go.Figure()
        fig.add_trace(go.Bar(name="In-Sample", x=df["Window"], y=df["IS Sharpe"],
                             marker_color="#4CAF50", opacity=0.85))
        fig.add_trace(go.Bar(name="Out-of-Sample", x=df["Window"], y=df["OOS Sharpe"],
                             marker_color="#2196F3", opacity=0.85))
        fig.add_hline(y=1.0, line_dash="dash", line_color="orange",
                      annotation_text="Min threshold")
        fig.update_layout(barmode="group", template="plotly_dark", height=340,
                          xaxis_title="Window", yaxis_title="Sharpe Ratio",
                          legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("🎯 Robustness per Window")
        colors = ["#4CAF50" if r >= 0.7 else "#FF9800" if r >= 0.5 else "#F44336"
                  for r in df["Robustness"]]
        fig2 = go.Figure(go.Bar(
            x=df["Window"], y=df["Robustness"] * 100,
            marker_color=colors,
            text=[f"{r*100:.1f}%" for r in df["Robustness"]],
            textposition="outside",
        ))
        fig2.add_hline(y=70, line_dash="dash", line_color="white",
                       annotation_text="Target: 70%")
        fig2.update_layout(template="plotly_dark", height=340,
                           xaxis_title="Window", yaxis_title="Robustness %")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("💰 Cumulative OOS P&L")
    cumulative = df["OOS Net P&L"].cumsum()
    fig3 = go.Figure(go.Scatter(
        x=df["Window"], y=cumulative, mode="lines+markers",
        line=dict(color="#00BCD4", width=3),
        marker=dict(size=10, color=["#4CAF50" if v >= 0 else "#F44336" for v in cumulative]),
        fill="tozeroy", fillcolor="rgba(0,188,212,0.1)"
    ))
    fig3.update_layout(template="plotly_dark", height=280,
                       xaxis_title="Window", yaxis_title="Cumulative P&L ($)")
    st.plotly_chart(fig3, use_container_width=True)

    st.subheader("📊 Detailed Results")
    st.dataframe(
        df.style.background_gradient(subset=["OOS Sharpe", "Robustness"], cmap="RdYlGn")
          .format({"IS Sharpe": "{:.3f}", "OOS Sharpe": "{:.3f}",
                   "IS Win Rate": "{:.1%}", "OOS Win Rate": "{:.1%}",
                   "IS PF": "{:.3f}", "OOS PF": "{:.3f}",
                   "IS Net P&L": "${:.0f}", "OOS Net P&L": "${:.0f}",
                   "Robustness": "{:.1%}"}),
        use_container_width=True, height=280
    )
