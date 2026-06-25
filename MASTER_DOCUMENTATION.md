# MASTER DOCUMENTATION
# Galaxy Vast AI Trading Platform

> **نسخه:** 2.0.0 | **تاریخ:** 2026-06-25 | **وضعیت:** Production-Ready

---

## راهنمای استفاده از این سند

| مخاطب | بخش‌های پیشنهادی |
|--------|----------------|
| 🟢 **کاربر تازه‌کار** | بخش ۱ (معرفی) → بخش ۷ (نصب) → بخش ۸ (تنظیمات) |
| 🔵 **توسعه‌دهنده جدید** | بخش ۱ → ۲ → ۳ → ۷ → ۸ → ۱۷ |
| 🟣 **توسعه‌دهنده حرفه‌ای** | بخش ۲ → ۴ → ۵ → ۶ → ۱۷ → ۱۸ |
| 🟡 **مدیر پروژه** | بخش ۱ → ۲ → ۱۹ → ۲۰ → ۲۳ → ۲۵ |

---

# بخش ۱ — Project Overview

## ۱.۱ معرفی پروژه

**Galaxy Vast AI Trading Platform** یک پلتفرم معاملاتی هوش مصنوعی است که برای معامله‌گری خودکار و نیمه‌خودکار در بازارهای **Forex** و **CFD** از طریق **MetaTrader 5** طراحی شده است.

این سیستم چندین لایه هوشمند را با هم ترکیب می‌کند:
- 🤖 **هوش مصنوعی چندعاملی** — ۷ عامل مستقل موازی که با هم رأی می‌دهند
- 🛡️ **موتور ریسک ۷ لایه‌ای** — از Equity Protection تا Portfolio Risk
- ⚡ **اجرای سریع** — ارتباط مستقیم با MT5 از طریق Python API
- 📊 **یادگیری مستمر** — مدل ML خود را از نتایج معاملات آپدیت می‌کند
- 📱 **کنترل از راه دور** — Bot تلگرام برای مدیریت زنده

---

## ۱.۲ قابلیت‌های اصلی

### برای معامله‌گر تازه‌کار
| قابلیت | توضیح ساده |
|--------|----------|
| 📡 دریافت سیگنال از MT5 | EA در MetaTrader 5 سیگنال می‌فرستد، سیستم تصمیم می‌گیرد |
| 🧠 تحلیل هوشمند | ۷ هوش مصنوعی موازی سیگنال را بررسی می‌کنند |
| 🛑 محافظت از حساب | اگر ضرر از حد مشخص بگذرد، سیستم خودکار متوقف می‌شود |
| 📲 گزارش فوری | هر معامله از طریق تلگرام به شما اطلاع می‌دهد |
| 📈 بک‌تست | استراتژی خود را روی داده‌های گذشته آزمایش کنید |

### برای توسعه‌دهنده حرفه‌ای
| قابلیت | جزئیات فنی |
|--------|----------|
| Multi-Agent Voting | ۷ agent موازی با `asyncio.gather()`, weighted voting, veto power |
| 7-Gate Risk Engine | EquityProtection→DailyLimits→Volatility→Correlation→Exposure→Portfolio→LotSizer |
| Circuit Breaker | 5 failures/60s → OPEN state, half-open probing, lazy asyncio.Lock |
| ML Pipeline | XGBoost + Walk-Forward CV + CalibratedClassifierCV + auto-retrain |
| Institutional Analytics | Monte Carlo VaR, RL Agent (PPO/SAC), tick-level backtest |
| Self-Learning | TradeMemory→PerformanceTracker→LearningService→WeightAdjuster |

---

## ۱.۳ جریان کلی داده (Data Flow)

