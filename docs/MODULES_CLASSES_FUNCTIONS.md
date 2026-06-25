# 4. Modules Documentation

> **برای تازه‌کار:** هر ماژول یک پوشه یا فایل Python است که مسئولیت مشخصی دارد. مثل قطعات لگو که هر کدام یک کار می‌کنند و با هم یک سیستم کامل می‌سازند.
>
> **برای حرفه‌ای:** پروژه از Clean Architecture پیروی می‌کند. وابستگی‌ها فقط به سمت داخل (core) جاری‌اند. هیچ inner layer از outer layer import نمی‌کند.

---

## 4.1 نمودار وابستگی ماژول‌ها

```
┌─────────────────────────────────────────────────────────────────────┐
│                          API Layer                                   │
│   api/main.py → api/routes/* → api/health.py                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ depends on
┌──────────────────────────▼──────────────────────────────────────────┐
│                       Service Layer                                  │
│  agents/  ←→  execution/  ←→  risk/  ←→  intelligence/             │
│  services/  ←→  observability/  ←→  telegram/                      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ depends on
┌──────────────────────────▼──────────────────────────────────────────┐
│                     Infrastructure Layer                             │
│        database/  ←→  middleware/  ←→  circuit_breaker.py          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ depends on
┌──────────────────────────▼──────────────────────────────────────────┐
│                        Core Layer                                    │
│   core/interfaces.py  core/exceptions.py  core/retry.py            │
│   core/logger.py  core/deps.py  core/enums.py  core/config.py      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4.2 Core — هسته مرکزی

| ماژول | فایل | توضیح | نقش | وابستگی |
|-------|------|-------|-----|----------|
| **Config** | `backend/core/config.py` | تنظیمات Pydantic BaseSettings | بارگذاری ENV vars، validation | `pydantic`, `python-dotenv` |
| **Enums** | `backend/core/enums.py` | تمام Enum های مشترک پروژه | Single source of truth برای `TradeDirection`, `TrendDirection`, `OrderState` | stdlib only |
| **Interfaces** | `backend/core/interfaces.py` | Protocol definitions برای DI | قراردادهای `IRiskGate`, `IOrderBroker`, `ILotSizer`, `IAgent` | `typing_extensions` |
| **Exceptions** | `backend/core/exceptions.py` | سلسله‌مراتب Exception ها | `AppError → RetryableError / NonRetryableError` | stdlib only |
| **Retry** | `backend/core/retry.py` | مکانیزم retry با exponential backoff | `@async_retry`, `with_retry_async()`, `RetryConfig` | `asyncio` |
| **Logger** | `backend/core/logger.py` | Structured JSON logging | `ContextualLogger`, `AuditLogger` | `logging`, `json` |
| **Deps** | `backend/core/deps.py` | FastAPI Dependency Injection container | همه singletons از اینجا inject می‌شوند | `fastapi`, همه modules |
| **Auth** | `backend/core/auth.py` | JWT authentication | token decode/verify | `jose`, `passlib` |
| **Security** | `backend/core/security.py` | password hashing, token generation | bcrypt, token helpers | `passlib`, `secrets` |
| **Cache** | `backend/core/cache.py` | Redis caching utilities | TTL cache, invalidation | `redis.asyncio` |
| **Validators** | `backend/core/validators.py` | Input validation helpers | symbol, lot, price validation | `pydantic` |
| **Unified Types** | `backend/core/unified_types.py` | Shared dataclass types | `TradeContext`, `RiskInput`, `RiskResult` | stdlib |

---

## 4.3 Risk — موتور ریسک

| ماژول | فایل | توضیح | نقش | وابستگی |
|-------|------|-------|-----|----------|
| **Risk Orchestrator** | `backend/risk/risk_orchestrator.py` | هماهنگ‌کننده ۷ gate ریسک | ورودی سیگنال → خروجی approved/blocked | همه risk modules |
| **Equity Protection** | `backend/risk/equity_protection.py` | محافظت از سرمایه | Drawdown check، daily loss limit | `dataclasses` |
| **Daily Limits** | `backend/risk/daily_limits.py` | محدودیت‌های روزانه | تعداد معاملات، ضرر روزانه/هفتگی/ماهانه | `datetime` |
| **Lot Sizing** | `backend/risk/lot_sizing.py` | محاسبه حجم لات | Kelly Criterion، pip value | `MT5Connector` |
| **Volatility Filter** | `backend/risk/volatility_filter.py` | فیلتر نوسانات | ATR-based blocking، news filter | `news_filter` |
| **Correlation Filter** | `backend/risk/correlation_filter.py` | فیلتر همبستگی | Pearson correlation، rolling window | `numpy` (optional) |
| **Exposure Control** | `backend/risk/exposure_control.py` | کنترل exposure کل پرتفولیو | max lot per symbol/currency | — |
| **Portfolio Risk** | `backend/risk/portfolio_risk.py` | ریسک کل پرتفولیو | position netting، net exposure | `core/enums` |
| **News Filter** | `backend/risk/news_filter.py` | بلاک قبل از خبر | pre/post news blackout window | — |

---

## 4.4 Execution — موتور اجرا

| ماژول | فایل | توضیح | نقش | وابستگی |
|-------|------|-------|-----|----------|
| **ExecutionService** | `backend/execution/execution_service.py` | نقطه ورود اجرای signal | Pipeline: idempotency → risk → create → submit | `MT5Connector`, `RiskOrchestrator`, `OSM`, `FR`, `PR` |
| **MT5 Connector** | `backend/execution/mt5_connector.py` | اتصال به MetaTrader 5 | `initialize()`, `send_order()`, `close_position()`, `health_check()` | `MetaTrader5` (C++) |
| **Order State Machine** | `backend/execution/order_state_machine.py` | ماشین حالت سفارش‌ها | PENDING→SUBMITTED→FILLED/FAILED | `asyncio` |
| **Failure Recovery** | `backend/execution/failure_recovery.py` | بازیابی سفارش‌های ناموفق | Retry queue، dead letter queue | `asyncio.Queue` |
| **Position Reconciliation** | `backend/execution/position_reconciliation.py` | تطبیق موقعیت‌های MT5 | Orphan detection، duplicate check | `MT5Connector` |
| **Semi Auto** | `backend/execution/semi_auto.py` | تأیید دستی قبل از اجرا | Pending signal management، approve/reject | `asyncio` |
| **Order Journal** | `backend/execution/order_journal.py` | دفتر ثبت سفارش‌ها | Audit trail کامل هر event | `asyncio`, `deque` |

---

## 4.5 Agents — هوش مصنوعی چندعاملی

| ماژول | فایل | توضیح | وزن پیش‌فرض | Veto |
|-------|------|-------|-------------|------|
| **BaseAgent** | `backend/agents/base_agent.py` | کلاس پایه همه agent ها | — | — |
| **VotingEngine** | `backend/agents/voting_engine.py` | سیستم رأی‌گیری | — | — |
| **AgentService** | `backend/agents/agent_service.py` | مدیریت و orchestration | — | — |
| **SMC Agent** | `backend/agents/smc_agent.py` | Smart Money Concepts | 0.25 | ❌ |
| **ML Agent** | `backend/agents/ml_agent.py` | مدل یادگیری ماشین | 0.20 | ❌ |
| **Risk Agent** | `backend/agents/risk_agent.py` | بررسی شرایط ریسک | 0.20 | ✅ |
| **Market Structure Agent** | `backend/agents/market_structure_agent.py` | ساختار بازار | 0.15 | ❌ |
| **News Agent** | `backend/agents/news_agent.py` | تأثیر اخبار | 0.10 | ✅ |
| **Liquidity Agent** | `backend/agents/liquidity_agent.py` | نقاط نقدینگی | 0.05 | ❌ |
| **AI Prediction Agent** | `backend/agents/ai_prediction_agent.py` | پیش‌بینی AI | 0.05 | ❌ |
| **Execution Agent** | `backend/agents/execution_agent.py` | کیفیت اجرا | — | ❌ |

---

## 4.6 Intelligence — یادگیری ماشین

| ماژول | فایل | توضیح | نقش |
|-------|------|-------|-----|
| **ML Engine** | `backend/intelligence/ml_engine.py` | موتور اصلی ML | RandomForest + GradientBoosting + walk-forward CV |
| **Trade Memory** | `backend/intelligence/trade_memory.py` | حافظه معاملات | ذخیره TradeContext برای training |
| **Learning Service** | `backend/intelligence/learning_service.py` | سرویس یادگیری | هماهنگی training pipeline |
| **Weight Adjuster** | `backend/intelligence/weight_adjuster.py` | تنظیم وزن agent ها | بر اساس performance تاریخی |
| **Failure Analyzer** | `backend/intelligence/failure_analyzer.py` | تحلیل معاملات ناموفق | pattern extraction از dead letter |

---

## 4.7 Observability — نظارت

| ماژول | فایل | توضیح | نقش |
|-------|------|-------|-----|
| **Metrics** | `backend/observability/metrics.py` | ثبت متریک‌ها | Prometheus + in-memory snapshot |
| **Alert Manager** | `backend/observability/alert_manager.py` | مدیریت هشدارها | AlertDeduplicator، flood prevention |
| **Structured Logger** | `backend/observability/structured_logger.py` | logging ساختاریافته | JSON log output |
| **Tracing** | `backend/observability/tracing.py` | distributed tracing | OpenTelemetry |

---

## 4.8 Services — سرویس‌های عمومی

| ماژول | فایل | توضیح | نقش |
|-------|------|-------|-----|
| **Scheduler** | `backend/services/scheduler.py` | مدیریت task های پس‌زمینه | Register/run/monitor background loops |
| **Audit Service** | `backend/services/audit_service.py` | ثبت رویدادهای حسابرسی | `AuditAction` enum، DB write |
| **RBAC** | `backend/services/rbac.py` | کنترل دسترسی نقش‌محور | Permission check، role hierarchy |
| **Trade Service** | `backend/services/trade_service.py` | منطق کسب‌وکار معاملات | آمار، statistics |
| **Signal Service** | `backend/services/signal_service.py` | پردازش سیگنال‌های ورودی | validation، routing |
| **Session Manager** | `backend/services/session_manager.py` | مدیریت نشست کاربران | Redis-based sessions |

---

## 4.9 Analysis — تحلیل تکنیکال

| ماژول | فایل | توضیح | نقش |
|-------|------|-------|-----|
| **Decision Engine** | `backend/analysis/decision_engine.py` | موتور تصمیم‌گیری (746 خط) | Multi-timeframe، SMC scoring، PA scoring |
| **SMC Engine** | `backend/analysis/smc_engine.py` | Smart Money Concepts (3,077 خط) | Order blocks، FVG، BOS، liquidity |

---

## 4.10 سایر ماژول‌ها

| ماژول | فایل | توضیح |
|-------|------|-------|
| **Circuit Breaker** | `backend/circuit_breaker.py` | قطع‌کننده مدار در بحران |
| **Database** | `backend/database/connection.py` | اتصال Supabase async |
| **Telegram Bot** | `backend/telegram/bot.py` | ربات Telegram |
| **Middleware** | `backend/middleware/` | Rate limiting، security، observability |
| **Backtest Engine** | `backend/backtest_engine/` | موتور بک‌تست |
| **Institutional** | `backend/institutional/` | ابزارهای سطح حرفه‌ای |

---

# 5. Classes Documentation

> **برای تازه‌کار:** هر class یک قالب است. مثل نقشه یک خانه — از روی نقشه می‌توان خانه‌های زیادی ساخت.
>
> **برای حرفه‌ای:** تمام class ها type-annotated هستند. Protocols برای DI استفاده می‌شوند. Dataclasses برای value objects.

---

## 5.1 AppError و سلسله‌مراتب Exception

**فایل:** `backend/core/exceptions.py`

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
├── RetryableError          → retry.py می‌تواند retry کند
│   ├── OrderSubmissionError
│   ├── BrokerConnectionError
│   └── DatabaseError
└── NonRetryableError       → فوری raise می‌شود
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

## 5.2 RetryConfig — مکانیزم Retry

**فایل:** `backend/core/retry.py`

```python
@dataclass
class RetryConfig:
    max_attempts:  int           = 3
    base_delay_s:  float         = 1.0
    max_delay_s:   float         = 30.0
    jitter:        bool          = True
    strategy:      RetryStrategy = RetryStrategy.EXPONENTIAL
    retry_on:      tuple         = (RetryableError,)
    no_retry_on:   tuple         = (NonRetryableError,)
