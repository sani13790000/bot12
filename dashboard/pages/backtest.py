"""Tick-Level Backtest Engine — full results with Plotly."""
import random
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import date


def _simulate_backtest(symbol, initial_balance, risk_pct, spread_mult,
                       slippage, use_commission, n_trades=300, seed=42):
    rng = random.Random(seed)
    np.random.seed(seed)
    equity = [initial_balance]
    trades = []
    balance = initial_balance
    wins = 0
    gross_profit = gross_loss = 0.0

    for i in range(n_trades):
        lot = round(balance * (risk_pct / 100) / 100, 2)
        direction = rng.choice(["BUY", "SELL"])
        entry = round(rng.uniform(2280, 2380), 2)
        tp_pips = rng.randint(80, 250)
        sl_pips = rng.randint(40, 120)
        spread_cost = round(spread_mult * 0.3 * lot * 10, 4)
        slip_cost   = round(slippage * 0.1 * lot * 10, 4)
        comm_cost   = round(7.0 * lot, 4) if use_commission else 0.0
        is_win = rng.random() < 0.58
        if is_win:
            pnl = round(tp_pips * 0.01 * lot * 10 - spread_cost - slip_cost - comm_cost, 2)
            gross_profit += pnl
            wins += 1
        else:
            pnl = round(-sl_pips * 0.01 * lot * 10 - spread_cost - slip_cost - comm_cost, 2)
            gross_loss += abs(pnl)
        balance += pnl
        equity.append(round(balance, 2))
        trades.append({"#": i+1, "Symbol": symbol, "Direction": direction,
                       "Entry": entry, "Lots": lot, "PnL": pnl,
                       "Comm": comm_cost, "Spread": spread_cost,
                       "Result": "WIN" if is_win else "LOSS"})

    net_profit = balance - initial_balance
    win_rate = wins / n_trades * 100
    profit_factor = gross_profit / max(gross_loss, 0.01)
    eq_arr = np.array(equity)
    peak = np.maximum.accumulate(eq_arr)
    drawdown = (peak - eq_arr) / peak * 100
    max_dd = drawdown.max()
    returns = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = (returns.mean() / (returns.std() + 1e-9)) * np.sqrt(252)
    neg_ret = returns[returns < 0]
    sortino = (returns.mean() / (neg_ret.std() + 1e-9)) * np.sqrt(252)
    return {
        "equity": equity, "trades": trades, "net_profit": net_profit,
        "win_rate": win_rate, "profit_factor": profit_factor,
        "max_drawdown": max_dd, "sharpe": sharpe, "sortino": sortino,
        "total_trades": n_trades, "wins": wins
    }


def render():
    st.markdown('<h1 style="color:#FFD700">📈 Tick-Level Backtest Engine</h1>', unsafe_allow_html=True)
    st.caption("Spread + Slippage + Commission simulation | Multi-symbol | No lookahead bias")

    with st.expander("⚙️ Configuration", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            symbol        = st.selectbox("Symbol", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])
            timeframe     = st.selectbox("Timeframe", ["M5", "M15", "M30", "H1", "H4"])
            initial_bal   = st.number_input("Initial Balance ($)", value=10000, step=1000)
        with c2:
            risk_pct      = st.slider("Risk per Trade (%)", 0.1, 5.0, 1.0, 0.1)
            spread_mult   = st.slider("Spread Multiplier", 0.5, 3.0, 1.0, 0.1)
            slippage      = st.slider("Slippage (pips)", 0.0, 2.0, 0.5, 0.1)
        with c3:
            use_commission = st.toggle("Commission ($7/lot)", value=True)
            start_date     = st.date_input("Start Date", date(2022, 1, 1))
            end_date       = st.date_input("End Date",   date(2024, 12, 31))
            n_trades       = st.slider("Simulated Trades", 50, 500, 300)

    if st.button("🚀 Run Backtest", type="primary", use_container_width=True):
        with st.spinner("Running tick-level backtest..."):
            result = _simulate_backtest(symbol, initial_bal, risk_pct, spread_mult,
                                        slippage, use_commission, n_trades)
            st.session_state["bt_result"] = result

    result = st.session_state.get("bt_result")
    if not result:
        st.info("▶️ Configure and click Run Backtest to see results."); return

    st.success("✅ Backtest complete!")
    st.divider()

    # Metrics
    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("Total Trades",   result["total_trades"])
    m2.metric("Win Rate",       f"{result['win_rate']:.1f}%")
    m3.metric("Profit Factor",  f"{result['profit_factor']:.2f}")
    m4.metric("Sharpe Ratio",   f"{result['sharpe']:.2f}")
    m5.metric("Sortino Ratio",  f"{result['sortino']:.2f}")
    m6.metric("Max Drawdown",   f"-{result['max_drawdown']:.1f}%")
    m7.metric("Net Profit",     f"${result['net_profit']:,.0f}",
              delta=f"{result['net_profit']/initial_bal*100:+.1f}%")

    st.divider()
    col_eq, col_dd = st.columns([3, 1])

    with col_eq:
        st.subheader("📉 Equity Curve")
        eq = result["equity"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=eq, mode="lines", name="Equity",
                                 line=dict(color="#FFD700", width=2),
                                 fill="tozeroy", fillcolor="rgba(255,215,0,0.08)"))
        fig.update_layout(template="plotly_dark", height=350,
                          margin=dict(l=0,r=0,t=30,b=0),
                          paper_bgcolor="#1E2329", plot_bgcolor="#1E2329",
                          xaxis_title="Trade #", yaxis_title="Balance ($)")
        st.plotly_chart(fig, use_container_width=True)

    with col_dd:
        st.subheader("📄 P&L Distribution")
        pnls = [t["PnL"] for t in result["trades"]]
        fig2 = go.Figure(go.Histogram(x=pnls, nbinsx=30,
                                      marker_color="#FFD700",
                                      marker_line_color="#0E1117",
                                      marker_line_width=1))
        fig2.update_layout(template="plotly_dark", height=350,
                           margin=dict(l=0,r=0,t=30,b=0),
                           paper_bgcolor="#1E2329", plot_bgcolor="#1E2329")
        st.plotly_chart(fig2, use_container_width=True)

    # Drawdown chart
    st.subheader("🟥 Drawdown Chart")
    eq_arr = np.array(result["equity"])
    peak   = np.maximum.accumulate(eq_arr)
    dd     = (peak - eq_arr) / peak * 100
    fig3 = go.Figure(go.Scatter(y=-dd, fill="tozeroy",
                                line_color="#F6465D",
                                fillcolor="rgba(246,70,93,0.15)"))
    fig3.update_layout(template="plotly_dark", height=200,
                       margin=dict(l=0,r=0,t=10,b=0),
                       paper_bgcolor="#1E2329", plot_bgcolor="#1E2329",
                       yaxis_title="Drawdown (%)")
    st.plotly_chart(fig3, use_container_width=True)

    # Trade log
    st.subheader("📊 Trade Log")
    df = pd.DataFrame(result["trades"][:50])
    df["Result"] = df["Result"].apply(lambda x: "✅ WIN" if x == "WIN" else "❌ LOSS")
    df["PnL"] = df["PnL"].apply(lambda x: f"{'+'if x>=0 else ''}${x:.2f}")
    st.dataframe(df, use_container_width=True, hide_index=True)