```
۱. MT5 EA سیگنال HTTP ارسال می‌کند
         ↓
۲. SecurityMiddleware + RateLimitMiddleware
         ↓
۳. POST /api/v1/signals/receive
         ↓
۴. AgentService → VotingEngine (7 agents موازی, timeout=5s هر کدام)
         ↓
۵. VoteResult {decision, confidence, weighted_score}
         ↓
۶. RiskOrchestrator (7 gate متوالی)
         ├── Gate 1: EquityProtection  → drawdown check
         ├── Gate 2: DailyLimits      → trade count + P&L limit
         ├── Gate 3: VolatilityFilter → ATR + spread + news filter
         ├── Gate 4: CorrelationFilter→ Pearson rolling correlation
         ├── Gate 5: ExposureControl  → max exposure per symbol
         ├── Gate 6: PortfolioRisk    → net exposure + direction
         └── Gate 7: LotSizer        → Kelly blend + ATR sizing
         ↓
۷. RiskDecision {approved, lot_size, reason}
         ↓
۸. ExecutionService
         ├── Idempotency check (TTL=300s)
         ├── CircuitBreaker check
         ├── ManagedOrder creation
         └── OrderStateMachine: PENDING→SUBMITTED
         ↓
۹. MT5Connector.send_order() [asyncio.Lock, timeout=30s]
         ↓
۱۰. OrderStateMachine: SUBMITTED→FILLED
         ↓
۱۱. PositionReconciliation (هر 10 ثانیه)
         ↓
۱۲. TradeMemory → ML retraining trigger
         ↓
۱۳. Telegram alert + Observability metrics
```

---

## ۱.۴ Stack فناوری

| لایه | فناوری | نسخه |
|------|--------|------|
| **Backend Framework** | FastAPI | ≥0.100 |
| **Python** | Python | ≥3.11 |
| **ASGI Server** | Uvicorn + Gunicorn | Latest |
| **Database** | Supabase (PostgreSQL) | Latest |
| **Cache** | Redis | ≥7.0 |
| **ML** | XGBoost + scikit-learn | Latest |
| **Deep Learning** | PyTorch (CPU) | 2.4.1+cpu |
| **Telegram Bot** | aiogram | 3.x |
| **Dashboard** | Streamlit | Latest |
| **Metrics** | Prometheus Client | Latest |
| **Broker API** | MetaTrader5 Python | Latest |
| **Containerization** | Docker + Docker Compose | Latest |
| **CI/CD** | GitHub Actions | Latest |

---

# بخش ۲ — System Architecture

## ۲.۱ معماری کلی — نمودار کامل