```

| Config | max_attempts | base_delay | strategy |
|--------|-------------|------------|----------|
| `MT5_RETRY` | 3 | 0.5s | EXPONENTIAL |
| `DB_RETRY` | 5 | 0.2s | EXPONENTIAL |
| `RISK_RETRY` | 2 | 0.1s | FIXED |

```python
@async_retry(MT5_RETRY)
async def send_order(request: MT5OrderRequest) -> MT5OrderResult:
    return await mt5.send_order_sync(request)
```

---

## 5.3 ContextualLogger — Structured Logging

**فایل:** `backend/core/logger.py`

```python
class ContextualLogger:
    def bind(self, **kwargs: Any) -> 'ContextualLogger'
    def info(self, msg: str, **kwargs: Any) -> None
    def error(self, msg: str, **kwargs: Any) -> None
    def warning(self, msg: str, **kwargs: Any) -> None

class AuditLogger:
    def record(self, action: str, actor: str, resource: str, result: str, *, detail: Optional[Dict] = None) -> None
```

```python
log = get_logger("execution").bind(signal_id="sig-123", symbol="EURUSD")
log.info("Order submitted", order_id="ord-456", fill_ms=12.3)
# JSON: {"ts":"2026-06-25T13:15:00Z","level":"INFO","msg":"Order submitted",
#        "signal_id":"sig-123","symbol":"EURUSD","order_id":"ord-456","fill_ms":12.3}
```

---

## 5.4 EquityProtectionEngine — محافظت سرمایه

**فایل:** `backend/risk/equity_protection.py`

```python
class EquityProtectionEngine:
    def __init__(self, config: Optional[EquityProtectionConfig] = None) -> None
    def initialize(self, initial_balance: float) -> None
    def update_equity(self, equity: float, balance: float) -> None
    def record_trade_result(self, pnl_usd: float) -> None
    def check(self) -> ProtectionCheckResult
    def reset_daily(self) -> None
    def reset_weekly(self) -> None
    def get_state(self) -> dict

