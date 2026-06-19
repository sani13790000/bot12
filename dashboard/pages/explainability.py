"""AI Explainability — full trade decision breakdown with agent votes."""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd

AGENTS = [
    {"name": "SMC Agent",       "weight": 35, "icon": "🟦"},
    {"name": "PA Agent",        "weight": 20, "icon": "🟡"},
    {"name": "ML Agent",        "weight": 30, "icon": "🧠"},
    {"name": "Risk Agent",      "weight": 10, "icon": "🛡️"},
    {"name": "News Agent",      "weight":  5, "icon": "📰"},
    {"name": "Liquidity Agent", "weight":  0, "icon": "💧"},
    {"name": "Exec Agent",      "weight":  0, "icon": "⚡"},
]

SMC_SIGNALS = {
    "BUY": [
        ("✅", "BOS",             "Break of Structure confirmed — market shifted bullish"),
        ("✅", "Order Block",     "Bullish OB at 2,345.50 (strong, untested)"),
        ("✅", "FVG",             "Imbalance between 2,338.20 – 2,342.10 (discount)"),
        ("✅", "Liquidity Sweep", "BSL swept at 2,330.00 before reversal"),
        ("✅", "Discount Zone",   "Price at 32% of premium/discount range"),
        ("⚠️", "CHoCH",           "No CHoCH yet — watching for confirmation"),
    ],
    "SELL": [
        ("✅", "CHoCH",           "Change of Character detected — bearish flip"),
        ("✅", "Order Block",     "Bearish OB at 2,378.00 (strong, price rejected)"),
        ("✅", "Premium Zone",    "Price at 85% of premium/discount range"),
        ("✅", "Liquidity Sweep", "SSL swept below 2,360.00"),
        ("⚠️", "FVG",             "No FVG confirmation yet"),
        ("❌", "BOS",             "BOS not confirmed on sell side"),
    ],
    "NO_TRADE": [
        ("❌", "BOS",     "No BOS detected"),
        ("❌", "OB",      "No valid Order Block found"),
        ("⚠️", "FVG",    "FVG present but no confluence"),
        ("❌", "Liquidity","No liquidity sweep detected"),
    ],
}


def render():
    st.markdown('<h1 style="color:#FFD700">🧠 AI Decision Explainability</h1>', unsafe_allow_html=True)
    st.caption("Every trade decision fully explained — no black box | BOS | CHoCH | OB | FVG | Liquidity | Premium/Discount")

    c1, c2, c3 = st.columns(3)
    with c1: symbol     = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD"])
    with c2: decision   = st.selectbox("Decision", ["🟢 BUY", "🔴 SELL", "⏸️ NO_TRADE"])
    with c3: confidence = st.slider("AI Confidence (%)", 0, 100, 72)

    decision_key = decision.split()[-1]
    score = 78.5 if decision_key == "BUY" else (74.2 if decision_key == "SELL" else 42.0)

    st.divider()

    # Decision banner
    if decision_key == "BUY":
        st.success(f"## 🟢 DECISION: BUY | Score: {score}/100 | AI Confidence: {confidence}%")
    elif decision_key == "SELL":
        st.error(f"## 🔴 DECISION: SELL | Score: {score}/100 | AI Confidence: {confidence}%")
    else:
        st.warning(f"## ⏸️ DECISION: NO TRADE | Score: {score}/100 | Confidence: {confidence}%")

    st.divider()

    # Agent scores radar chart + detail
    agent_scores = {
        "BUY":      [82, 74, confidence, 100, 50, 78, 100],
        "SELL":     [76, 68, confidence, 100, 45, 80, 100],
        "NO_TRADE": [38, 42, confidence,  90, 55, 35, 100],
    }
    scores = agent_scores[decision_key]

    col_radar, col_detail = st.columns([1, 2])

    with col_radar:
        st.subheader("📊 Agent Scores")
        agent_names = [a["name"] for a in AGENTS]
        fig = go.Figure(go.Scatterpolar(
            r=scores + [scores[0]],
            theta=agent_names + [agent_names[0]],
            fill="toself",
            line_color="#FFD700",
            fillcolor="rgba(255,215,0,0.15)",
            name="Agent Votes"
        ))
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100])),
                          template="plotly_dark", height=350,
                          margin=dict(l=20,r=20,t=30,b=20),
                          paper_bgcolor="#1E2329")
        st.plotly_chart(fig, use_container_width=True)

    with col_detail:
        st.subheader("📝 Agent Vote Table")
        vote_label = "🟢 BUY" if decision_key == "BUY" else ("🔴 SELL" if decision_key == "SELL" else "⏸️ SKIP")
        rows = []
        for agent, score_v in zip(AGENTS, scores):
            rows.append({
                "Agent":  f"{agent['icon']} {agent['name']}",
                "Vote":   vote_label,
                "Score":  score_v,
                "Weight": f"{agent['weight']}%" if agent['weight'] > 0 else "Gate",
                "Status": "✅" if score_v >= 60 else "⚠️"
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()
    # SMC Breakdown
    col_smc, col_ml = st.columns(2)
    with col_smc:
        st.subheader("🟦 SMC Analysis")
        smc_signals = SMC_SIGNALS.get(decision_key, SMC_SIGNALS["NO_TRADE"])
        for icon, signal, desc in smc_signals:
            st.markdown(f"{icon} **{signal}** — {desc}")

    with col_ml:
        st.subheader("🧠 ML Engine")
        st.metric("Prediction", decision_key, delta=f"{confidence}% confidence")
        st.markdown("**Top Features (SHAP):")
        features = [
            ("atr_14",       0.234),
            ("rsi_14",       0.181),
            ("ema_crossover",0.152),
            ("volume_delta", 0.118),
            ("vwap_distance",0.097),
        ]
        fig2 = go.Figure(go.Bar(
            x=[f[1] for f in features],
            y=[f[0] for f in features],
            orientation="h",
            marker_color="#FFD700"
        ))
        fig2.update_layout(template="plotly_dark", height=220,
                           margin=dict(l=0,r=0,t=10,b=0),
                           paper_bgcolor="#1E2329", plot_bgcolor="#1E2329",
                           xaxis_title="SHAP Value")
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("✅ Risk Check")
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Daily P&L",       "$320 / $3,000 limit")
    r2.metric("Open Trades",      "1 / 5")
    r3.metric("Volatility",       "NORMAL")
    r4.metric("Circuit Breaker",  "OFF")
    r5.metric("Session",          "London Active")

    st.divider()
    if decision_key == "BUY":
        st.info("🟢 Summary: Order Block at 2,345.50 + Bullish Engulfing + ML 72% confident + Discount Zone 32% + BSL Swept")
    elif decision_key == "SELL":
        st.info("🔴 Summary: CHoCH detected + Premium Zone 85% + Bearish OB rejected + SSL swept + ML 68% confident")
    else:
        st.warning("⏸️ Summary: No valid Order Block | ML confidence below 50% threshold | No BOS confirmation")
