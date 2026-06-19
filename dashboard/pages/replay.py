"""Market Replay Page — Galaxy Vast AI Dashboard

Fixes applied:
- HIGH: time.sleep() in playing loop — now ONE sleep per rerun cycle
  (step-by-step pattern: sleep a short delay, advance one candle, rerun)
  This is the correct Streamlit pattern: sleep is outside button handler,
  inside the auto-advance block. One step per rerun = no UI freeze.
- MEDIUM: API calls cached with @st.cache_data(ttl=60)
- LOW: numpy seeded RNG for reproducible demo data
"""
import time
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


def render() -> None:
    st.title("🎦 Market Replay")
    st.caption("Candle-by-candle market replay with trade simulation")

    # ── Sidebar controls ──
    with st.sidebar:
        st.subheader("⚙️ Replay Settings")
        symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "USDJPY", "BTCUSD"], key="replay_symbol")
        timeframe = st.selectbox("Timeframe", ["M1", "M5", "M15", "M30", "H1", "H4", "D1"], key="replay_tf", index=2)
        n_candles = st.slider("Candles to load", 100, 1000, 300, key="replay_n")
        speed = st.selectbox("Speed", ["Slow (1s)", "Normal (0.5s)", "Fast (0.2s)", "Turbo (0.05s)"], index=1)
        speed_map = {"Slow (1s)": 1.0, "Normal (0.5s)": 0.5, "Fast (0.2s)": 0.2, "Turbo (0.05s)": 0.05}
        delay = speed_map[speed]
        show_ema = st.checkbox("Show EMA 20", value=True)
        show_volume = st.checkbox("Show Volume", value=True)

    # ── Load data ──
    @st.cache_data(ttl=300, show_spinner=False)
    def load_data(sym: str, tf: str, n: int) -> tuple:
        """Try API first, fallback to demo."""
        df = _fetch_api(sym, tf, n)
        source = "live API" if df is not None else "demo"
        if df is None:
            df = _gen_demo(sym, n)
        return df, source

    df, source = load_data(symbol, timeframe, n_candles)

    # ── Session state init ──
    if "replay_idx" not in st.session_state or st.session_state.get("replay_symbol_prev") != symbol:
        st.session_state.replay_idx = 50
        st.session_state.replay_equity = [10000.0]
        st.session_state.replay_trades = []
        st.session_state.replay_playing = False
        st.session_state.replay_symbol_prev = symbol

    idx = st.session_state.replay_idx

    # ── Controls ──
    c1, c2, c3, c4, c5 = st.columns(5)
    if c1.button("⏮ Reset"):
        st.session_state.replay_idx = 50
        st.session_state.replay_equity = [10000.0]
        st.session_state.replay_trades = []
        st.session_state.replay_playing = False
        st.rerun()

    # Play/Pause toggle — no time.sleep in button handler
    if c2.button("⏸ Pause" if st.session_state.replay_playing else "▶ Play"):
        st.session_state.replay_playing = not st.session_state.replay_playing
        st.rerun()

    if c3.button("⏭ Step"):
        if idx < len(df) - 1:
            st.session_state.replay_idx += 1
            st.rerun()

    if c4.button("⏪ Back"):
        if idx > 1:
            st.session_state.replay_idx = max(1, idx - 1)
            st.rerun()

    c5.metric("Candle", f"{idx} / {len(df)}")
    st.progress(idx / max(len(df) - 1, 1))

    # ── Auto-advance when playing ──
    # Pattern: sleep ONCE (short), advance ONE candle, rerun.
    # Streamlit runs the entire script per rerun — this is the correct
    # non-blocking approach: one candle per cycle, no loop sleep.
    if st.session_state.replay_playing:
        if idx < len(df) - 1:
            time.sleep(delay)          # one short sleep, then rerun
            st.session_state.replay_idx += 1
            st.rerun()
        else:
            st.session_state.replay_playing = False

    # ── Chart ──
    visible = df.iloc[:idx].copy()
    rows = 2 if show_volume else 1
    row_heights = [0.7, 0.3] if show_volume else [1.0]
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        vertical_spacing=0.03, row_heights=row_heights
    )

    colors = ["#0ECB81" if r["close"] >= r["open"] else "#F6465D" for _, r in visible.iterrows()]
    fig.add_trace(go.Candlestick(
        x=visible["time"], open=visible["open"], high=visible["high"],
        low=visible["low"], close=visible["close"],
        increasing_line_color="#0ECB81", decreasing_line_color="#F6465D",
        name="Price",
    ), row=1, col=1)

    if show_ema and len(visible) >= 20:
        ema20 = visible["close"].ewm(span=20, adjust=False).mean()
        fig.add_trace(go.Scatter(
            x=visible["time"], y=ema20, name="EMA 20",
            line=dict(color="#F0B90B", width=1.5)
        ), row=1, col=1)

    for t in st.session_state.replay_trades:
        fig.add_trace(go.Scatter(
            x=[t["time"]], y=[t["price"]],
            mode="markers", name=t["type"],
            marker=dict(
                symbol="triangle-up" if t["type"] == "BUY" else "triangle-down",
                color="#0ECB81" if t["type"] == "BUY" else "#F6465D", size=12
            ),
        ), row=1, col=1)

    if show_volume:
        fig.add_trace(go.Bar(
            x=visible["time"], y=visible["volume"],
            marker_color=colors, name="Volume", opacity=0.6,
        ), row=2, col=1)

    fig.update_layout(
        template="plotly_dark", height=500,
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=30, b=0),
        showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Current candle OHLCV
    row = df.iloc[idx - 1]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Open",  f"{row['open']:.2f}")
    m2.metric("High",  f"{row['high']:.2f}")
    m3.metric("Low",   f"{row['low']:.2f}")
    m4.metric("Close", f"{row['close']:.2f}", delta=f"{row['close']-row['open']:+.2f}")
    m5.metric("Volume", f"{row['volume']:,}")

    # Equity curve
    eq = st.session_state.replay_equity
    if len(eq) > 1:
        st.subheader("💰 Equity Curve")
        fig_eq = go.Figure(go.Scatter(
            y=eq, mode="lines",
            line=dict(color="#0ECB81" if eq[-1] >= eq[0] else "#F6465D", width=2),
            fill="tozeroy", fillcolor="rgba(14,203,129,0.1)"
        ))
        fig_eq.update_layout(
            template="plotly_dark", height=200,
            margin=dict(l=0, r=0, t=10, b=0), yaxis_title="Equity ($)"
        )
        st.plotly_chart(fig_eq, use_container_width=True)

    if source == "live API":
        st.success("✅ Live API data")
    else:
        st.info("ℹ️ Demo data (API not connected)")


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_api(symbol: str, tf: str, n: int) -> Optional[pd.DataFrame]:
    """Fetch candles from API — cached 60s."""
    try:
        import requests
        import os
        base = os.environ.get("API_BASE_URL", "http://api:8000")
        r = requests.get(
            f"{base}/api/v1/analysis/candles",
            params={"symbol": symbol, "timeframe": tf, "limit": n},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            return pd.DataFrame(data)
    except Exception:
        pass
    return None


@st.cache_data(ttl=300)
def _gen_demo(symbol: str, n: int) -> pd.DataFrame:
    """Generate realistic demo OHLCV data."""
    rng = np.random.default_rng(42)
    base = 2000.0 if symbol == "XAUUSD" else 1.1
    closes = base + np.cumsum(rng.normal(0, base * 0.002, n))
    times = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="15min")
    hi = closes + rng.uniform(0, base * 0.003, n)
    lo = closes - rng.uniform(0, base * 0.003, n)
    op = closes - rng.normal(0, base * 0.001, n)
    vol = rng.integers(500, 3000, n)
    return pd.DataFrame({"time": times, "open": op, "high": hi, "low": lo, "close": closes, "volume": vol})
