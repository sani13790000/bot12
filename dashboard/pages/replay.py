"""Market Replay Dashboard Page — real API integration with demo fallback."""
from __future__ import annotations

import os
import random
import time

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

API_BASE = os.getenv("API_BASE_URL", "http://api:8000/api/v1")


def _fetch_candles_from_api(symbol: str, timeframe: str, n: int) -> pd.DataFrame | None:
    """Try to fetch real candles from API; return None on failure."""
    try:
        resp = requests.get(
            f"{API_BASE}/analysis/candles",
            params={"symbol": symbol, "timeframe": timeframe, "limit": n},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 10:
                df = pd.DataFrame(data)
                df["date"] = pd.to_datetime(df["date"])
                return df
    except Exception:
        pass
    return None


@st.cache_data(ttl=300)
def _generate_demo_candles(sym: str, n: int, seed: int = 42) -> pd.DataFrame:
    """Generate deterministic demo OHLCV data."""
    random.seed(seed)
    opens, highs, lows, closes, volumes = [], [], [], [], []
    price = 2320.0 if sym == "XAUUSD" else (1.0850 if "USD" in sym else 150.0)
    dates = pd.date_range("2024-01-01", periods=n, freq="15min")
    for _ in range(n):
        op = price + random.uniform(-3, 3)
        cl = op + random.uniform(-8, 8)
        hi = max(op, cl) + random.uniform(0, 4)
        lo = min(op, cl) - random.uniform(0, 4)
        opens.append(round(op, 2))
        highs.append(round(hi, 2))
        lows.append(round(lo, 2))
        closes.append(round(cl, 2))
        volumes.append(random.randint(500, 5000))
        price = cl
    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": volumes})


def render() -> None:
    st.title("\U0001f4ca Market Replay Engine")
    st.markdown("*Candle-by-candle historical playback with trade visualization and equity curve*")

    # ── Sidebar controls ──────────────────────────────────────────────────────
    with st.sidebar:
        st.header("\u2699\ufe0f Replay Settings")
        symbol     = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"])
        timeframe  = st.selectbox("Timeframe", ["M1", "M5", "M15", "H1", "H4", "D1"])
        n_candles  = st.slider("Candles to Load", 100, 1000, 300)
        speed      = st.select_slider("Playback Speed", options=["x1", "x2", "x4", "x10"], value="x1")
        st.divider()
        use_api    = st.checkbox("Use Live API Data", value=True)
        load_btn   = st.button("\U0001f4e5 Load Data", type="primary", use_container_width=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    if "replay_df" not in st.session_state or load_btn:
        with st.spinner(f"Loading {n_candles} candles for {symbol} {timeframe}..."):
            df = None
            source = "demo"
            if use_api:
                df = _fetch_candles_from_api(symbol, timeframe, n_candles)
                if df is not None:
                    source = "live API"
            if df is None:
                df = _generate_demo_candles(symbol, n_candles)
            st.session_state.replay_df     = df
            st.session_state.replay_idx    = min(50, n_candles - 1)
            st.session_state.replay_trades = []
            st.session_state.replay_equity = [10000.0]
            st.session_state.replay_source = source
        st.success(f"Loaded {len(df)} candles ({st.session_state.replay_source})")

    df: pd.DataFrame = st.session_state.replay_df
    idx: int         = st.session_state.replay_idx

    # ── Playback controls ─────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    if c1.button("\u23ee Prev",  use_container_width=True) and idx > 1:
        st.session_state.replay_idx -= 1;  st.rerun()
    if c2.button("\u25b6 Play",  use_container_width=True):
        delay = {"x1": 0.5, "x2": 0.25, "x4": 0.125, "x10": 0.05}[speed]
        for _ in range(min(20, len(df) - idx - 1)):
            st.session_state.replay_idx += 1
            time.sleep(delay)
        st.rerun()
    if c3.button("\u23ed Next",  use_container_width=True) and idx < len(df) - 1:
        st.session_state.replay_idx += 1;  st.rerun()
    if c4.button("\u23f9 Stop",  use_container_width=True):
        pass
    c5.progress(idx / max(len(df) - 1, 1), text=f"{idx}/{len(df)}")

    # ── Candlestick chart ─────────────────────────────────────────────────────
    visible = df.iloc[max(0, idx - 80): idx + 1]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.75, 0.25], vertical_spacing=0.03)

    fig.add_trace(go.Candlestick(
        x=visible["date"], open=visible["open"], high=visible["high"],
        low=visible["low"], close=visible["close"],
        increasing_line_color="#0ECB81", decreasing_line_color="#F6465D",
        name="Price"
    ), row=1, col=1)

    if len(visible) >= 20:
        ema20 = visible["close"].ewm(span=20).mean()
        fig.add_trace(go.Scatter(x=visible["date"], y=ema20, name="EMA20",
                                 line=dict(color="#FFD700", width=1.5)), row=1, col=1)

    colors = ["#0ECB81" if c >= o else "#F6465D"
              for c, o in zip(visible["close"], visible["open"])]
    fig.add_trace(go.Bar(x=visible["date"], y=visible["volume"],
                         marker_color=colors, name="Volume", opacity=0.7), row=2, col=1)

    cur_price = df.iloc[idx]["close"]
    fig.add_hline(y=cur_price, line_dash="dash", line_color="#FFD700",
                  annotation_text=f"  {cur_price:.2f}", row=1, col=1)

    # Trade markers
    for trade in st.session_state.get("replay_trades", []):
        if max(0, idx - 80) <= trade.get("bar", -1) <= idx:
            color = "#0ECB81" if trade["type"] == "BUY" else "#F6465D"
            symbol_marker = "triangle-up" if trade["type"] == "BUY" else "triangle-down"
            fig.add_trace(go.Scatter(
                x=[trade["date"]], y=[trade["price"]],
                mode="markers",
                marker=dict(symbol=symbol_marker, size=14, color=color),
                name=trade["type"], showlegend=False
            ), row=1, col=1)

    fig.update_layout(
        template="plotly_dark", height=480,
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", y=1.05),
        title=f"{symbol} {timeframe} \u2014 Candle {idx}/{len(df)}"
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Current candle metrics ────────────────────────────────────────────────
    row = df.iloc[idx]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Open",   f"{row['open']:.2f}")
    m2.metric("High",   f"{row['high']:.2f}")
    m3.metric("Low",    f"{row['low']:.2f}")
    m4.metric("Close",  f"{row['close']:.2f}",
              delta=f"{row['close'] - row['open']:+.2f}")
    m5.metric("Volume", f"{row['volume']:,}")

    # ── Equity curve ──────────────────────────────────────────────────────────
    equity = st.session_state.replay_equity
    if len(equity) > 1:
        st.subheader("\U0001f4b0 Equity Curve")
        fig_eq = go.Figure(go.Scatter(
            y=equity, mode="lines",
            line=dict(color="#0ECB81" if equity[-1] >= equity[0] else "#F6465D", width=2),
            fill="tozeroy", fillcolor="rgba(14,203,129,0.1)"
        ))
        fig_eq.update_layout(template="plotly_dark", height=200,
                              margin=dict(l=0, r=0, t=10, b=0),
                              yaxis_title="Equity ($)")
        st.plotly_chart(fig_eq, use_container_width=True)

    # ── Data source badge ─────────────────────────────────────────────────────
    source = st.session_state.get("replay_source", "demo")
    if source == "live API":
        st.success("\u2705 Live API data")
    else:
        st.info("\u2139\ufe0f Demo data (API not connected)")
