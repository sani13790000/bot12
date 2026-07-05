"""Portfolio page — Phase I: live equity + KPIs from API."""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st


def render(api_get: Callable) -> None:
    st.title("💼 Portfolio Analytics")
    st.subheader("📈 Equity Curve")
    eq = api_get("/metrics/equity?days=30")
    if eq and "curve" in eq:
        df_eq = pd.DataFrame(eq["curve"])
        if not df_eq.empty and "timestamp" in df_eq.columns and "equity" in df_eq.columns:
            df_eq["timestamp"] = pd.to_datetime(df_eq["timestamp"])
            fig = go.Figure(go.Scatter(x=df_eq["timestamp"], y=df_eq["equity"], mode="lines",
                                       line=dict(color="#00D4FF", width=2), fill="tozeroy",
                                       fillcolor="rgba(0,212,255,0.1)"))
            fig.update_layout(title="30-Day Equity Curve", height=380, template="plotly_dark",
                               xaxis_title="Date", yaxis_title="Equity ($)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough data yet")
    else:
        st.info("Equity curve unavailable")
    st.markdown("---")
    st.subheader("📊 Performance KPIs")
    kpis = api_get("/metrics/performance")
    if kpis:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Win Rate", f"{kpis.get('win_rate', 0)*100:.1f}%")
        c2.metric("Profit Factor", f"{kpis.get('profit_factor', 0):.2f}")
        c3.metric("Sharpe Ratio", f"{kpis.get('sharpe_ratio', 0):.2f}")
        c4.metric("Max Drawdown", f"{kpis.get('max_drawdown', 0)*100:.1f}%")
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Total Trades", kpis.get('total_trades', 0))
        c6.metric("Avg RR", f"{kpis.get('avg_rr', 0):.2f}")
        c7.metric("Total PnL", f"${kpis.get('total_pnl', 0):,.2f}")
        c8.metric("Avg Holding (min)", f"{kpis.get('avg_holding_minutes', 0):.0f}")
    else:
        st.info("Performance data not available")
    st.markdown("---")
    st.subheader("🥧 PnL by Symbol")
    sym = api_get("/metrics/by-symbol")
    if sym:
        df_s = pd.DataFrame(sym)
        if not df_s.empty:
            fig2 = px.pie(df_s, values="total_pnl", names="symbol", title="PnL by Symbol", template="plotly_dark")
            st.plotly_chart(fig2, use_container_width=True)
            st.dataframe(df_s, use_container_width=True)
    else:
        st.info("No symbol data yet")