@dataclass
class EquityProtectionConfig:
    max_daily_drawdown_pct:  float = 3.0
    max_weekly_drawdown_pct: float = 8.0
    max_total_drawdown_pct:  float = 20.0
    cooldown_minutes:        int   = 60
    soft_warning_pct:        float = 1.5

@dataclass
class ProtectionCheckResult:
    allowed:              bool
    reason:               str
    level:                ProtectionLevel   # NORMAL, WARNING, SOFT_HALT, HARD_HALT
    cooldown_remaining_s: float
```

**مثال:**
```python
engine = EquityProtectionEngine(EquityProtectionConfig(max_daily_drawdown_pct=2.5))
engine.initialize(initial_balance=10_000.0)
engine.update_equity(equity=9_600.0, balance=10_000.0)
result = engine.check()
if not result.allowed:
    logger.warning("Trading halted", reason=result.reason)
```

---

## 5.5 DailyLimitsEngine — محدودیت روزانه

**فایل:** `backend/risk/daily_limits.py`

```python
class DailyLimitsEngine:
    def __init__(
        self,
        max_daily_trades:     int   = 10,
        max_daily_loss_pct:   float = 3.0,
        max_weekly_loss_pct:  float = 8.0,
        max_monthly_loss_pct: float = 15.0,
    ) -> None

    def check_limits(
        self,
        account_balance: float,
        today:           TodayTrades,
        week_pnl_usd:    float = 0.0,
        month_pnl_usd:   float = 0.0,
    ) -> LimitsCheckResult

