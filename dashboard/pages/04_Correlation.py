"""Correlation engine page."""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from api_client import APIClient

st.set_page_config(page_title="Correlation", layout="wide")
st.title("🔗 Correlation Engine")

client = APIClient()

symbols = st.multiselect("Symbols", ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "US30", "BTCUSD"], default=["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"])

if st.button("🔍 Analyze Correlations"):
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.utcnow(), periods=100, freq="D")
    price_series = {}
    base = {"XAUUSD": 2350, "EURUSD": 1.08, "GBPUSD": 1.26, "USDJPY": 150.0, "US30": 39000.0, "BTCUSD": 65000.0}
    for sym in symbols:
        price = base.get(sym, 100.0)
        series = []
        for _ in range(100):
            price *= (1 + np.random.normal(0, 0.01))
            series.append(price)
        price_series[sym] = series

    payload = {"symbols": symbols, "price_series": price_series}
    result = client.correlation(payload)
    if "error" in result:
        st.error(result["error"])
    else:
        pairs = result.get("pairs", [])
        if pairs:
            df = pd.DataFrame(pairs)
            st.dataframe(df)
            corr_data = []
            for p in pairs:
                a, b = p["symbol_pair"]
                corr_data.append((a, b, p["correlation"]))
            matrix = pd.DataFrame(index=symbols, columns=symbols, dtype=float).fillna(1.0)
            for a, b, c in corr_data:
                matrix.loc[a, b] = c
                matrix.loc[b, a] = c
            fig = px.imshow(matrix.astype(float), text_auto=".2f", aspect="auto", color_continuous_scale="RdBu_r", zmin=-1, zmax=1)
            st.plotly_chart(fig, use_container_width=True)
