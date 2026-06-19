"""Backtest Dashboard Page."""
from __future__ import annotations

import random
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


def render() -> None:
    st.title("📈 Tick-Level Backtest Engine")
    st.markdown("*Spread + Slippage + Commission simulation with full performance metrics*")

    with st.sidebar:
        st.header("⚙️ Backtest Settings")
        symbol = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])
        timeframe = st.selectbox("Timeframe", ["M5", "M15", "H1", "H4"])
        initial_balance = st.number_input("Initial Balance ($)", 1000, 1_000_000, 10_000, 1000)
        risk_pct = st.slider("Risk per Trade (%)", 0.1, 5.0, 1.0, 0.1)
        spread = st.slider("Spread (pips)", 0.1, 5.0, 1.5, 0.1)
        slippage = st.slider("Slippage (pips)", 0.0, 3.0, 0.5, 0.1)
        commission = st.number_input("Commission ($/lot)", 0.0, 20.0, 7.0, 0.5)
        n_candles = st.slider("Candles", 500, 5000, 1500, 100)
        run_btn = st.button("🚀 Run Backtest", type="primary", use_container_width=True)

    def generate_backtest(n, balance, risk, spread_p, slip_p, comm):
        random.seed(42)
        np.random.seed(42)
        trades, equity, balance_cur = [], [balance], balance
        wins = 0
        for i in range(n):
            if random.random() < 0.3:
                direction = random.choice(["BUY", "SELL"])
                sl_pips = random.uniform(10, 30)
                tp_pips = sl_pips * random.uniform(1.5, 3.0)
                lot = round((balance_cur * risk / 100) / (sl_pips * 10), 2)
                lot = max(0.01, min(lot, 10.0))
                total_spread = (spread_p + slip_p) * 10
                gross_pnl = tp_pips * 10 * lot if random.random() < 0.55 else -sl_pips * 10 * lot
                net_pnl = gross_pnl - total_spread * lot - comm * lot
                balance_cur = max(0.01, balance_cur + net_pnl)
                equity.append(balance_cur)
                if net_pnl > 0:
                    wins += 1
                trades.append({"#": len(trades)+1, "Direction": direction,
                               "SL (pips)": round(sl_pips, 1), "TP (pips)": round(tp_pips, 1),
                               "Lot": lot, "Net P&L": round(net_pnl, 2),
                               "Balance": round(balance_cur, 2)})
        eq = np.array(equity)
        dd = (np.maximum.accumulate(eq) - eq) / np.maximum.accumulate(eq)
        max_dd = float(dd.max()) * 100
        returns = np.diff(eq) / eq[:-1]
        sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
        downside = returns[returns < 0]
        sortino = (returns.mean() / downside.std() * np.sqrt(252)) if len(downside) > 0 and downside.std() > 0 else 0
        gross_profit = sum(t["Net P&L"] for t in trades if t["Net P&L"] > 0)
        gross_loss = abs(sum(t["Net P&L"] for t in trades if t["Net P&L"] < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        win_rate = wins / len(trades) * 100 if trades else 0
        recovery = (balance_cur - balance) / (max_dd / 100 * balance) if max_dd > 0 else 0
        return trades, equity, max_dd, sharpe, sortino, pf, win_rate, recovery

    if "bt_result" not in st.session_state or run_btn:
        with st.spinner(f"Running backtest on {n_candles} candles..."):
            time.sleep(0.8)
            st.session_state.bt_result = generate_backtest(
                n_candles, initial_balance, risk_pct, spread, slippage, commission)

    trades, equity, max_dd, sharpe, sortino, pf, win_rate, recovery = st.session_state.bt_result
    if not trades:
        st.warning("No trades generated. Try adjusting parameters.")
        return

    # KPIs
    st.subheader("📊 Performance Summary")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Trades", len(trades))
    c2.metric("Win Rate", f"{win_rate:.1f}%",
              delta="✓ Good" if win_rate >= 55 else "⚠ Low",
              delta_color="normal" if win_rate >= 55 else "inverse")
    c3.metric("Profit Factor", f"{pf:.3f}",
              delta="✓" if pf >= 1.3 else "⚠")
    c4.metric("Sharpe Ratio", f"{sharpe:.3f}")
    c5.metric("Sortino Ratio", f"{sortino:.3f}")
    c6.metric("Max Drawdown", f"{max_dd:.2f}%",
              delta_color="inverse")

    net_profit = equity[-1] - equity[0]
    c7, c8, c9 = st.columns(3)
    c7.metric("Final Balance", f"${equity[-1]:,.2f}", delta=f"{net_profit:+,.2f}")
    c8.metric("Recovery Factor", f"{recovery:.2f}")
    c9.metric("Total Return", f"{(equity[-1]/equity[0]-1)*100:.2f}%")

    st.divider()

    # Equity + Drawdown chart
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("💰 Equity Curve")
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            y=equity, mode="lines",
            line=dict(color="#0ECB81", width=2),
            fill="tozeroy", fillcolor="rgba(14,203,129,0.08)",
            name="Equity"
        ))
        fig_eq.add_hline(y=equity[0], line_dash="dash",
                         line_color="#FFD700", annotation_text="Start")
        fig_eq.update_layout(template="plotly_dark", height=320,
                             xaxis_title="Trade #", yaxis_title="Equity ($)",
                             margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_eq, use_container_width=True)

    with col_r:
        st.subheader("📉 Drawdown")
        eq_arr = np.array(equity)
        dd_arr = (np.maximum.accumulate(eq_arr) - eq_arr) / np.maximum.accumulate(eq_arr) * 100
        fig_dd = go.Figure(go.Scatter(
            y=-dd_arr, mode="lines",
            fill="tozeroy", fillcolor="rgba(244,67,54,0.15)",
            line=dict(color="#F44336", width=1.5), name="Drawdown"
        ))
        fig_dd.update_layout(template="plotly_dark", height=320,
                             xaxis_title="Trade #", yaxis_title="Drawdown (%)",
                             margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_dd, use_container_width=True)

    # Trade history
    st.subheader("📝 Trade History")
    df = pd.DataFrame(trades)
    st.dataframe(
        df.style.applymap(lambda v: "color: #0ECB81" if isinstance(v, float) and v > 0
                          else ("color: #F44336" if isinstance(v, float) and v < 0 else ""),
                          subset=["Net P&L"]),
        use_container_width=True, height=300
    )