@dataclass
class TodayTrades:
    count:   int   = 0
    pnl_usd: float = 0.0

@dataclass
class LimitsCheckResult:
    allowed:          bool
    status:           LimitStatus
    reason:           str
    remaining_trades: int
    resets_at:        datetime
```

---

## 5.6 CorrelationFilter — فیلتر همبستگی

**فایل:** `backend/risk/correlation_filter.py`

```python
class CorrelationFilter:
    def __init__(self, config: Optional[CorrelationFilterConfig] = None,
                 rolling_engine: Optional[RollingCorrelationEngine] = None) -> None

    async def add_price(self, symbol: str, price: float) -> None

    async def check(
        self,
        new_symbol:     str,
        new_direction:  str,
        open_positions: List[CorrPosition],
    ) -> CorrelationResult

    async def portfolio_correlation_matrix(self, symbols: List[str]) -> Dict[Tuple[str,str], float]

class RollingCorrelationEngine:
    def __init__(self, window: int = 50, cache_ttl: float = 60.0)
    async def add_price(self, symbol: str, price: float) -> None
    async def get_correlation(self, a: str, b: str) -> Optional[float]

@dataclass
class CorrelationFilterConfig:
    max_correlation: float = 0.85
    min_window:      int   = 20
    ignore_pairs:    List  = []

