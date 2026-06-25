# GALAXY VAST AI TRADING PLATFORM
# MASTER DOCUMENTATION

> **Version:** 2.0.0 | **Date:** 2026-06-25 | **Status:** Production Ready  
> این مستندات برای توسعه‌دهنده حرفه‌ای، تازه‌کار، مدیر پروژه و کاربر نهایی نوشته شده است.

---

## Table of Contents

| # | Section | Audience |
|---|---------|----------|
| [1](#1-project-overview) | Project Overview | همه |
| [2](#2-system-architecture) | System Architecture | Architect, Dev |
| [3](#3-folder-structure) | Folder Structure | Dev |
| [4](#4-modules-documentation) | Modules Documentation | Dev, Architect |
| [5](#5-classes-documentation) | Classes Documentation | Dev |
| [6](#6-functions-documentation) | Functions Documentation | Dev |
| [7](#7-installation-guide) | Installation Guide | همه |
| [8](#8-configuration-guide) | Configuration Guide | DevOps, Dev |
| [9](#9-environment-variables) | Environment Variables | DevOps |
| [10](#10-database-guide) | Database Guide | Dev, DBA |
| [11](#11-api-documentation) | API Documentation | Dev, QA |
| [12](#12-ai-models-documentation) | AI Models Documentation | ML Engineer |
| [13](#13-exchange-integration-guide) | Exchange Integration Guide | Dev |
| [14](#14-risk-management-system) | Risk Management System | Quant, PM |
| [15](#15-docker-guide) | Docker Guide | DevOps |
| [16](#16-cicd-guide) | CI/CD Guide | DevOps |
| [17](#17-development-guide) | Development Guide | Dev |
| [18](#18-debugging-guide) | Debugging Guide | Dev |
| [19](#19-backup--recovery-guide) | Backup & Recovery Guide | DevOps |
| [20](#20-update--upgrade-guide) | Update & Upgrade Guide | DevOps |
| [21](#21-troubleshooting-guide) | Troubleshooting Guide | همه |
| [22](#22-faq) | FAQ | همه |
| [23](#23-production-deployment-guide) | Production Deployment Guide | DevOps |
| [24](#24-security-best-practices) | Security Best Practices | Security |
| [25](#25-maintenance-guide) | Maintenance Guide | DevOps |

---

# 1. Project Overview

## 1.1 پروژه چیست؟

**Galaxy Vast AI Trading Platform** یک پلتفرم معاملاتی هوش مصنوعی است که برای MetaTrader 5 طراحی شده.

> **برای تازه‌کار:** این سیستم به‌طور خودکار در بازار فارکس معامله می‌کند. یک Expert Advisor (EA) در MetaTrader 5 سیگنال می‌فرستد، هوش مصنوعی آن را تحلیل می‌کند، ریسک را بررسی می‌کند و اگر همه شرایط مناسب بود، معامله را انجام می‌دهد.

> **برای حرفه‌ای:** Multi-Agent system با 7 voting agent، 7 risk gate مستقل، XGBoost ensemble ML، Clean Architecture با Dependency Injection، SOLID principles، و production-grade observability.

## 1.2 Key Features

| Feature | Description | Status |
|---------|-------------|--------|
| **Multi-Agent Voting** | 7 agent موازی با weighted voting | ✅ Active |
| **7-Gate Risk Engine** | Equity, Daily, Volatility, Correlation, Exposure, Portfolio, Lot | ✅ Active |
| **MT5 Auto-Execution** | اجرای اتوماتیک سفارش در MetaTrader 5 | ✅ Active |
| **Semi-Auto Mode** | تأیید دستی قبل از اجرا | ✅ Active |
| **ML Engine** | XGBoost + Random Forest + Logistic Regression | ✅ Active |
| **Self-Learning** | Walk-Forward CV + Auto-Retrain + Drift Detection | ✅ Active |
| **Circuit Breaker** | توقف خودکار در شرایط بحرانی | ✅ Active |
| **Telegram Bot** | کنترل و نظارت از طریق Telegram | ✅ Active |
| **Backtesting** | Multi-symbol backtest with Walk-Forward CV | ✅ Active |
| **Institutional Analytics** | Monte Carlo, VaR, Sharpe, RL | ✅ Active |
| **Security AI** | تشخیص ناهنجاری و تهدید | ✅ Active |
| **Streamlit Dashboard** | داشبورد تحلیلی | ✅ Active |

## 1.3 Tech Stack

```
Backend:        Python 3.11+ | FastAPI 0.115 | uvicorn
Database:       Supabase (PostgreSQL) | Redis 7.4
ML/AI:          XGBoost 2.1 | scikit-learn 1.5 | PyTorch 2.4 | stable-baselines3
Broker:         MetaTrader 5 (MT5 C++ Python API)
Bot:            aiogram 3.13 (Telegram)
Dashboard:      Streamlit
Observability:  Prometheus + custom metrics | Sentry
Security:       JWT (python-jose) | bcrypt | RBAC
Infra:          Docker + Docker Compose | GitHub Actions
```

## 1.4 Project Statistics

```
Total Files:       429        Python Files:    294
Lines of Code:  ~45,000       Test Files:      50+
API Endpoints:    35+         Risk Gates:        7
AI Agents:          8         ML Models:         6
Background Workers: 11        DB Tables:        15+
SQL Migrations:   25+         Docker Services:   6
```

---

# 2. System Architecture

## 2.1 Full Architecture Diagram

```
+-----------------------------------------------------------------------------+
|                        MetaTrader 5 (Windows/VPS)                           |
|                     MT5TradingEA_Complete.mq5                               |
|              POST /api/v1/signals/receive  (MQL5_API_TOKEN)                 |
+----------------------------+------------------------------------------------+
                             | HTTPS Signal Payload
                             v
+-----------------------------------------------------------------------------+
|                    MIDDLEWARE STACK (FastAPI)                                |
|  SecurityMiddleware -> RateLimitMiddleware -> ObservabilityMiddleware        |
|  (XSS,Headers,IP)    (Redis, 100req/min)    (Prometheus, tracing)          |
|                             |                                               |
|  +---------------------------v----------------------------------------------+  |
|  |                   API Routes /api/v1/*                               |   |
|  |  signals|trades|risk|agents|analysis|backtest|dashboard|...         |   |
|  +---------------------------+----------------------------------------------+  |
|                             |                                               |
|  +---------------------------v----------------------------------------------+  |
|  |                    AGENT LAYER                                       |   |
|  |  AgentService -> VotingEngine                                        |   |
|  |  MarketStruct(0.20) | SMC(0.20) | AIPred(0.20) | Liquidity(0.15)   |   |
|  |  Risk-veto(0.15) | News(0.05) | Execution(0.05)                     |   |
|  |  Weighted Vote -> VoteDecision{BUY/SELL/NO_TRADE, confidence}        |   |
|  +---------------------------+----------------------------------------------+  |
|                             | VoteDecision                                  |
|  +---------------------------v----------------------------------------------+  |
|  |                   RISK ENGINE (7 Gates)                              |   |
|  |  Gate1: EquityProtection  -> halt if drawdown > threshold            |   |
|  |  Gate2: DailyLimits       -> block if daily/weekly/monthly exceeded  |   |
|  |  Gate3: VolatilityFilter  -> block if ATR spike / news event         |   |
|  |  Gate4: CorrelationFilter -> block if corr > 0.7 with open positions |   |
|  |  Gate5: ExposureControl   -> block if total exposure > 10%           |   |
|  |  Gate6: PortfolioRisk     -> block if portfolio VaR exceeded         |   |
|  |  Gate7: LotSizer          -> Kelly-based lot size calculation         |   |
|  |                  RiskOrchestrator (Singleton)                        |   |
|  +---------------------------+----------------------------------------------+  |
|                             | RiskDecision + LotSize                        |
|  +---------------------------v----------------------------------------------+  |
|  |                   EXECUTION LAYER                                    |   |
|  |  ExecutionService -> OrderStateMachine -> PositionReconciliation     |   |
|  |  MT5Connector(mutex) | FailureRecovery | CircuitBreaker(5/60s)       |   |
|  +---------------------------+----------------------------------------------+  |
|                             |                                               |
|  Intelligence: MLEngine <- TradeMemory <- TrainingPipeline(WalkForward)     |
|  Observability: MetricsRegistry | AlertManager | AuditService               |
+-----------------------------------------------------------------------------+
         |                          |                        |
         v                          v                        v
  Telegram Bot               Streamlit Dashboard       Supabase + Redis
  (aiogram3)                 (port 8501)               (PostgreSQL + Cache)
```

## 2.2 Architecture Principles

**Clean Architecture** — 4 layers, inner layers never import from outer:

```
Layer 4 (Presentation):  api/, telegram/, dashboard/
Layer 3 (Application):   execution/, agents/, services/
Layer 2 (Domain):        risk/, intelligence/, analysis/
Layer 1 (Core/Infra):    core/, database/, observability/
```

**SOLID Applied:**
- **S**: ExecutionService orchestrates only (delegates to risk, broker, osm, fr, pr)
- **O**: All gates implement IRiskGate — add new gate without touching orchestrator
- **L**: Any IOrderBroker can replace MT5Connector
- **I**: IRiskGate.check(), IOrderBroker.send_order() — minimal interfaces
- **D**: All deps injected via constructor / FastAPI Depends()

## 2.3 Complete Signal Flow

```
Step  1: MT5 EA -> POST /api/v1/signals/receive (MQL5_API_TOKEN)
Step  2: SecurityMiddleware + RateLimitMiddleware
Step  3: JWT auth -> input validation -> SignalService.create_signal()
Step  4: AgentService.vote(context) -> 7 agents parallel (asyncio.gather)
Step  5: VoteDecision.approved? -> ExecutionService.execute_signal()
Step  6: Idempotency check -- prevent duplicate execution
Step  7: RiskOrchestrator.assess(RiskInput) -> 7 gates in sequence
Step  8: All gates PASS -> LotSizer.calculate() -> lot_size
Step  9: OrderStateMachine.create_order(PENDING)
Step 10: MT5Connector.send_order(request) [async with self._lock]
Step 11: OSM transition: PENDING -> SUBMITTED -> FILLED
Step 12: PositionReconciliation.run_once() -- orphan detection
Step 13: TradeService.create_trade() -> Supabase insert
Step 14: MetricsRegistry + AuditService + Telegram alert
Step 15: On failure: FailureRecovery -> RETRY / DEAD_LETTER
```

---

# 3. Folder Structure

```
bot12/
|
+-- .env                          # متغیرهای محیطی (از .env.example کپی کنید)
+-- .env.example                  # نمونه همه متغیرها با توضیح
+-- .github/
|   +-- workflows/
|       +-- ci-cd.yml             # GitHub Actions CI/CD pipeline
+-- Dockerfile                    # Docker image برای API
+-- Dockerfile.bot                # Docker image برای Telegram bot
+-- docker-compose.yml            # همه سرویس‌ها
+-- docker-compose.prod.yml       # Production overrides
+-- requirements.txt              # Python dependencies (version-pinned)
+-- pyproject.toml                # ruff + mypy configuration
+-- startup_check.py              # Pre-flight checks
|
+-- backend/
|   |
|   +-- circuit_breaker.py        # Circuit breaker singleton
|   |
|   +-- core/                     # Foundation -- imports nothing
|   |   +-- config.py             # Settings (pydantic-settings)
|   |   +-- enums.py              # 20+ shared enums
|   |   +-- exceptions.py         # AppError hierarchy
|   |   +-- interfaces.py         # Protocol contracts for DI
|   |   +-- deps.py               # FastAPI Depends() factories
|   |   +-- logger.py             # ContextualLogger + AuditLogger
|   |   +-- retry.py              # RetryConfig + @async_retry
|   |   +-- auth.py               # JWT encode/decode
|   |   +-- security.py           # Password hashing (bcrypt)
|   |
|   +-- api/
|   |   +-- main.py               # FastAPI app, lifespan, middleware
|   |   +-- main_patch.py         # Dynamic route registration
|   |   +-- health.py             # /health endpoints
|   |   +-- websocket_routes.py   # WebSocket /ws/signals
|   |   +-- routes/               # 20+ route modules
|   |
|   +-- risk/                     # 7-Gate Risk Engine
|   |   +-- risk_orchestrator.py  # Orchestrator + Singleton factory
|   |   +-- equity_protection.py  # Gate 1: Equity drawdown
|   |   +-- daily_limits.py       # Gate 2: Daily/weekly/monthly limits
|   |   +-- volatility_filter.py  # Gate 3: ATR + news
|   |   +-- news_filter.py        # News events data
|   |   +-- correlation_filter.py # Gate 4: Cross-symbol correlation
|   |   +-- exposure_control.py   # Gate 5: Total exposure
|   |   +-- portfolio_risk.py     # Gate 6: Portfolio-level risk
|   |   +-- lot_sizing.py         # Gate 7: Kelly lot sizing
|   |   +-- fail_mode.py          # FAIL_OPEN / FAIL_CLOSED
|   |
|   +-- execution/
|   |   +-- execution_service.py  # Main pipeline (SOLID, DI)
|   |   +-- mt5_connector.py      # MT5 C++ API async wrapper
|   |   +-- order_state_machine.py # PENDING->FILLED state machine
|   |   +-- position_reconciliation.py # Orphan detection
|   |   +-- failure_recovery.py   # Retry queue + dead letter
|   |   +-- semi_auto.py          # Manual approval flow
|   |   +-- order_journal.py      # Order audit trail
|   |
|   +-- agents/
|   |   +-- base_agent.py         # BaseAgent ABC + VoteResult
|   |   +-- voting_engine.py      # Weighted voting aggregation
|   |   +-- agent_service.py      # Registry + lifecycle
|   |   +-- market_structure_agent.py  # weight=0.20
|   |   +-- smc_agent.py               # weight=0.20
|   |   +-- ai_prediction_agent.py     # weight=0.20
|   |   +-- liquidity_agent.py         # weight=0.15
|   |   +-- risk_agent.py              # weight=0.15, VETO
|   |   +-- news_agent.py              # weight=0.05
|   |   +-- execution_agent.py         # weight=0.05
|   |   +-- security_score_engine.py   # Anomaly detection
|   |
|   +-- analysis/
|   |   +-- decision_engine.py    # 6-step decision (746 lines)
|   |   +-- smc_engine.py         # Smart Money Concepts (3077 lines)
|   |   +-- price_action_engine.py
|   |   +-- session_manager.py
|   |
|   +-- intelligence/
|   |   +-- ml_engine.py          # XGBoost + RF + LR ensemble
|   |   +-- trade_memory.py       # Trade history storage
|   |   +-- learning_service.py
|   |   +-- weight_adjuster.py
|   |
|   +-- ai_prediction/
|   |   +-- model_manager.py      # Model save/load/LRU cache
|   |   +-- prediction_service.py
|   |   +-- feature_pipeline.py
|   |   +-- xgboost_trainer.py
|   |
|   +-- self_learning/
|   |   +-- training_pipeline.py  # Walk-Forward CV + CalibratedCV
|   |   +-- retraining_service.py
|   |   +-- performance_tracker.py
|   |   +-- dataset_generator.py
|   |
|   +-- services/
|   |   +-- trade_service.py      # CRUD trades -> Supabase
|   |   +-- signal_service.py
|   |   +-- audit_service.py      # Async audit trail buffer
|   |   +-- rbac_service.py
|   |   +-- scheduler.py          # Background task scheduler
|   |   +-- license_service.py
|   |
|   +-- database/
|   |   +-- connection.py         # Supabase + Redis
|   |   +-- health.py
|   |   +-- connection_pool_monitor.py
|   |
|   +-- middleware/
|   |   +-- security.py           # Security headers + XSS
|   |   +-- rate_limit.py         # Redis-backed rate limiting
|   |   +-- observability.py      # Request tracing
|   |
|   +-- observability/
|   |   +-- metrics.py            # MetricsRegistry (Prometheus)
|   |   +-- alert_manager.py
|   |   +-- structured_logger.py
|   |   +-- tracing.py
|   |
|   +-- telegram/
|   |   +-- bot.py                # aiogram3 bot
|   |   +-- handlers/             # 11 handler files
|   |
|   +-- institutional/
|   |   +-- risk_engine.py        # VaR + Sharpe + Drawdown
|   |   +-- portfolio_manager.py  # Kelly/Risk-Parity allocation
|   |   +-- monte_carlo.py
|   |   +-- rl_agent.py           # PPO Reinforcement Learning
|   |
|   +-- backtest_engine/          # Multi-symbol backtest
|   +-- research/                 # Walk-forward research
|   +-- analytics/                # Performance analytics
|   +-- security_reporting/       # Security reports
|   +-- contracts/                # Decision contracts
|   |
|   +-- tests/                    # Test Suite (249 tests, 100% pass)
|       +-- conftest.py
|       +-- test_01_unit_risk.py      # 86 tests
|       +-- test_02_unit_execution.py # 59 tests
|       +-- test_03_integration.py    # 54 tests
|       +-- test_04_security.py       # 50 tests
|
+-- dashboard/                    # Streamlit (port 8501)
+-- frontend/                     # React/Vue frontend
+-- mql5/                         # MT5TradingEA_Complete.mq5
+-- infra/                        # prometheus/ + grafana/
+-- supabase/migrations/          # 25+ SQL migration files
```

---

# 4. Modules Documentation

## 4.1 core/ -- Foundation Layer

| File | Key Class/Function | Role | Dependencies |
|------|--------------------|------|--------------|
| `config.py` | `Settings`, `get_settings()` | All settings from `.env` | pydantic-settings |
| `enums.py` | 20+ Enum classes | Shared type definitions | stdlib |
| `exceptions.py` | `AppError`, `RetryableError` | Exception hierarchy | stdlib |
| `interfaces.py` | `IRiskGate`, `IOrderBroker`, `IAgent` | Protocol DI contracts | typing |
| `deps.py` | `get_execution_service()`, `get_risk_orchestrator_dep()` | FastAPI factories | - |
| `logger.py` | `ContextualLogger`, `AuditLogger` | Structured JSON logging | stdlib |
| `retry.py` | `RetryConfig`, `@async_retry` | Exponential backoff retry | asyncio |
| `auth.py` | `create_access_token()`, `verify_token()` | JWT management | python-jose |

## 4.2 risk/ -- 7-Gate Risk Engine

> **برای تازه‌کار:** هر معامله باید از 7 دروازه بگذرد. هر کدام block کند، معامله نمی‌شود.

| File | Gate | When it BLOCKS |
|------|------|----------------|
| `equity_protection.py` | 1 | drawdown > threshold |
| `daily_limits.py` | 2 | تعداد/ضرر از حد گذشت |
| `volatility_filter.py` | 3 | ATR بالا یا news مهم |
| `correlation_filter.py` | 4 | corr > 0.7 با positions باز |
| `exposure_control.py` | 5 | total exposure > 10% |
| `portfolio_risk.py` | 6 | portfolio VaR exceeded |
| `lot_sizing.py` | 7 | همیشه PASS -- فقط lot محاسبه می‌کند |

## 4.3 execution/ -- Order Lifecycle

| File | Key Class | Role |
|------|-----------|------|
| `execution_service.py` | `ExecutionService` | Main pipeline (SOLID, DI) |
| `mt5_connector.py` | `MT5Connector` | MT5 C++ API async wrapper with mutex |
| `order_state_machine.py` | `OrderStateMachine` | PENDING->FILLED FSM |
| `position_reconciliation.py` | `PositionReconciliation` | MT5 sync + orphan detection |
| `failure_recovery.py` | `FailureRecoveryEngine` | Retry queue + dead letter |
| `semi_auto.py` | `SemiAutoHandler` | Manual approval with TTL |
| `order_journal.py` | `OrderJournal` | Immutable order audit trail |

## 4.4 agents/ -- Multi-Agent Voting System

| Agent | Weight | Veto | Role |
|-------|--------|------|------|
| `MarketStructureAgent` | 0.20 | No | BOS, ChoCH, structure |
| `SMCAgent` | 0.20 | No | Order blocks, FVG, SMC |
| `AIPredictionAgent` | 0.20 | No | XGBoost ML prediction |
| `LiquidityAgent` | 0.15 | No | Liquidity zones |
| `RiskAgent` | 0.15 | **YES** | Portfolio risk (CAN VETO) |
| `NewsAgent` | 0.05 | No | High-impact news |
| `ExecutionAgent` | 0.05 | No | Spread, session quality |

**Voting Formula:**
```
buy_score  = sum(confidence * weight) for BUY votes
sell_score = sum(confidence * weight) for SELL votes
approved   = (max_score >= 0.60) and (abs(buy - sell) >= 0.01)
```

---

# 5. Classes Documentation

## 5.1 ExecutionService

```python
class ExecutionService:
    """
    Main execution pipeline. SOLID-compliant.
    Constructor injection: risk, broker, osm, fr, pr
    
    Usage:
        svc = ExecutionService(risk, broker, osm, fr, pr)
        await svc.start()
        result = await svc.execute_signal(signal_dict)
        # result: {"success": bool, "order_id": str, "lot_size": float}
    """
    def __init__(self, risk, broker, osm, fr, pr, *, default_risk_pct=1.0)
    async def start() -> None
    async def stop() -> None
    async def execute_signal(signal: Dict) -> Dict
    async def health() -> Dict
```

## 5.2 RiskOrchestrator

```python
class RiskOrchestrator:
    """
    Singleton. Coordinates all 7 risk gates.
    ALWAYS use get_risk_orchestrator() factory.
    
    Usage:
        orch = await get_risk_orchestrator()
        decision = await orch.assess(RiskInput(
            symbol="EURUSD", direction="BUY",
            balance=10000.0, stop_loss_pips=50.0, ...
        ))
        if decision.get("approved"):
            lot_size = decision.get("lot_size")
    """
    async def assess(inp: RiskInput) -> Dict
    async def check(**ctx) -> Dict

async def get_risk_orchestrator() -> RiskOrchestrator:
    """Double-checked locking singleton factory."""
```

## 5.3 MT5Connector

```python
class MT5Connector:
    """
    Thread-safe async wrapper for MT5 C++ Python API.
    Uses asyncio.to_thread() + self._lock for all MT5 calls.
    
    Usage:
        connector = MT5Connector(login=12345, password="...", server="...")
        await connector.initialize()
        req = MT5OrderRequest(
            symbol="EURUSD", action="buy",
            volume=0.01, sl=1.0800, tp=1.0950
        )
        result = await connector.send_order(req)
        # result.success, result.price, result.order (ticket)
    """
    async def initialize() -> bool
    async def shutdown() -> None
    async def health_check() -> bool
    async def send_order(request: MT5OrderRequest) -> MT5OrderResult
    async def close_position(ticket: int, volume: float) -> bool
    async def get_positions() -> List
    async def get_account_info() -> Dict
```

## 5.4 CircuitBreaker

```python
class CircuitBreaker:
    """
    States: CLOSED -> OPEN (5 failures/60s) -> HALF_OPEN -> CLOSED
    
    Usage:
        cb = get_mt5_breaker()
        async with cb:
            result = await mt5.send_order(req)
        # raises CircuitOpenError if OPEN
    """
    async def __aenter__() -> None
    async def __aexit__(exc_type, exc_val, exc_tb) -> bool
    async def record_success() -> None
    async def record_failure(reason: str = "") -> None
    async def force_open(reason: str) -> None
    async def force_close(reason: str) -> None
    def snapshot() -> Dict

async def halt_trading(reason: str) -> None
async def resume_trading(reason: str = "") -> None
def is_trading_halted() -> bool
def get_mt5_breaker() -> CircuitBreaker   # singleton factory
```

## 5.5 BaseAgent

```python
class BaseAgent(ABC):
    """
    Subclass this to create a new voting agent.
    
    Usage:
        class MyAgent(BaseAgent):
            DEFAULT_WEIGHT = 0.10
            
            async def _analyze(self, ctx: Dict) -> VoteResult:
                return VoteResult(
                    agent_id=self.agent_id,
                    signal=VoteSignal.BUY,
                    confidence=0.75,
                    weight=self.weight,
                    reason="my analysis"
                )
    """
    DEFAULT_WEIGHT: float = 1.0
    
    @property
    def agent_id(self) -> str        # derived from class name
    @property
    def weight(self) -> float        # DEFAULT_WEIGHT
    
    @abstractmethod
    async def _analyze(context: Dict) -> VoteResult
    async def analyze(context: Dict) -> VoteResult   # safe wrapper
    async def health() -> Dict

@dataclass
class VoteResult:
    agent_id: str
    signal: VoteSignal          # BUY | SELL | NEUTRAL | ABSTAIN
    confidence: float           # 0.0 to 1.0
    weight: float
    latency_ms: float = 0.0
    reason: str = ""
    metadata: Dict = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict() -> Dict
    @property
    def weighted_confidence(self) -> float
```

## 5.6 RetryConfig

```python
@dataclass(frozen=True)
class RetryConfig:
    """
    Immutable retry configuration.
    
    Pre-built configs:
        MT5_RETRY  = RetryConfig(max_attempts=3, base_delay_s=0.5, strategy=EXPONENTIAL)
        DB_RETRY   = RetryConfig(max_attempts=5, base_delay_s=0.2)
        RISK_RETRY = RetryConfig(max_attempts=2, base_delay_s=0.1, strategy=FIXED)
    
    Usage:
        @async_retry(MT5_RETRY)
        async def send_order(self, req): ...
        
        result = await with_retry_async(
            lambda: mt5.send_order(req),
            config=MT5_RETRY,
            on_retry=lambda a, e, s: metrics.increment("order_retry")
        )
    """
    max_attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    jitter: bool = True
    retry_on: Tuple[Type[Exception], ...] = ()
    no_retry_on: Tuple[Type[Exception], ...] = ()
```

## 5.7 Settings

```python
class Settings(BaseSettings):
    """
    All configuration loaded from .env file.
    Validated at startup -- server exits if required fields missing.
    """
    # App
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # Database (REQUIRED)
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_JWT_SECRET: str           # min 32 chars
    JWT_SECRET_KEY: str                # min 32 chars
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    
    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str]
    TELEGRAM_ADMIN_IDS: str
    
    # MT5
    MT5_LOGIN: Optional[int]
    MT5_PASSWORD: Optional[str]
    MT5_SERVER: Optional[str]
    MT5_PATH: Optional[str]
    
    # Risk
    INITIAL_ACCOUNT_BALANCE: float = 10_000.0
    RECONCILE_INTERVAL_SECONDS: int = 10
    SEMI_AUTO_PENDING_TTL_S: int = 300
    DRIFT_THRESHOLD: float = 0.08
    
    # Auth
    MQL5_API_TOKEN: Optional[str]
    LICENSE_SECRET: str
    LICENSE_SALT: str
```

---

# 6. Functions Documentation

## 6.1 ExecutionService Key Functions

| Function | Input | Output | Description |
|----------|-------|--------|-------------|
| `execute_signal(signal)` | `Dict` | `{success, order_id, lot_size, ...}` | Main entry point |
| `_run_risk(signal, log)` | signal dict | risk dict | Calls RiskOrchestrator |
| `_create_order(signal, risk, sid)` | - | `ManagedOrder` | Builds order object |
| `_submit(order)` | `ManagedOrder` | `MT5OrderResult` | Sends to MT5 with retry |
| `_retry_execute(metadata)` | `Dict` | `bool` | FailureRecovery callback |
| `health()` | - | `Dict` | Service health status |

## 6.2 LotSizer Kelly Formula

```
Kelly Formula:
    kelly_pct = win_rate - (1 - win_rate) / avg_rr
    kelly_blend = kelly_pct * 0.25   # fractional Kelly

Fixed Risk:
    risk_usd = balance * risk_pct / 100
    lot = risk_usd / (stop_loss_pips * pip_value)

Final:
    lot = min(kelly_lot, fixed_risk_lot) * volatility_ratio
    lot = max(0.01, min(lot, symbol_max_lot))
```

## 6.3 VotingEngine Key Functions

| Function | Role |
|----------|------|
| `vote(context)` | Parallel voting + aggregation -> VoteDecision |
| `_check_risk_veto(context)` | Risk Agent veto check |
| `_run_parallel_safe(agents, ctx)` | asyncio.gather with per-agent timeout (5s) |
| `_aggregate(results)` | Weighted sum -> winner + confidence |
| `update_weights(weight_map)` | Runtime weight adjustment |
| `enable_agent(name)` | Agent on |
| `disable_agent(name)` | Agent off |

## 6.4 Health Check Response

```json
{
    "status": "healthy",
    "version": "2.0.0",
    "uptime_s": 3600.5,
    "components": {
        "database":        {"status": "healthy", "latency_ms": 5},
        "redis":           {"status": "healthy", "latency_ms": 1},
        "mt5":             {"status": "healthy", "connected": true},
        "circuit_breaker": {"state": "CLOSED", "failures_in_window": 0},
        "risk_engine":     {"status": "healthy", "latency_ms": 0.1}
    }
}
```

---

# 7. Installation Guide

## 7.1 Prerequisites

| Tool | Version | Download |
|------|---------|----------|
| Python | 3.11+ | python.org |
| Docker | 24+ | docker.com |
| Docker Compose | 2.20+ | included with Docker |
| Git | 2.40+ | git-scm.com |
| MetaTrader 5 | Latest | metatrader5.com (Windows only) |

## 7.2 Step-by-Step Installation

### Step 1: Clone

```bash
git clone https://github.com/sani13790000/bot12.git
cd bot12
```

### Step 2: Environment File

```bash
cp .env.example .env
nano .env
```

Minimum required:
```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your_service_role_key
SUPABASE_JWT_SECRET=your_jwt_secret_min_32_chars
JWT_SECRET_KEY=your_app_jwt_secret_min_32_chars
MQL5_API_TOKEN=your_random_token_for_ea
LICENSE_SECRET=your_license_secret
LICENSE_SALT=your_license_salt
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_ADMIN_IDS=123456789
ALLOWED_ORIGINS=http://localhost:3000
```

### Step 3: Install Dependencies

```bash
python -m venv venv
source venv/bin/activate      # Linux/Mac
# venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

### Step 4: Database Migrations

```bash
supabase db push
# Or manually run each supabase/migrations/*.sql file in Supabase SQL Editor
```

### Step 5: Verify

```bash
python startup_check.py
# Expected: All checks passed
```

### Step 6: Start

```bash
docker compose up --build -d
curl http://localhost:8000/health/deep
```

---

# 8. Configuration Guide

## 8.1 Small Account (< $5,000)

```env
DEFAULT_RISK_PCT=0.5
MAX_DAILY_TRADES=5
MAX_DAILY_LOSS_PCT=2.0
MAX_WEEKLY_LOSS_PCT=5.0
MAX_MONTHLY_DD_PCT=10.0
MAX_CORRELATION=0.6
MAX_TOTAL_EXPOSURE_PCT=5.0
```

## 8.2 Medium Account ($5,000-$50,000)

```env
DEFAULT_RISK_PCT=1.0
MAX_DAILY_TRADES=10
MAX_DAILY_LOSS_PCT=3.0
MAX_WEEKLY_LOSS_PCT=7.0
MAX_MONTHLY_DD_PCT=15.0
MAX_CORRELATION=0.7
MAX_TOTAL_EXPOSURE_PCT=10.0
```

## 8.3 Large Account (> $50,000)

```env
DEFAULT_RISK_PCT=0.5
MAX_DAILY_TRADES=20
MAX_DAILY_LOSS_PCT=2.0
MAX_WEEKLY_LOSS_PCT=5.0
MAX_MONTHLY_DD_PCT=8.0
MAX_CORRELATION=0.5
MAX_TOTAL_EXPOSURE_PCT=8.0
```

## 8.4 MT5 Configuration

```env
MT5_LOGIN=12345678
MT5_PASSWORD=YourPassword
MT5_SERVER=BrokerName-Server
MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe
MT5_ORDER_FILLING=ORDER_FILLING_IOC
MT5_SLIPPAGE_BASE=10
MT5_SLIPPAGE_MAX=50
```

---

# 9. Environment Variables

## 9.1 Complete Reference

| Variable | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `ENVIRONMENT` | str | No | `production` | development/staging/production |
| `DEBUG` | bool | No | `false` | Always false in production |
| `LOG_LEVEL` | str | No | `INFO` | DEBUG/INFO/WARNING/ERROR |
| `SUPABASE_URL` | str | **Yes** | - | https://xxx.supabase.co |
| `SUPABASE_KEY` | str | **Yes** | - | service_role key (NOT anon) |
| `SUPABASE_JWT_SECRET` | str | **Yes** | - | From Supabase Settings/API |
| `JWT_SECRET_KEY` | str | **Yes** | - | Min 32 random chars |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | int | No | `30` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | int | No | `30` | Refresh token TTL |
| `REDIS_URL` | str | No | `redis://redis:6379/0` | Redis address |
| `REDIS_PASSWORD` | str | No | - | Redis auth password |
| `REDIS_MAX_CONNECTIONS` | int | No | `20` | Connection pool size |
| `ALLOWED_ORIGINS` | str | **Yes (prod)** | - | https://app.example.com |
| `TELEGRAM_BOT_TOKEN` | str | **Yes** | - | From @BotFather |
| `TELEGRAM_ADMIN_IDS` | str | **Yes** | - | Comma-separated: 123,456 |
| `TELEGRAM_WEBHOOK_SECRET` | str | **Yes** | - | Random string |
| `MT5_LOGIN` | int | No | - | MT5 account number |
| `MT5_PASSWORD` | str | No | - | MT5 password |
| `MT5_SERVER` | str | No | - | e.g. ICMarkets-Live |
| `MT5_PATH` | str | No | - | Path to terminal64.exe |
| `MT5_ORDER_FILLING` | str | No | `ORDER_FILLING_IOC` | Filling type |
| `MT5_SLIPPAGE_BASE` | int | No | `10` | Base slippage (pips) |
| `MT5_SLIPPAGE_MAX` | int | No | `50` | Max slippage (pips) |
| `MQL5_API_TOKEN` | str | **Yes** | - | EA authentication token |
| `API_PREFIX` | str | No | `/api/v1` | API route prefix |
| `DEFAULT_RISK_PCT` | float | No | `1.0` | Default risk % per trade |
| `MAX_DAILY_TRADES` | int | No | `10` | Max trades per day |
| `MAX_DAILY_LOSS_PCT` | float | No | `3.0` | Max daily loss % |
| `MAX_WEEKLY_LOSS_PCT` | float | No | `7.0` | Max weekly loss % |
| `MAX_MONTHLY_DD_PCT` | float | No | `15.0` | Max monthly drawdown % |
| `INITIAL_ACCOUNT_BALANCE` | float | No | `10000.0` | Starting balance |
| `RECONCILE_INTERVAL_SECONDS` | int | No | `10` | Position sync interval |
| `SEMI_AUTO_PENDING_TTL_S` | int | No | `300` | Approval timeout |
| `DRIFT_THRESHOLD` | float | No | `0.08` | Concept drift threshold |
| `LICENSE_SECRET` | str | **Yes** | - | License encryption key |
| `LICENSE_SALT` | str | **Yes** | - | Hash salt |
| `ENABLE_METRICS` | bool | No | `true` | Prometheus metrics |
| `SENTRY_DSN` | str | No | - | Sentry error tracking |
| `BACKTEST_MAX_WORKERS` | int | No | `4` | Parallel workers |
| `BACKTEST_JOB_TIMEOUT` | int | No | `300` | Job timeout (s) |

## 9.2 Generating Secure Values

```bash
# JWT keys (min 32 chars):
python -c "import secrets; print(secrets.token_hex(32))"

# MQL5 API token:
python -c "import secrets; print(secrets.token_urlsafe(32))"

# License secret/salt:
python -c "import secrets; print(secrets.token_hex(16))"
```

---

# 10. Database Guide

## 10.1 Supabase Setup

```
1. Create account at supabase.com
2. New project -> note URL, service_role key, JWT Secret
3. SQL Editor -> run each migration file in order
4. Authentication -> enable Email provider
5. Database -> note connection string for backups
```

## 10.2 Core Tables

| Table | Key Fields | Role |
|-------|-----------|------|
| `users` | id, email, role, status, created_at | Users |
| `trades` | id, user_id, symbol, direction, lot_size, entry_price, sl, tp, pnl, status | Trade records |
| `signals` | id, user_id, symbol, direction, entry_price, sl, tp, status, signal_id | Signals |
| `audit_logs` | id, user_id, action, resource, metadata, created_at | Audit trail |
| `ml_models` | id, model_type, version, accuracy, path, created_at | ML registry |
| `backtest_results` | id, config, metrics, created_at | Backtest data |
| `security_events` | id, type, severity, ip, user_id, details | Security logs |
| `licenses` | id, user_id, type, status, expires_at, features | Licenses |
| `dead_letter_queue` | id, order_id, failure_reason, attempts, metadata | Failed orders |
| `rbac_permissions` | id, user_id, resource, action, level | Permissions |

## 10.3 Running Migrations

```bash
# List all migration files:
ls supabase/migrations/ | sort

# With Supabase CLI:
supabase db push --project-ref YOUR_PROJECT_REF

# Manual: paste each file in SQL Editor in numeric order
```

## 10.4 Redis Usage

| Use Case | Key Pattern | TTL |
|---------|------------|-----|
| Rate limiting | `rate_limit:{ip}:{endpoint}` | 60s |
| Session cache | `session:{user_id}` | 30min |
| Idempotency | `idempotency:{signal_id}` | 10min |
| Metrics cache | `metrics:snapshot` | 30s |

---

# 11. API Documentation

## 11.1 Authentication

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Get token:
```http
POST /api/v1/auth/login
{"email": "user@example.com", "password": "your_password"}
-> {"access_token": "eyJ...", "refresh_token": "eyJ...", "expires_in": 1800}
```

## 11.2 Key Endpoints

### Signal from EA

```http
POST /api/v1/signals/receive
X-API-Token: {MQL5_API_TOKEN}
{
    "signal_id": "uuid-v4",
    "symbol": "EURUSD",
    "direction": "BUY",
    "entry_price": 1.08500,
    "stop_loss": 1.08000,
    "take_profit": 1.09500,
    "timeframe": "H1"
}
-> {"success": true, "order_id": "ord_...", "lot_size": 0.05, "latency_ms": 45}
```

### Risk Assessment

```http
POST /api/v1/risk/assess
Authorization: Bearer {token}
{"symbol": "EURUSD", "direction": "BUY", "entry_price": 1.0850,
 "stop_loss": 1.0800, "balance": 10000.0, "stop_loss_pips": 50.0}
-> {"approved": true, "lot_size": 0.04, "risk_usd": 20.0,
    "gates": {"equity": "PASS", "daily": "PASS", ...}}
```

### Circuit Breaker

```http
GET  /api/v1/risk/circuit-breaker
POST /api/v1/risk/circuit-breaker  {"action": "halt", "reason": "..."}
POST /api/v1/risk/circuit-breaker  {"action": "resume"}
```

### Health

```http
GET /health/live   -> 200 {"status": "ok"}
GET /health/ready  -> 200/503
GET /health/deep   -> {status, components, uptime_s}
```

### WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/signals?token=JWT');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

### Prometheus Metrics

```http
GET /metrics
-> galaxy_vast_trades_total{symbol="EURUSD",direction="BUY"} 42
   galaxy_vast_fill_latency_seconds_bucket{le="0.1"} 38
   galaxy_vast_equity_usd 9850.50
```

---

# 12. AI Models Documentation

## 12.1 Models Overview

| Model | Algorithm | Goal | Typical Accuracy |
|-------|-----------|------|-----------------|
| `direction_model` | XGBoost | Predict BUY/SELL | 55-65% |
| `confidence_model` | Random Forest | Confidence 0-1 | - |
| `risk_model` | Logistic Regression | Risk level | 60-70% |
| `calibrated_ensemble` | CalibratedClassifierCV | Calibrated proba | Best |
| `rl_agent` | PPO (stable-baselines3) | Execution timing | reward-based |

## 12.2 Feature Engineering

```python
features = {
    "price_change_1h": 0.0015,    "price_change_4h": 0.0032,
    "volatility_atr": 0.0008,     "rsi_14": 58.3,
    "macd_signal": 0.0002,        "bb_position": 0.65,
    "is_london_session": 1,       "hour_of_day": 14,
    "spread_pips": 1.2,           "spread_vs_avg": 0.95,
    "win_rate_7d": 0.58,          "smc_score": 0.72,
}
```

## 12.3 Training Pipeline

```
TradeMemory -> DatasetGenerator -> WalkForwardCV (k=5, embargo=5)
    -> XGBoost + RandomForest + LogisticRegression
    -> CalibratedClassifierCV
    -> ConceptDriftDetector (ADWIN-style)
    -> ModelManager.save(version=timestamp)
```

## 12.4 Auto-Retrain Triggers

```
1. New trades since last train >= 50
2. Drift score > DRIFT_THRESHOLD (0.08)
3. Win rate < 45% in last 50 trades
4. Manual: POST /api/v1/self-learning/retrain
```

## 12.5 Manual Retraining

```bash
curl -X POST http://localhost:8000/api/v1/self-learning/retrain \
  -H "Authorization: Bearer $ADMIN_TOKEN"

curl http://localhost:8000/api/v1/self-learning/status
# {"last_train": "...", "current_accuracy": 0.61, "drift_status": "STABLE"}
```

---

# 13. Exchange Integration Guide

## 13.1 MetaTrader 5

```bash
pip install MetaTrader5
python -c "import MetaTrader5 as mt5; print(mt5.__version__)"
```

EA Setup in MT5:
```
1. Copy mql5/MT5TradingEA_Complete.mq5 to MQL5/Experts
2. Open MetaEditor (F4) -> F7 to Compile
3. Drag EA onto chart -> Properties:
   - API_URL = http://your-server:8000
   - API_TOKEN = {MQL5_API_TOKEN from .env}
   - MAGIC_NUMBER = 12345
```

Test connection:
```python
import MetaTrader5 as mt5
mt5.initialize(login=LOGIN, password='PASS', server='SERVER')
info = mt5.account_info()
print(f'Balance: {info.balance}')
mt5.shutdown()
```

## 13.2 Custom Broker (IOrderBroker)

```python
class MyBrokerAdapter:
    """Implements IOrderBroker protocol."""
    
    async def initialize(self) -> bool:
        self._client = await MyBrokerAPI.connect(api_key="...")
        return True
    
    async def send_order(self, request) -> Any:
        return await self._client.place_order({
            "symbol": request.symbol, "side": request.action,
            "quantity": request.volume, "sl": request.sl, "tp": request.tp
        })
    
    async def close_position(self, ticket: int, volume: float) -> bool:
        return await self._client.close(ticket, volume)
    
    async def get_positions(self) -> list:
        return await self._client.positions()
    
    async def health_check(self) -> bool:
        return await self._client.ping()
    
    async def shutdown(self) -> None:
        await self._client.disconnect()

# Usage:
broker = MyBrokerAdapter()
svc = ExecutionService(risk=orch, broker=broker, osm=osm, fr=fr, pr=pr)
```

---

# 14. Risk Management System

## 14.1 7-Gate Pipeline

```
Signal arrives
     |
     v
[Gate 1] EquityProtection   drawdown بیش از حد؟
     |
     v
[Gate 2] DailyLimits        تعداد یا ضرر از حد گذشت؟
     |
     v
[Gate 3] VolatilityFilter   ATR/spread بیش از حد یا news؟
     |
     v
[Gate 4] CorrelationFilter  همبستگی > 0.7؟
     |
     v
[Gate 5] ExposureControl    کل exposure > حد؟
     |
     v
[Gate 6] PortfolioRisk      portfolio VaR exceeded؟
     |
     v
[Gate 7] LotSizer           محاسبه Kelly+ATR
     |
     v
ORDER SUBMITTED
```

## 14.2 Circuit Breaker State Machine

```
      CLOSED (normal)
     /                \
5 fails/60s        2 successes from 3 probes
     |                   ^
     v                   |
   OPEN             HALF_OPEN
 (halted)         (after 30s timeout)
     \                /
      +--HALF_OPEN---+
```

Manual control:
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/risk/circuit-breaker \
     -d '{"action": "halt", "reason": "Emergency stop"}'

curl -X POST -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/risk/circuit-breaker \
     -d '{"action": "resume"}'
```

## 14.3 Semi-Auto Mode

```
Signal -> Risk Gates -> Telegram notification to admin
                              |
              /approve (within TTL)    /reject
                    |
              MT5 order_send
```

---

# 15. Docker Guide

## 15.1 Services

| Service | Port | RAM | Role |
|---------|------|-----|------|
| `api` | 8000 | 2GB | FastAPI backend |
| `telegram_bot` | - | 512MB | Telegram bot |
| `dashboard` | 8501 | 1GB | Streamlit |
| `redis` | 6379 | 256MB | Cache + Rate limit |
| `prometheus` | 9090 | 512MB | Metrics |
| `grafana` | 3000 | 256MB | Dashboard |

## 15.2 Commands

```bash
# Start:
docker compose up --build -d

# Logs:
docker compose logs -f api --tail=100

# Enter container:
docker compose exec api bash

# Run tests:
docker compose exec api pytest backend/tests/ -q

# Status:
docker compose ps

# Stop:
docker compose down

# Production:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Health:
curl http://localhost:8000/health/deep | python3 -m json.tool
```

---

# 16. CI/CD Guide

## 16.1 Pipeline

```
git push/PR
    |
    v
Job 1: Backend Tests (pytest 249 tests, ruff, mypy, bandit)
    |
    v
Job 2: Frontend Build (npm, ESLint, TypeScript)
    |
    v
Job 3: Docker Build + Push to GHCR (main/tags only)
    |
    +-- Job 4: Deploy Staging (develop branch)
    +-- Job 5: Deploy Production (v*.*.* tags only)
```

## 16.2 Local Pre-Push Checks

```bash
OTEL_SDK_DISABLED=true pytest backend/tests/ -q
ruff check backend/
mypy backend/ --ignore-missing-imports
bandit -r backend/ -ll -x backend/tests/
ruff format backend/
```

## 16.3 Production Release

```bash
git tag v2.1.0
git push origin v2.1.0
# GitHub Actions auto-deploys to production
```

---

# 17. Development Guide

## 17.1 Setup

```bash
git clone https://github.com/sani13790000/bot12.git
cd bot12
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
ENVIRONMENT=development uvicorn backend.api.main:app --reload --port 8000
```

## 17.2 Adding a New Agent

```python
# backend/agents/my_agent.py
from backend.agents.base_agent import BaseAgent, VoteResult, VoteSignal

class MyAgent(BaseAgent):
    DEFAULT_WEIGHT = 0.10
    
    async def _analyze(self, context: dict) -> VoteResult:
        score = 0.6  # your analysis logic
        signal = (VoteSignal.BUY if score > 0.7 else
                  VoteSignal.SELL if score < 0.3 else VoteSignal.NEUTRAL)
        return VoteResult(
            agent_id=self.agent_id,
            signal=signal,
            confidence=min(abs(score - 0.5) * 2, 1.0),
            weight=self.weight,
            reason=f"score={score:.2f}"
        )

# Register in agent_service.py:
# self._agents["myagent"] = MyAgent()
```

## 17.3 Adding a New Risk Gate

```python
class MyRiskGate:
    @property
    def name(self) -> str: return "my_gate"
    
    async def check(self, **ctx) -> dict:
        if some_condition:
            return {"passed": False, "gate": self.name,
                    "reason": "blocked", "detail": "..."}
        return {"passed": True, "gate": self.name}

# In risk_orchestrator.py:
# 1. self._my_gate = MyRiskGate()
# 2. Add _run_my_gate() method
# 3. Call from check()
```

## 17.4 Coding Standards

```python
# Always:
from __future__ import annotations
from typing import Any, Dict, Optional
from backend.core.logger import get_logger

log = get_logger(__name__)

async def my_function(
    param: Dict[str, Any],
    *,
    timeout: float = 5.0,
) -> Optional[Dict[str, Any]]:
    """
    Brief description.
    
    Args:
        param: Input dict with required keys
        timeout: Maximum wait time
    
    Returns:
        Result dict or None
    """
    log.info("event_name", key=value)  # structured logging
```

---

# 18. Debugging Guide

## 18.1 Enable Debug Mode

```env
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
```

## 18.2 View Logs

```bash
# All logs:
docker compose logs -f api --tail=100

# Errors only:
docker compose logs api | grep '"level":"ERROR"'

# By component:
docker compose logs api | grep '"logger":"execution'

# MT5 specific:
docker compose logs api | grep "mt5"

# Audit trail:
docker compose logs api | grep '"audit":true'
```

## 18.3 System Status

```bash
# Full health:
curl http://localhost:8000/health/deep | python3 -m json.tool

# Circuit breaker:
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/risk/circuit-breaker

# Metrics:
curl http://localhost:8000/metrics | grep galaxy_vast
```

## 18.4 Manual Debug

```python
# debug_signal.py
import asyncio
from backend.execution.execution_service import ExecutionService

async def debug():
    result = await svc.execute_signal({
        "signal_id": "DEBUG-001", "symbol": "EURUSD",
        "direction": "BUY", "entry_price": 1.0850,
        "stop_loss": 1.0830, "take_profit": 1.0890,
    })
    print(result)

asyncio.run(debug())
```

---

# 19. Backup & Recovery Guide

## 19.1 Backup Script

```bash
#!/bin/bash
# /opt/scripts/backup.sh - run daily via cron: 0 3 * * *

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/galaxyvast"
mkdir -p "$BACKUP_DIR"

# ML Models
docker compose exec -T api tar -czf - /app/models/ > "$BACKUP_DIR/models_$DATE.tar.gz"

# Redis snapshot
docker compose exec redis redis-cli BGSAVE
sleep 2
docker cp $(docker compose ps -q redis):/data/dump.rdb "$BACKUP_DIR/redis_$DATE.rdb"

# Environment config
cp /opt/bot12/.env "$BACKUP_DIR/env_$DATE.backup"

# Keep 30 days
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.rdb" -mtime +30 -delete

echo "Backup OK: $DATE"
```

```bash
# Setup crontab:
crontab -e
# Add: 0 3 * * * /opt/scripts/backup.sh >> /var/log/backup.log 2>&1
```

## 19.2 Restore

```bash
# Models:
docker compose exec -T api tar -xzf - < /backups/galaxyvast/models_DATE.tar.gz

# Redis:
docker compose stop redis
docker cp /backups/galaxyvast/redis_DATE.rdb $(docker compose ps -q redis):/data/dump.rdb
docker compose start redis

curl http://localhost:8000/health/deep
```

---

# 20. Update & Upgrade Guide

## 20.1 Routine Update

```bash
git pull origin main
git log --oneline -10
pip install -r requirements.txt
ls supabase/migrations/ | sort | tail -5  # check new migrations
OTEL_SDK_DISABLED=true pytest backend/tests/ -q
docker compose up --build -d
curl http://localhost:8000/health/deep
```

## 20.2 Zero-Downtime Update

```bash
docker compose up --scale api=2 -d
# Wait 30s for new instance
docker compose up --scale api=1 -d
```

## 20.3 Rollback

```bash
git log --oneline -10
git checkout v2.0.0
docker compose up --build -d
curl http://localhost:8000/health/deep
```

---

# 21. Troubleshooting Guide

## 21.1 Server Won't Start

```bash
docker compose logs api | tail -50
python startup_check.py              # check .env
lsof -i :8000 && kill -9 PID        # port conflict
docker compose up redis -d && redis-cli ping  # Redis down
```

## 21.2 MT5 Won't Connect

```bash
curl http://localhost:8000/health/deep | python3 -m json.tool
# Check: MT5 needs Windows, verify MT5_LOGIN/PASSWORD/SERVER
python -c "import MetaTrader5 as mt5; print(mt5.initialize())"
```

## 21.3 All Trades Blocked

```bash
# Check circuit breaker:
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/risk/circuit-breaker

# Resume if OPEN:
curl -X POST -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/risk/circuit-breaker \
     -d '{"action": "resume"}'

# Check block reason:
docker compose logs api | grep "risk_blocked" | tail -20
```

## 21.4 MT5 Error Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 10004 | Requote | Retry |
| 10006 | Rejected | Check spread |
| 10013 | Invalid request | Check parameters |
| 10014 | Invalid volume | Check lot size |
| 10016 | Invalid stops | Check SL/TP distance |
| 10018 | Market closed | Weekend/holiday |
| 10019 | No money | Check margin |
| 10033 | Too many orders | Reduce open positions |

## 21.5 Emergency Procedure

```bash
# 1. Halt trading:
curl -X POST -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/risk/circuit-breaker \
     -d '{"action": "halt", "reason": "emergency"}'

# 2. Restart:
docker compose restart api

# 3. Verify health:
curl http://localhost:8000/health/deep

# 4. Resume when safe:
curl -X POST -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/risk/circuit-breaker \
     -d '{"action": "resume"}'
```

---

# 22. FAQ

**Q: Linux support?**  
A: Yes for backend (Docker). MT5 needs Windows VPS separately.

**Q: Multi-user?**  
A: Yes, RBAC with separate trades/settings per user.

**Q: Other symbols (Gold, Oil)?**  
A: Yes, any MT5 symbol. Set correct symbol name in EA.

**Q: Semi-Auto mode?**  
A: Signal -> risk gates -> Telegram notification -> admin approves/rejects within TTL (default 300s).

**Q: When does ML retrain?**  
A: After 50 new trades, drift detected, or win rate < 45%. Or manually via API.

**Q: What if MT5 disconnects mid-trade?**  
A: FailureRecovery retries 3x with exponential backoff, then dead letter queue + Telegram alert.

**Q: Custom broker?**  
A: Implement IOrderBroker (5 async methods). See Section 13.2.

**Q: Minimum VPS spec?**  
A: 4 vCPU, 8GB RAM, 50GB SSD, Ubuntu 22.04 + separate Windows VPS for MT5.

**Q: Access Grafana?**  
A: docker compose up grafana -d -> http://localhost:3000 (admin/admin)

**Q: Backtest accuracy?**  
A: Walk-Forward CV with embargo reduces lookahead bias. Results approximate, not a guarantee.

---

# 23. Production Deployment Guide

## 23.1 Requirements

```
CPU: 4 vCPU | RAM: 8GB | Disk: 50GB SSD
OS: Ubuntu 22.04 LTS
Domain: api.example.com with SSL
MT5: Separate Windows VPS
```

## 23.2 Deploy Steps

```bash
# Server prep:
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git nginx certbot

# Clone:
git clone https://github.com/sani13790000/bot12.git /opt/bot12
cd /opt/bot12 && cp .env.example .env && nano .env

# SSL:
certbot certonly --standalone -d api.example.com

# Nginx:
cat > /etc/nginx/sites-available/galaxyvast << 'EOF'
server {
    listen 443 ssl;
    server_name api.example.com;
    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF
ln -s /etc/nginx/sites-available/galaxyvast /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Start production:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
curl https://api.example.com/health/deep
```

## 23.3 Firewall

```bash
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP redirect
ufw allow 443/tcp  # HTTPS
ufw deny 8000/tcp  # Block direct API
ufw deny 6379/tcp  # Block Redis
ufw enable
```

---

# 24. Security Best Practices

## 24.1 Secret Management

```bash
# Never commit to git:
echo ".env" >> .gitignore

# Generate secure values:
python -c "import secrets; print(secrets.token_hex(32))"

# Rotate keys every 90 days
```

## 24.2 CORS

```env
# Production ONLY (specific origins):
ALLOWED_ORIGINS=https://app.example.com

# NEVER:
ALLOWED_ORIGINS=*
```

## 24.3 JWT

```env
ACCESS_TOKEN_EXPIRE_MINUTES=30    # Short-lived
REFRESH_TOKEN_EXPIRE_DAYS=7       # Not 30 days
```

## 24.4 Database

```sql
-- Enable Row Level Security:
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
-- Create policies in Supabase Dashboard
-- Authentication -> Policies -> Add RLS policy per table
```

## 24.5 Rate Limiting

Default: 100 req/min per IP. Sensitive endpoints:
- `/auth/login`: 5/min
- `/signals/receive`: 60/min

---

# 25. Maintenance Guide

## 25.1 Daily Checklist

```bash
curl http://localhost:8000/health/deep
docker compose logs api --since=24h | grep '"level":"ERROR"' | wc -l
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/risk/circuit-breaker
df -h && docker system df
```

## 25.2 Weekly Checklist

```bash
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/intelligence/metrics
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/execution/dead-letter
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/reconciliation/orphans
/opt/scripts/backup.sh
```

## 25.3 Monthly Checklist

```bash
pip list --outdated
pip install -r requirements.txt --upgrade
certbot certificates   # check SSL expiry
docker system prune -f
curl -X POST -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/self-learning/retrain
```

## 25.4 Grafana Dashboard

```
URL: http://localhost:3000
Dashboard: "Galaxy Vast AI Trading Platform"

Key Panels:
- Trade Rate (trades/hour)
- Fill Latency (P95, ms)
- Risk Block Rate
- Equity Curve (USD)
- Circuit Breaker State
- ML Accuracy (7-day rolling)
- API Latency (P50/P95/P99)
- Error Rate (5xx/min)
- Memory Usage (MB)

Alerts:
- equity_drawdown > 10%  -> WARNING
- equity_drawdown > 15%  -> CRITICAL
- circuit_breaker = OPEN -> CRITICAL
- fill_latency P95 > 5s  -> WARNING
- error_rate > 5/min     -> WARNING
- ml_accuracy < 45%      -> WARNING
```

---

## Glossary

| Term | Definition |
|------|-----------|
| **SMC** | Smart Money Concept -- institutional order flow analysis |
| **FVG** | Fair Value Gap -- price inefficiency zone |
| **Order Block** | Supply/demand zone from institutional orders |
| **BOS** | Break of Structure -- trend direction change |
| **ChoCH** | Change of Character -- momentum shift |
| **ATR** | Average True Range -- volatility measure |
| **Kelly Criterion** | Optimal position sizing formula |
| **Walk-Forward** | Time-series CV to prevent lookahead bias |
| **Concept Drift** | Change in market data distribution over time |
| **Drawdown** | Equity decline from peak to trough |
| **Circuit Breaker** | Automatic halt on consecutive failures |
| **Gate** | Individual risk check in pipeline |
| **Semi-Auto** | Manual approval required before execution |
| **Idempotency** | Same signal executed only once |
| **Dead Letter Queue** | Failed orders after all retries exhausted |
| **Orphan Position** | MT5 position not recorded in database |
| **Singleton** | Only one instance exists in the process |
| **DI** | Dependency Injection -- pass deps via constructor |
| **RBAC** | Role-Based Access Control |
| **Spread** | Bid-ask price difference |
| **Pip** | Smallest price unit (0.0001 for EURUSD) |
| **Lot** | 1 lot = 100,000 units of base currency |
| **SL** | Stop Loss |
| **TP** | Take Profit |
| **R:R** | Risk:Reward ratio |
| **ADWIN** | Adaptive Windowing -- drift detection algorithm |
| **MQL5** | MetaQuotes Language 5 (MT5 programming language) |
| **EA** | Expert Advisor -- automated trading program in MT5 |
| **NFP** | Non-Farm Payrolls -- high-impact US economic news |
| **VaR** | Value at Risk |

---

*Version 2.0.0 | Galaxy Vast AI Trading Platform | 2026-06-25*  
*Generated from analysis of 429 files, 294 Python files, ~45,000 lines of code*
