"""AI Explainability page."""
import pandas as pd
import streamlit as st

from api_client import APIClient

st.set_page_config(page_title="Explainability", layout="wide")
st.title("🧠 AI Explainability")

client = APIClient()

symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD"])
direction = st.selectbox("Direction", ["BUY", "SELL"])
entry = st.number_input("Entry Price", value=2350.0)
stop = st.number_input("Stop Loss", value=2340.0)
take = st.number_input("Take Profit", value=2370.0)
confidence = st.slider("Confidence", 0.0, 100.0, 75.0)

if st.button("🔮 Explain Decision"):
    signal = {
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry,
        "stop_loss": stop,
        "take_profit": take,
        "confidence": confidence,
    }
    payload = {
        "symbol": symbol,
        "signal": signal,
        "agent_scores": {"SMC": 82, "ML": 74, "Risk": 90, "News": 60},
    }
    result = client.explain(payload)
    if "error" in result:
        st.error(result["error"])
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("Confidence", f"{result.get('confidence_score', 0)}%")
        col2.metric("Direction", result.get("direction"))
        col3.metric("Decision", result.get("final_decision"))

        st.subheader("Reasons")
        for reason in result.get("reasons", []):
            st.markdown(f"- {reason}")

        st.subheader("SMC Analysis")
        st.json(result.get("smc", {}))

        st.subheader("Agent Scores")
        scores = result.get("agent_scores", {})
        if scores:
            st.bar_chart(pd.DataFrame([scores]).T.rename(columns={0: "Score"}))
