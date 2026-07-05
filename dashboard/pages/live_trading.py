"""Live Trading page — Phase I: Real-time positions from REST API."""
from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render(api_get: Callable, api_base: str) -> None:
    st.title("💹 Live Trades")
    col1, col2, col3, col4 = st.columns(4)
    account = api_get("/metrics/account")
    if account:
        col1.metric("Equity", f"${account.get('equity', 0):,.2f}", delta=f"{account.get('equity_change_pct', 0):+.2f}%")
        col2.metric("Balance", f"${account.get('balance', 0):,.2f}")
        col3.metric("Free Margin", f"${account.get('free_margin', 0):,.2f}")
        col4.metric("Margin Level", f"{account.get('margin_level', 0):.1f}%")
    else:
        for c in [col1, col2, col3, col4]:
            c.metric("—", "—")
    st.markdown("---")
    ks = api_get("/health/kill-switch")
    if ks:
        if ks.get("kill_switch_active", False):
            st.error("🚨 KILL SWITCH ACTIVE — Trading is halted")
        else:
            st.success("✅ Kill Switch: Inactive — Trading enabled")
    st.subheader("📌 Open Positions")
    positions: Optional[List[Dict]] = api_get("/trades/positions")
    if positions is None:
        st.warning("Cannot fetch positions — API unavailable")
    elif len(positions) == 0:
        st.info("No open positions")
    else:
        df = pd.DataFrame(positions)
        fmt: Dict = {}
        for col in ["open_price", "current_price", "sl", "tp"]:
            if col in df.columns:
                fmt[col] = "{:.5f}"
        if "profit" in df.columns:
            fmt["profit"] = "${:.2f}"
        st.dataframe(df.style.format(fmt, na_rep="—"), use_container_width=True)
        if "profit" in df.columns:
            fig = go.Figure(go.Bar(x=df.get("symbol", df.index), y=df["profit"],
                                   marker_color=["green" if p >= 0 else "red" for p in df["profit"]]))
            fig.update_layout(title="Open P&L by Position", height=280, template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")
    st.subheader("📡 Recent Signals")
    sigs = api_get("/signals/recent?limit=20")
    if sigs:
        st.dataframe(pd.DataFrame(sigs), use_container_width=True)
    else:
        st.info("No recent signals")
    st.markdown("---")
    st.subheader("📋 Recent Closed Trades")
    trades = api_get("/trades/?limit=20")
    if trades:
        st.dataframe(pd.DataFrame(trades), use_container_width=True)
    else:
        st.info("No closed trades yet")
    with st.expander("ℹ️ WebSocket URL"):
        st.code(api_base.replace("http", "ws") + "/ws/positions")
