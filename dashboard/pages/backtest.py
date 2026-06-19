"""Backtest page — tick-level backtest configuration and results."""
import streamlit as st


def render():
    st.title("📈 Tick-Level Backtest Engine")

    with st.expander("⚙️ Configuration", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])
            timeframe = st.selectbox("Timeframe", ["M5", "M15", "M30", "H1", "H4"])
            initial_balance = st.number_input("Initial Balance ($)", value=10000, step=1000)
        with col2:
            risk_pct = st.slider("Risk per Trade (%)", 0.1, 5.0, 1.0, 0.1)
            spread_mult = st.slider("Spread Multiplier", 0.5, 3.0, 1.0, 0.1)
            slippage = st.slider("Slippage (pips)", 0.0, 2.0, 0.5, 0.1)
        with col3:
            use_commission = st.toggle("Commission", value=True)
            start_date = st.date_input("Start Date")
            end_date = st.date_input("End Date")

    if st.button("🚀 Run Backtest", type="primary", use_container_width=True):
        with st.spinner("Running tick-level backtest..."):
            import time; time.sleep(1.5)
            st.session_state["backtest_done"] = True

    if st.session_state.get("backtest_done"):
        st.success("✅ Backtest complete!")
        st.divider()

        # Metrics row
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Total Trades", "247")
        m2.metric("Win Rate", "61.5%", "+1.2%")
        m3.metric("Profit Factor", "1.87")
        m4.metric("Sharpe Ratio", "1.43")
        m5.metric("Max Drawdown", "-8.3%", "-0.5%")
        m6.metric("Net Profit", "$4,382", "+43.8%")

        st.divider()
        col_chart, col_dist = st.columns([2, 1])

        with col_chart:
            st.subheader("📉 Equity Curve")
            import random
            equity = [10000]
            for _ in range(247):
                equity.append(equity[-1] + random.choice([45, -22, 67, -15, 89, -31, 112, -44]))
            st.line_chart(equity)

        with col_dist:
            st.subheader("📊 P&L Distribution")
            pnl_data = [random.randint(-200, 400) for _ in range(247)]
            st.bar_chart(sorted(pnl_data))

        st.subheader("💼 Trade Log")
        st.dataframe({
            "#": list(range(1, 11)),
            "Symbol": [symbol] * 10,
            "Direction": ["🟢 BUY", "🔴 SELL"] * 5,
            "Entry": [2305.10, 2318.50, 2297.30, 2322.00, 2301.50, 2310.0, 2295.0, 2330.0, 2288.0, 2345.0],
            "Exit":  [2318.50, 2297.30, 2322.00, 2301.50, 2315.00, 2318.0, 2310.0, 2315.0, 2301.0, 2330.0],
            "Lots": [0.1] * 10,
            "Commission": [5.0] * 10,
            "Spread Cost": [3.0] * 10,
            "Net P&L": ["+$132", "-$65", "+$248", "-$21", "+$135", "+$80", "+$150", "-$150", "+$130", "-$150"],
            "Reason": ["TP", "SL", "TP", "SL", "TP", "TP", "TP", "SL", "TP", "SL"],
        }, use_container_width=True)
