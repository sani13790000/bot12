# Galaxy Vast AI Trading Platform — Technical Reference

> **بخش دوم مستندات** | ماژول‌ها · کلاس‌ها · توابع
>
> 📊 **آمار:** ۱۲۳ کلاس | ۳۱۶ متد | ۳۰ ماژول | استخراج مستقیم از source code

---

## فهرست مطالب

- [Section 4 — Modules Documentation](#4-modules-documentation)
- [Section 5 — Classes Documentation](#5-classes-documentation)
- [Section 6 — Functions Documentation](#6-functions-documentation)

---

# 4. Modules Documentation

> **برای تازه‌کار:** هر Package یک کار مشخص انجام می‌دهد. لایه‌های داخلی هرگز از لایه‌های خارجی import نمی‌کنند.

```
╔══════════════════════════════════════════════════════╗
║                    API Layer                         ║
║  api/main.py → api/routes/* → api/health.py          ║
╚═══════════════════════════╦══════════════════════════╝
                            ║ depends on
╔═══════════════════════════╩══════════════════════════╗
║                  Service Layer                        ║
║  agents/  →  execution/  →  risk/  →  intelligence/  ║
╚═══════════════════════════╦══════════════════════════╝
                            ║ depends on
╔═══════════════════════════╩══════════════════════════╗
║              Infrastructure Layer                     ║
║        database/  →  middleware/  →  circuit_breaker  ║
╚═══════════════════════════╦══════════════════════════╝
                            ║ depends on
╔═══════════════════════════╩══════════════════════════╗
║                   Core Layer                          ║
║  core/interfaces.py  core/exceptions.py  core/retry  ║
║  core/logger.py  core/deps.py  core/enums.py          ║
╚══════════════════════════════════════════════════════╝
```

---

## 4.1 Core Package

> بنیادی‌ترین لایه. هیچ وابستگی داخلی ندارد. همه لایه‌ها از اینجا import می‌کنند.

| ماژول | فایل | توضیح | نقش | وابستگی خارجی |
|-------|------|-------|-----|---------------|
| **config** | `backend/core/config.py` | تنظیمات Pydantic BaseSettings | بارگذاری ENV vars، validation | `pydantic-settings` |
| **enums** | `backend/core/enums.py` | ۲۷ Enum — `TradeDirection`, `OrderStatus`, `MarketSession`, ... | Single source of truth | stdlib |
| **exceptions** | `backend/core/exceptions.py` | سلسله‌مراتب exception با HTTP status code | همه لایه‌ها از اینجا raise می‌کنند | stdlib |
| **interfaces** | `backend/core/interfaces.py` | Protocol definitions — `IRiskGate`, `IOrderBroker`, `ILotSizer`, `IAgent` | قرارداد بین لایه‌ها (SOLID-I) | `typing_extensions` |
| **logger** | `backend/core/logger.py` | Structured JSON logging | `ContextualLogger` + `AuditLogger` | `logging`, `json` |
| **retry** | `backend/core/retry.py` | Retry با exponential backoff | `@async_retry`, `with_retry_async()`, `RetryConfig` | `asyncio` |
| **auth** | `backend/core/auth.py` | JWT authentication | Token decode/verify | `jose`, `passlib` |
| **deps** | `backend/core/deps.py` | FastAPI Dependency Injection container | همه singletons از اینجا inject می‌شوند | `fastapi` + همه modules |
| **security** | `backend/core/security.py` | Password hashing، token generation | bcrypt، token helpers | `passlib`, `secrets` |
| **cache** | `backend/core/cache.py` | Redis caching utilities | TTL cache، invalidation | `redis.asyncio` |
| **validators** | `backend/core/validators.py` | Input validation helpers | symbol، lot، price validation | `pydantic` |
| **unified_types** | `backend/core/unified_types.py` | Shared dataclass types | `TradeContext`, `RiskInput`, `RiskResult` | stdlib |

---

## 4.2 Risk Package — ۷ Gate موازی

> هر signal باید از همه ۷ gate عبور کند. `RiskOrchestrator` همه را هماهنگ می‌کند.

| ماژول | فایل | توضیح | ورودی | خروجی | وابستگی |
|-------|------|-------|-------|-------|--------|
| **risk_orchestrator** | `backend/risk/risk_orchestrator.py` | هماهنگ‌کننده همه gate ها. Singleton با double-checked locking | `RiskInput` | `RiskDecision` | همه ۷ gate |
| **equity_protection** | `backend/risk/equity_protection.py` | حفاظت equity. Drawdown ≤ X% → halt | `equity: float` | `ProtectionCheckResult` | — |
| **daily_limits** | `backend/risk/daily_limits.py` | محدودیت روزانه trade/ضرر. Reset روزانه | `TradeContext` | `LimitsCheckResult` | `datetime` |
| **lot_sizing** | `backend/risk/lot_sizing.py` | محاسبه حجم. Kelly formula | `symbol, risk_pct, sl_pips` | `LotSizeResult` | MT5 pip data |
| **volatility_filter** | `backend/risk/volatility_filter.py` | فیلتر نوسان ATR + news blackout | `symbol, atr` | `bool` | `news_filter` |
| **correlation_filter** | `backend/risk/correlation_filter.py` | جلوگیری از trades همبسته. Pearson rolling | `new_symbol, new_direction` | `CorrelationResult` | — |
| **exposure_control** | `backend/risk/exposure_control.py` | کنترل exposure. Max lot per symbol/currency | `symbol, lot` | `ExposureCheckResult` | — |
| **news_filter** | `backend/risk/news_filter.py` | فیلتر اخبار. HIGH/MEDIUM impact → block | `currency, time` | `NewsBlockResult` | ForexFactory API |
| **portfolio_risk** | `backend/risk/portfolio_risk.py` | Portfolio-level risk. Max symbols، direction bias | Portfolio state | `bool` | `core/enums` |

---

## 4.3 Execution Package — Pipeline کامل Signal تا MT5

| ماژول | فایل | توضیح | نقش |
|-------|------|-------|-----|
| **execution_service** | `backend/execution/execution_service.py` | نقطه ورودی. `execute(signal)` → risk → lot → MT5 | Orchestrator اصلی |
| **mt5_connector** | `backend/execution/mt5_connector.py` | اتصال MetaTrader 5. Thread-safe asyncio.Lock | تنها نقطه تماس با broker |
| **order_state_machine** | `backend/execution/order_state_machine.py` | FSM: `PENDING→SUBMITTED→FILLED/FAILED` | ردیابی دقیق وضعیت order |
| **failure_recovery** | `backend/execution/failure_recovery.py` | Retry queue + dead letter queue (max 500) | تضمین اجرا حتی در خطا |
| **position_reconciliation** | `backend/execution/position_reconciliation.py` | مطابقت positions با MT5. Orphan detection | جلوگیری از duplicate trade |
| **order_journal** | `backend/execution/order_journal.py` | ثبت immutable هر رویداد. Audit trail | Compliance و post-trade analysis |
| **semi_auto** | `backend/execution/semi_auto.py` | حالت نیمه‌خودکار. تأیید انسانی | کنترل دستی معاملات |

---

## 4.4 Agents Package — Multi-Agent Voting

| Agent | فایل | وزن | Veto | تخصص |
|-------|------|-----|------|---------|
| **SMCAgent** | `agents/smc_agent.py` | ۲۵٪ | ✗ | Smart Money: BOS، CHoCH، FVG |
| **MLAgent** | `agents/ml_agent.py` | ۲۰٪ | ✗ | ML prediction |
| **PriceActionAgent** | `agents/price_action_agent.py` | ۱۵٪ | ✗ | کندل‌شناسی، Pin Bar |
| **MarketStructureAgent** | `agents/market_structure_agent.py` | ۱۵٪ | ✗ | Supply/Demand zones |
| **RiskAgent** | `agents/risk_agent.py` | — | ✓ | ریسک نهایی — می‌تواند block کند |
| **NewsAgent** | `agents/news_agent.py` | ۱۰٪ | ✓ | تحلیل اخبار NFP/CPI/FOMC |
| **LiquidityAgent** | `agents/liquidity_agent.py` | ۵٪ | ✗ | نقاط نقدشوندگی |
| **AIPredictionAgent** | `agents/ai_prediction_agent.py` | ۵٪ | ✗ | AI calibrated probability |
| **ExecutionAgent** | `agents/execution_agent.py` | — | ✗ | بهینه‌سازی entry point |
| **VotingEngine** | `agents/voting_engine.py` | — | — | جمع‌بندی، tie-breaking |
| **BaseAgent** | `agents/base_agent.py` | — | — | Abstract base class |

```
قانون رأی‌گیری:
  BUY weighted_score  ≥ threshold(0.60)  →  EXECUTE BUY
  SELL weighted_score ≥ threshold(0.60)  →  EXECUTE SELL
  هر Veto agent مخالف                  →  BLOCKED
  Circuit Breaker OPEN                   →  BLOCKED
  timeout > 5s                           →  BLOCKED (conservative)
```

---

## 4.5 Analysis Package

| ماژول | فایل | توضیح | خروجی |
|-------|------|-------|-------|
| **decision_engine** | `backend/analysis/decision_engine.py` | موتور تصمیم‌گیری اصلی. Multi-timeframe. ۷۴۶ خط | `DecisionOutput {approved, confidence, levels}` |
| **smc_engine** | `backend/analysis/smc_engine.py` | Smart Money Concepts. BOS، CHoCH، FVG، Liquidity. ۳۰۷۷ خط | `SMCScoreResult` |

---

## 4.6 Intelligence Package

| ماژول | فایل | توضیح |
|-------|------|-------|
| **ml_engine** | `backend/intelligence/ml_engine.py` | XGBoost + Walk-Forward CV + CalibratedClassifierCV |
| **trade_memory** | `backend/intelligence/trade_memory.py` | ذخیره TradeContext برای training |
| **learning_service** | `backend/intelligence/learning_service.py` | یادگیری مداوم. Trigger: ۱۰۰ trade یا ۷ روز |
| **weight_adjuster** | `backend/intelligence/weight_adjuster.py` | تنظیم dynamic وزن agents |
| **failure_analyzer** | `backend/intelligence/failure_analyzer.py` | تحلیل trades ناموفق، pattern extraction |

---

## 4.7 Observability Package

| ماژول | فایل | توضیح |
|-------|------|-------|
| **metrics** | `backend/observability/metrics.py` | Prometheus Counter/Gauge/Histogram. `GET /metrics` |
| **alert_manager** | `backend/observability/alert_manager.py` | AlertDeduplicator، flood prevention |
| **structured_logger** | `backend/observability/structured_logger.py` | JSON logging با ECS format |
| **tracing** | `backend/observability/tracing.py` | OpenTelemetry distributed tracing |

---

## 4.8 Services Package

| سرویس | فایل | توضیح | Singleton |
|-------|------|-------|----------|
| **scheduler** | `backend/services/scheduler.py` | Background task registry. Register/run/monitor | ✅ |
| **audit_service** | `backend/services/audit_service.py` | ثبت رویدادها. Immutable log | ✅ |
| **rbac** | `backend/services/rbac.py` | Role-Based Access Control. Permission cache | ✅ |
| **trade_service** | `backend/services/trade_service.py` | CRUD معاملات، statistics | — |
| **signal_service** | `backend/services/signal_service.py` | پردازش و validation سیگنال‌ها | — |
| **session_manager** | `backend/services/session_manager.py` | Redis-based session management | — |

---

## 4.9 API Package

| فایل | Route Prefix | توضیح |
|------|-------------|-------|
| `api/main.py` | — | FastAPI app، lifespan، middleware، router registration |
| `api/health.py` | `/health` | Liveness، Readiness، Deep health check |
| `api/routes/signals.py` | `/api/v1/signals` | دریافت و پردازش signals |
| `api/routes/trades.py` | `/api/v1/trades` | تاریخچه و مدیریت معاملات |
| `api/routes/risk.py` | `/api/v1/risk` | ارزیابی ریسک، Circuit Breaker control |
| `api/routes/users.py` | `/api/v1/users` | مدیریت کاربران، RBAC |
| `api/routes/analytics.py` | `/api/v1/analytics` | آمار عملکرد |
| `api/routes/backtest.py` | `/api/v1/backtest` | اجرای backtest |
| `api/websocket_routes.py` | `/ws` | Real-time WebSocket updates |

---

## 4.10 Root Level

| فایل | توضیح |
|------|-------|
| `backend/circuit_breaker.py` | Circuit Breaker برای MT5. 3-state FSM. Singleton |
| `backend/database/connection.py` | Supabase async connection pool |
| `backend/telegram/bot.py` | aiogram3 Telegram Bot |
| `backend/middleware/` | Rate limiting، Security، Observability |
| `backend/backtest_engine/` | موتور backtest |
| `backend/institutional/` | Monte Carlo، RL Agent (PPO/SAC)، tick backtest |

---

# 5. Classes Documentation

> **برای تازه‌کار:** هر class یک موجودیت با داده‌ها و قابلیت‌هایش.  
> **برای حرفه‌ای:** همه signatures مستقیم از source code استخراج شده (AST parse).

---

## 5.1 Core — Exception Hierarchy

### `class AppError(Exception)`

| | |
|---|---|
| **فایل** | `backend/core/exceptions.py` |
| **توضیح** | Base exception با HTTP status code، error code، و context |

```python
class AppError(Exception):
    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        http_status: int = 500,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None
    def to_dict(self) -> Dict[str, Any]
```

**سلسله‌مراتب:**
```
AppError
├── RetryableError         → retry.py این را recognize می‌کند
│   ├── OrderSubmissionError
│   ├── BrokerConnectionError
│   └── DatabaseError
└── NonRetryableError      → فوری raise می‌شود
    ├── OrderDuplicateError  (409)
    ├── RiskBlockedError     (422)
    ├── CircuitOpenError     (503)
    └── AuthenticationError  (401)
```

**مثال:**
```python
from backend.core.exceptions import RiskBlockedError
raise RiskBlockedError(
    "Daily loss limit exceeded",
    context={"daily_loss_pct": 3.2, "limit_pct": 3.0}
)
```

---

### `class RetryConfig`

| | |
|---|---|
| **فایل** | `backend/core/retry.py` |
| **توضیح** | Configuration برای retry mechanism با exponential backoff |

```python
@dataclass
class RetryConfig:
    max_attempts:   int   = 3
    base_delay_s:   float = 0.5
    max_delay_s:    float = 30.0
    backoff_factor: float = 2.0
    strategy:       RetryStrategy = RetryStrategy.EXPONENTIAL
    retry_on:       Tuple[type, ...] = (RetryableError,)
    no_retry_on:    Tuple[type, ...] = (NonRetryableError,)

# پروفایل‌های آماده:
MT5_RETRY  = RetryConfig(max_attempts=3, base_delay_s=0.5, strategy=EXPONENTIAL)
DB_RETRY   = RetryConfig(max_attempts=5, base_delay_s=0.2, strategy=EXPONENTIAL)
RISK_RETRY = RetryConfig(max_attempts=2, base_delay_s=0.1, strategy=FIXED)
```

**مثال:**
```python
@async_retry(MT5_RETRY)
async def send_order(request: MT5OrderRequest) -> MT5OrderResult:
    return await mt5.order_send(request)

# یا programmatic:
result = await with_retry_async(
    lambda: broker.send_order(req),
    config=MT5_RETRY,
    on_retry=lambda attempt, err, delay: metrics.order_retry(symbol)
)
```

---

### `class ContextualLogger`

| | |
|---|---|
| **فایل** | `backend/core/logger.py` |
| **توضیح** | JSON structured logger با request-scoped context |

```python
class ContextualLogger:
    def bind(self, **fields: Any) -> "ContextualLogger"
    def info(self, msg: str, **kwargs: Any) -> None
    def warning(self, msg: str, **kwargs: Any) -> None
    def error(self, msg: str, **kwargs: Any) -> None
    def critical(self, msg: str, **kwargs: Any) -> None
    def debug(self, msg: str, **kwargs: Any) -> None

class AuditLogger:
    def record(self, action: str, actor: str, resource: str,
               result: str, **meta: Any) -> None
```

**مثال:**
```python
logger = get_logger("execution.service")
logger.info("Order submitted", order_id="ord_001", symbol="EURUSD", fill_ms=12.3)
# JSON: {"ts":"2026-06-25T16:00:00Z","level":"INFO","msg":"Order submitted","order_id":"ord_001"}

# با request context:
req_logger = logger.bind(request_id="req_abc", user_id="user_001")
req_logger.info("Signal received", signal_id="sig_001")
```

---

## 5.2 Core — Enums (27 Enum)

| Enum | فایل | مقادیر |
|------|------|--------|
| `TradeDirection` | `core/enums.py` | `BUY`, `SELL`, `NEUTRAL` |
| `TradeStatus` | `core/enums.py` | `PENDING`, `ACTIVE`, `CLOSED`, `CANCELLED` |
| `OrderStatus` | `core/enums.py` | `PENDING`, `SUBMITTED`, `FILLED`, `FAILED`, `CANCELLED` |
| `SignalStatus` | `core/enums.py` | `NEW`, `PROCESSING`, `EXECUTED`, `REJECTED`, `EXPIRED` |
| `SignalDirection` | `core/enums.py` | `BUY`, `SELL` |
| `OrderType` | `core/enums.py` | `MARKET`, `LIMIT`, `STOP` |
| `MarketSession` | `core/enums.py` | `SYDNEY`, `TOKYO`, `LONDON`, `NEW_YORK`, `OVERLAP` |
| `TrendDirection` | `core/enums.py` | `BULLISH`, `BEARISH`, `NEUTRAL`, `RANGING`, `UNDEFINED` |
| `MarketStructure` | `core/enums.py` | `BULLISH_BOS`, `BEARISH_BOS`, `CHOCH`, `RANGING` |
| `LiquidityType` | `core/enums.py` | `BSL`, `SSL`, `EQH`, `EQL` |
| `FVGType` | `core/enums.py` | `BULLISH`, `BEARISH` |
| `TradeQuality` | `core/enums.py` | `A_PLUS`, `A`, `B`, `C`, `POOR` |
| `ConfidenceLevel` | `core/enums.py` | `VERY_HIGH`, `HIGH`, `MEDIUM`, `LOW`, `VERY_LOW` |
| `RiskLevel` | `core/enums.py` | `MINIMAL`, `LOW`, `MEDIUM`, `HIGH`, `EXTREME` |
| `AlertSeverity` | `core/enums.py` | `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `HealthStatus` | `core/enums.py` | `HEALTHY`, `DEGRADED`, `UNHEALTHY`, `UNKNOWN` |

---

## 5.3 Risk — EquityProtectionEngine

### `class EquityProtectionEngine`

| | |
|---|---|
| **فایل** | `backend/risk/equity_protection.py` |
| **توضیح** | حفاظت از سرمایه. Drawdown max → halt. Cooldown period. |

```python
class EquityProtectionEngine:
    def __init__(self, config: EquityProtectionConfig) -> None
    async def start(self) -> None
    async def stop(self) -> None
    async def check(self) -> ProtectionCheckResult
    async def update_equity(self, equity: float, balance: float) -> None
    async def reset_daily(self) -> None
    async def health(self) -> Dict[str, Any]

@dataclass
class EquityProtectionConfig:
    max_drawdown_pct:     float = 5.0    # حداکثر drawdown
    daily_loss_limit_pct: float = 2.0    # ضرر روزانه
    cooldown_minutes:     int   = 60     # پس از halt
    trailing_enabled:     bool  = True

@dataclass
class ProtectionCheckResult:
    approved:          bool
    reason:            str
    current_drawdown:  float
    daily_loss_pct:    float
    cooldown_remaining: float
```

**مثال:**
```python
config = EquityProtectionConfig(max_drawdown_pct=5.0, daily_loss_limit_pct=2.0)
engine = EquityProtectionEngine(config)
await engine.start()
await engine.update_equity(equity=9800.0, balance=10000.0)
result = await engine.check()
# result.approved = False (drawdown=2.0% < 5% → approved=True در این مثال)
```

---

### `class LotSizer`

| | |
|---|---|
| **فایل** | `backend/risk/lot_sizing.py` |
| **توضیح** | محاسبه حجم معامله با فرمول Kelly. Risk % از balance. |

```python
class LotSizer:
    def __init__(self, config: LotSizingConfig, mt5: Optional[Any] = None) -> None
    async def calculate(
        self,
        balance:         float,
        stop_loss_pips:  float,
        symbol:          str,
        risk_pct:        float = 1.0,
    ) -> LotSizeResult
    async def get_pip_value(self, symbol: str) -> Tuple[float, str]

@dataclass
class LotSizingConfig:
    risk_per_trade_pct: float = 1.0
    min_lot:            float = 0.01
    max_lot:            float = 5.0
    max_risk_pct:       float = 3.0

@dataclass
class LotSizeResult:
    lot_size:       float
    risk_amount:    float
    pip_value:      float
    currency:       str
    capped:         bool     # True اگر max_lot اعمال شد
```

**فرمول:**
```
risk_usd  = balance × (risk_pct / 100)
lot_size  = risk_usd / (stop_loss_pips × pip_value)
lot_size  = clamp(lot_size, min_lot, max_lot)
```

**مثال:** balance=10,000 | SL=20pip | risk_pct=1.0 | pip_value=10 USD  
→ `lot_size = 100 / (20 × 10) = 0.50 lots`

---

### `class CorrelationFilter`

| | |
|---|---|
| **فایل** | `backend/risk/correlation_filter.py` |
| **توضیح** | جلوگیری از trades همبسته. Pearson rolling correlation. |

```python
class CorrelationFilter:
    def __init__(
        self,
        max_correlation:  float = 0.75,
        window:           int   = 20,
        cache_ttl_s:      float = 300.0,
    ) -> None
    async def check(
        self,
        new_symbol:       str,
        new_direction:    str,
        open_positions:   List[Any],
    ) -> CorrelationResult
    def add_price_data(self, symbol: str, price: float) -> None
    def clear_cache(self) -> None

@dataclass
class CorrelationResult:
    approved:         bool
    max_correlation:  float
    blocking_symbol:  Optional[str]
    reason:           str
```

**مثال:**
```python
cf = CorrelationFilter(max_correlation=0.75)
result = await cf.check(
    new_symbol="GBPUSD",
    new_direction="BUY",
    open_positions=[{"symbol": "EURUSD", "direction": "BUY", "lot": 0.1}]
)
# result.approved = False (EURUSD/GBPUSD correlation ~ 0.89 > 0.75)
```

---

### `class NewsFilterGate`

| | |
|---|---|
| **فایل** | `backend/risk/news_filter.py` |
| **توضیح** | بلاک trades قبل/بعد از اخبار HIGH/MEDIUM impact |

```python
class NewsFilterGate:
    def __init__(
        self,
        pre_window_minutes:  int = 30,
        post_window_minutes: int = 15,
        blocked_impacts:     List[NewsImpact] = [HIGH, MEDIUM],
    ) -> None
    def load_events(self, events: List[NewsEvent]) -> None
    def check(self, symbol: str, now: Optional[datetime] = None) -> NewsBlockResult
    async def refresh_from_provider(self, provider: NewsProvider) -> int
    def upcoming_events(self, symbol: str, hours_ahead: int = 24) -> List[NewsEvent]

@dataclass(frozen=True)
class NewsEvent:
    title:       str
    currency:    str
    impact:      NewsImpact
    event_time:  datetime

@dataclass
class NewsBlockResult:
    blocked:           bool
    reason:            str
    event:             Optional[NewsEvent]
    minutes_to_event:  Optional[float]
```

---

### `class ExposureControlEngine`

| | |
|---|---|
| **فایل** | `backend/risk/exposure_control.py` |
| **توضیح** | کنترل exposure کلی. Max lot per symbol/currency/total |

```python
class ExposureControlEngine:
    async def check(
        self,
        symbol:    str,
        lot:       float,
        direction: str,
    ) -> ExposureCheckResult
    async def add_position(self, pos: ExposurePosition) -> None
    async def remove_position(self, symbol: str, lot: float) -> None
    def snapshot(self) -> ExposureSnapshot

@dataclass
class ExposureControlConfig:
    max_total_lots:      float = 10.0
    max_symbol_lots:     float = 2.0
    max_currency_lots:   float = 5.0

@dataclass
class ExposureSnapshot:
    total_lots:    float
    by_symbol:     Dict[str, float]
    by_currency:   Dict[str, float]
    net_exposure:  float
```

---

## 5.4 Execution — ExecutionService

### `class ExecutionService`

| | |
|---|---|
| **فایل** | `backend/execution/execution_service.py` |
| **توضیح** | Orchestrator اصلی execution pipeline |

```python
class ExecutionService:
    def __init__(
        self,
        risk:              Any,
        broker:            Any,
        osm:               Any,
        fr:                Any,
        pr:                Any,
        *,
        default_risk_pct:  float = 1.0,
    ) -> None
    async def start(self) -> None
    async def stop(self) -> None
    async def execute_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]
    async def health(self) -> Dict[str, Any]
```

**Pipeline:**
```
execute_signal(signal)
  ↓ idempotency check  (TTL=300s)
  ↓ inflight dedup
  ↓ _run_risk()        → RiskOrchestrator.assess()
  ↓ _create_order()    → OSM.create_order()
  ↓ _submit()          → MT5Connector.send_order()
  ↓ OSM.transition(SUBMITTED → FILLED/FAILED)
  ↓ idempotency register
```

**مثال:**
```python
from backend.core.deps import get_execution_service
svc = get_execution_service()
await svc.start()
result = await svc.execute_signal({
    "signal_id": "sig_001",
    "symbol": "EURUSD",
    "direction": "BUY",
    "sl_pips": 20,
    "tp_pips": 40
})
# result = {"status": "FILLED", "ticket": 12345678, "lot": 0.05}
```

---

### `class MT5Connector`

| | |
|---|---|
| **فایل** | `backend/execution/mt5_connector.py` |
| **توضیح** | اتصال MetaTrader 5. asyncio.Lock. timeout=30s. retry×3 |

```python
class MT5Connector:
    def __init__(self, exe_path=None, timeout_seconds=30,
                 max_retries=3, retry_delay=1.0) -> None
    async def initialize(self) -> bool
    async def health_check(self) -> bool
    async def send_order(
        self,
        request:       MT5OrderRequest,
        retry_policy:  Optional[RetryConfig] = None,
    ) -> MT5OrderResult
    async def close_position(self, ticket: int, deviation: int = 10) -> MT5OrderResult
    async def get_positions(self) -> List[Any]
    async def get_account_info(self) -> Optional[Any]
    async def shutdown(self) -> None

@dataclass
class MT5OrderRequest:
    symbol:      str
    order_type:  int     # mt5.ORDER_TYPE_BUY/SELL
    volume:      float
    price:       float
    sl:          float
    tp:          float
    deviation:   int
    comment:     str = ""

@dataclass
class MT5OrderResult:
    retcode:  int
    ticket:   int
    volume:   float
    price:    float
    @property
    def success(self) -> bool: return self.retcode == 10009
```

---

### `class OrderStateMachine`

| | |
|---|---|
| **فایل** | `backend/execution/order_state_machine.py` |
| **توضیح** | FSM برای tracking دقیق وضعیت هر order |

```python
class OrderStateMachine:
    async def create_order(self, order: ManagedOrder) -> ManagedOrder
    async def transition(
        self, order_id: str, new_state: OrderState,
        *, ticket=None, fill_price=None, error=None
    ) -> ManagedOrder
    async def get_active_orders(self) -> List[ManagedOrder]
    async def get_order(self, order_id: str) -> Optional[ManagedOrder]
    async def get_timed_out(self, timeout_seconds: float) -> List[str]

@dataclass
class ManagedOrder:
    order_id:    str
    signal_id:   str
    symbol:      str
    direction:   str
    lot_size:    float
    state:       OrderState
    created_at:  datetime
    ticket:      Optional[int]   = None
    fill_price:  Optional[float] = None
```

**State Machine:**
```
PENDING → SUBMITTED → FILLED      (terminal ✓)
               ↓
            FAILED               (terminal ✓)
PENDING → CANCELLED              (terminal ✓)
```

---

### `class FailureRecoveryEngine`

| | |
|---|---|
| **فایل** | `backend/execution/failure_recovery.py` |
| **توضیح** | Retry queue با exponential backoff. Dead letter queue (max 500). |

```python
class FailureRecoveryEngine:
    async def handle_failure(
        self, order: ManagedOrder, error: str, retcode: int = 0
    ) -> None
    def dead_letter_queue(self) -> List[FailedOrder]
    def retry_queue_size(self) -> int
    def health_stats(self) -> Dict[str, Any]

class RecoveryStrategy(str, Enum):
    RETRY_IMMEDIATE  = "retry_immediate"   # reject/timeout
    RETRY_DELAYED    = "retry_delayed"     # partial fill
    DEAD_LETTER      = "dead_letter"       # invalid → DLQ
    IGNORE           = "ignore"            # duplicate
```

---

## 5.5 Agents — VotingEngine

### `class VotingEngine`

| | |
|---|---|
| **فایل** | `backend/agents/voting_engine.py` |
| **توضیح** | Weighted majority voting. asyncio.gather() برای parallel execution. |

```python
class VotingEngine:
    def __init__(
        self,
        agents:       List[BaseAgent],
        threshold:    float = 0.60,
        timeout_s:    float = 5.0,
        run_parallel: bool  = True,
    ) -> None
    async def vote(self, context: Dict[str, Any]) -> VoteResult
    def update_weights(self, weight_map: Dict[str, float]) -> None
    def enable_agent(self, name: str) -> None
    def disable_agent(self, name: str) -> None

@dataclass
class VoteResult:
    decision:       VoteDecision     # APPROVE, REJECT, ABSTAIN
    confidence:     float            # [0.0, 1.0]
    agent_results:  List[AgentResult]
    veto_by:        Optional[str]
    risk_blocked:   bool
    duration_ms:    float
    @property
    def passed_threshold(self) -> bool
    @property
    def blocking_agents(self) -> List[str]
    def to_dict(self) -> Dict[str, Any]
```

**مثال:**
```python
engine = VotingEngine(agents=[smc_agent, pa_agent, ml_agent, risk_agent], threshold=0.60)
result = await engine.vote({"symbol": "EURUSD", "timeframe": "H1", "price": 1.0850})
# result.decision = VoteDecision.APPROVE
# result.confidence = 0.78
# result.veto_by = None
```

---

### `class BaseAgent`

| | |
|---|---|
| **فایل** | `backend/agents/base_agent.py` |
| **توضیح** | Abstract base class برای همه agents |

```python
class BaseAgent:
    name:          str
    weight:        float
    has_veto:      bool
    enabled:       bool

    async def analyze(self, context: Dict[str, Any]) -> VoteSignal
    # VoteSignal: {direction: str, confidence: float, reason: str}
```

---

## 5.6 Circuit Breaker

### `class CircuitBreaker`

| | |
|---|---|
| **فایل** | `backend/circuit_breaker.py` |
| **توضیح** | 3-state FSM. CLOSED→OPEN پس از 5 failure در 60s. HALF_OPEN برای probe. |

```python
class CircuitBreaker:
    async def can_execute(self) -> bool
    async def record_success(self) -> None
    async def record_failure(self, reason: str = "") -> None
    async def force_open(self, reason: str = "manual") -> None
    async def force_close(self, reason: str = "manual") -> None
    def snapshot(self) -> Dict[str, Any]
    async def __aenter__(self) -> "CircuitBreaker"
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool

@dataclass
class BreakerConfig:
    failure_threshold:    int   = 5
    window_seconds:       float = 60.0
    recovery_timeout_s:   float = 30.0
    success_threshold:    int   = 2
```

**State Machine:**
```
CLOSED ──(failures≥threshold)──→ OPEN ──(timeout)──→ HALF_OPEN
  ↑                                                        │
  └──────────────(successes≥threshold)────────────────────┘
```

**مثال:**
```python
cb = get_mt5_breaker()  # singleton
try:
    async with cb:           # CircuitOpenError اگر OPEN
        result = await mt5.send_order(request)
except CircuitOpenError:
    logger.warning("Circuit breaker OPEN, order blocked")

stats = cb.snapshot()
# {"state": "CLOSED", "failures": 0, "last_failure": null}
```

---

## 5.7 Observability — MetricsRegistry

### `class MetricsRegistry`

| | |
|---|---|
| **فایل** | `backend/observability/metrics.py` |
| **توضیح** | Prometheus Counter/Gauge/Histogram + in-memory snapshot |

```python
class MetricsRegistry:
    def trade_submitted(self, symbol: str, direction: str) -> None
    def trade_filled(self, symbol: str, direction: str, fill_latency_s: float) -> None
    def trade_rejected(self, symbol: str, reason: str) -> None
    def order_retry(self, symbol: str) -> None
    def risk_block(self, gate: str, reason: str) -> None
    def risk_latency(self, gate: str, latency_s: float) -> None
    def set_equity(self, equity: float) -> None
    def snapshot(self) -> Dict[str, Any]
    async def health(self) -> Dict[str, Any]
```

**مثال:**
```python
metrics = get_metrics()
metrics.trade_submitted(symbol="EURUSD", direction="BUY")
metrics.trade_filled(symbol="EURUSD", direction="BUY", fill_latency_s=0.045)
metrics.risk_block(gate="equity_protection", reason="drawdown_exceeded")

snapshot = metrics.snapshot()
# {"trades_submitted": 142, "trades_filled": 138, "fill_rate_pct": 97.18}
```

---

## 5.8 Services — BackgroundScheduler

### `class BackgroundScheduler`

| | |
|---|---|
| **فایل** | `backend/services/scheduler.py` |
| **توضیح** | Registry برای background tasks. Lazy asyncio primitive init. |

```python
class BackgroundScheduler:
    def register(
        self,
        name:          str,
        coro_fn:       Callable,
        interval_s:    float,
        *,
        run_on_start:  bool = False,
        max_errors:    int  = 10,
    ) -> None
    async def shutdown(self, timeout_s: float = 10.0) -> None
    def health(self) -> Dict[str, Any]
```

**مثال:**
```python
scheduler = get_scheduler()
scheduler.register("position_reconcile", reconciler.run_once,
                   interval_s=30.0, run_on_start=True)
scheduler.register("daily_reset", equity_engine.reset_daily,
                   interval_s=86400.0)
```

**Tasks ثبت‌شده در production:**

| Task | Interval | توضیح |
|------|----------|-------|
| `position_reconcile` | 30s | مطابقت positions با MT5 |
| `orphan_cleanup` | 300s | پاکسازی orphan positions |
| `equity_check` | 60s | چک equity protection |
| `daily_reset` | 86400s | Reset counters روزانه |
| `news_refresh` | 3600s | دریافت اخبار جدید |
| `ml_retrain_check` | 3600s | بررسی trigger برای retraining |
| `circuit_breaker_probe` | 30s | HALF_OPEN probe |
| `metrics_flush` | 60s | Flush Prometheus |
| `dead_letter_review` | 1800s | بررسی DLQ |
| `weight_adjustment` | 86400s | تنظیم وزن agents |
| `session_cleanup` | 3600s | پاکسازی sessions منقضی |

---

## 5.9 API — Health Check Classes

### `class SystemHealth`

| | |
|---|---|
| **فایل** | `backend/api/health.py` |
| **توضیح** | وضعیت کل سیستم. همه components موازی چک می‌شوند. |

```python
@dataclass
class ComponentHealth:
    name:        str
    status:      HealthStatus    # HEALTHY, DEGRADED, UNHEALTHY
    latency_ms:  Optional[float]
    details:     Dict[str, Any]
    error:       Optional[str]

@dataclass
class SystemHealth:
    status:      HealthStatus
    version:     str
    uptime_s:    float
    components:  Dict[str, ComponentHealth]
    def to_dict(self) -> Dict[str, Any]
    @property
    def is_healthy(self) -> bool
```

---

## 5.10 Analysis — DecisionEngine

### `class DecisionEngine`

| | |
|---|---|
| **فایل** | `backend/analysis/decision_engine.py` (746 خط) |
| **توضیح** | موتور تصمیم‌گیری اصلی. Multi-timeframe analysis. SMC + Price Action. |

```python
class DecisionEngine:
    async def evaluate(
        self,
        inp:  DecisionInput,
    ) -> DecisionOutput

@dataclass
class DecisionInput:
    symbol:          str
    smc_ctx:         SMCContext
    pa_ctx:          PriceActionContext
    risk_ctx:        RiskContext
    session_ctx:     SessionContext
    volatility_ctx:  VolatilityContext
    mtf_ctx:         MultiTimeframeContext

@dataclass
class DecisionOutput:
    approved:     bool
    direction:    TrendDirection
    confidence:   float           # [0.0, 1.0]
    levels:       TradingLevels   # SL, TP, entry
    reason_codes: List[ReasonCode]
    blocked_by:   Optional[BlockedReason]
```

**classes مرتبط (در همین فایل):**

| Class | توضیح |
|-------|-------|
| `SMCContext` | BOS، CHoCH، FVG، Order Block data |
| `PriceActionContext` | کندل‌شناسی، trend، momentum |
| `RiskContext` | Account balance، equity، drawdown |
| `SessionContext` | Market session، spread، volume |
| `VolatilityContext` | ATR، spread، volatility index |
| `MultiTimeframeContext` | H4/H1/M15/M5 analysis |
| `TradingLevels` | entry، sl، tp، risk/reward |
| `MultiTimeframeEngine` | جمع‌بندی چند timeframe |

---

# 6. Functions Documentation

> توابع مستقل (خارج از class). شامل factory functions، DI، retry، و health checks.

---

## 6.1 Factory Functions — Singleton Providers

| تابع | فایل | خروجی | نوع |
|------|------|-------|-----|
| `get_settings()` | `core/config.py` | `Settings` | `@lru_cache` — یک بار load |
| `get_logger(name)` | `core/logger.py` | `ContextualLogger` | per-module logger |
| `get_audit_logger()` | `core/logger.py` | `AuditLogger` | compliance trail |
| `get_metrics()` | `observability/metrics.py` | `MetricsRegistry` | module singleton |
| `get_scheduler()` | `services/scheduler.py` | `BackgroundScheduler` | process singleton |
| `get_risk_orchestrator()` | `risk/risk_orchestrator.py` | `RiskOrchestrator` | double-checked locking |
| `get_equity_protection()` | `risk/equity_protection.py` | `EquityProtectionEngine` | module singleton |
| `get_volatility_filter()` | `risk/volatility_filter.py` | `VolatilityFilter` | module singleton |
| `get_execution_service()` | `execution/execution_service.py` | `ExecutionService` | module singleton |
| `get_mt5_breaker()` | `circuit_breaker.py` | `CircuitBreaker` | MT5-specific CB |
| `get_agent_service()` | `agents/agent_service.py` | `AgentService` | module singleton |
| `get_order_journal()` | `execution/order_journal.py` | `OrderJournal` | module singleton |

---

## 6.2 FastAPI Dependency Functions — `core/deps.py`

```python
# احراز هویت
async def get_db() -> AsyncGenerator
async def get_current_user(credentials=Depends(_bearer)) -> dict
async def get_current_active_user(user=Depends(get_current_user)) -> dict
async def require_admin(user=Depends(get_current_active_user)) -> dict
async def require_super_admin(user=Depends(get_current_active_user)) -> dict

# سرویس‌ها
async def get_risk_orchestrator_dep() -> RiskOrchestrator
def get_metrics() -> MetricsRegistry
def get_audit_log() -> AuditLogger
def get_mt5_retry_config() -> RetryConfig
def get_db_retry_config() -> RetryConfig
```

**مثال استفاده در route:**
```python
from backend.core.deps import get_current_user, get_risk_orchestrator_dep

@router.post('/signals/execute')
async def execute_signal(
    payload: SignalPayload,
    user    = Depends(get_current_user),          # احراز هویت خودکار
    risk    = Depends(get_risk_orchestrator_dep), # Risk engine inject
    metrics = Depends(get_metrics),               # Metrics
):
    decision = await risk.assess(payload)
    metrics.trade_submitted(payload.symbol, payload.direction)
```

---

## 6.3 Retry Functions — `core/retry.py`

```python
def async_retry(config: RetryConfig) -> Callable
# دکوراتور: @async_retry(MT5_RETRY)

async def with_retry_async(
    fn:          Callable[[], Awaitable[T]],
    config:      RetryConfig,
    *,
    on_retry:    Optional[Callable[[int, Exception, float], None]] = None,
    context_log: Optional[Dict[str, Any]] = None,
) -> T
# اجرای async function با retry
```

---

## 6.4 Health Check Functions — `api/health.py`

```python
async def liveness() -> Dict[str, Any]
# → {status: "alive", uptime_s: 3600.5}
# مناسب برای: Kubernetes liveness probe

async def readiness() -> Dict[str, Any]
# → {status: "ready"|"not_ready", checks: {db, redis, mt5}}
# مناسب برای: Kubernetes readiness probe

async def deep_health() -> Dict[str, Any]
# → SystemHealth.to_dict() — همه components موازی
# مناسب برای: Monitoring dashboard
```

**Response example:**
```json
{
  "status": "healthy",
  "version": "2.1.0",
  "uptime_seconds": 3600,
  "components": {
    "database":    {"status": "healthy", "latency_ms": 2.1},
    "redis":       {"status": "healthy", "latency_ms": 0.8},
    "mt5":         {"status": "healthy", "connected": true},
    "risk_engine": {"status": "healthy", "gates_active": 7},
    "scheduler":   {"status": "healthy", "tasks": 11}
  }
}
```

---

## 6.5 Circuit Breaker Functions — `circuit_breaker.py`

```python
async def halt_trading(reason: str) -> None
# توقف فوری همه معاملات

async def resume_trading(reason: str = "") -> None
# از سرگیری معاملات

def is_trading_halted() -> bool
# بررسی وضعیت توقف

async def get_breaker(name: str, config: Optional[BreakerConfig] = None) -> CircuitBreaker
# دریافت یا ایجاد CB با نام مشخص

def get_mt5_breaker() -> CircuitBreaker
# CB اختصاصی MT5 (5 failures/60s → OPEN)
```

---

## 6.6 Logging Functions — `core/logger.py`

```python
def get_logger(name: str) -> ContextualLogger
# log = get_logger("execution.service")
# در production: JSON، در development: human-readable

def get_audit_logger() -> AuditLogger
# برای ثبت compliance events
# audit_log.record(action="TRADE_APPROVED", actor="system",
#                  resource="signal:123", result="success")
```

---

## 6.7 جدول خلاصه توابع مهم

| تابع | فایل | Async | ورودی | خروجی |
|------|------|-------|-------|-------|
| `execute_signal()` | `execution/execution_service.py` | ✅ | `Dict[signal]` | `Dict[result]` |
| `assess()` | `risk/risk_orchestrator.py` | ✅ | `RiskInput` | `RiskResult` |
| `vote()` | `agents/voting_engine.py` | ✅ | `Dict[context]` | `VoteResult` |
| `send_order()` | `execution/mt5_connector.py` | ✅ | `MT5OrderRequest` | `MT5OrderResult` |
| `check()` | `risk/equity_protection.py` | ✅ | — | `ProtectionCheckResult` |
| `check_limits()` | `risk/daily_limits.py` | — | `balance, TodayTrades` | `LimitsCheckResult` |
| `check()` | `risk/correlation_filter.py` | ✅ | `symbol, direction, positions` | `CorrelationResult` |
| `calculate()` | `risk/lot_sizing.py` | ✅ | `balance, sl_pips, symbol` | `LotSizeResult` |
| `transition()` | `execution/order_state_machine.py` | ✅ | `order_id, new_state` | `ManagedOrder` |
| `handle_failure()` | `execution/failure_recovery.py` | ✅ | `order, error, retcode` | `None` |
| `run_once()` | `execution/position_reconciliation.py` | ✅ | — | `ReconciliationResult` |
| `deep_health()` | `api/health.py` | ✅ | — | `Dict[SystemHealth]` |
| `halt_trading()` | `circuit_breaker.py` | ✅ | `reason: str` | `None` |
| `get_logger()` | `core/logger.py` | — | `name: str` | `ContextualLogger` |
| `async_retry()` | `core/retry.py` | — | `RetryConfig` | `Callable` |

---

## 6.8 وابستگی بین ماژول‌ها (Import Graph)

```
core/exceptions.py      ← (هیچ وابستگی داخلی ندارد)
core/enums.py           ← (هیچ وابستگی داخلی ندارد)
core/config.py          ← core/enums
core/logger.py          ← core/config
core/retry.py           ← core/exceptions, core/logger
core/interfaces.py      ← core/enums
core/deps.py            ← core/config, core/logger, risk/*, execution/*

risk/equity_protection  ← core/exceptions, core/enums
risk/daily_limits       ← core/exceptions, core/enums
risk/lot_sizing         ← core/exceptions, core/enums
risk/volatility_filter  ← core/enums, risk/news_filter
risk/correlation_filter ← core/enums
risk/exposure_control   ← core/enums
risk/news_filter        ← core/enums
risk/risk_orchestrator  ← core/*, risk/* (همه)

execution/mt5_connector      ← core/*, circuit_breaker
execution/order_state_machine← core/enums, core/logger
execution/failure_recovery   ← core/*, execution/osm
execution/position_reconcil  ← core/*, execution/mt5
execution/execution_service  ← core/*, risk/*, execution/* (همه)

agents/base_agent       ← core/enums, core/logger
agents/voting_engine    ← agents/base_agent, circuit_breaker
agents/*_agent          ← agents/base_agent, analysis/*

analysis/decision_engine← core/*, agents/*
analysis/smc_engine     ← core/enums

api/main.py             ← همه لایه‌ها
api/routes/*            ← core/deps, services/*, execution/*
```

---

*بخش‌های ۷–۲۵ در MASTER_DOCUMENTATION.md ادامه دارند.*
