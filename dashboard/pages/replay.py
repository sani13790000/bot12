"""Market Replay Engine — full candlestick chart with trade markers."""
import time
import random
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def _generate_ohlcv(n: int = 200, base: float = 2320.0, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates, opens, highs, lows, closes, vols = [], [], [], [], [], []
    price = base
    for i in range(n):
        dates.append(datetime(2024, 1, 1) + timedelta(hours=i * 15))
        change = rng.normal(0, 3.5)
        o = price
        c = price + change
        h = max(o, c) + abs(rng.normal(0, 1.5))
        l = min(o, c) - abs(rng.normal(0, 1.5))
        v = rng.integers(500, 3000)
        opens.append(round(o, 2)); highs.append(round(h, 2))
        lows.append(round(l, 2)); closes.append(round(c, 2))
        vols.append(int(v))
        price = c
    return pd.DataFrame({"date": dates, "open": opens, "high": highs,
                         "low": lows, "close": closes, "volume": vols})


def _generate_trades(df: pd.DataFrame, n_trades: int = 12) -> list:
    trades = []
    rng = random.Random(42)
    for _ in range(n_trades):
        idx = rng.randint(5, len(df) - 15)
        exit_idx = idx + rng.randint(3, 12)
        direction = rng.choice(["BUY", "SELL"])
        entry = df.iloc[idx]["close"]
        exit_p = df.iloc[exit_idx]["close"]
        pnl = (exit_p - entry) * (1 if direction == "BUY" else -1) * 10
        trades.append({"entry_idx": idx, "exit_idx": exit_idx,
                       "direction": direction, "entry": entry,
                       "exit": exit_p, "pnl": round(pnl, 2)})
    return sorted(trades, key=lambda x: x["entry_idx"])


def render():
    st.markdown('<h1 style="color:#FFD700">📊 Market Replay Engine</h1>', unsafe_allow_html=True)
    st.caption("Candle-by-candle historical playback — 2018 to present | Pause, Play, Speed x1/x2/x4/x10")

    # Controls row
    col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])
    with col1:
        symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY"], key="rp_symbol")
    with col2:
        timeframe = st.selectbox("Timeframe", ["M1", "M5", "M15", "M30", "H1", "H4", "D1"], index=2, key="rp_tf")
    with col3:
        speed_map = {"x1": 1.0, "x2": 0.5, "x4": 0.25, "x10": 0.1}
        speed_label = st.select_slider("Speed", options=["x1", "x2", "x4", "x10"], value="x1")
    with col4:
        visible_bars = st.slider("Visible Bars", 50, 200, 100)
    with col5:
        show_trades = st.toggle("Show Trades", value=True)

    st.divider()

    # Playback buttons
    b1, b2, b3, b4, b5 = st.columns(5)
    playing = st.session_state.get("replay_playing", False)
    cursor = st.session_state.get("replay_cursor", visible_bars)

    with b1:
        if st.button("◄◄ Prev", use_container_width=True):
            st.session_state["replay_cursor"] = max(visible_bars, cursor - 1)
    with b2:
        label = "⏸ Pause" if playing else "▶️ Play"
        if st.button(label, use_container_width=True):
            st.session_state["replay_playing"] = not playing
    with b3:
        if st.button("►► Next", use_container_width=True):
            st.session_state["replay_cursor"] = min(200, cursor + 1)
    with b4:
        if st.button("⏹ Stop", use_container_width=True):
            st.session_state["replay_playing"] = False
            st.session_state["replay_cursor"] = visible_bars
    with b5:
        st.metric("Bar", f"{st.session_state.get('replay_cursor', visible_bars)} / 200")

    cursor = st.session_state.get("replay_cursor", visible_bars)
    df = _generate_ohlcv(200)
    trades = _generate_trades(df)
    visible_df = df.iloc[max(0, cursor - visible_bars): cursor]

    # Candlestick chart
    chart_col, info_col = st.columns([3, 1])
    with chart_col:
        fig = go.Figure()
        # Candlesticks
        fig.add_trace(go.Candlestick(
            x=visible_df["date"], open=visible_df["open"],
            high=visible_df["high"], low=visible_df["low"],
            close=visible_df["close"], name=symbol,
            increasing_line_color="#0ECB81", decreasing_line_color="#F6465D"
        ))
        # Trade markers
        if show_trades:
            for t in trades:
                if max(0, cursor - visible_bars) <= t["entry_idx"] < cursor:
                    color = "#0ECB81" if t["direction"] == "BUY" else "#F6465D"
                    symbol_marker = "triangle-up" if t["direction"] == "BUY" else "triangle-down"
                    fig.add_trace(go.Scatter(
                        x=[df.iloc[t["entry_idx"]]["date"]],
                        y=[t["entry"]], mode="markers",
                        marker=dict(color=color, size=12, symbol=symbol_marker),
                        name=f"{t['direction']} entry", showlegend=False
                    ))
                    if t["exit_idx"] < cursor:
                        fig.add_trace(go.Scatter(
                            x=[df.iloc[t["exit_idx"]]["date"]],
                            y=[t["exit"]], mode="markers",
                            marker=dict(color="#F0B90B", size=10, symbol="x"),
                            name="Exit", showlegend=False
                        ))
        fig.update_layout(
            template="plotly_dark", height=450, margin=dict(l=0, r=0, t=30, b=0),
            xaxis_rangeslider_visible=False,
            title=f"{symbol} {timeframe} — Historical Replay",
            title_font_color="#FFD700", paper_bgcolor="#1E2329", plot_bgcolor="#1E2329"
        )
        st.plotly_chart(fig, use_container_width=True)

    with info_col:
        st.markdown("**📐 Current Bar**")
        current = df.iloc[cursor - 1]
        delta_c = round(current["close"] - current["open"], 2)
        st.metric("Open",  f"{current['open']:.2f}")
        st.metric("High",  f"{current['high']:.2f}")
        st.metric("Low",   f"{current['low']:.2f}")
        st.metric("Close", f"{current['close']:.2f}", delta=f"{delta_c:+.2f}")
        st.metric("Volume", f"{current['volume']:,}")
        equity = 10000.0
        for t in trades:
            if t["exit_idx"] < cursor: equity += t["pnl"]
        st.divider()
        st.metric("💰 Equity", f"${equity:,.2f}",
                  delta=f"{((equity-10000)/10000*100):+.1f}%")

    # Equity curve
    st.subheader("📉 Equity Curve")
    eq_values = [10000.0]
    trade_by_exit = {t["exit_idx"]: t["pnl"] for t in trades}
    for i in range(1, cursor):
        eq_values.append(eq_values[-1] + trade_by_exit.get(i, 0))
    eq_df = pd.DataFrame({"Equity": eq_values, "Bar": list(range(cursor))})
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=eq_df["Bar"], y=eq_df["Equity"],
                              fill="tozeroy", line_color="#FFD700",
                              fillcolor="rgba(255,215,0,0.1)"))
    fig2.update_layout(template="plotly_dark", height=200,
                       margin=dict(l=0, r=0, t=10, b=0),
                       paper_bgcolor="#1E2329", plot_bgcolor="#1E2329")
    st.plotly_chart(fig2, use_container_width=True)

    # Trade history
    if show_trades:
        st.subheader("📒 Trade History")
        visible_trades = [t for t in trades if t["exit_idx"] < cursor]
        if visible_trades:
            trade_rows = []
            for i, t in enumerate(visible_trades, 1):
                trade_rows.append({
                    "#": i,
                    "Direction": "🟢 BUY" if t["direction"] == "BUY" else "🔴 SELL",
                    "Entry": f"{t['entry']:.2f}",
                    "Exit": f"{t['exit']:.2f}",
                    "P&L": f"{'+'if t['pnl']>=0 else ''}${t['pnl']:.2f}",
                    "Result": "✅ WIN" if t["pnl"] >= 0 else "❌ LOSS"
                })
            st.dataframe(pd.DataFrame(trade_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No completed trades yet in current replay position.")

    # Auto-advance
    if st.session_state.get("replay_playing"):
        time.sleep(speed_map[speed_label])
        st.session_state["replay_cursor"] = min(200, cursor + 1)
        if cursor >= 200:
            st.session_state["replay_playing"] = False
        st.rerun()
