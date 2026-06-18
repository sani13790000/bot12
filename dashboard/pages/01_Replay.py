"""Market Replay page."""
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Market Replay", layout="wide")
st.title("▶️ Market Replay")

if "replay_index" not in st.session_state:
    st.session_state.replay_index = 0
if "replay_playing" not in st.session_state:
    st.session_state.replay_playing = False
if "replay_speed" not in st.session_state:
    st.session_state.replay_speed = 1.0

# Generate synthetic OHLC data for demo
def generate_candles(n=200):
    np.random.seed(42)
    now = datetime.utcnow() - timedelta(days=n)
    price = 2350.0
    candles = []
    for i in range(n):
        open_p = price
        high = price * (1 + abs(np.random.normal(0, 0.002)))
        low = price * (1 - abs(np.random.normal(0, 0.002)))
        close = low + (high - low) * np.random.random()
        candles.append({
            "timestamp": now + timedelta(hours=i),
            "open": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": round(np.random.uniform(100, 1000), 2),
        })
        price = close
    return candles

candles = generate_candles(500)
df = pd.DataFrame(candles)

# Controls
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    if st.button("⏮️ Previous"):
        st.session_state.replay_index = max(0, st.session_state.replay_index - 1)
with col2:
    play_label = "⏸️ Pause" if st.session_state.replay_playing else "▶️ Play"
    if st.button(play_label):
        st.session_state.replay_playing = not st.session_state.replay_playing
with col3:
    if st.button("⏭️ Next"):
        st.session_state.replay_index = min(len(candles) - 1, st.session_state.replay_index + 1)
with col4:
    if st.button("⏹️ Stop"):
        st.session_state.replay_playing = False
        st.session_state.replay_index = 0
with col5:
    st.session_state.replay_speed = st.selectbox("Speed", [0.25, 1.0, 2.0, 4.0, 10.0], index=1)

idx = st.session_state.replay_index
window = 80
start = max(0, idx - window)
end = min(len(df), idx + 1)
sub = df.iloc[start:end]

fig = go.Figure(data=[go.Candlestick(
    x=sub["timestamp"],
    open=sub["open"],
    high=sub["high"],
    low=sub["low"],
    close=sub["close"],
    name="XAUUSD",
)])

# Simulate trade markers
markers = []
for i in range(10, idx, 25):
    if i % 2 == 0:
        markers.append((df.iloc[i]["timestamp"], df.iloc[i]["low"], "BUY", "green"))
    else:
        markers.append((df.iloc[i]["timestamp"], df.iloc[i]["high"], "SELL", "red"))

for ts, price, direction, color in markers:
    fig.add_trace(go.Scatter(
        x=[ts],
        y=[price],
        mode="markers+text",
        marker=dict(color=color, size=12, symbol="triangle-up" if direction == "BUY" else "triangle-down"),
        text=[direction],
        textposition="top center" if direction == "SELL" else "bottom center",
        showlegend=False,
    ))

fig.update_layout(
    title=f"Replay — candle {idx + 1} / {len(candles)}",
    xaxis_rangeslider_visible=False,
    height=600,
)
st.plotly_chart(fig, use_container_width=True)

# Auto-advance
if st.session_state.replay_playing:
    delay = 0.5 / st.session_state.replay_speed
    time.sleep(delay)
    st.session_state.replay_index = min(len(candles) - 1, st.session_state.replay_index + 1)
    st.rerun()

progress = (idx + 1) / len(candles)
st.progress(progress, text=f"Progress: {progress*100:.1f}%")
