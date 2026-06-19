"""AI Decision Explainability Dashboard Page"""
from __future__ import annotations

import random
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

st.set_page_config(page_title="AI Explainability", layout="wide")

st.title("🧠 AI Decision Explainability")
st.markdown("*Why did the AI make this trade? Full breakdown of every signal component.*")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Trade Selector")
    symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])
    direction = st.radio("Direction", ["BUY", "SELL"])
    trade_date = st.date_input("Trade Date")
    regenerate = st.button("🔄 Generate New Explanation", type="primary", use_container_width=True)
    st.divider()
    st.caption("💡 SMC = Smart Money Concepts")
    st.caption("💡 BOS = Break of Structure")
    st.caption("💡 CHoCH = Change of Character")
    st.caption("💡 OB = Order Block")
    st.caption("💡 FVG = Fair Value Gap / Imbalance")
    st.caption("💡 PD = Premium/Discount Zone")

# ── Generate demo explanation ─────────────────────────────────────────────
def gen_explanation(symbol, direction):
    smc_signals = [
        {"Signal": "BOS (Break of Structure)", "Detected": random.choice([True, True, False]),
         "Weight": 0.20, "Detail": f"Price broke above H4 structure at {random.uniform(2300, 2400):.2f}"},
        {"Signal": "CHoCH (Change of Character)", "Detected": random.choice([True, False]),
         "Weight": 0.15, "Detail": "Higher high + higher low confirmed on M15"},
        {"Signal": "Order Block", "Detected": random.choice([True, True, True, False]),
         "Weight": 0.20, "Detail": f"Bullish OB at {random.uniform(2280, 2310):.2f}–{random.uniform(2310, 2330):.2f}"},
        {"Signal": "Fair Value Gap (FVG)", "Detected": random.choice([True, True, False]),
         "Weight": 0.15, "Detail": f"3-candle imbalance at {random.uniform(2320, 2340):.2f}"},
        {"Signal": "Liquidity Sweep", "Detected": random.choice([True, False]),
         "Weight": 0.10, "Detail": "Equal lows swept at session open"},
        {"Signal": "Premium/Discount Zone", "Detected": random.choice([True, True, False]),
         "Weight": 0.10, "Detail": "Price in 38.2% discount of daily range"},
        {"Signal": "Session Alignment", "Detected": random.choice([True, True, False]),
         "Weight": 0.05, "Detail": "London/NY overlap — highest volume window"},
        {"Signal": "News Neutrality", "Detected": random.choice([True, True, True, False]),
         "Weight": 0.05, "Detail": "No high-impact news within 30 min"},
    ]
    agents = [
        {"Agent": "SMC Agent", "Vote": direction, "Confidence": round(random.uniform(0.60, 0.95), 3), "Weight": 0.25},
        {"Agent": "Price Action Agent", "Vote": direction if random.random() > 0.2 else "NO_TRADE", "Confidence": round(random.uniform(0.55, 0.90), 3), "Weight": 0.20},
        {"Agent": "ML Agent", "Vote": direction if random.random() > 0.25 else "NO_TRADE", "Confidence": round(random.uniform(0.50, 0.88), 3), "Weight": 0.25},
        {"Agent": "Risk Agent", "Vote": "APPROVE" if random.random() > 0.1 else "REJECT", "Confidence": round(random.uniform(0.75, 0.99), 3), "Weight": 0.15},
        {"Agent": "News Agent", "Vote": "NEUTRAL" if random.random() > 0.2 else "CAUTION", "Confidence": round(random.uniform(0.60, 0.90), 3), "Weight": 0.10},
        {"Agent": "Liquidity Agent", "Vote": direction if random.random() > 0.3 else "NO_TRADE", "Confidence": round(random.uniform(0.55, 0.88), 3), "Weight": 0.05},
    ]
    features = [
        ("RSI (14)", round(random.uniform(30, 70), 1)),
        ("ATR (14)", round(random.uniform(5, 25), 2)),
        ("EMA 20", round(random.uniform(2300, 2400), 2)),
        ("EMA 50", round(random.uniform(2280, 2380), 2)),
        ("MACD", round(random.uniform(-5, 5), 3)),
        ("BB Width", round(random.uniform(0.5, 3.0), 3)),
        ("Volume Delta", round(random.uniform(-1000, 1000), 0)),
        ("Spread (pts)", round(random.uniform(1, 8), 1)),
    ]
    score = round(random.uniform(65, 92), 1)
    confidence = round(random.uniform(0.60, 0.95), 3)
    return smc_signals, agents, features, score, confidence

if "explanation" not in st.session_state or regenerate:
    st.session_state.explanation = gen_explanation(symbol, direction)

smc_signals, agents, features, score, confidence = st.session_state.explanation

# ── Header cards ─────────────────────────────────────────────────────────────
dir_emoji = "🟢" if direction == "BUY" else "🔴"
st.info(f"{dir_emoji} **{direction}** signal on **{symbol}** | AI Score: **{score}/100** | Confidence: **{confidence*100:.1f}%**")

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
        x=smc_df["Weight"] * 100,
        y=smc_df["Signal"],
        orientation="h",
        marker_color=["#4CAF50" if d else "#607D8B" for d in smc_df["Detected"]],
        text=["ACTIVE" if d else "NOT DETECTED" for d in smc_df["Detected"]],
        textposition="outside",
    ))
    fig_smc.update_layout(template="plotly_dark", xaxis_title="Weight %",
                          height=380, margin=dict(l=10, r=80, t=10, b=10))
    st.plotly_chart(fig_smc, use_container_width=True)

with col_r:
    st.subheader("🤖 Agent Votes")
    agents_df = pd.DataFrame(agents)
    fig_agents = go.Figure()
    colors_votes = ["#4CAF50" if direction in v else "#F44336" if v == "REJECT" else "#FF9800"
                    for v in agents_df["Vote"]]
    fig_agents.add_trace(go.Bar(
        x=agents_df["Agent"], y=agents_df["Confidence"] * 100,
        marker_color=colors_votes,
        text=[f"{v} ({c*100:.0f}%)" for v, c in zip(agents_df["Vote"], agents_df["Confidence"])],
        textposition="outside",
    ))
    fig_agents.update_layout(template="plotly_dark", yaxis_title="Confidence %",
                             height=380, xaxis_tickangle=-15)
    st.plotly_chart(fig_agents, use_container_width=True)

# ── Feature importance (SHAP-like) ──────────────────────────────────────────
st.subheader("📊 ML Feature Importance (SHAP-style)")
feature_names = [f[0] for f in features]
shap_values = [round(random.uniform(-0.08, 0.12), 4) for _ in features]
fig_shap = go.Figure(go.Bar(
    x=shap_values,
    y=feature_names,
    orientation="h",
    marker_color=["#4CAF50" if v > 0 else "#F44336" for v in shap_values],
))
fig_shap.add_vline(x=0, line_color="white", line_width=1)
fig_shap.update_layout(
    template="plotly_dark", xaxis_title="SHAP Value (impact on model output)",
    height=320, margin=dict(l=10, r=10, t=10, b=10)
)
st.plotly_chart(fig_shap, use_container_width=True)

# ── SMC signal details table ───────────────────────────────────────────────────
st.subheader("📝 Signal Details")
for sig in smc_signals:
    icon = "✅" if sig["Detected"] else "⚪"
    with st.expander(f"{icon} {sig['Signal']} — Weight: {sig['Weight']*100:.0f}%"):
        st.write(sig["Detail"])
