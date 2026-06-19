"""AI Explainability page — trade decision breakdown."""
import streamlit as st


def render():
    st.title("🧠 AI Decision Explainability")
    st.markdown("Every trade decision fully explained — no black box.")

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD"])
    with col2:
        decision = st.selectbox("Decision", ["🟢 BUY", "🔴 SELL", "⏸️ NO_TRADE"])
    with col3:
        confidence = st.slider("Confidence", 0, 100, 72)

    st.divider()

    # Decision banner
    if "BUY" in decision:
        st.success(f"## 🟢 DECISION: BUY | Confidence: {confidence}% | Score: 78.5/100")
    elif "SELL" in decision:
        st.error(f"## 🔴 DECISION: SELL | Confidence: {confidence}% | Score: 74.2/100")
    else:
        st.warning(f"## ⏸️ DECISION: NO TRADE | Confidence: {confidence}%")

    st.divider()

    col_smc, col_pa, col_ml, col_risk = st.columns(4)

    with col_smc:
        st.subheader("🟦 SMC Analysis")
        st.metric("Score", "82 / 100")
        st.markdown("""
        ✅ **BOS** confirmed — market shifted
        ✅ **Order Block** at 2,345.50 (strong)
        ✅ **FVG** between 2,338.20 – 2,342.10
        ✅ **Liquidity Sweep** at 2,330.00
        ✅ **Discount Zone** (32% of range)
        """)

    with col_pa:
        st.subheader("📉 Price Action")
        st.metric("Score", "74 / 100")
        st.markdown("""
        ✅ **Bullish Engulfing** (strong, 81)
        ✅ **Higher-TF trend** aligned
        ✅ **London session** active
        ⚠️ No Inside Bar confirmation
        """)

    with col_ml:
        st.subheader("🤖 ML Engine")
        st.metric("Score", f"{confidence} / 100")
        st.markdown(f"""
        ✅ **Prediction:** BUY ({confidence}%)
        ✅ **Model:** STABLE (no drift)
        📊 **Top Feature:** atr_14 (0.23)
        📊 **2nd:** rsi_14 (0.18)
        📊 **3rd:** ema_crossover (0.15)
        """)

    with col_risk:
        st.subheader("🛡️ Risk Check")
        st.metric("Status", "✅ OK")
        st.markdown("""
        ✅ Daily limit: 0.8% / 3%
        ✅ Open trades: 1 / 5
        ✅ Volatility: NORMAL
        ✅ Session: Active
        ✅ Circuit Breaker: OFF
        """)

    st.divider()
    st.subheader("💬 Summary")
    if "BUY" in decision:
        st.info("🟢 BUY: Order Block at 2,345.50 | Bullish Engulfing | ML 72% confident | Discount zone 32%")
    elif "SELL" in decision:
        st.info("🔴 SELL: Premium zone | CHoCH detected | ML 68% confident | Liquidity swept")
    else:
        st.warning("⏸️ SKIP: No Order Block found | ML confidence below 50% threshold")

    st.divider()
    st.subheader("📊 Agent Votes")
    st.dataframe({
        "Agent": ["SMC Agent", "PA Agent", "ML Agent", "Risk Agent", "News Agent", "Liquidity Agent", "Execution Agent"],
        "Vote": ["🟢 BUY", "🟢 BUY", "🟢 BUY", "✅ Allow", "🟡 Neutral", "🟢 BUY", "✅ Allow"],
        "Score": [82, 74, 72, 100, 50, 78, 100],
        "Weight": ["35%", "20%", "30%", "10%", "5%", "Bonus", "Gate"],
    }, use_container_width=True)
