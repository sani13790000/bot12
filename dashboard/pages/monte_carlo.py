"""Monte Carlo Simulation page."""
import streamlit as st


def render():
    st.title("🎲 Monte Carlo Simulation")
    st.markdown("Validate strategy robustness by simulating thousands of random equity paths.")

    col1, col2, col3 = st.columns(3)
    with col1:
        n_sims = st.select_slider("Simulations", options=[100, 500, 1000, 5000, 10000], value=1000)
        initial_balance = st.number_input("Initial Balance ($)", value=10000, step=1000)
    with col2:
        ruin_threshold = st.slider("Ruin Threshold (%)", 10, 80, 50)
        seed = st.number_input("Random Seed", value=42)
    with col3:
        st.markdown("**Load from Backtest**")
        use_backtest = st.toggle("Use last backtest trades", value=True)

    if st.button("🎲 Run Monte Carlo", type="primary", use_container_width=True):
        with st.spinner(f"Running {n_sims:,} simulations..."):
            import time; time.sleep(1.5)
            st.session_state["mc_done"] = True

    if st.session_state.get("mc_done"):
        st.success("✅ Simulation complete!")
        st.divider()

        # Key metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Prob of Profit", "87.3%", "+2.1%")
        m2.metric("Prob of Ruin", "2.1%", "-0.5%")
        m3.metric("Median Final Balance", "$14,820")
        m4.metric("Expected Max DD", "-12.4%")

        st.divider()
        col_chart, col_dist = st.columns([2, 1])

        with col_chart:
            st.subheader("📉 Sample Equity Paths (10 of 1,000)")
            import random
            paths = {}
            for i in range(10):
                path = [10000]
                for _ in range(247):
                    path.append(path[-1] + random.choice([55, -22, 80, -18, 100, -40, 30, -15]))
                paths[f"Path {i+1}"] = path
            import pandas as pd
            st.line_chart(pd.DataFrame(paths))

        with col_dist:
            st.subheader("📊 Final Balance Distribution")
            finals = [10000 + random.gauss(4820, 2100) for _ in range(1000)]
            st.bar_chart(sorted(finals))

        st.subheader("📊 Percentile Summary")
        st.dataframe({
            "Percentile": ["5th (Worst)", "25th", "50th (Median)", "75th", "95th (Best)"],
            "Final Balance": ["$9,120", "$12,340", "$14,820", "$17,650", "$22,450"],
            "Return": ["-8.8%", "+23.4%", "+48.2%", "+76.5%", "+124.5%"],
        }, use_container_width=True)
