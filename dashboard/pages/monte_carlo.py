"""Monte Carlo Simulation — probability of ruin + equity path distribution."""
import streamlit as st
import plotly.graph_objects as go
import numpy as np
import pandas as pd


def _run_monte_carlo(n_paths, n_trades, win_rate, avg_win, avg_loss,
                     initial_balance, ruin_threshold, seed=42):
    rng = np.random.default_rng(seed)
    paths = np.zeros((n_paths, n_trades + 1))
    paths[:, 0] = initial_balance
    for step in range(n_trades):
        wins  = rng.random(n_paths) < (win_rate / 100)
        pnl   = np.where(wins, avg_win, -avg_loss)
        paths[:, step + 1] = paths[:, step] + pnl
    # Ruin = balance drops below threshold
    ruin_count = np.sum(np.any(paths < ruin_threshold, axis=1))
    final       = paths[:, -1]
    return paths, final, ruin_count / n_paths * 100


def render():
    st.markdown('<h1 style="color:#FFD700">🎲 Monte Carlo Simulation</h1>', unsafe_allow_html=True)
    st.caption("1,000+ equity path simulation | Probability of ruin | Percentile distribution")

    c1, c2, c3 = st.columns(3)
    with c1:
        n_paths         = st.slider("Simulation Paths", 100, 5000, 1000, 100)
        n_trades        = st.slider("Trades per Path",  50, 500, 200)
        initial_balance = st.number_input("Initial Balance ($)", value=10000, step=1000)
    with c2:
        win_rate  = st.slider("Win Rate (%)",   30.0, 80.0, 58.0, 0.5)
        avg_win   = st.number_input("Avg Win ($)",  value=150.0, step=10.0)
        avg_loss  = st.number_input("Avg Loss ($)", value=80.0,  step=10.0)
    with c3:
        ruin_threshold = st.number_input("Ruin Threshold ($)", value=5000, step=500)
        show_paths     = st.slider("Display Paths", 10, 200, 50)
        seed           = st.number_input("Random Seed", value=42, step=1)

    if st.button("🚀 Run Monte Carlo", type="primary", use_container_width=True):
        with st.spinner(f"Simulating {n_paths:,} paths x {n_trades} trades..."):
            paths, final, ruin_pct = _run_monte_carlo(
                n_paths, n_trades, win_rate, avg_win, avg_loss,
                initial_balance, ruin_threshold, int(seed)
            )
            st.session_state["mc_paths"]   = paths
            st.session_state["mc_final"]   = final
            st.session_state["mc_ruin"]    = ruin_pct
            st.session_state["mc_n_paths"] = n_paths

    if "mc_paths" not in st.session_state:
        st.info("▶️ Configure and click Run Monte Carlo."); return

    paths   = st.session_state["mc_paths"]
    final   = st.session_state["mc_final"]
    ruin_pct= st.session_state["mc_ruin"]

    st.divider()
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Paths",          f"{len(paths):,}")
    m2.metric("Prob of Ruin",   f"{ruin_pct:.1f}%",
              delta="HIGH" if ruin_pct > 20 else "LOW",
              delta_color="inverse")
    m3.metric("Median Final",   f"${np.median(final):,.0f}")
    m4.metric("P10 (Worst 10%)",f"${np.percentile(final,10):,.0f}")
    m5.metric("P90 (Best 10%)", f"${np.percentile(final,90):,.0f}")
    m6.metric("Profit Factor",  f"{(win_rate/100*avg_win)/((1-win_rate/100)*avg_loss):.2f}")

    st.divider()
    col_paths, col_dist = st.columns([3, 1])

    with col_paths:
        st.subheader(f"📉 {min(show_paths, len(paths))} Sample Paths")
        fig = go.Figure()
        sample_idx = np.random.choice(len(paths), min(show_paths, len(paths)), replace=False)
        for i, idx in enumerate(sample_idx):
            color = "rgba(246,70,93,0.3)" if np.any(paths[idx] < ruin_threshold) \
                    else "rgba(255,215,0,0.15)"
            fig.add_trace(go.Scatter(y=paths[idx], mode="lines",
                                     line=dict(color=color, width=1),
                                     showlegend=False))
        # Add percentile bands
        p10 = np.percentile(paths, 10, axis=0)
        p50 = np.percentile(paths, 50, axis=0)
        p90 = np.percentile(paths, 90, axis=0)
        fig.add_trace(go.Scatter(y=p90, mode="lines",
                                 line=dict(color="#0ECB81", width=2, dash="dash"),
                                 name="P90"))
        fig.add_trace(go.Scatter(y=p50, mode="lines",
                                 line=dict(color="#FFD700", width=2),
                                 name="Median"))
        fig.add_trace(go.Scatter(y=p10, mode="lines",
                                 line=dict(color="#F6465D", width=2, dash="dash"),
                                 name="P10"))
        fig.add_hline(y=ruin_threshold, line_dash="dot", line_color="#F6465D",
                      annotation_text=f"Ruin: ${ruin_threshold:,}")
        fig.update_layout(template="plotly_dark", height=400,
                          margin=dict(l=0,r=0,t=30,b=0),
                          paper_bgcolor="#1E2329", plot_bgcolor="#1E2329",
                          xaxis_title="Trade #", yaxis_title="Balance ($)")
        st.plotly_chart(fig, use_container_width=True)

    with col_dist:
        st.subheader("📊 Final Distribution")
        fig2 = go.Figure(go.Histogram(
            x=final, nbinsx=40,
            marker_color="#FFD700",
            marker_line_color="#0E1117",
            marker_line_width=1,
            orientation="v"
        ))
        fig2.add_vline(x=initial_balance, line_dash="dash",
                       line_color="#F0B90B",
                       annotation_text="Initial")
        fig2.add_vline(x=ruin_threshold, line_dash="dot",
                       line_color="#F6465D",
                       annotation_text="Ruin")
        fig2.update_layout(template="plotly_dark", height=400,
                           margin=dict(l=0,r=0,t=30,b=0),
                           paper_bgcolor="#1E2329", plot_bgcolor="#1E2329")
        st.plotly_chart(fig2, use_container_width=True)

    # Percentile table
    st.subheader("📊 Percentile Summary")
    pcts = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    pct_data = {
        "Percentile": [f"P{p}" for p in pcts],
        "Final Balance ($)": [f"${np.percentile(final, p):,.0f}" for p in pcts],
        "Return (%)": [f"{(np.percentile(final,p)-initial_balance)/initial_balance*100:+.1f}%" for p in pcts],
    }
    st.dataframe(pd.DataFrame(pct_data), use_container_width=True, hide_index=True)
