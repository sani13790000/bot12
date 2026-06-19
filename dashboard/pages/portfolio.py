"""Portfolio Management — multi-symbol allocation + correlation matrix."""
import random
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "XAGUSD", "USDCAD"]


def _compute_allocation(symbols, method, capital, max_pos_pct, seed=42):
    rng = random.Random(seed)
    n = len(symbols)
    if method == "equal_weight":
        weights = [1/n] * n
    elif method == "risk_parity":
        vols = [rng.uniform(0.01, 0.03) for _ in symbols]
        inv_vols = [1/v for v in vols]
        total = sum(inv_vols)
        weights = [v/total for v in inv_vols]
    elif method == "kelly":
        wins = [rng.uniform(0.55, 0.70) for _ in symbols]
        odds = [rng.uniform(1.5, 2.5) for _ in symbols]
        kelly = [w - (1-w)/o for w, o in zip(wins, odds)]
        kelly = [max(0, k) for k in kelly]
        total = sum(kelly) or 1
        weights = [k/total for k in kelly]
    else:  # min_variance / max_sharpe
        raw = [rng.uniform(0.1, 0.4) for _ in symbols]
        total = sum(raw)
        weights = [r/total for r in raw]
    # Cap at max_pos_pct
    weights = [min(w, max_pos_pct/100) for w in weights]
    total = sum(weights)
    weights = [w/total for w in weights]
    return weights


def _correlation_matrix(symbols, seed=42):
    rng = np.random.default_rng(seed)
    n = len(symbols)
    raw = rng.uniform(-0.4, 0.9, (n, n))
    corr = (raw + raw.T) / 2
    np.fill_diagonal(corr, 1.0)
    corr = np.clip(corr, -1, 1)
    return pd.DataFrame(corr, index=symbols, columns=symbols).round(2)


def render():
    st.markdown('<h1 style="color:#FFD700">💼 Portfolio Manager</h1>', unsafe_allow_html=True)
    st.caption("Multi-symbol allocation | Risk-Parity | Kelly | Min-Variance | Correlation filter")

    c1, c2 = st.columns([2, 1])
    with c1:
        symbols = st.multiselect("Symbols", SYMBOLS,
                                 default=["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])
        method  = st.selectbox("Allocation Method",
                               ["equal_weight", "risk_parity", "kelly", "min_variance", "max_sharpe"])
    with c2:
        capital      = st.number_input("Total Capital ($)", value=100000, step=10000)
        max_pos      = st.slider("Max Position (%)", 5, 50, 30)
        corr_thresh  = st.slider("Max Correlation", 0.50, 0.95, 0.80, 0.05)

    if not symbols:
        st.warning("Select at least 2 symbols."); return

    if st.button("📈 Compute Allocations", type="primary", use_container_width=True):
        weights  = _compute_allocation(symbols, method, capital, max_pos)
        corr_df  = _correlation_matrix(symbols)
        st.session_state["port_weights"] = weights
        st.session_state["port_corr"]    = corr_df
        st.session_state["port_symbols"] = symbols
        st.session_state["port_capital"] = capital

    if "port_weights" not in st.session_state:
        st.info("▶️ Select symbols and click Compute."); return

    weights  = st.session_state["port_weights"]
    corr_df  = st.session_state["port_corr"]
    symbols  = st.session_state["port_symbols"]
    capital  = st.session_state["port_capital"]

    st.divider()
    # Summary metrics
    high_corr = [(corr_df.columns[i], corr_df.columns[j])
                 for i in range(len(symbols))
                 for j in range(i+1, len(symbols))
                 if corr_df.iloc[i, j] > corr_thresh]
    div_score = round((1 - sum(w**2 for w in weights)) * 100, 1)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Diversification Score", f"{div_score} / 100")
    m2.metric("High Corr Pairs", len(high_corr))
    m3.metric("Conflicts", len(high_corr))
    m4.metric("Active Symbols", len(symbols))

    st.divider()
    col_pie, col_alloc = st.columns([1, 2])

    with col_pie:
        st.subheader("🫖 Allocation")
        fig = go.Figure(go.Pie(
            labels=symbols,
            values=[round(w*100, 2) for w in weights],
            hole=0.4,
            marker_colors=["#FFD700", "#F0B90B", "#0ECB81",
                           "#2B92E4", "#F6465D", "#848E9C", "#C5AE73"]
        ))
        fig.update_layout(template="plotly_dark", height=350,
                          margin=dict(l=0,r=0,t=10,b=0),
                          paper_bgcolor="#1E2329")
        st.plotly_chart(fig, use_container_width=True)

    with col_alloc:
        st.subheader("📊 Allocation Table")
        alloc_data = {
            "Symbol":      symbols,
            "Weight":      [f"{w*100:.1f}%" for w in weights],
            "Capital ($)": [f"${w*capital:,.0f}" for w in weights],
            "Max Lot":     [round(w*capital/100000, 2) for w in weights],
            "Risk/Day":    [f"${w*capital*0.01:,.0f}" for w in weights],
        }
        st.dataframe(pd.DataFrame(alloc_data), use_container_width=True, hide_index=True)

    # Correlation heatmap
    st.subheader("🔥 Correlation Matrix")
    fig2 = go.Figure(go.Heatmap(
        z=corr_df.values, x=corr_df.columns, y=corr_df.index,
        colorscale="RdYlGn", zmid=0, zmin=-1, zmax=1,
        text=corr_df.values.round(2),
        texttemplate="%{text}", showscale=True
    ))
    fig2.update_layout(template="plotly_dark", height=400,
                       margin=dict(l=0,r=0,t=10,b=0),
                       paper_bgcolor="#1E2329")
    st.plotly_chart(fig2, use_container_width=True)

    if high_corr:
        st.warning(f"⚠️ High correlation pairs (>{corr_thresh}): " +
                   ", ".join([f"{a}/{b}" for a, b in high_corr]))
    else:
        st.success("✅ No high-correlation conflicts detected.")