@dataclass
class CorrelationResult:
    allowed:          bool
    correlated_pairs: List[Tuple[str, str, float]]
    max_correlation:  float
    reason:           str
```

---

## 5.7 ExposureControlEngine — کنترل Exposure

**فایل:** `backend/risk/exposure_control.py`

```python
class ExposureControlEngine:
    def check(
        self,
        new_symbol:     str,
        new_direction:  str,
        new_lots:       float,
        open_positions: List[ExposurePosition],
    ) -> ExposureCheckResult

    def get_snapshot(self, open_positions: List[ExposurePosition]) -> ExposureSnapshot

@dataclass
class ExposureControlConfig:
    max_total_lots:    float = 10.0
    max_symbol_lots:   float = 3.0
    max_currency_lots: float = 5.0

@dataclass
class ExposurePosition:
    symbol:    str
    direction: str
    lots:      float

@dataclass
class ExposureSnapshot:
    total_lots:   float
    by_symbol:    Dict[str, float]
    by_currency:  Dict[str, float]
    net_exposure: float
```

---

## 5.8 NewsFilterGate — بلاک اخبار

**فایل:** `backend/risk/news_filter.py`

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
    title:      str
    currency:   str
    impact:     NewsImpact
    event_time: datetime

@dataclass
class NewsBlockResult:
    blocked:          bool
    reason:           str
    event:            Optional[NewsEvent]
    minutes_to_event: Optional[float]
```

---

## 5.9 LotSizer — محاسبه حجم

**فایل:** `backend/risk/lot_sizing.py`

```python
class LotSizer:
    async def calculate(
        self,
        balance:        float,
        stop_loss_pips: float,
        symbol:         str,
        risk_pct:       float = 1.0,
    ) -> LotSizeResult

    async def get_pip_value(self, symbol: str) -> Tuple[float, str]
```

**فرمول:**
```
risk_usd = balance × (risk_pct / 100)
lot_size = risk_usd / (stop_loss_pips × pip_value)
lot_size = clamp(lot_size, min_lot, max_lot)
```

**مثال:** balance=10,000 | SL=20pip | risk_pct=1.0 | pip_value=10 USD
→ `lot_size = 100 / (20 × 10) = 0.50 lots`

---

## 5.10 ExecutionService — اجرای سیگنال

**فایل:** `backend/execution/execution_service.py`

```python
class ExecutionService:
    def __init__(
        self,
        risk:             Any,
        broker:           Any,
        osm:              Any,
        fr:               Any,
        pr:               Any,
        *,
        default_risk_pct: float = 1.0,
    ) -> None

    async def start(self) -> None
    async def stop(self) -> None
    async def execute_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]
    async def health(self) -> Dict[str, Any]
```

**Pipeline:**
```
execute_signal(signal)
  ↓ idempotency check
  ↓ inflight dedup
  ↓ _run_risk()  → RiskOrchestrator.assess()
  ↓ _create_order()
  ↓ OSM.create_order()
  ↓ _submit() → MT5Connector.send_order()
  ↓ OSM.transition(SUBMITTED → FILLED/FAILED)
  ↓ idempotency register
```

---

## 5.11 MT5Connector — اتصال MetaTrader

**فایل:** `backend/execution/mt5_connector.py`

```python
class MT5Connector:
    def __init__(self, exe_path=None, timeout_seconds=30, max_retries=3, retry_delay=1.0) -> None
    async def initialize(self) -> bool
    async def health_check(self) -> bool
    async def send_order(self, request: MT5OrderRequest, retry_policy=None) -> MT5OrderResult
    async def close_position(self, ticket: int, deviation: int = 10) -> MT5OrderResult
    async def get_positions(self) -> List[Any]
    async def get_account_info(self) -> Optional[Any]
    async def shutdown(self) -> None

@dataclass
class MT5OrderRequest:
    symbol:     str
    order_type: int
    volume:     float
    price:      float
    sl:         float
    tp:         float
    deviation:  int
    comment:    str = ""

@dataclass
class MT5OrderResult:
    retcode: int
    ticket:  int
    volume:  float
    price:   float
    @property
    def success(self) -> bool: return self.retcode == 10009
```

---

## 5.12 OrderStateMachine — ماشین حالت

**فایل:** `backend/execution/order_state_machine.py`

