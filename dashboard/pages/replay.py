"""Market Replay page — candle-by-candle playback with controls."""
import time
import streamlit as st


def render():
    st.title("🎥 Market Replay Engine")
    st.markdown("Candle-by-candle historical playback from 2018 to present.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"], index=0)
    with col2:
        timeframe = st.selectbox("Timeframe", ["M1", "M5", "M15", "M30", "H1", "H4", "D1"], index=2)
    with col3:
        start_date = st.date_input("Start Date")
    with col4:
        speed = st.select_slider("Speed", options=["x1", "x2", "x4", "x10"], value="x1")

    st.divider()

    ctrl1, ctrl2, ctrl3, ctrl4, ctrl5 = st.columns(5)
    playing = st.session_state.get("replay_playing", False)

    with ctrl1:
        if st.button("⏮ Prev", use_container_width=True):
            st.session_state["replay_cursor"] = max(0, st.session_state.get("replay_cursor", 0) - 1)
    with ctrl2:
        label = "⏸ Pause" if playing else "▶ Play"
        if st.button(label, use_container_width=True):
            st.session_state["replay_playing"] = not playing
    with ctrl3:
        if st.button("⏭ Next", use_container_width=True):
            st.session_state["replay_cursor"] = st.session_state.get("replay_cursor", 0) + 1
    with ctrl4:
        if st.button("⏹ Stop", use_container_width=True):
            st.session_state["replay_playing"] = False
            st.session_state["replay_cursor"] = 0
    with ctrl5:
        cursor = st.session_state.get("replay_cursor", 0)
        st.metric("Bar", cursor)

    st.divider()

    # Chart area
    chart_col, info_col = st.columns([3, 1])
    with chart_col:
        st.subheader(f"{symbol} {timeframe} — Historical Replay")
        # Placeholder — in production, replace with Plotly candlestick chart
        import random
        cursor = st.session_state.get("replay_cursor", 0)
        # Simulate a small OHLCV dataset
        base = 2300 + cursor * 0.5
        data = {"open": [base + random.uniform(-5, 5) for _ in range(50)],
                "close": [base + random.uniform(-5, 5) for _ in range(50)]}
        st.line_chart(data)

    with info_col:
        st.subheader("📊 Bar Info")
        cursor = st.session_state.get("replay_cursor", 0)
        st.metric("Open", f"2{cursor + 300:.2f}")
        st.metric("High", f"2{cursor + 315:.2f}")
        st.metric("Low",  f"2{cursor + 285:.2f}")
        st.metric("Close",f"2{cursor + 305:.2f}")
        st.metric("Equity", f"${10000 + cursor * 12:.2f}")

    # Equity curve
    st.subheader("📉 Equity Curve")
    equity_data = [10000 + i * 12 + (i % 5) * (-20) for i in range(st.session_state.get("replay_cursor", 50) + 1)]
    st.line_chart(equity_data)

    # Trade markers
    st.subheader("📊 Trade History on Replay")
    st.dataframe({
        "Bar": [5, 12, 23, 31, 44],
        "Direction": ["🟢 BUY", "🔴 SELL", "🟢 BUY", "🔴 SELL", "🟢 BUY"],
        "Entry": [2305.10, 2318.50, 2297.30, 2322.00, 2301.50],
        "Exit":  [2318.50, 2297.30, 2322.00, 2301.50, 2315.00],
        "PnL": ["+ $132", "- $65", "+ $248", "- $21", "+ $135"],
    }, use_container_width=True)
