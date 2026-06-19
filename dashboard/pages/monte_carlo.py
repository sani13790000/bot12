"""Monte Carlo Simulation Dashboard Page"""
from __future__ import annotations

import random
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

st.set_page_config(page_title="Monte Carlo Simulation", layout="wide")

st.title("🎲 Monte Carlo Simulation")
st.markdown("*1000+ path simulation of future equity curves with probability of ruin analysis*")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Simulation Settings")
    n_paths = st.slider("Number of Paths", 100, 2000, 1000, 100)
    n_trades = st.slider("Trades per Path", 50, 500, 200, 50)
    initial_capital = st.number_input("Initial Capital ($)", 1000, 1000000, 10000, 1000)
    win_rate = st.slider("Win Rate (%)", 30, 80, 58, 1) / 100
    avg_win = st.number_input("Average Win ($)", 10, 10000, 150, 10)
    avg_loss = st.number_input("Average Loss ($)", 10, 10000, 80, 10)
    ruin_threshold = st.slider("Ruin Threshold (%)", 10, 90, 50, 5) / 100
    run_btn = st.button("🚀 Run Simulation", type="primary", use_container_width=True)

# ── Simulation engine ─────────────────────────────────────────────────────────
def run_monte_carlo(n_paths, n_trades, capital, win_rate, avg_win, avg_loss, ruin_level):
    np.random.seed(None)
    ruin_capital = capital * (1 - ruin_level)
    all_paths = np.zeros((n_paths, n_trades + 1))
    all_paths[:, 0] = capital
    wins = np.random.binomial(1, win_rate, size=(n_paths, n_trades))
    pnl = np.where(wins == 1,
                   np.random.normal(avg_win, avg_win * 0.3, size=(n_paths, n_trades)),
                   -np.random.normal(avg_loss, avg_loss * 0.2, size=(n_paths, n_trades)))
    for t in range(n_trades):
        all_paths[:, t + 1] = np.maximum(all_paths[:, t] + pnl[:, t], 0)
    final = all_paths[:, -1]
    ruined = (final < ruin_capital).sum()
    return all_paths, final, ruined

if "mc_results" not in st.session_state or run_btn:
    with st.spinner(f"Running {n_paths:,} Monte Carlo paths ..."):
        paths, final_equity, n_ruined = run_monte_carlo(
            n_paths, n_trades, initial_capital, win_rate,
            avg_win, avg_loss, ruin_threshold
        )
        st.session_state.mc_results = (paths, final_equity, n_ruined)

paths, final_equity, n_ruined = st.session_state.mc_results

# ── KPIs ───────────────────────────────────────────────────────────────────────
prob_ruin = n_ruined / len(final_equity)
median_final = np.median(final_equity)
p5 = np.percentile(final_equity, 5)
p95 = np.percentile(final_equity, 95)
expected_rr = (win_rate * avg_win - (1 - win_rate) * avg_loss)

st.subheader("📊 Simulation Summary")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Probability of Ruin", f"{prob_ruin*100:.1f}%",
          delta=f"{ruin_threshold*100:.0f}% threshold",
          delta_color="inverse")
c2.metric("Median Final Equity", f"${median_final:,.0f}",
          delta=f"{(median_final/initial_capital-1)*100:.1f}%")
c3.metric("5th Percentile", f"${p5:,.0f}")
c4.metric("95th Percentile", f"${p95:,.0f}")
c5.metric("Expected Value/Trade", f"${expected_rr:.2f}")

st.divider()

# ── Paths chart ───────────────────────────────────────────────────────────────────
st.subheader("🌊 Equity Path Fan (sample 200 paths)")
fig_paths = go.Figure()
sample_idx = np.random.choice(len(paths), min(200, len(paths)), replace=False)
for i in sample_idx:
    final_val = paths[i, -1]
    color = f"rgba(76,175,80,0.12)" if final_val >= initial_capital else "rgba(244,67,54,0.12)"
    fig_paths.add_trace(go.Scatter(
        y=paths[i], mode="lines",
        line=dict(color=color, width=1),
        showlegend=False, hoverinfo="skip",
    ))
# Percentile bands
fig_paths.add_trace(go.Scatter(y=np.percentile(paths, 95, axis=0),
                                line=dict(color="#4CAF50", width=2, dash="dash"),
                                name="95th Percentile"))
fig_paths.add_trace(go.Scatter(y=np.percentile(paths, 50, axis=0),
                                line=dict(color="#2196F3", width=3),
                                name="Median"))
fig_paths.add_trace(go.Scatter(y=np.percentile(paths, 5, axis=0),
                                line=dict(color="#F44336", width=2, dash="dash"),
                                name="5th Percentile"))
fig_paths.add_hline(y=initial_capital * (1 - ruin_threshold),
                    line_color="orange", line_dash="dot",
                    annotation_text=f"Ruin Level ({ruin_threshold*100:.0f}%)")
fig_paths.update_layout(template="plotly_dark", xaxis_title="Trade Number",
                         yaxis_title="Equity ($)", height=420,
                         legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig_paths, use_container_width=True)

# ── Final equity distribution ─────────────────────────────────────────────────
st.subheader("📊 Final Equity Distribution")
fig_hist = go.Figure()
fig_hist.add_trace(go.Histogram(
    x=final_equity, nbinsx=60,
    marker_color=["#4CAF50" if v >= initial_capital else "#F44336" for v in final_equity[:1]],
    marker_color="#2196F3",
    name="Final Equity",
))
fig_hist.add_vline(x=initial_capital, line_color="white", line_dash="dash",
                   annotation_text="Initial Capital")
fig_hist.add_vline(x=initial_capital * (1 - ruin_threshold), line_color="orange",
                   line_dash="dot", annotation_text="Ruin Level")
fig_hist.add_vline(x=median_final, line_color="#4CAF50",
                   annotation_text=f"Median: ${median_final:,.0f}")
fig_hist.update_layout(template="plotly_dark", xaxis_title="Final Equity ($)",
                        yaxis_title="Frequency", height=320)
st.plotly_chart(fig_hist, use_container_width=True)

# ── Risk table ───────────────────────────────────────────────────────────────────
st.subheader("🛡️ Risk Percentile Table")
percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
risk_data = [{
    "Percentile": f"P{p}",
    "Final Equity": f"${np.percentile(final_equity, p):,.0f}",
    "Return": f"{(np.percentile(final_equity, p)/initial_capital-1)*100:.1f}%",
    "Outcome": "✅ Profit" if np.percentile(final_equity, p) > initial_capital else "❌ Loss",
} for p in percentiles]
st.dataframe(pd.DataFrame(risk_data), use_container_width=True, hide_index=True)
