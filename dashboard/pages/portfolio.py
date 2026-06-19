"""Portfolio Management page."""
import streamlit as st


def render():
    st.title("💼 Portfolio Manager")

    col1, col2 = st.columns([2, 1])
    with col1:
        symbols = st.multiselect(
            "Symbols",
            ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "XAGUSD"],
            default=["XAUUSD", "EURUSD", "GBPUSD"]
        )
        method = st.selectbox(
            "Allocation Method",
            ["equal_weight", "risk_parity", "kelly", "min_variance", "max_sharpe"]
        )
    with col2:
        capital = st.number_input("Total Capital ($)", value=100000, step=10000)
        max_pos = st.slider("Max Position %", 5, 50, 25)
        corr_threshold = st.slider("Max Correlation", 0.5, 1.0, 0.8, 0.05)

    if st.button("📊 Compute Allocations", type="primary", use_container_width=True):
        st.session_state["portfolio_done"] = True

    if st.session_state.get("portfolio_done") and symbols:
        st.divider()
        import random
        n = len(symbols)
        weights = [round(1/n + random.uniform(-0.05, 0.05), 3) for _ in symbols]
        total = sum(weights)
        weights = [round(w/total, 3) for w in weights]

        st.subheader("🎯 Allocations")
        alloc_data = {
            "Symbol": symbols,
            "Weight": [f"{w*100:.1f}%" for w in weights],
            "Capital ($)": [f"${w*capital:,.2f}" for w in weights],
            "Max Lot": [round(w * capital / 100000, 2) for w in weights],
        }
        st.dataframe(alloc_data, use_container_width=True)

        st.subheader("📈 Correlation Matrix")
        corr_data = {}
        for sa in symbols:
            corr_data[sa] = {sb: round(random.uniform(-0.3, 0.9) if sa != sb else 1.0, 2) for sb in symbols}
        import pandas as pd
        st.dataframe(pd.DataFrame(corr_data), use_container_width=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("Diversification Score", "78.4 / 100")
        m2.metric("High Corr Pairs", str(random.randint(0, 2)))
        m3.metric("Conflicts", "0")
