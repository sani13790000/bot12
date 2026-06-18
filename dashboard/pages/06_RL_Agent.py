"""Reinforcement Learning agent page."""
import numpy as np
import pandas as pd
import streamlit as st

from api_client import APIClient

st.set_page_config(page_title="RL Agent", layout="wide")
st.title("🤖 Reinforcement Learning Agent")

client = APIClient()

symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD"])
timesteps = st.select_slider("Training Timesteps", options=[1000, 5000, 10000, 50000], value=10000)

if st.button("🎓 Train RL Agent"):
    np.random.seed(42)
    candles = []
    price = 2350.0
    for i in range(500):
        o = price
        h = price * (1 + abs(np.random.normal(0, 0.003)))
        l = price * (1 - abs(np.random.normal(0, 0.003)))
        c = l + (h - l) * np.random.random()
        candles.append({"timestamp": f"2024-01-01T{i:04d}", "open": o, "high": h, "low": l, "close": c, "volume": 100})
        price = c
    payload = {"symbol": symbol, "candles": candles, "timesteps": timesteps}
    with st.spinner("Training PPO agent..."):
        result = client.rl_train(payload)
    if "error" in result:
        st.error(result["error"])
    else:
        st.success(f"Trained {result.get('timesteps')} timesteps — model saved to {result.get('model_path')}")

if st.button("🎯 Predict Next Action"):
    np.random.seed(42)
    candles = []
    price = 2350.0
    for i in range(50):
        o = price
        h = price * (1 + abs(np.random.normal(0, 0.003)))
        l = price * (1 - abs(np.random.normal(0, 0.003)))
        c = l + (h - l) * np.random.random()
        candles.append({"timestamp": f"2024-01-01T{i:04d}", "open": o, "high": h, "low": l, "close": c, "volume": 100})
        price = c
    payload = {"symbol": symbol, "candles": candles}
    result = client.rl_predict(payload)
    if "error" in result:
        st.error(result["error"])
    else:
        action_map = {0: "HOLD", 1: "BUY", 2: "SELL"}
        st.metric("Predicted Action", action_map.get(result.get("action"), "UNKNOWN"))
