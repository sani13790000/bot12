# 🌌 Galaxy Vast AI Trading Platform

**Institutional-grade AI trading framework** for XAUUSD and multi-asset markets.

[![CI](https://github.com/sani13790000/bot12/actions/workflows/ci.yml/badge.svg)](https://github.com/sani13790000/bot12/actions)

---

## 🏛 Architecture

```
FastAPI + Streamlit + PostgreSQL/Superbase + Redis + Docker + MetaTrader5 + XGBoost + Reinforcement Learning
```

---

## ✨ What It Does

Galaxy Vast is a fully automated, institutional-grade trading system that:

- **Analyzes** XAUUSD (and other symbols) using 7 parallel AI agents
- **Decides** when to BUY, SELL, or stay out via a voting engine
- **Manages risk** with VaR, CVaR, Kelly sizing, and drawdown circuit breakers
- **Executes** trades through MetaTrader 5
- **Learns** continuously with XGBoost + Walk-Forward validation + Concept Drift detection
- **Replays** historical markets candle-by-candle
- **Backtests** tick-level strategies across multiple symbols and timeframes
- **Optimizes** parameters with Walk-Forward Analysis
- **Reports** everything through a Streamlit dashboard and Telegram

---

## 🚀 Quick Start

### 1. Clone

```bash
git clone https://github.com/sani13790000/bot12.git
cd bot12
```

### 2. Environment

```bash
cp .env.example .env
# Edit .env with your Supabase, Telegram, and MT5 credentials
```

### 3. Run with Docker

```bash
docker compose up -d --build
```

Services:

| Service | URL | Description |
|---------|-----|-------------|
| FastAPI | http://localhost:8000 | Trading API + research endpoints |
| Streamlit | http://localhost:8501 | Interactive dashboard |
| Telegram Bot | — | Control and alerts |

### 4. Health Check

```bash
curl http://localhost:8000/health
```

---

## 📦 Modules

### 1. Market Replay Engine
- Candle-by-candle playback
- Play / Pause / Stop / Step forward / Step backward
- Speed: x1, x2, x4, x10
- Trade entry/exit markers
- Signal overlay

### 2. Tick-Level Backtest Engine
- Simulates bid/ask/last ticks inside OHLC candles
- Spread, slippage, and commission modeling
- Multi-symbol and multi-timeframe support
- Market / Limit / Stop orders

### 3. Walk-Forward Optimization
- Train / Validation / Test periods
- Automatic parameter grid search
- Robustness score and recommendation

### 4. Performance Metrics
- Win rate, profit factor, Sharpe, Sortino, Calmar
- Max drawdown (pct & USD)
- Recovery factor, expectancy, average R:R
- CAGR, volatility, Ulcer index, skewness, kurtosis

### 5. Streamlit Dashboard
- Market Replay page
- Backtest page with equity curve
- Portfolio allocation
- Correlation heatmap
- AI explainability
- RL agent training/prediction

### 6. AI Explainability
- BOS / CHOCH detection
- Order Block count
- Fair Value Gap count
- Liquidity sweep detection
- Premium / Discount / Equilibrium zone
- Per-agent confidence scores

### 7. Reinforcement Learning Agent
- Custom Gymnasium trading environment
- Stable-Baselines3 PPO
- Train / predict / persist

### 8. Portfolio Management
- Equal weight, risk parity, minimum variance, Kelly criterion
- Risk-capped position sizing
- Multi-symbol allocation

### 9. Correlation Engine
- Cross-asset correlation matrix
- Cointegration testing
- Conflicting signal filtering

### 10. Monte Carlo Simulation
- 1,000+ equity-path simulations
- Probability of ruin
- Drawdown distribution
- Confidence intervals

### 11. Institutional Risk Engine
- VaR (95% / 99%) and CVaR
- Recommended position size
- Drawdown circuit breaker
- Exposure limits

### 12. Data Persistence
- All trades saved to PostgreSQL / Supabase
- Backtest results, replay sessions, and RL models persisted
- Row-Level Security per user

---

## 🧪 Testing

```bash
pytest backend/tests/ -v --asyncio-mode=auto --cov=backend --cov-report=html
```

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI, Uvicorn |
| Dashboard | Streamlit, Plotly |
| Database | PostgreSQL, Supabase, SQLAlchemy, Alembic |
| Cache | Redis |
| ML | scikit-learn, XGBoost, Stable-Baselines3, PyTorch |
| Data | pandas, yfinance, pandas-ta |
| Execution | MetaTrader 5 |
| Ops | Docker, Docker Compose, Sentry, Prometheus |

---

## 📂 Repository Structure

```
backend/
  agents/              # SMC, PA, ML, Risk, News, Liquidity agents
  analysis/            # SMC engine + decision engine
  api/                 # FastAPI app and routes
  backtest_engine/     # Multi-symbol + walk-forward
  database/            # Supabase/PostgreSQL connection
  execution/           # MT5 connector + order state machine
  institutional/       # ⭐ New institutional modules
  ml_engine.py         # XGBoost + drift detection
  risk/                # Risk orchestrator
  telegram/            # Telegram bot
  tests/               # Test suite

dashboard/             # Streamlit app + pages
supabase/migrations/   # Database migrations
mql5/                  # MetaTrader 5 EA and libraries
```

---

## ⚠️ Disclaimer

This software is for educational and research purposes. Trading financial instruments involves substantial risk. Past performance does not guarantee future results. Always test thoroughly on a demo account before deploying live capital.

---

## 📄 License

Proprietary — Galaxy Vast AI Trading Team.