```
╔══════════════════════════════════════════════════════════════════╗
║             LAYER 0: EXTERNAL SOURCES                            ║
║  ┌─────────────────────────┐  ┌──────────────────────────────┐  ║
║  │  MetaTrader 5 (MQL5 EA) │  │  Telegram Client             │  ║
║  │  POST /signals/receive  │  │  aiogram3 webhook/polling    │  ║
║  └────────────┬────────────┘  └───────────────┬──────────────┘  ║
╚═══════════════│════════════════════════════════│═════════════════╝
                │ HTTP+Bearer Token              │ Webhook
                ▼                                ▼
╔══════════════════════════════════════════════════════════════════╗
║             LAYER 1: API GATEWAY (port 8000)                     ║
║  Middleware: SecurityMW → RateLimitMW → ObservabilityMW          ║
║  Routes: /signals /trades /risk /agents /analysis /backtest      ║
║          /intelligence /self_learning /institutional /health     ║
╚══════════════════════════════════════════════════════════════════╝
                │
                ▼
╔══════════════════════════════════════════════════════════════════╗
║             LAYER 2: AGENT LAYER                                  ║
║  AgentService → VotingEngine → asyncio.gather()                  ║
║  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           ║
║  │ Market   │ │Liquidity │ │   SMC    │ │AI Predict│           ║
║  │Structure │ │ w=0.15   │ │  w=0.25  │ │  w=0.20  │           ║
║  │ w=0.20   │ └──────────┘ └──────────┘ └──────────┘           ║
║  └──────────┘ ┌──────────┐ ┌──────────┐ ┌──────────┐           ║
║               │  Risk    │ │  News    │ │Execution │           ║
║               │  VETO ⛔  │ │  w=0.10  │ │  w=0.10  │           ║
║               └──────────┘ └──────────┘ └──────────┘           ║
║  Output: VoteResult {decision, confidence, weighted_score}       ║
╚══════════════════════════════════════════════════════════════════╝
                │
                ▼
╔══════════════════════════════════════════════════════════════════╗
║             LAYER 3: RISK ENGINE (7 Gates)                        ║
║  RiskOrchestrator (Singleton — double-checked locking)           ║
║  Gate1:Equity → Gate2:Daily → Gate3:Volatility → Gate4:Corr      ║
║  → Gate5:Exposure → Gate6:Portfolio → Gate7:LotSizer             ║
║  Output: RiskDecision {approved, lot_size, gate_results}         ║
╚══════════════════════════════════════════════════════════════════╝
                │
                ▼
╔══════════════════════════════════════════════════════════════════╗
║             LAYER 4: EXECUTION LAYER                              ║
║  ExecutionService: Idempotency → CircuitBreaker → ManagedOrder   ║
║  OrderStateMachine: PENDING→SUBMITTED→FILLED→CLOSING→CLOSED      ║
║  MT5Connector: asyncio.Lock, timeout=30s, retry×3                ║
║  PositionReconciliation: every 10s                               ║
║  FailureRecovery: dead_letter(maxlen=500), retry queue           ║
╚══════════════════════════════════════════════════════════════════╝
                │
                ▼
╔══════════════════════════════════════════════════════════════════╗
║             LAYER 5: INTELLIGENCE & OBSERVABILITY                 ║
║  MLEngine: XGBoost+sklearn, TradeMemory, auto-retrain            ║
║  Metrics: Prometheus counters/gauges/histograms                  ║
║  Alerts: AlertManager → Telegram/Email                           ║
║  Logging: StructuredLogger (JSON), AuditLogger (immutable)       ║
╚══════════════════════════════════════════════════════════════════╝
                │
                ▼
╔══════════════════════════════════════════════════════════════════╗
║             LAYER 6: DATA PERSISTENCE                             ║
║  Supabase (PostgreSQL): users, trades, signals, licenses         ║
║  Redis: session cache, rate limiting, idempotency, pub/sub       ║
║  Filesystem: ML models (.pkl/.pt), backtest results, logs        ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## ۲.۲ ارتباط ماژول‌ها (Dependency Graph)

```
core/  (پایه — بدون dependency به بقیه لایه‌ها)
  ├── config.py        ← pydantic-settings
  ├── enums.py         ← stdlib
  ├── exceptions.py    ← stdlib
  ├── interfaces.py    ← stdlib typing (Protocol)
  ├── logger.py        ← stdlib logging
  ├── retry.py         ← stdlib asyncio
  ├── auth.py          ← python-jose
  └── deps.py          ← fastapi + core/*

risk/  (فقط از core/ import می‌کند)
  equity_protection → daily_limits → volatility_filter
  → correlation_filter → exposure_control
  → portfolio_risk → lot_sizer
  └── risk_orchestrator (همه gate ها را wire می‌کند)

execution/  (از core/ و risk/ import می‌کند)
  mt5_connector → order_state_machine → position_reconciliation
  → failure_recovery → execution_service (orchestrates all)

agents/  (از core/ و analysis/ import می‌کند)
  base_agent → market_structure, liquidity, smc, ai_prediction,
               risk, news, execution
  └── voting_engine (همه agent ها را اجرا می‌کند)

analysis/  (از core/ import می‌کند)
  decision_engine → smc_engine

intelligence/  (از core/, analysis/ import می‌کند)
  ml_engine ← trade_memory ← learning_service ← weight_adjuster

services/  (از core/, database/, risk/ import می‌کند)
  trade_service, signal_service, audit_service, rbac, scheduler

api/  (بالاترین لایه — از همه import می‌کند)
  main.py ← middleware/* + routes/* + health
```

---

## ۲.۳ ارتباط Agent‌ها

```
AgentService.register(agent)
        ↓
VotingEngine.vote(context)
        ↓  asyncio.gather() — همه موازی، timeout=5s هر کدام
┌───────────────────────────────────────────┐
│ MarketStructure  │ Liquidity  │ SMC        │
│ w=0.20           │ w=0.15     │ w=0.25     │
├───────────────────────────────────────────┤
│ AIPrediction     │ Risk(VETO) │ News       │
│ w=0.20           │ veto power │ w=0.10     │
├───────────────────────────────────────────┤
│ Execution        │            │            │
│ w=0.10           │            │            │
└───────────────────────────────────────────┘
        ↓  _aggregate()
قوانین:
  • اگر Risk Agent بلاک کند → BLOCKED (صرف‌نظر از بقیه)
  • اگر |BUY_w - SELL_w| < 0.01 → NO_TRADE (tie)
  • Crash یک agent باعث توقف بقیه نمی‌شود
  • Timeout → score=0 برای آن agent
        ↓
VoteResult {decision, confidence, weighted_score, agent_results[]}
```

---

## ۲.۴ ارتباط AI Components

```
TradeMemory (completed trades)
        ↓
PerformanceTracker (win_rate, avg_rr, Sharpe)
        ↓
LearningService (feature extraction)
        ↓
TrainingPipeline (Walk-Forward CV + embargo)
  ├── XGBoost.fit()
  ├── CalibratedClassifierCV
  └── roc_auc_score validation
        ↓
ModelManager.save() / SafeModelCache (async LRU)
        ↓
PredictionService → feature_pipeline → XGBoost.predict()
        ↓
AIPredictionAgent (confidence = calibrated probability)
        ↓
VotingEngine (weight=0.20)

Trigger برای Retraining:
  ├── هر 100 trade جدید در TradeMemory
  ├── Win rate زیر 45%
  ├── DRIFT_THRESHOLD = 0.08 (feature shift)
  └── POST /api/v1/self_learning/train (دستی)

Institutional Analytics (جداگانه از ML pipeline):
  ├── Monte Carlo (10,000 simulations) → VaR/CVaR
  ├── RL Agent (PPO/SAC via Stable-Baselines3)
  └── Tick-Level Backtest (microsecond resolution)
```

---

# بخش ۳ — Folder Structure

## ۳.۱ ساختار کامل پوشه‌ها

```
bot12/                                 ← Root repository
│
├── .env                               ← [ایجاد کنید] متغیرهای محیطی
├── .env.example                       ← نمونه با placeholder
├── docker-compose.yml                 ← همه سرویس‌ها
├── docker-compose.prod.yml            ← تنظیمات production
├── Dockerfile                         ← Backend image
├── requirements.txt                   ← Python dependencies
├── pytest.ini                         ← تنظیمات pytest
│
├── backend/                           ← کد اصلی Python
│   ├── core/                          ← هسته مرکزی (پایه همه چیز)
│   │   ├── config.py                  ← Settings با pydantic-settings
│   │   ├── enums.py                   ← همه Enum های پروژه
│   │   ├── exceptions.py              ← سلسله‌مراتب Exception ها
│   │   ├── interfaces.py              ← Protocol definitions (SOLID-I)
│   │   ├── logger.py                  ← ContextualLogger + AuditLogger
│   │   ├── retry.py                   ← RetryConfig + decorators
│   │   ├── auth.py                    ← JWT verify/create
│   │   ├── deps.py                    ← FastAPI Depends() factories
│   │   └── security.py                ← Password hashing, token utils
│   │
│   ├── api/                           ← FastAPI Application
│   │   ├── main.py                    ← app + lifespan + middleware
│   │   ├── main_patch.py              ← [ACTIVE] register_missing_routes
│   │   ├── health.py                  ← /health /health/ready /health/deep
│   │   ├── observability_routes.py    ← /metrics /traces
│   │   └── routes/
│   │       ├── auth.py                ← POST /auth/login /register /refresh
│   │       ├── signals.py             ← POST /signals/receive (MT5 EA)
│   │       ├── trades.py              ← GET/POST /trades
│   │       ├── risk.py                ← POST /risk/assess
│   │       ├── agents.py              ← POST /agents/vote
│   │       ├── analysis.py            ← POST /analysis/decision
│   │       ├── backtest.py            ← POST /backtest/run
│   │       ├── institutional.py       ← POST /institutional/monte_carlo
│   │       ├── self_learning.py       ← POST /self_learning/train
│   │       ├── users.py               ← GET/PUT /users/profile
│   │       ├── ai_prediction.py       ← POST /ai_prediction/predict
│   │       └── websocket_routes.py    ← ws:// realtime updates
│   │
│   ├── risk/                          ← موتور ریسک (7 Gate)
│   │   ├── risk_orchestrator.py       ← هماهنگ‌کننده اصلی (Singleton)
│   │   ├── equity_protection.py       ← Gate 1: محافظت equity
│   │   ├── daily_limits.py            ← Gate 2: محدودیت روزانه
│   │   ├── volatility_filter.py       ← Gate 3: فیلتر نوسان+اخبار
│   │   ├── correlation_filter.py      ← Gate 4: همبستگی Pearson
│   │   ├── exposure_control.py        ← Gate 5: کنترل exposure
│   │   ├── portfolio_risk.py          ← Gate 6: ریسک پرتفولیو
│   │   └── lot_sizer.py               ← Gate 7: حجم (Kelly blend)
│   │
│   ├── execution/                     ← لایه اجرای سفارشات
│   │   ├── execution_service.py       ← سرویس اصلی اجرا
│   │   ├── mt5_connector.py           ← اتصال به MetaTrader5
│   │   ├── order_state_machine.py     ← ماشین وضعیت سفارش
│   │   ├── position_reconciliation.py ← تطبیق موقعیت هر 10s
│   │   ├── failure_recovery.py        ← بازیابی + dead letter
│   │   ├── semi_auto.py               ← حالت نیمه‌اتوماتیک
│   │   └── order_journal.py           ← دفتر audit سفارشات
│   │
│   ├── agents/                        ← Agent های هوشمند
│   │   ├── base_agent.py              ← BaseAgent (ABC) + AgentResult
│   │   ├── voting_engine.py           ← VotingEngine + VoteResult
│   │   ├── agent_service.py           ← AgentService (registry)
│   │   ├── market_structure_agent.py  ← w=0.20
│   │   ├── liquidity_agent.py         ← w=0.15
│   │   ├── smc_agent.py               ← w=0.25
│   │   ├── ai_prediction_agent.py     ← w=0.20
│   │   ├── risk_agent.py              ← VETO power
│   │   ├── news_agent.py              ← w=0.10
│   │   └── execution_agent.py         ← w=0.10
│   │
│   ├── analysis/                      ← موتور تحلیل تکنیکال
│   │   ├── decision_engine.py         ← موتور تصمیم (746 خط)
│   │   └── smc_engine.py              ← SMC engine (3,077 خط)
│   │
│   ├── intelligence/                  ← هوش مصنوعی
│   │   ├── ml_engine.py               ← XGBoost trainer
│   │   ├── trade_memory.py            ← حافظه معاملات
│   │   ├── learning_service.py        ← یادگیری مستمر
│   │   └── weight_adjuster.py         ← تنظیم وزن agent ها
│   │
│   ├── ai_prediction/                 ← پیش‌بینی AI
│   │   ├── model_manager.py           ← مدیریت مدل‌ها
│   │   ├── prediction_service.py      ← سرویس پیش‌بینی
│   │   └── feature_pipeline.py        ← pipeline ویژگی
│   │
│   ├── self_learning/                 ← خودآموزی
│   │   ├── learning_service.py        ← یادگیری خودکار
│   │   ├── performance_tracker.py     ← ردیابی عملکرد
│   │   └── training_pipeline.py       ← آموزش مدل
│   │
│   ├── services/                      ← سرویس‌های عمومی
│   │   ├── trade_service.py           ← CRUD معاملات
│   │   ├── signal_service.py          ← مدیریت سیگنال
│   │   ├── audit_service.py           ← رویدادهای امنیتی
│   │   ├── rbac_service.py            ← کنترل دسترسی
│   │   └── scheduler.py               ← BackgroundScheduler
│   │
│   ├── database/                      ← لایه پایگاه داده
│   │   ├── connection.py              ← Supabase + AsyncSession
│   │   └── connection_pool_monitor.py ← نظارت pool
│   │
│   ├── middleware/                    ← Middleware های امنیتی
│   │   ├── security.py                ← CORS, CSP, HSTS, XSS
│   │   ├── rate_limit.py              ← Rate limiting با Redis
│   │   └── observability.py           ← Request tracing
│   │
│   ├── observability/                 ← مانیتورینگ و لاگ
│   │   ├── metrics.py                 ← MetricsRegistry + Prometheus
│   │   ├── alert_manager.py           ← مدیریت هشدارها
│   │   ├── structured_logger.py       ← JSON logging
│   │   └── tracing.py                 ← OpenTelemetry
│   │
│   ├── telegram/                      ← Bot تلگرام
│   │   ├── bot.py                     ← aiogram3 Bot
│   │   ├── keyboards.py               ← keyboard ها
│   │   ├── handlers/                  ← 11 handler
│   │   └── routers/                   ← 5 router
│   │
│   ├── institutional/                 ← Analytics سازمانی
│   │   ├── monte_carlo.py             ← شبیه‌سازی 10k
│   │   ├── var_calculator.py          ← VaR / CVaR
│   │   ├── rl_agent.py                ← PPO/SAC
│   │   └── tick_backtest.py           ← backtest دقیق
│   │
│   ├── backtest_engine/               ← موتور backtest
│   │   ├── engine.py                  ← موتور اصلی
│   │   ├── data_manager.py            ← داده تاریخی
│   │   └── report_generator.py        ← گزارش
│   │
│   ├── circuit_breaker.py             ← Circuit Breaker مرکزی
│   │
│   └── tests/                         ← مجموعه تست (249 تست)
│       ├── conftest.py                ← Fixtures مشترک
│       ├── test_01_unit_risk.py        ← 86 تست risk
│       ├── test_02_unit_execution.py   ← 59 تست execution
│       ├── test_03_integration.py      ← 54 تست integration
│       └── test_04_security.py         ← 50 تست security
│
├── dashboard/                         ← Streamlit (port 8501)
│   ├── app.py                         ← نقطه شروع
│   └── pages/                         ← صفحات مختلف
│
├── MQL5/                              ← کدهای MetaTrader 5
│   └── Experts/
│       └── MT5TradingEA_Complete.mq5  ← EA اصلی
│
├── supabase/migrations/               ← 30+ SQL migration
├── .github/workflows/                 ← CI/CD pipeline
├── nginx/nginx.conf                   ← Reverse Proxy
├── prometheus/prometheus.yml          ← Monitoring
└── grafana/dashboards/trading.json    ← Dashboard
```

---

## ۳.۲ توضیح هر پوشه مهم

| پوشه | نقش | فایل‌های مهم |
|------|-----|--------------|
| `backend/core/` | هسته مرکزی — پایه همه چیز | `config.py`, `exceptions.py`, `interfaces.py` |
| `backend/api/` | دروازه ورودی — همه HTTP requests | `main.py`, `health.py`, `routes/signals.py` |
| `backend/risk/` | محافظت مالی — ۷ gate مستقل | `risk_orchestrator.py`, `equity_protection.py` |
| `backend/execution/` | اجرای سفارش — ارتباط با MT5 | `execution_service.py`, `mt5_connector.py` |
| `backend/agents/` | هوش مصنوعی — ۷ agent موازی | `voting_engine.py`, `base_agent.py` |
| `backend/analysis/` | تحلیل تکنیکال — SMC + Price Action | `smc_engine.py`, `decision_engine.py` |
| `backend/intelligence/` | یادگیری ماشین — XGBoost | `ml_engine.py`, `trade_memory.py` |
| `backend/services/` | منطق کسب‌وکار — CRUD + RBAC | `trade_service.py`, `audit_service.py` |
| `backend/telegram/` | کانال ارتباطی — Bot تلگرام | `bot.py`, `handlers/` |
| `backend/tests/` | تضمین کیفیت — 249 تست | `test_01_unit_risk.py`, `conftest.py` |
| `MQL5/Experts/` | نقطه آغاز — EA در MT5 | `MT5TradingEA_Complete.mq5` |
| `supabase/migrations/` | تاریخچه Schema | `001_create_users.sql` و بعدی‌ها |
| `.github/workflows/` | CI/CD خودکار | `ci.yml`, `cd.yml` |

---

## ۳.۳ فایل‌های Root Level

| فایل | توضیح | تغییر لازم؟ |
|------|-------|-------------|
| `.env` | متغیرهای محیطی — **محرمانه** | ✅ بله — حتماً |
| `.env.example` | نمونه با placeholder | نه |
| `docker-compose.yml` | تعریف همه سرویس‌ها | کمتر |
| `requirements.txt` | وابستگی‌های Python | فقط برای update |
| `pytest.ini` | تنظیمات اجرای تست | ندرتاً |
