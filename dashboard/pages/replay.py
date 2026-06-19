"""Market Replay Dashboard Page."""
from __future__ import annotations

import random
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


def render() -> None:
    st.title("📉 Market Replay Engine")
    st.markdown("*Candle-by-candle historical playback with trade visualization and equity curve*")

    # ── Sidebar controls
    with st.sidebar:
        st.header("⚙️ Replay Settings")
        symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])
        timeframe = st.selectbox("Timeframe", ["M1", "M5", "M15", "H1", "H4", "D1"])
        n_candles = st.slider("Candles to Load", 100, 1000, 300)
        speed = st.select_slider("Playback Speed", options=["x1", "x2", "x4", "x10"], value="x1")
        st.divider()
        load_btn = st.button("📥 Load Data", type="primary", use_container_width=True)

    # ── Generate demo OHLCV
    @st.cache_data
    def generate_candles(sym: str, n: int, seed: int = 42) -> pd.DataFrame:
        random.seed(seed)
        prices, opens, highs, lows, closes, volumes = [], [], [], [], [], []
        price = 2320.0 if sym == "XAUUSD" else 1.0850
        dates = pd.date_range("2024-01-01", periods=n, freq="15min")
        for _ in range(n):
            op = price + random.uniform(-3, 3)
            cl = op + random.uniform(-8, 8)
            hi = max(op, cl) + random.uniform(0, 4)
            lo = min(op, cl) - random.uniform(0, 4)
            vol = random.randint(500, 5000)
            opens.append(round(op, 2))
            highs.append(round(hi, 2))
            lows.append(round(lo, 2))
            closes.append(round(cl, 2))
            volumes.append(vol)
            price = cl
        return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                             "low": lows, "close": closes, "volume": volumes})

    if "replay_df" not in st.session_state or load_btn:
        with st.spinner(f"Loading {n_candles} candles for {symbol} {timeframe}..."):
            time.sleep(0.5)
            st.session_state.replay_df = generate_candles(symbol, n_candles)
            st.session_state.replay_idx = min(50, n_candles - 1)
            st.session_state.replay_trades = []
            st.session_state.replay_equity = [10000.0]

    df: pd.DataFrame = st.session_state.replay_df
    idx: int = st.session_state.replay_idx

    # ── Playback controls
    c1, c2, c3, c4, c5 = st.columns(5)
    if c1.button("⏮ Prev", use_container_width=True) and idx > 1:
        st.session_state.replay_idx -= 1
        st.rerun()
    if c2.button("▶ Play", use_container_width=True):
        delay = {"x1": 0.5, "x2": 0.25, "x4": 0.125, "x10": 0.05}[speed]
        for _ in range(min(20, len(df) - idx - 1)):
            st.session_state.replay_idx += 1
            time.sleep(delay)
        st.rerun()
    if c3.button("⏭ Next", use_container_width=True) and idx < len(df) - 1:
        st.session_state.replay_idx += 1
        st.rerun()
    if c4.button("⏹ Stop", use_container_width=True):
        pass
    c5.progress(idx / max(len(df) - 1, 1), text=f"{idx}/{len(df)}")

    # ── Candlestick chart
    visible = df.iloc[max(0, idx - 80): idx + 1]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25],
                        vertical_spacing=0.03)

    fig.add_trace(go.Candlestick(
        x=visible["date"], open=visible["open"], high=visible["high"],
        low=visible["low"], close=visible["close"],
        increasing_line_color="#0ECB81", decreasing_line_color="#F6465D",
        name="Price"
    ), row=1, col=1)

    # EMA overlay
    if len(visible) >= 20:
        ema20 = visible["close"].ewm(span=20).mean()
        fig.add_trace(go.Scatter(x=visible["date"], y=ema20, name="EMA20",
                                 line=dict(color="#FFD700", width=1.5)), row=1, col=1)

    # Volume
    colors = ["#0ECB81" if c >= o else "#F6465D"
              for c, o in zip(visible["close"], visible["open"])]
    fig.add_trace(go.Bar(x=visible["date"], y=visible["volume"],
                         marker_color=colors, name="Volume", opacity=0.7), row=2, col=1)

    # Current price line
    cur_price = df.iloc[idx]["close"]
    fig.add_hline(y=cur_price, line_dash="dash", line_color="#FFD700",
                  annotation_text=f"  {cur_price:.2f}", row=1, col=1)

    fig.update_layout(
        template="plotly_dark", height=480,
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", y=1.05),
        title=f"{symbol} {timeframe} — Candle {idx}/{len(df)}"
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Current candle info
    row = df.iloc[idx]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Open", f"{row['open']:.2f}")
    m2.metric("High", f"{row['high']:.2f}")
    m3.metric("Low", f"{row['low']:.2f}")
    m4.metric("Close", f"{row['close']:.2f}",
              delta=f"{row['close'] - row['open']:+.2f}")
    m5.metric("Volume", f"{row['volume']:,}")

    # ── Equity curve
    equity = st.session_state.replay_equity
    if len(equity) > 1:
        st.subheader("💰 Equity Curve")
        fig_eq = go.Figure(go.Scatter(
            y=equity, mode="lines",
            line=dict(color="#0ECB81" if equity[-1] >= equity[0] else "#F6465D", width=2),
            fill="tozeroy", fillcolor="rgba(14,203,129,0.1)"
        ))
        fig_eq.update_layout(template="plotly_dark", height=200,
                             margin=dict(l=0, r=0, t=10, b=0),
                             yaxis_title="Equity ($)")
        st.plotly_chart(fig_eq, use_container_width=True)
