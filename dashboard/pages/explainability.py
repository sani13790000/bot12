"""AI Explainability Dashboard Page."""
from __future__ import annotations

import random

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render() -> None:
    st.title("🧠 AI Trade Explainability")
    st.markdown("*Every trade decision explained: SMC signals, agent votes, ML features, SHAP values*")

    with st.sidebar:
        st.header("⚙️ Settings")
        symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])
        direction = st.radio("Signal Direction", ["BUY", "SELL"])
        st.divider()
        regenerate = st.button("🔄 New Signal", type="primary", use_container_width=True)

    def gen_explanation(sym, dirn):
        smc_signals = [
            {"Signal": "BOS (Break of Structure)", "Detected": random.choice([True, True, False]),
             "Weight": 0.30, "Detail": f"Bullish BOS at {random.uniform(2310, 2330):.2f}"},
            {"Signal": "CHoCH (Change of Character)", "Detected": random.choice([True, False]),
             "Weight": 0.25, "Detail": "Lower high broken — structure shift confirmed"},
            {"Signal": "Order Block", "Detected": random.choice([True, True, False]),
             "Weight": 0.15, "Detail": f"Bullish OB zone at {random.uniform(2310, 2330):.2f}"},
            {"Signal": "Fair Value Gap (FVG)", "Detected": random.choice([True, True, False]),
             "Weight": 0.15, "Detail": f"3-candle imbalance at {random.uniform(2320, 2340):.2f}"},
            {"Signal": "Liquidity Sweep", "Detected": random.choice([True, False]),
             "Weight": 0.10, "Detail": "Equal lows swept at session open"},
            {"Signal": "Premium/Discount Zone", "Detected": random.choice([True, True, False]),
             "Weight": 0.05, "Detail": "Price in 38.2% discount of daily range"},
        ]
        agents = [
            {"Agent": "SMC Agent", "Vote": dirn, "Confidence": round(random.uniform(0.60, 0.95), 3), "Weight": 0.25},
            {"Agent": "Price Action", "Vote": dirn if random.random() > 0.2 else "NO_TRADE",
             "Confidence": round(random.uniform(0.55, 0.90), 3), "Weight": 0.20},
            {"Agent": "ML Agent", "Vote": dirn if random.random() > 0.25 else "NO_TRADE",
             "Confidence": round(random.uniform(0.50, 0.88), 3), "Weight": 0.25},
            {"Agent": "Risk Agent", "Vote": "APPROVE" if random.random() > 0.1 else "REJECT",
             "Confidence": round(random.uniform(0.75, 0.99), 3), "Weight": 0.15},
            {"Agent": "News Agent", "Vote": "NEUTRAL" if random.random() > 0.2 else "CAUTION",
             "Confidence": round(random.uniform(0.60, 0.90), 3), "Weight": 0.10},
            {"Agent": "Liquidity Agent", "Vote": dirn if random.random() > 0.3 else "NO_TRADE",
             "Confidence": round(random.uniform(0.55, 0.88), 3), "Weight": 0.05},
        ]
        features = [("RSI (14)", round(random.uniform(30, 70), 1)),
                    ("ATR (14)", round(random.uniform(5, 25), 2)),
                    ("EMA 20", round(random.uniform(2300, 2400), 2)),
                    ("EMA 50", round(random.uniform(2280, 2380), 2)),
                    ("MACD", round(random.uniform(-5, 5), 3)),
                    ("BB Width", round(random.uniform(0.5, 3.0), 3)),
                    ("Volume Delta", round(random.uniform(-1000, 1000), 0))]
        score = round(random.uniform(65, 92), 1)
        confidence = round(random.uniform(0.60, 0.95), 3)
        return smc_signals, agents, features, score, confidence

    if "explanation" not in st.session_state or regenerate:
        st.session_state.explanation = gen_explanation(symbol, direction)

    smc_signals, agents, features, score, confidence = st.session_state.explanation

    # Header
    dir_emoji = "🟢" if direction == "BUY" else "🔴"
    st.info(f"{dir_emoji} **{direction}** on **{symbol}** | AI Score: **{score}/100** | Confidence: **{confidence*100:.1f}%**")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AI Score", f"{score}/100")
    c2.metric("Confidence", f"{confidence*100:.1f}%")
    c3.metric("SMC Signals Active", sum(1 for s in smc_signals if s["Detected"]))
    c4.metric("Agent Consensus", f"{sum(1 for a in agents if direction in a['Vote'])}/{len(agents)}")

    st.divider()
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("📌 SMC Signal Breakdown")
        smc_df = pd.DataFrame(smc_signals)
        fig_smc = go.Figure(go.Bar(
            x=smc_df["Weight"] * 100, y=smc_df["Signal"], orientation="h",
            marker_color=["#4CAF50" if d else "#607D8B" for d in smc_df["Detected"]],
            text=["ACTIVE" if d else "NOT DETECTED" for d in smc_df["Detected"]],
            textposition="outside",
        ))
        fig_smc.update_layout(template="plotly_dark", xaxis_title="Weight %",
                              height=360, margin=dict(l=10, r=80, t=10, b=10))
        st.plotly_chart(fig_smc, use_container_width=True)

    with col_r:
        st.subheader("🤖 Agent Votes")
        agents_df = pd.DataFrame(agents)
        colors = ["#4CAF50" if direction in v else "#F44336" if v == "REJECT" else "#FF9800"
                  for v in agents_df["Vote"]]
        fig_agents = go.Figure(go.Bar(
            x=agents_df["Agent"], y=agents_df["Confidence"] * 100,
            marker_color=colors,
            text=[f"{v} ({c*100:.0f}%)" for v, c in zip(agents_df["Vote"], agents_df["Confidence"])],
            textposition="outside",
        ))
        fig_agents.update_layout(template="plotly_dark", yaxis_title="Confidence %",
                                 height=360, xaxis_tickangle=-15)
        st.plotly_chart(fig_agents, use_container_width=True)

    # SHAP
    st.subheader("📊 ML Feature Importance (SHAP-style)")
    names = [f[0] for f in features]
    shap_vals = [round(random.uniform(-0.08, 0.12), 4) for _ in features]
    fig_shap = go.Figure(go.Bar(
        x=shap_vals, y=names, orientation="h",
        marker_color=["#4CAF50" if v > 0 else "#F44336" for v in shap_vals],
    ))
    fig_shap.add_vline(x=0, line_color="white", line_width=1)
    fig_shap.update_layout(template="plotly_dark",
                           xaxis_title="SHAP Value (impact on model output)",
                           height=300, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_shap, use_container_width=True)

    # Details
    st.subheader("📝 Signal Details")
    for sig in smc_signals:
        icon = "✅" if sig["Detected"] else "❌"
        with st.expander(f"{icon} {sig['Signal']} — Weight: {sig['Weight']*100:.0f}%"):
            st.write(sig["Detail"])