```python
class OrderStateMachine:
    async def create_order(self, order: ManagedOrder) -> ManagedOrder
    async def transition(self, order_id: str, new_state: OrderState,
                        *, ticket=None, fill_price=None, error=None) -> ManagedOrder
    async def get_active_orders(self) -> List[ManagedOrder]
    async def get_order(self, order_id: str) -> Optional[ManagedOrder]

@dataclass
class ManagedOrder:
    order_id:   str
    signal_id:  str
    symbol:     str
    direction:  str
    lot_size:   float
    state:      OrderState
    created_at: datetime
    ticket:     Optional[int]   = None
    fill_price: Optional[float] = None
```

**State Machine:**
```
PENDING → SUBMITTED → FILLED    (terminal)
             │
             └──────→ FAILED    (terminal)
PENDING → CANCELLED             (terminal)
```

---

## 5.13 FailureRecoveryEngine — بازیابی شکست

**فایل:** `backend/execution/failure_recovery.py`

```python
class FailureRecoveryEngine:
    async def handle_failure(self, order: ManagedOrder, error: str, retcode: int = 0) -> None
    def dead_letter_queue(self) -> List[FailedOrder]
    def retry_queue_size(self) -> int
    def health_stats(self) -> Dict[str, Any]

class RecoveryStrategy(str, Enum):
    RETRY_IMMEDIATE = "retry_immediate"   # شبکه/timeout
    RETRY_DELAYED   = "retry_delayed"     # partial fill
    DEAD_LETTER     = "dead_letter"       # invalid → مستقیم DLQ
    IGNORE          = "ignore"            # duplicate
```

---

## 5.14 VotingEngine — سیستم رأی‌گیری

**فایل:** `backend/agents/voting_engine.py`

```python
class VotingEngine:
    def __init__(self, agents: List[BaseAgent], threshold: float = 0.60,
                 timeout_s: float = 5.0, run_parallel: bool = True) -> None
    async def vote(self, context: Dict[str, Any]) -> VoteResult
    def update_weights(self, weight_map: Dict[str, float]) -> None
    def enable_agent(self, name: str) -> None
    def disable_agent(self, name: str) -> None

@dataclass
class VoteResult:
    decision:      VoteDecision     # APPROVE, REJECT, ABSTAIN
    confidence:    float            # [0.0, 1.0]
    agent_results: List[AgentResult]
    veto_by:       Optional[str]
    risk_blocked:  bool
    duration_ms:   float
    @property
    def passed_threshold(self) -> bool
    @property
    def blocking_agents(self) -> List[str]
    def to_dict(self) -> Dict[str, Any]
```

---

## 5.15 CircuitBreaker — قطع‌کننده مدار

**فایل:** `backend/circuit_breaker.py`

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
    failure_threshold:  int   = 5
    window_seconds:     float = 60.0
    recovery_timeout_s: float = 30.0
    success_threshold:  int   = 2
```

**State Machine:**
```
CLOSED ─(failures≥threshold)→ OPEN ─(timeout)→ HALF_OPEN
  ↑                                                  │
  └──────(successes≥threshold)─────────────────────┘
```

---

## 5.16 BackgroundScheduler — مدیریت Tasks

**فایل:** `backend/services/scheduler.py`

```python
class BackgroundScheduler:
    def register(self, name: str, coro_fn: Callable, interval_s: float,
                 *, run_on_start: bool = False, max_errors: int = 10) -> None
    async def shutdown(self, timeout_s: float = 10.0) -> None
    def health(self) -> Dict[str, Any]
```

```python
scheduler = get_scheduler()
scheduler.register("position_reconcile", reconciler.run_once, interval_s=30.0, run_on_start=True)
scheduler.register("daily_reset", equity_engine.reset_daily, interval_s=86400.0)
```

---

## 5.17 MetricsRegistry — متریک‌ها

**فایل:** `backend/observability/metrics.py`

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

---

# 6. Functions Documentation

> **برای تازه‌کار:** توابع کارهای کوچکی هستند که از بیرون صدا زده می‌شوند.
>
> **برای حرفه‌ای:** توابع public API هستند. همه type-annotated و async-aware.

---

## 6.1 Factory Functions — Singleton ها

| تابع | فایل | خروجی | توضیح |
|------|------|-------|-------|
| `get_execution_service()` | `core/deps.py` | `ExecutionService` | Singleton execution service |
| `get_risk_orchestrator()` | `risk/risk_orchestrator.py` | `RiskOrchestrator` | double-checked locking singleton |
| `get_equity_protection()` | `risk/equity_protection.py` | `EquityProtectionEngine` | module-level singleton |
| `get_exposure_control()` | `risk/exposure_control.py` | `ExposureControlEngine` | module-level singleton |
| `get_scheduler()` | `services/scheduler.py` | `BackgroundScheduler` | process-level singleton |
| `get_order_journal()` | `execution/order_journal.py` | `OrderJournal` | module-level singleton |
| `get_mt5_breaker()` | `circuit_breaker.py` | `CircuitBreaker` | MT5-specific circuit breaker |
| `get_agent_service()` | `agents/agent_service.py` | `AgentService` | module-level singleton |

---

## 6.2 FastAPI Dependency Functions

```python
# backend/core/deps.py

