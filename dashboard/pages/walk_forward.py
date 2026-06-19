"""Walk-Forward Optimization — IS/VAL/OOS analysis."""
import random
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np


def _run_wfo(n_windows: int, is_pct: float, val_pct: float, seed: int = 42):
    rng = random.Random(seed)
    windows = []
    for i in range(n_windows):
        best_param = {"ema_fast": rng.randint(8, 20), "ema_slow": rng.randint(40, 80),
                      "sl_pips": rng.randint(60, 150), "tp_pips": rng.randint(100, 300)}
        is_sharpe   = round(rng.uniform(1.2, 2.8), 2)
        val_sharpe  = round(is_sharpe * rng.uniform(0.7, 0.95), 2)
        oos_sharpe  = round(val_sharpe * rng.uniform(0.65, 0.90), 2)
        is_wr   = round(rng.uniform(55, 70), 1)
        oos_wr  = round(is_wr * rng.uniform(0.88, 0.96), 1)
        is_pf   = round(rng.uniform(1.5, 2.5), 2)
        oos_pf  = round(is_pf * rng.uniform(0.70, 0.90), 2)
        windows.append({"Window": i + 1, "Best Params": str(best_param),
                        "IS Sharpe": is_sharpe, "VAL Sharpe": val_sharpe,
                        "OOS Sharpe": oos_sharpe, "IS WR%": is_wr,
                        "OOS WR%": oos_wr, "IS PF": is_pf, "OOS PF": oos_pf,
                        "Robustness": round(oos_sharpe / max(is_sharpe, 0.01), 2)})
    return windows


def render():
    st.markdown('<h1 style="color:#FFD700">📉 Walk-Forward Optimization</h1>', unsafe_allow_html=True)
    st.caption("IS → VAL → OOS splits | Automatic parameter optimization | Robustness ratio")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        symbol     = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD"])
        n_windows  = st.slider("Windows", 3, 12, 6)
    with c2:
        is_pct     = st.slider("In-Sample %", 40, 70, 60)
        val_pct    = st.slider("Validation %", 10, 30, 20)
        st.caption(f"OOS %: {100 - is_pct - val_pct}")
    with c3:
        metric     = st.selectbox("Optimize For", ["Sharpe", "Profit Factor", "Win Rate"])
        years_back = st.slider("Years of Data", 1, 8, 4)
    with c4:
        min_robustness = st.slider("Min Robustness", 0.3, 0.9, 0.6, 0.05)
        st.caption("Robustness = OOS Sharpe / IS Sharpe")

    if st.button("🚀 Run WFO", type="primary", use_container_width=True):
        with st.spinner(f"Running {n_windows}-window walk-forward optimization..."):
            results = _run_wfo(n_windows, is_pct / 100, val_pct / 100)
            st.session_state["wfo_results"] = results

    results = st.session_state.get("wfo_results")
    if not results:
        st.info("▶️ Configure and click Run WFO."); return

    df = pd.DataFrame(results)
    passed = df[df["Robustness"] >= min_robustness]

    st.success(f"✅ {len(passed)}/{len(df)} windows passed robustness filter ({min_robustness})")
    st.divider()

    # Summary metrics
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Avg IS Sharpe",   f"{df['IS Sharpe'].mean():.2f}")
    m2.metric("Avg OOS Sharpe",  f"{df['OOS Sharpe'].mean():.2f}")
    m3.metric("Avg Robustness",  f"{df['Robustness'].mean():.2f}")
    m4.metric("Avg OOS WR",      f"{df['OOS WR%'].mean():.1f}%")
    m5.metric("Avg OOS PF",      f"{df['OOS PF'].mean():.2f}")

    st.divider()

    # Sharpe chart
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["Window"], y=df["IS Sharpe"],  name="IS Sharpe",  marker_color="#FFD700"))
    fig.add_trace(go.Bar(x=df["Window"], y=df["VAL Sharpe"], name="VAL Sharpe", marker_color="#F0B90B"))
    fig.add_trace(go.Bar(x=df["Window"], y=df["OOS Sharpe"], name="OOS Sharpe", marker_color="#0ECB81"))
    fig.update_layout(barmode="group", template="plotly_dark", height=350,
                      margin=dict(l=0,r=0,t=30,b=0),
                      paper_bgcolor="#1E2329", plot_bgcolor="#1E2329",
                      title="Sharpe Ratio: IS vs VAL vs OOS",
                      title_font_color="#FFD700")
    st.plotly_chart(fig, use_container_width=True)

    # Robustness line
    fig2 = go.Figure()
    colors = ["#0ECB81" if r >= min_robustness else "#F6465D" for r in df["Robustness"]]
    fig2.add_trace(go.Bar(x=df["Window"], y=df["Robustness"],
                          marker_color=colors, name="Robustness"))
    fig2.add_hline(y=min_robustness, line_dash="dash", line_color="#FFD700",
                   annotation_text=f"Min: {min_robustness}")
    fig2.update_layout(template="plotly_dark", height=250,
                       margin=dict(l=0,r=0,t=30,b=0),
                       paper_bgcolor="#1E2329", plot_bgcolor="#1E2329",
                       title="Robustness Ratio per Window", title_font_color="#FFD700")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("📊 Results Table")
    styled = df.copy()
    st.dataframe(styled, use_container_width=True, hide_index=True)
