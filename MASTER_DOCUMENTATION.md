# 🌌 Galaxy Vast AI Trading Platform
## MASTER DOCUMENTATION — نسخه ۲.۰.۰

> **راهنمای جامع برای توسعه‌دهنده، DevOps، و کاربر نهایی**
> آخرین بروزرسانی: ۲۰۲۶-۰۶-۲۵ | Python 3.11 | FastAPI 0.115

---

## فهرست مطالب

1. [معرفی پروژه](#-۱-معرفی-پروژه)
2. [معماری کامل](#-۲-معماری-کامل)
3. [ساختار پوشه‌ها](#-۳-ساختار-پوشه‌ها)
4. [تمام ماژول‌ها، کلاس‌ها و توابع](#-۴-تمام-ماژول‌ها-کلاس‌ها-و-توابع)
5. [نحوه نصب](#-۵-نحوه-نصب)
6. [نحوه اجرا](#-۶-نحوه-اجرا)
7. [متغیرهای ENV](#-۷-متغیرهای-env)
8. [تنظیمات سیستم](#-۸-تنظیمات-سیستم)
9. [Docker](#-۹-docker)
10. [CI/CD](#-۱۰-cicd)
11. [نحوه توسعه](#-۱۱-نحوه-توسعه)
12. [نحوه دیباگ](#-۱۲-نحوه-دیباگ)
13. [نحوه بکاپ](#-۱۳-نحوه-بکاپ)
14. [نحوه آپدیت](#-۱۴-نحوه-آپدیت)
15. [آموزش مدل‌های ML](#-۱۵-آموزش-مدل‌های-ml)
16. [اتصال به صرافی‌ها و بروکرها](#-۱۶-اتصال-به-صرافی‌ها-و-بروکرها)
17. [مدیریت ریسک](#-۱۷-مدیریت-ریسک)
18. [راهنمای رفع خطا](#-۱۸-راهنمای-رفع-خطا)
19. [API Reference](#-۱۹-api-reference)
20. [Glossary](#-۲۰-glossary)

---

## 🌟 ۱. معرفی پروژه

### Galaxy Vast AI Trading Platform چیست؟

Galaxy Vast یک پلتفرم معاملاتی **هوش مصنوعی** سازمانی است که برای معامله خودکار (Automated Trading) در بازارهای فارکس (Forex) طراحی شده. این سیستم:

- 📊 **سیگنال‌های معاملاتی** را از ۱۳ agent هوش مصنوعی دریافت می‌کند
- 🛡️ **ریسک** هر معامله را با ۷ لایه فیلتر بررسی می‌کند
- ⚡ **سفارش‌ها** را از طریق MetaTrader 5 (MT5) اجرا می‌کند
- 📱 **ربات تلگرام** برای کنترل و مانیتورینگ دارد
- 🤖 **یادگیری ماشین** مداوم برای بهبود عملکرد دارد

### ویژگی‌های کلیدی

| ویژگی | توضیح |
|-------|--------|
| **Multi-Agent AI** | ۱۳ agent مستقل، یک نتیجه نهایی از voting |
| **۷-Layer Risk** | Daily Limits, Equity Protection, Volatility, Correlation, Exposure, Portfolio, Lot Sizing |
| **MT5 Integration** | اتصال مستقیم به MetaTrader 5 از طریق API |
| **Self-Learning** | مدل‌ها پس از هر معامله آپدیت می‌شوند |
| **Semi-Auto Mode** | معامله‌گر انسانی می‌تواند سیگنال‌ها را تایید یا رد کند |
| **Circuit Breaker** | در صورت شکست‌های متوالی، سیستم auto-halt می‌شود |
| **Telegram Bot** | کنترل کامل از طریق تلگرام |
| **Enterprise Logging** | Structured JSON logging با full audit trail |
| **Health Checks** | Kubernetes-compatible liveness/readiness probes |

### Stack فناوری

```
Backend:   Python 3.11 + FastAPI 0.115 + Pydantic v2
Database:  Supabase (PostgreSQL) + Redis 7.4
ML:        PyTorch 2.4 + XGBoost 2.1 + scikit-learn 1.5
Trading:   MetaTrader 5 (MQL5 EA)
Bot:       aiogram 3.13 (Telegram)
Deploy:    Docker + Docker Compose
CI/CD:     GitHub Actions
Monitor:   Prometheus + structured logging
```

---

## 🏗️ ۲. معماری کامل

### نمودار معماری سیستم

```
+---------------------------------------------------------------+
|                    EXTERNAL SIGNALS                           |
|         (MQL5 EA / Telegram / REST API / WebSocket)           |
+-------------------------------+-------------------------------+
                                |
                                v
+---------------------------------------------------------------+
|              FastAPI Gateway (Port 8000)                      |
|  SecurityMW -> RateLimitMW (Redis) -> ObservabilityMW        |
|  CORS | JWT Auth | Rate Limiting | Request Tracing            |
+-------------------+---------------------------+---------------+
                    |                           |
                    v                           v
       +------------------------+  +------------------------+
       |    REST API Routes     |  |   WebSocket Routes     |
       |  /api/v1/signals       |  | /ws/signals /ws/trades |
       |  /api/v1/risk          |  +------------------------+
       |  /api/v1/trades        |
       |  ... 25 route files    |
       +----------+-------------+
                  |
                  v
+---------------------------------------------------------------+
|                   AGENT VOTING LAYER                          |
|                                                               |
|  [SMC Agent] [ML Agent] [Risk Agent] [News Agent]            |
|  [Market Struct] [Liquidity] [Execution] [AI Prediction]     |
|  [Security AI] [Institutional] ...13 agents total            |
|                                                               |
|         VotingEngine.vote() -> VoteResult (BUY/SELL/HOLD)    |
+------------------------------+--------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|                    DECISION ENGINE                            |
|  SMCEngine (3077L) + PriceActionEngine + SessionManager      |
|  -> TradingDecision (symbol, direction, entry, sl, tp, lot)  |
+------------------------------+--------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|            RISK ORCHESTRATOR -- 7 Gates (FAIL_CLOSED)        |
|                                                               |
|  Gate 1: DailyLimitsEngine     max trades/day, P&L limits    |
|  Gate 2: EquityProtectionEngine drawdown halt (HWM)          |
|  Gate 3: VolatilityFilter       ATR + spread + news events   |
|  Gate 4: CorrelationFilter      cross-asset correlation      |
|  Gate 5: ExposureControl        total exposure % of balance  |
|  Gate 6: PortfolioRisk          portfolio-level risk budget  |
|  Gate 7: LotSizer (Kelly)       optimal position sizing      |
|                                                               |
|  CircuitBreaker: 5 fails/60s -> OPEN -> halt ALL trading     |
+------------------------------+--------------------------------+
                               |  RiskCheckResult(approved=True)
                               v
+---------------------------------------------------------------+
|                   EXECUTION SERVICE                           |
|                                                               |
|  Idempotency Check (TTL=600s) -> In-flight dedup             |
|  OrderStateMachine: PENDING->SUBMITTED->FILLED->CLOSED       |
|  MT5Connector (thread-safe): health->send_order->confirm     |
|  FailureRecovery: exponential backoff retry (max 3)          |
|  PositionReconciliation: duplicate check before retry        |
+------------------------------+--------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|                    MetaTrader 5 (MT5)                         |
|  MQL5 Expert Advisor -> POST /api/v1/signals -> JSON resp    |
|  order_send() -> position opened in live broker account      |
+------------------------------+--------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|                 SELF-LEARNING PIPELINE                        |
|  TradeDatasetGenerator -> FeaturePipeline -> TrainingPipeline|
|  XGBoost / PyTorch retrain -> ModelManager update            |
|  PerformanceTracker -> WeightAdjuster -> Agent weight update |
+---------------------------------------------------------------+
```

### اصول طراحی معماری

| اصل | پیاده‌سازی |
|-----|----------|
| **SOLID** | هر class یک مسئولیت؛ Protocol interfaces در `core/interfaces.py`؛ DI در constructor |
| **Clean Architecture** | `core/` <- `risk/` <- `execution/` <- `api/` -- هرگز برعکس |
| **Dependency Injection** | `core/deps.py` -- همه singletons از یک مکان inject می‌شوند |
| **Fail-Safe** | FAIL_CLOSED default -- هر خطا = trade block (ایمن‌ترین حالت) |
| **Idempotency** | هر `signal_id` فقط یکبار execute می‌شود (TTL=600 ثانیه) |
| **Circuit Breaker** | 5 شکست در 60 ثانیه -> سیستم halt می‌شود |

---

## 📁 ۳. ساختار پوشه‌ها

```
bot12/
|
+-- .env.example                 <- نمونه متغیرهای محیطی (copy -> .env)
+-- .github/workflows/
|   +-- ci-cd.yml                <- Pipeline کامل CI/CD
|   +-- ci.yml                   <- CI سریع برای PR
+-- Dockerfile                   <- API server (multi-stage, non-root)
+-- Dockerfile.bot               <- Telegram bot image
+-- docker-compose.yml           <- Development stack
+-- docker-compose.prod.yml      <- Production stack
+-- requirements.txt             <- Python dependencies (pinned)
+-- pytest.ini                   <- Test configuration
+-- startup_check.py             <- Health check قبل از start
|
+-- backend/                     <- کد اصلی Python (294 فایل)
|   |
|   +-- core/                    <- زیرساخت مشترک (هیچ dependency به سایر packages)
|   |   +-- config.py            <- Settings (Pydantic BaseSettings)
|   |   +-- interfaces.py        <- Protocol definitions (SOLID/DI)
|   |   +-- exceptions.py        <- Exception hierarchy
|   |   +-- logger.py            <- Structured JSON logging
|   |   +-- retry.py             <- Retry mechanism (exponential/fixed)
|   |   +-- deps.py              <- Dependency injection
|   |   +-- enums.py             <- Shared enumerations
|   |   +-- auth.py              <- JWT authentication
|   |   +-- security.py          <- Security utilities
|   |   +-- cache.py             <- Redis cache helper
|   |   +-- validators.py        <- Input validation
|   |
|   +-- api/                     <- FastAPI layer
|   |   +-- main.py              <- App entry point + lifespan
|   |   +-- health.py            <- /health /health/ready /health/deep
|   |   +-- websocket_manager.py <- WebSocket management
|   |   +-- routes/              <- 25 route files
|   |       +-- auth.py          <- POST /auth/login, /register
|   |       +-- signals.py       <- POST /signals (from MQL5)
|   |       +-- trades.py        <- GET/POST/DELETE /trades
|   |       +-- risk.py          <- POST /risk/assess
|   |       +-- agents.py        <- GET /agents/status
|   |       +-- analysis.py      <- POST /analysis/analyze
|   |       +-- ... 19 more
|   |
|   +-- risk/                    <- موتور ریسک (7 gate)
|   |   +-- risk_orchestrator.py <- هماهنگ‌کننده + RiskInput + RiskCheckResult
|   |   +-- lot_sizing.py        <- Kelly Criterion sizing
|   |   +-- daily_limits.py      <- محدودیت‌های روزانه
|   |   +-- equity_protection.py <- Drawdown halt
|   |   +-- volatility_filter.py <- ATR + spread + news
|   |   +-- correlation_filter.py<- Cross-asset correlation
|   |   +-- exposure_control.py  <- Total exposure control
|   |   +-- portfolio_risk.py    <- Portfolio-level risk
|   |   +-- news_filter.py       <- High-impact news filter
|   |
|   +-- execution/               <- موتور اجرا
|   |   +-- execution_service.py <- سرویس اصلی (idempotency + retry)
|   |   +-- mt5_connector.py     <- اتصال MT5 (thread-safe)
|   |   +-- order_state_machine.py <- State machine سفارش‌ها
|   |   +-- position_reconciliation.py <- تطابق MT5
|   |   +-- failure_recovery.py  <- Retry + dead letter queue
|   |   +-- semi_auto.py         <- حالت نیمه‌خودکار
|   |   +-- order_journal.py     <- Audit trail سفارش‌ها
|   |
|   +-- agents/                  <- Agent‌های هوش مصنوعی (13 agent)
|   |   +-- base_agent.py        <- BaseAgent ABC + VoteResult
|   |   +-- voting_engine.py     <- Weighted voting
|   |   +-- smc_agent.py         <- Smart Money Concept
|   |   +-- ml_agent.py          <- Machine Learning
|   |   +-- risk_agent.py        <- Risk assessment
|   |   +-- news_agent.py        <- News sentiment
|   |   +-- market_structure_agent.py <- Market structure
|   |   +-- liquidity_agent.py   <- Liquidity zones
|   |   +-- execution_agent.py   <- Execution timing
|   |   +-- ai_prediction_agent.py <- AI prediction
|   |   +-- security_ai_agent.py <- Security monitoring
|   |
|   +-- analysis/                <- موتور تحلیل بازار
|   |   +-- smc_engine.py        <- Smart Money Concept (3077 خط)
|   |   +-- decision_engine.py   <- تصمیم نهایی
|   |   +-- price_action_engine.py <- Price action
|   |   +-- session_manager.py   <- London/NY/Tokyo sessions
|   |
|   +-- intelligence/            <- یادگیری ماشین
|   |   +-- ml_engine.py         <- موتور ML (XGBoost + PyTorch)
|   |   +-- trade_memory.py      <- حافظه بلندمدت معاملات
|   |   +-- learning_service.py  <- سرویس یادگیری
|   |   +-- weight_adjuster.py   <- تنظیم وزن agent‌ها
|   |
|   +-- ai_prediction/           <- پیش‌بینی قیمت
|   |   +-- prediction_service.py <- سرویس پیش‌بینی
|   |   +-- model_manager.py     <- مدیریت مدل‌ها (LRU cache)
|   |   +-- feature_pipeline.py  <- Feature engineering (50+)
|   |   +-- xgboost_trainer.py   <- XGBoost training
|   |
|   +-- institutional/           <- ابزارهای سازمانی
|   |   +-- monte_carlo.py       <- Monte Carlo simulation
|   |   +-- portfolio_manager.py <- مدیریت portfolio
|   |   +-- risk_engine.py       <- VAR + CVaR
|   |   +-- rl_agent.py          <- Reinforcement Learning
|   |   +-- correlation_engine.py<- تحلیل همبستگی
|   |
|   +-- self_learning/           <- بازآموزی خودکار
|   |   +-- learning_service.py  <- سرویس یادگیری مستمر
|   |   +-- training_pipeline.py <- Pipeline آموزش
|   |   +-- performance_tracker.py <- ردیابی KPI
|   |   +-- trade_dataset_generator.py <- تولید dataset
|   |
|   +-- backtest_engine/         <- موتور بک‌تست
|   |   +-- multi_symbol_engine.py <- بک‌تست چند نماد
|   |   +-- walk_forward_advanced.py <- Walk-forward analysis
|   |   +-- monte_carlo_advanced.py <- Monte Carlo پیشرفته
|   |   +-- parameter_optimizer.py <- بهینه‌سازی پارامتر
|   |
|   +-- database/                <- لایه پایگاه داده
|   |   +-- connection.py        <- Supabase client + connection pool
|   |   +-- connection_health.py <- بررسی سلامت DB
|   |
|   +-- middleware/              <- میان‌افزارهای FastAPI
|   |   +-- security.py          <- Security headers + IP blocking
|   |   +-- rate_limit.py        <- Rate limiting (Redis)
|   |   +-- observability.py     <- Request tracing
|   |
|   +-- observability/           <- مانیتورینگ
|   |   +-- metrics.py           <- Prometheus metrics
|   |   +-- alert_manager.py     <- مدیریت alert‌ها
|   |   +-- structured_logger.py <- JSON logging
|   |   +-- tracing.py           <- Distributed tracing
|   |
|   +-- services/                <- سرویس‌های business مشترک
|   |   +-- scheduler.py         <- Background task scheduler
|   |   +-- trade_service.py     <- Trade CRUD
|   |   +-- signal_service.py    <- Signal management
|   |   +-- audit_service.py     <- Immutable audit trail
|   |   +-- rbac_service.py      <- Role-Based Access Control
|   |
|   +-- telegram/                <- ربات تلگرام
|   |   +-- bot.py               <- Entry point
|   |   +-- handlers/            <- 11 handler files
|   |   +-- routers/             <- 7 router files
|   |
|   +-- circuit_breaker.py       <- Circuit breaker
|   +-- tests/                   <- Test suite (55 فایل، 249+ test)
|
+-- mql5/                        <- کد MetaTrader 5
+-- supabase/migrations/         <- 30+ SQL migration files
```

---

## 📚 ۴. تمام ماژول‌ها، کلاس‌ها و توابع

### 4.1 -- backend/core/

#### config.py
```python
class Settings(BaseSettings):
    APP_NAME: str = "Galaxy Vast AI Trading Platform"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str            # "development" | "staging" | "production"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    SUPABASE_URL: str           # REQUIRED
    SUPABASE_KEY: str           # REQUIRED - service_role key
    SUPABASE_JWT_SECRET: str    # REQUIRED - min 32 chars
    JWT_SECRET_KEY: str         # REQUIRED - min 32 chars
    REDIS_URL: str = "redis://redis:6379/0"
    MT5_LOGIN: Optional[int]
    MT5_PASSWORD: Optional[str]
    MT5_SERVER: Optional[str]
    DEFAULT_RISK_PERCENT: float = 1.0
    MAX_LOT_SIZE: float = 10.0
    MIN_LOT_SIZE: float = 0.01
    MAX_DAILY_TRADES: int = 20
    MAX_DAILY_LOSS_PERCENT: float = 3.0
    MAX_DRAWDOWN_PERCENT: float = 10.0
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_TIMEOUT_S: int = 300
    TELEGRAM_BOT_TOKEN: Optional[str]
    TELEGRAM_ADMIN_IDS: str
    ALLOWED_ORIGINS: List[str]

def get_settings() -> Settings:
    """Singleton via @lru_cache. Always use this."""
```

#### interfaces.py -- Protocol Definitions
```python
class IRiskGate(Protocol):
    async def check(self, **kwargs) -> Any: ...
    @property
    def name(self) -> str: ...

class IRiskOrchestrator(Protocol):
    async def assess(self, inp: Any) -> Any: ...
    async def check(self, **kwargs) -> Any: ...

class IOrderBroker(Protocol):
    async def send_order(self, request: Any) -> Any: ...
    async def close_position(self, ticket: int, volume: float) -> bool: ...
    async def get_positions(self) -> List[Any]: ...
    async def health_check(self) -> bool: ...
    async def initialize(self) -> bool: ...
    async def shutdown(self) -> None: ...

class IOrderStateMachine(Protocol):
    async def create_order(self, **kwargs) -> Any: ...
    async def transition(self, order_id: str, new_state: Any, **meta) -> bool: ...
    def get_order(self, order_id: str) -> Optional[Any]: ...

class IAgent(Protocol):
    async def analyze(self, market_data: Dict) -> Any: ...
    @property
    def name(self) -> str: ...
    @property
    def weight(self) -> float: ...
```

#### exceptions.py
```
AppError
+-- RetryableError
|   +-- OrderSubmissionError
|   +-- BrokerConnectionError
|   +-- DatabaseError
+-- NonRetryableError
    +-- OrderDuplicateError  (409)
    +-- RiskBlockedError     (422)
    +-- CircuitOpenError     (503)
    +-- AuthError            (401)
    +-- ValidationError      (422)
    +-- ConfigurationError   (500)
```

#### logger.py
```python
class ContextualLogger:
    def bind(self, **context) -> "ContextualLogger": ...
    def info(self, msg: str, **kwargs) -> None: ...
    def error(self, msg: str, exc_info=False, **kwargs) -> None: ...
    def warning(self, msg: str, **kwargs) -> None: ...

def get_logger(name: str) -> ContextualLogger:
    """
    Usage:
        logger = get_logger(__name__)
        logger.info("Order submitted", order_id="uuid", lot=0.1)
    Output JSON:
        {"ts":"2026-06-25T13:00:00","level":"INFO",
         "msg":"Order submitted","order_id":"uuid","lot":0.1}
    """
```

#### retry.py
```python
class RetryStrategy(Enum):
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"

@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 60.0
    jitter: bool = True
    strategy: RetryStrategy = EXPONENTIAL
    retry_on: tuple = (RetryableError,)

# Pre-built configs
MT5_RETRY  = RetryConfig(max_attempts=3, base_delay_s=0.5)
DB_RETRY   = RetryConfig(max_attempts=5, base_delay_s=0.2)
RISK_RETRY = RetryConfig(max_attempts=2, strategy=FIXED)

@async_retry(MT5_RETRY)
async def my_function(): ...

await with_retry_async(coro_factory, config=MT5_RETRY, on_retry=cb)
```

---

### 4.2 -- backend/risk/

#### risk_orchestrator.py
```python
@dataclass
class RiskInput:
    symbol: str               # EURUSD
    direction: str            # "BUY" | "SELL"
    balance: float            # account balance (USD)
    stop_loss_pips: float     # SL distance in pips
    entry_price: float = 0.0
    stop_loss: float = 0.0
    equity: float = 0.0
    current_atr: float = 10.0
    atr_history: List[float] = []
    current_spread: float = 0.0
    avg_spread: float = 0.0
    open_positions: List[Any] = []
    today_trades_count: int = 0
    today_pnl_usd: float = 0.0
    week_pnl_usd: float = 0.0
    month_pnl_usd: float = 0.0
    user_id: str = ""
    signal_id: str = ""
    override_risk_pct: Optional[float] = None
    extra_ctx: Dict[str, Any] = {}  # win_rate, avg_rr ...

@dataclass
class RiskCheckResult:
    approved: bool
    decision: RiskDecision    # APPROVED | BLOCKED | REVIEW
    block_reason: str
    risk_percent: float
    lot_size: float
    lot_multiplier: float
    gates_passed: List[str]
    gates_failed: List[str]
    metadata: Dict[str, Any]
    def to_dict(self) -> Dict: ...

class RiskOrchestrator:
    async def assess(self, inp: RiskInput) -> RiskCheckResult: ...
    async def check(self, symbol, direction, ...) -> RiskCheckResult: ...

async def get_risk_orchestrator() -> RiskOrchestrator:
    """Singleton -- double-checked locking. All 7 gates injected."""
```

#### lot_sizing.py
```python
class LotSizer:
    async def calculate(
        self,
        balance: float,           # REQUIRED -- NOT account_balance
        stop_loss_pips: float,
        symbol: str,
        volatility_ratio: float = 1.0,  # NOT lot_multiplier
        win_rate: float = 0.55,
        avg_rr: float = 1.5,
        override_risk_pct: Optional[float] = None,
    ) -> LotSizingResult: ...
    # Formula: kelly = W - (1-W)/R; lot = kelly * balance / (sl * pip_value)
```

#### daily_limits.py
```python
@dataclass
class TodayTrades:
    trade_count: int
    pnl_usd: float
    risk_used_percent: float

class DailyLimitsEngine:
    def check_limits(
        self,
        account_balance: float,   # NOT balance_usd
        today: TodayTrades,       # TodayTrades dataclass REQUIRED
        week_pnl_usd: float,
        month_pnl_usd: float,
    ) -> DailyCheckResult: ...
```

#### equity_protection.py
```python
class EquityProtectionEngine:
    # WARNING: check() takes ZERO arguments
    # Call update_equity() first!
    def update_equity(self, equity: float, balance: float) -> None: ...
    def check(self) -> ProtectionCheckResult: ...
    # drawdown = (high_water_mark - equity) / high_water_mark
    # if drawdown > MAX_DRAWDOWN -> can_trade=False
```

#### volatility_filter.py
```python
class VolatilityFilter:
    def check(
        self,
        current_atr: float,       # POSITIONAL -- first arg
        atr_history=None,         # NOT price_distance or entry_price
        current_spread: float = 0.0,
        avg_spread: float = 0.0,
        symbol: str = "",
    ) -> VolatilityCheckResult: ...
    def load_news_events(self, events: List[NewsEvent]) -> None:
        # events must be from backend.risk.news_filter.NewsEvent
```

#### correlation_filter.py
```python
class CorrelationFilter:
    async def check(
        self,
        new_symbol: str,           # NOT "symbol"
        new_direction: str,        # NOT "direction"
        open_positions: List[CorrPosition],
        base_risk_percent: float,
    ) -> CorrelationCheckResult: ...
```

---

### 4.3 -- backend/execution/

#### execution_service.py
```python
class ExecutionService:
    def __init__(
        self,
        broker: IOrderBroker,
        risk: IRiskOrchestrator,
        osm: IOrderStateMachine,
        fr: IFailureRecovery,
        pr: Any,  # PositionReconciliation
    ): ...

    async def start(self) -> None:
        # Must be called before execute_signal()
        # Wires: MT5.initialize() -> OSM.start() -> FR.start()
        #   -> PR.set_mt5(self._mt5) -> PR.start()

    async def execute_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        signal fields:
          signal_id (REQUIRED), symbol (REQUIRED), direction (REQUIRED)
          entry_price, stop_loss, take_profit, stop_loss_pips
          balance, equity, current_atr, lot_size (override)
          today_trades_count, today_pnl_usd, week_pnl_usd, month_pnl_usd
          user_id, win_rate, avg_rr

        Returns:
          status: "FILLED" | "BLOCKED" | "ERROR"
          order_id, ticket, lot_size, risk_percent, fill_latency_ms
        """
```

#### order_state_machine.py
```python
class OrderState(Enum):
    PENDING   = "PENDING"    # created
    SUBMITTED = "SUBMITTED"  # sent to MT5
    FILLED    = "FILLED"     # confirmed by broker
    CLOSING   = "CLOSING"    # being closed
    CLOSED    = "CLOSED"     # closed
    CANCELLED = "CANCELLED"  # cancelled
    ERROR     = "ERROR"      # error

# Valid transitions:
# PENDING -> SUBMITTED | CANCELLED | ERROR
# SUBMITTED -> FILLED | ERROR
# FILLED -> CLOSING | CLOSED
# CLOSING -> CLOSED | ERROR
```

---

### 4.4 -- backend/agents/

```python
@dataclass
class AgentVote:
    agent_name: str
    direction: str         # "BUY" | "SELL" | "HOLD"
    confidence: float      # 0.0 - 1.0
    reasoning: str
    metadata: Dict[str, Any]

class BaseAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @property
    def weight(self) -> float: return 1.0  # override for different weights
    @abstractmethod
    async def analyze(self, market_data: Dict) -> AgentVote: ...

@dataclass
class VoteResult:
    decision: str          # "BUY" | "SELL" | "HOLD" | "BLOCKED"
    confidence: float      # 0.0 - 1.0
    votes_buy: int
    votes_sell: int
    votes_hold: int
    reasoning: str
    agent_votes: List[Dict]
    def to_dict(self) -> Dict: ...

class VotingEngine:
    async def vote(self, market_data: Dict) -> VoteResult:
        """Runs all agents in parallel via asyncio.gather."""
```

---

### 4.5 -- circuit_breaker.py

```python
class CircuitState(Enum):
    CLOSED = "CLOSED"      # normal
    OPEN = "OPEN"          # halted
    HALF_OPEN = "HALF_OPEN" # probing

# Algorithm:
# 5 failures in 60s -> OPEN
# After 300s -> HALF_OPEN
# 2 successes -> CLOSED
# Any failure in HALF_OPEN -> OPEN (reset timer)

async def get_mt5_breaker() -> CircuitBreaker: ...  # singleton
async def halt_trading(reason: str) -> None: ...    # manual halt
async def resume_trading() -> None: ...             # manual resume
```

---

### 4.6 -- api/health.py

```
GET /health          -> {"status": "healthy"}   # liveness
GET /health/ready    -> {"status": "ready"}      # readiness
GET /health/deep     -> {
    status: "healthy" | "degraded" | "unhealthy",
    components: {
        database:          {status: "up", latency_ms: 5},
        redis:             {status: "up", latency_ms: 2},
        mt5_connector:     {status: "up" | "down"},
        risk_engine:       {status: "up"},
        circuit_breaker:   {status: "CLOSED" | "OPEN"},
        equity_protection: {status: "ACTIVE" | "HALTED"},
    }
}
```

---

## 🔧 ۵. نحوه نصب

### پیش‌نیازها

```
Python >= 3.11
Docker >= 24.0
Docker Compose >= 2.20
Git >= 2.40
Redis >= 7.0 (for local dev without Docker)
```

### گام ۱ -- Clone

```bash
git clone https://github.com/sani13790000/bot12.git
cd bot12
```

### گام ۲ -- تنظیم Environment

```bash
cp .env.example .env
nano .env
```

**فیلدهای اجباری:**
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=min-32-chars-secret
JWT_SECRET_KEY=min-32-chars-secret  # generate: python -c "import secrets; print(secrets.token_hex(32))"
MT5_LOGIN=12345678
MT5_PASSWORD=your-password
MT5_SERVER=YourBroker-Real
```

### گام ۳ -- نصب Dependencies

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
python -c "import fastapi, pydantic, supabase; print('OK')"
```

### گام ۴ -- Database Migrations

```bash
npm install -g supabase
supabase db push --project-ref YOUR_REF
```

### گام ۵ -- تایید Setup

```bash
PYTHONPATH=. python startup_check.py
# -> System ready to start.
```

---

## 🚀 ۶. نحوه اجرا

### Docker Compose (توصیه‌شده)

```bash
# Development
docker compose up --build

# Production
docker compose -f docker-compose.prod.yml up -d

# Logs
docker compose logs -f api

# Stop
docker compose down
```

### اجرای مستقیم Python

```bash
# API
PYTHONPATH=. uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload

# Telegram Bot
PYTHONPATH=. python -m backend.telegram.bot
```

### تایید اجرا

```bash
curl http://localhost:8000/health
# -> {"status":"healthy","version":"2.0.0"}

curl -s http://localhost:8000/health/deep | python -m json.tool
```

---

## 🔐 ۷. متغیرهای ENV

```env
# APP
ENVIRONMENT=production      # development | staging | production
DEBUG=false
LOG_LEVEL=INFO              # DEBUG | INFO | WARNING | ERROR

# DATABASE -- REQUIRED
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=service_role_key  # NOT anon key!
SUPABASE_JWT_SECRET=32+chars

# JWT -- REQUIRED
JWT_SECRET_KEY=32+chars
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30

# REDIS
REDIS_URL=redis://redis:6379/0
REDIS_PASSWORD=changeme
REDIS_MAX_CONNECTIONS=20

# MT5 TRADING
MT5_LOGIN=12345678
MT5_PASSWORD=pass
MT5_SERVER=Broker-Real
MT5_TIMEOUT_SECONDS=30

# RISK
DEFAULT_RISK_PERCENT=1.0
MAX_LOT_SIZE=10.0
MIN_LOT_SIZE=0.01
MAX_DAILY_TRADES=20
MAX_DAILY_LOSS_PERCENT=3.0
MAX_DRAWDOWN_PERCENT=10.0
MAX_EXPOSURE_PERCENT=20.0
INITIAL_ACCOUNT_BALANCE=10000.0

# CIRCUIT BREAKER
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT_S=300

# TELEGRAM
TELEGRAM_BOT_TOKEN=123:token
TELEGRAM_ADMIN_IDS=123456,789012

# CORS
ALLOWED_ORIGINS=https://yourdomain.com

# ML
BACKTEST_MAX_WORKERS=4
DRIFT_THRESHOLD=0.1
SEMI_AUTO_PENDING_TTL_S=300
```

---

## ⚙️ ۸. تنظیمات سیستم

### حساب کوچک (< $10,000)
```env
DEFAULT_RISK_PERCENT=0.5
MAX_LOT_SIZE=1.0
MAX_DAILY_TRADES=5
MAX_DAILY_LOSS_PERCENT=1.5
MAX_DRAWDOWN_PERCENT=5.0
```

### حساب متوسط ($10k-$100k)
```env
DEFAULT_RISK_PERCENT=1.0
MAX_LOT_SIZE=5.0
MAX_DAILY_TRADES=15
MAX_DRAWDOWN_PERCENT=8.0
```

### حساب بزرگ (> $100,000)
```env
DEFAULT_RISK_PERCENT=0.5  # کمتر برای سرمایه بزرگ
MAX_LOT_SIZE=50.0
MAX_DAILY_TRADES=30
MAX_DRAWDOWN_PERCENT=6.0
```

---

## 🐳 ۹. Docker

```bash
# Build
docker compose build
docker compose build --no-cache api

# Run
docker compose up -d
docker compose logs -f api
docker compose exec api bash
docker compose restart api
docker compose down -v
docker stats
```

### Dockerfile highlights

```
Multi-stage: builder (gcc + pip install) -> runtime (slim)
Non-root user: galaxyvast
Healthcheck: curl /health every 30s
EXPOSE 8000
CMD: uvicorn with 2 workers + graceful shutdown 30s
```

---

## 🔄 ۱۰. CI/CD

```
Push to main/develop
    |
    v
[backend] ruff + mypy + pytest + bandit + pip-audit
    |
    v
[docker-build] build api + bot images
    |
    v (only main or tag)
[deploy] staging (auto) | production (manual approval)
```

```bash
# Local checks
ruff check backend/ --select=E,W,F,I --ignore=E501
mypy backend/ --ignore-missing-imports
OTEL_SDK_DISABLED=true pytest backend/tests/ -q
bandit -r backend/ -ll
pip-audit --requirement requirements.txt
```

---

## 👨‍💻 ۱۱. نحوه توسعه

### اضافه کردن Agent جدید

```python
# backend/agents/momentum_agent.py
from backend.agents.base_agent import BaseAgent, AgentVote

class MomentumAgent(BaseAgent):
    @property
    def name(self) -> str: return "momentum_agent"
    @property
    def weight(self) -> float: return 1.2

    async def analyze(self, market_data: Dict) -> AgentVote:
        rsi = market_data.get("rsi", 50.0)
        macd = market_data.get("macd", 0.0)
        if rsi < 30 and macd > 0:
            return AgentVote(self.name, "BUY", 0.75, f"RSI={rsi:.0f}+MACD+", {})
        elif rsi > 70 and macd < 0:
            return AgentVote(self.name, "SELL", 0.75, f"RSI={rsi:.0f}+MACD-", {})
        return AgentVote(self.name, "HOLD", 0.5, "No momentum", {})
```

### اضافه کردن Route جدید

```python
# backend/api/routes/my_route.py
from fastapi import APIRouter, Depends
from backend.core.auth import require_auth

router = APIRouter(prefix="/my-feature", tags=["My Feature"])

@router.get("/status")
async def get_status(user=Depends(require_auth)):
    return {"status": "OK"}

# Register in main.py:
# from backend.api.routes import my_route
# app.include_router(my_route.router, prefix="/api/v1")
```

### استانداردهای کد

```python
# Always: from __future__ import annotations
# Always: full type hints
# Always: structured logging (not f-strings)
# Always: AppError subclass (not Exception)

logger.info("Order submitted", order_id=oid, symbol=sym, lot=lot)  # CORRECT
logger.info(f"Order {oid} submitted")                              # WRONG

raise RiskBlockedError("High ATR", context={"atr": 45, "thr": 30}) # CORRECT
raise Exception("error")                                           # WRONG
```

---

## 🔍 ۱۲. نحوه دیباگ

```bash
# Logs
docker compose logs -f api
docker compose logs api | grep '"level":"ERROR"'

# Debug mode
# .env: ENVIRONMENT=development, DEBUG=true, LOG_LEVEL=DEBUG
uvicorn backend.api.main:app --reload --log-level debug

# System status
curl -s http://localhost:8000/health/deep | python -m json.tool
curl -s http://localhost:8000/api/v1/risk/circuit-breaker/status
curl -s http://localhost:8000/metrics | grep galaxy_vast

# Common issues
# Circuit breaker OPEN:
curl -X POST http://localhost:8000/api/v1/risk/circuit-breaker/reset \
  -H "Authorization: Bearer ADMIN_TOKEN"

# Telegram conflict:
docker compose restart telegram_bot

# MT5 not connected:
curl http://localhost:8000/health/deep | python -m json.tool | grep mt5
```

---

## 💾 ۱۳. نحوه بکاپ

```bash
# Database
pg_dump "postgresql://postgres:[PASS]@db.[PROJECT].supabase.co:5432/postgres" \
  --no-owner --no-acl -F c -f backup_$(date +%Y%m%d).dump

# Redis
docker compose exec redis redis-cli -a "${REDIS_PASSWORD}" SAVE
docker compose cp redis:/data/dump.rdb ./backups/redis_$(date +%Y%m%d).rdb

# Models
tar -czf models_$(date +%Y%m%d).tar.gz ./models/

# Cron (daily 2am)
0 2 * * * /path/to/scripts/backup.sh
```

---

## 🔄 ۱۴. نحوه آپدیت

```bash
# Standard update
git pull origin main
pip install -r requirements.txt
supabase db push --project-ref YOUR_REF
docker compose build api && docker compose up -d api
curl http://localhost:8000/health/deep

# Rollback
git log --oneline -10
git checkout [COMMIT_SHA]
docker compose build api && docker compose up -d api
```

---

## 🤖 ۱۵. آموزش مدل‌های ML

### Pipeline

```
DB Trades -> TradeDatasetGenerator -> FeaturePipeline (50+ features)
-> TrainingPipeline (walk-forward, 12 folds)
-> ModelManager (versioning, LRU cache)
-> PredictionService (async, thread-safe)
```

### Features

| دسته | Features |
|------|----------|
| Price | OHLCV, Returns, Log returns |
| Technical | RSI, MACD, BB, ATR, EMA(9,21,50,200) |
| SMC | Order blocks, FVG, Liquidity, BOS, ChoCH |
| Session | London/NY/Tokyo/Overlap |
| Volatility | ATR ratio, Spread ratio |
| Time | Hour, Day, Month |

### آموزش دستی

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/self-learning/train \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -d '{"model_type":"xgboost","lookback_days":90,"min_trades":100}'

# Via Python
python -c "
import asyncio
from backend.self_learning.training_pipeline import TrainingPipeline
from backend.self_learning.trade_dataset_generator import TradeDatasetGenerator

async def main():
    gen = TradeDatasetGenerator()
    dataset = await gen.generate(lookback_days=90)
    print(f'Dataset: {len(dataset)} samples')
    result = await TrainingPipeline().train(dataset)
    print(f'Accuracy: {result.accuracy:.2%}')
asyncio.run(main())
"
```

---

## 🔗 ۱۶. اتصال به صرافی‌ها و بروکرها

### MetaTrader 5

```bash
# .env
MT5_LOGIN=12345678
MT5_PASSWORD=your-password
MT5_SERVER=YourBroker-Real

# Test connection
curl http://localhost:8000/health/deep | python -m json.tool | grep -A3 mt5
```

### MQL5 EA -- ارسال سیگنال

```mql5
// In your EA:
string body = StringFormat(
    "{\"signal_id\":\"%s\",\"symbol\":\"%s\",\"direction\":\"%s\","
    "\"entry_price\":%.5f,\"stop_loss\":%.5f,\"take_profit\":%.5f}",
    signal_id, Symbol(), direction, entry, sl, tp
);
WebRequest("POST", api_url+"/api/v1/signals",
           "Content-Type: application/json\r\nAuthorization: Bearer "+key,
           0, body, response, error);
```

### اضافه بروکر غیر-MT5

```python
class MyBrokerConnector:
    # Implement IOrderBroker protocol:
    async def initialize(self) -> bool: ...
    async def shutdown(self) -> None: ...
    async def health_check(self) -> bool: ...
    async def send_order(self, request) -> Any: ...
    async def close_position(self, ticket, volume) -> bool: ...
    async def get_positions(self) -> List: ...

# Use:
service = ExecutionService(broker=MyBrokerConnector(), ...)
```

---

## 🛡️ ۱۷. مدیریت ریسک

### ۷ لایه ریسک

```
Gate 1 - Daily Limits:
  max_daily_trades (20) | max_daily_loss% (3%) | weekly/monthly limits

Gate 2 - Equity Protection:
  drawdown = (HWM - equity) / HWM
  if drawdown > 10% -> HALT

Gate 3 - Volatility Filter:
  ATR check | spread check | news blocking (NFP/CPI/FOMC)

Gate 4 - Correlation Filter:
  new_symbol vs open_positions correlation < threshold
  e.g. EURUSD+GBPUSD both BUY -> corr 0.85 -> BLOCKED

Gate 5 - Exposure Control:
  sum(risk of all open positions) < MAX_EXPOSURE% (20%)

Gate 6 - Portfolio Risk:
  VAR | concentration | direction bias

Gate 7 - Lot Sizing (Kelly):
  f* = W - (1-W)/R
  blend = f* x 0.25 + fixed x 0.75 (conservative)
  lot = blend * balance / (sl_pips * pip_value)
```

### Circuit Breaker

```
CLOSED -> [5 fails/60s] -> OPEN -> [300s] -> HALF_OPEN -> [2 success] -> CLOSED
                                              HALF_OPEN -> [fail] -> OPEN (reset)
```

### کنترل دستی

```bash
# Halt
curl -X POST http://localhost:8000/api/v1/risk/circuit-breaker/halt \
  -H "Authorization: Bearer ADMIN_TOKEN" -d '{"reason":"Manual halt"}'

# Resume
curl -X POST http://localhost:8000/api/v1/risk/circuit-breaker/reset \
  -H "Authorization: Bearer ADMIN_TOKEN"

# Telegram
/halt    <- stop trading
/resume  <- continue
/status  <- full status
/set_risk 0.5
```

---

## 🚨 ۱۸. راهنمای رفع خطا

| خطا | علت | راه‌حل |
|-----|-----|--------|
| `RuntimeError: no running event loop` | asyncio.Lock() در import time | lazy init pattern |
| `ImportError: No module named backend.X` | PYTHONPATH تنظیم نیست | `export PYTHONPATH=.` |
| `Circuit Breaker OPEN` | شکست‌های متوالی | بررسی logs + reset |
| `Equity Protection HALTED` | drawdown بیش از حد | بستن موقعیت‌ها یا reset |
| `Duplicate order` | signal_id قبلاً execute شده | این feature است -- signal_id جدید |
| `Daily limit reached` | حد روزانه | فردا ادامه دهید |
| `MT5 not connected` | MT5 Terminal خاموش | restart MT5 |
| `Telegram conflict` | دو instance از bot | `docker compose restart telegram_bot` |
| `Redis connection refused` | Redis down است | `docker compose restart redis` |
| `JWT token expired` | توکن منقضی شده | دوباره login |

---

## 📡 ۱۹. API Reference

### Authentication

```bash
POST /api/v1/auth/login
{"username": "admin@example.com", "password": "pass"}
# -> {"access_token": "JWT...", "refresh_token": "JWT..."}

# All other requests:
Authorization: Bearer JWT_TOKEN
```

### سیگنال‌ها

```bash
# ارسال سیگنال
POST /api/v1/signals
{
  "signal_id": "uuid",     # REQUIRED
  "symbol": "EURUSD",      # REQUIRED
  "direction": "BUY",      # REQUIRED
  "entry_price": 1.0850,
  "stop_loss": 1.0800,
  "take_profit": 1.0950,
  "stop_loss_pips": 50,
  "win_rate": 0.60,
  "avg_rr": 1.8
}
# -> {status: "FILLED", ticket: 12345678, lot_size: 0.1, ...}

GET /api/v1/signals?limit=20&offset=0
```

### ریسک

```bash
POST /api/v1/risk/assess           # evaluate without executing
GET  /api/v1/risk/circuit-breaker/status
POST /api/v1/risk/circuit-breaker/halt
POST /api/v1/risk/circuit-breaker/reset
GET  /api/v1/risk/daily-status
```

### معاملات

```bash
GET    /api/v1/trades?status=OPEN&symbol=EURUSD
DELETE /api/v1/trades/{trade_id}   # close
GET    /api/v1/trades/statistics?period=today
```

### WebSocket

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/signals?token=JWT");
ws.onmessage = (e) => {
  const d = JSON.parse(e.data);
  // types: SIGNAL_NEW, SIGNAL_FILLED, SIGNAL_BLOCKED, RISK_ALERT, HEARTBEAT
};
```

### Health

```
GET /health         -> liveness
GET /health/ready   -> readiness
GET /health/deep    -> full check
GET /metrics        -> Prometheus
```

---

## 📖 ۲۰. Glossary

| اصطلاح | توضیح |
|--------|--------|
| ATR | Average True Range -- معیار نوسان |
| BOS | Break of Structure -- شکست ساختار (SMC) |
| ChoCH | Change of Character -- تغییر جهت (SMC) |
| Circuit Breaker | توقف خودکار در شکست‌های متوالی |
| DI | Dependency Injection -- تزریق وابستگی |
| Drawdown | کاهش از اوج به کف (%) |
| EA | Expert Advisor -- ربات MT5 |
| Equity | ارزش فعلی حساب |
| FAIL_CLOSED | خطا -> block trade (ایمن‌تر) |
| FVG | Fair Value Gap -- شکاف ارزش (SMC) |
| Gate | یک لایه بررسی ریسک |
| HWM | High Water Mark -- بالاترین equity تاریخی |
| Idempotency | اجرای مکرر، نتیجه یکسان |
| Kelly Criterion | فرمول بهینه‌سازی حجم |
| Lot | واحد حجم (1 lot = 100,000 واحد) |
| MT5 | MetaTrader 5 |
| MQL5 | زبان MT5 |
| Pip | کوچکترین واحد تغییر قیمت |
| RBAC | Role-Based Access Control |
| SMC | Smart Money Concept |
| Singleton | فقط یک instance |
| SL | Stop Loss |
| TP | Take Profit |
| VAR | Value at Risk |
| VotingEngine | جمع‌آوری آرای agent‌ها |

---

*آخرین بروزرسانی: ۲۰۲۶-۰۶-۲۵ | نسخه ۲.۰.۰ | Python 3.11 | FastAPI 0.115*