async def get_db() -> AsyncGenerator
async def get_current_user(credentials=Depends(_bearer)) -> dict
async def get_current_active_user(user=Depends(get_current_user)) -> dict
async def require_admin(user=Depends(get_current_active_user)) -> dict
async def require_super_admin(user=Depends(get_current_active_user)) -> dict
async def get_risk_orchestrator_dep() -> RiskOrchestrator
def get_metrics() -> MetricsRegistry
def get_audit_log() -> AuditLogger
def get_mt5_retry_config() -> RetryConfig
def get_db_retry_config() -> RetryConfig
```

---

## 6.3 Retry Functions

```python
# backend/core/retry.py

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

## 6.4 Health Check Functions

```python
# backend/api/health.py

async def liveness() -> Dict[str, Any]
# → {status: "alive", uptime_s: 3600.5}
# مناسب برای: Kubernetes liveness probe

async def readiness() -> Dict[str, Any]
# → {status: "ready"|"not_ready", checks: {db, redis, mt5}}
# مناسب برای: Kubernetes readiness probe

async def deep_health() -> Dict[str, Any]
# → SystemHealth.to_dict() — همه component ها به صورت موازی
# مناسب برای: Monitoring dashboard
```

---

## 6.5 Circuit Breaker Functions

```python
# backend/circuit_breaker.py

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

## 6.6 Logging Functions

```python
# backend/core/logger.py

def get_logger(name: str) -> ContextualLogger
# log = get_logger("execution.service")
# در production: JSON, در development: human-readable

def get_audit_logger() -> AuditLogger
# برای ثبت compliance events
# audit_log.record(action="TRADE_APPROVED", actor="system", resource="signal:123", result="success")
```

---

## 6.7 جدول خلاصه توابع مهم

| تابع | فایل | async | ورودی | خروجی |
|------|------|-------|-------|-------|
| `execute_signal()` | `execution/execution_service.py` | ✅ | `Dict[signal]` | `Dict[result]` |
| `assess()` | `risk/risk_orchestrator.py` | ✅ | `RiskInput` | `RiskResult` |
| `vote()` | `agents/voting_engine.py` | ✅ | `Dict[context]` | `VoteResult` |
| `send_order()` | `execution/mt5_connector.py` | ✅ | `MT5OrderRequest` | `MT5OrderResult` |
| `check()` | `risk/equity_protection.py` | ❌ | — | `ProtectionCheckResult` |
| `check_limits()` | `risk/daily_limits.py` | ❌ | `balance, TodayTrades` | `LimitsCheckResult` |
| `check()` | `risk/correlation_filter.py` | ✅ | `symbol, direction, positions` | `CorrelationResult` |
| `calculate()` | `risk/lot_sizing.py` | ✅ | `balance, sl_pips, symbol` | `LotSizeResult` |
| `transition()` | `execution/order_state_machine.py` | ✅ | `order_id, new_state` | `ManagedOrder` |
| `handle_failure()` | `execution/failure_recovery.py` | ✅ | `order, error, retcode` | `None` |
| `run_once()` | `execution/position_reconciliation.py` | ✅ | — | `ReconciliationResult` |
| `deep_health()` | `api/health.py` | ✅ | — | `Dict[SystemHealth]` |
| `halt_trading()` | `circuit_breaker.py` | ✅ | `reason: str` | `None` |
| `get_logger()` | `core/logger.py` | ❌ | `name: str` | `ContextualLogger` |
| `async_retry()` | `core/retry.py` | ❌ | `RetryConfig` | `Callable` |

---

*بخش‌های ۷–۲۵ در MASTER_DOCUMENTATION.md اصلی موجودند.*
