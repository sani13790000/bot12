# Galaxy Vast AI Trading Platform — Master Documentation

> **نسخه:** 2.0.0 | **آخرین به‌روزرسانی:** 2026-06-25 | **Python:** 3.11+

---

## فهرست مطالب

1. [معرفی پروژه](#1)
2. [معماری کامل](#2)
3. [ساختار پوشه‌ها](#3)
4. [تمام ماژول‌ها](#4)
5. [تمام کلاس‌ها و توابع](#5)
6. [نحوه نصب](#6)
7. [نحوه اجرا](#7)
8. [تنظیمات سیستم](#8)
9. [متغیرهای محیطی ENV](#9)
10. [Docker و Docker Compose](#10)
11. [CI/CD Pipeline](#11)
12. [نحوه توسعه](#12)
13. [نحوه دیباگ](#13)
14. [نحوه بکاپ](#14)
15. [نحوه آپدیت](#15)
16. [نحوه آموزش مدل‌های ML](#16)
17. [نحوه اتصال بروکرها](#17)
18. [مدیریت ریسک](#18)
19. [راهنمای رفع خطا](#19)
20. [Glossary](#20)

---

## 1. معرفی پروژه <a name="1"></a>

### Galaxy Vast چیست؟

Galaxy Vast یک پلتفرم هوش مصنوعی معاملاتی سطح Enterprise است که برای معاملات خودکار و نیمه‌خودکار در بازارهای فارکس و CFD طراحی شده است. این سیستم با ترکیب تحلیل SMC (Smart Money Concept)، یادگیری ماشین و مدیریت ریسک چندلایه، سیگنال‌های معاملاتی با کیفیت بالا تولید کرده و آن‌ها را از طریق MetaTrader 5 اجرا می‌کند.

### ویژگی‌های اصلی

| ویژگی | توضیح |
|-------|-------|
| **AI Multi-Agent Voting** | 13 agent هوشمند که با vote وزن‌دار به توافق می‌رسند |
| **Risk Engine چندلایه** | 7 gate ریسک که هر signal را بررسی می‌کنند |
| **Circuit Breaker** | توقف خودکار سیستم در صورت ضرر غیرعادی |
| **Semi-Auto Trading** | تأیید دستی سیگنال‌ها قبل اجرا |
| **Self-Learning** | بهبود خودکار مدل‌ها بر اساس نتایج واقعی |
| **Telegram Integration** | کنترل کامل از طریق ربات تلگرام |
| **Real-time Dashboard** | داشبورد Streamlit برای مانیتورینگ زنده |
| **Backtest Engine** | بک‌تست با داده‌های واقعی و Monte Carlo |

### Stack فناوری

```
Backend:    Python 3.11 + FastAPI + Uvicorn
Database:   Supabase (PostgreSQL)
Cache:      Redis 7.4
ML:         XGBoost + scikit-learn + PyTorch (CPU)
Broker:     MetaTrader 5 (MT5)
Telegram:   aiogram 3.x
Dashboard:  Streamlit
Container:  Docker + Docker Compose
Monitoring: Prometheus + custom metrics
```

---

## 2. معماری کامل <a name="2"></a>

### نمودار جریان سیگنال

```
MT5 EA --> POST /api/v1/signals/execute
            |
            v
     [Auth Middleware]  JWT verify + User lookup
     [Rate Limiter]     100 req/min per IP
     [Security MW]      XSS/Injection scan
            |
            v
   ExecutionService.execute_signal()
            |
   +---------+---------------------------+
   |    RISK GATE PIPELINE (7 gates)     |
   |                                     |
   | Gate 1: EquityProtectionEngine      |
   | Gate 2: DailyLimitsEngine           |
   | Gate 3: VolatilityFilter            |
   | Gate 4: NewsFilterGate              |
   | Gate 5: CorrelationFilter           |
   | Gate 6: ExposureControlEngine       |
   | Gate 7: LotSizer.calculate()        |
   |                                     |
   | X Any gate BLOCKS -> rejected       |
   | V All gates PASS  -> proceed        |
   +----------+--------------------------+
              |
              v
   CircuitBreaker.check()  OPEN? -> halt
              |
              v
   VotingEngine.vote()
    +- SMCAgent      weight: 0.25
    +- MLAgent       weight: 0.20
    +- RiskAgent     weight: 0.15
    +- TechnicalAgent weight: 0.15
    +- NewsAgent     weight: 0.10
    +- LiquidityAgent weight: 0.08
    +- SecurityAgent weight: 0.07
              |
        confidence >= 0.65?
              |
              v
   OrderStateMachine
   PENDING -> SUBMITTED -> FILLED -> CLOSING -> CLOSED
              |
              v
   MT5Connector.send_order()
    +- asyncio.to_thread (no GIL)
    +- Lock: no concurrent sends
    +- timeout: 30s
              |
              v
   PositionReconciliation.run_once()
    +- duplicate check before retry
    +- orphan detection
              |
        failed? -> FailureRecoveryEngine
              +- IMMEDIATE / EXPONENTIAL / DEAD_LETTER
              +- max 3 retries
              |
              v
   OrderJournal.record()    audit trail
   MetricsRegistry          Prometheus
   AuditLogger              compliance log
   Telegram alert           user notification
```

### معماری لایه‌ای (Clean Architecture)

```
Presentation : FastAPI Routes | Telegram Bot | Streamlit
Application  : ExecutionService | AgentService | LearningService
Domain       : RiskOrchestrator | VotingEngine | DecisionEngine
Infrastructure: MT5Connector | Database | Redis | Telegram API
```

### اصول طراحی

- **SOLID**: هر کلاس یک مسئولیت، open/closed، dependency injection
- **Fail-Safe**: همه risk gates در صورت خطا، trade را BLOCK می‌کنند
- **Idempotency**: هر signal_id فقط یک‌بار اجرا می‌شود
- **Singleton with DI**: singletons از `core/deps.py` inject می‌شوند

---

## 3. ساختار پوشه‌ها <a name="3"></a>

```
bot12/
+-- backend/
|   +-- agents/                  # 13 AI agent
|   |   +-- base_agent.py        # کلاس پایه
|   |   +-- voting_engine.py     # رای‌گیری وزن‌دار
|   |   +-- agent_service.py     # singleton factory
|   |   +-- smc_agent.py         # SMC analysis
|   |   +-- ml_agent.py          # ML prediction
|   |   +-- risk_agent.py        # risk scoring
|   |   +-- news_agent.py        # news impact
|   |   +-- liquidity_agent.py   # liquidity levels
|   |
|   +-- ai_prediction/           # ML prediction
|   |   +-- prediction_service.py
|   |   +-- model_manager.py
|   |   +-- feature_pipeline.py
|   |   +-- xgboost_trainer.py
|   |
|   +-- analysis/                # تحلیل بازار
|   |   +-- decision_engine.py   # 746 خط
|   |   +-- smc_engine.py        # 3077 خط
|   |
|   +-- api/                     # REST API
|   |   +-- main.py              # FastAPI app
|   |   +-- health.py            # health checks
|   |   +-- routes/              # 20+ route
|   |
|   +-- circuit_breaker.py       # halt trading
|   |
|   +-- core/                    # هسته مشترک
|   |   +-- config.py            # Settings
|   |   +-- enums.py             # 26 Enum
|   |   +-- exceptions.py        # error hierarchy
|   |   +-- interfaces.py        # Protocol/ABC
|   |   +-- logger.py            # JSON logger
|   |   +-- retry.py             # backoff retry
|   |   +-- deps.py              # DI
|   |   +-- auth.py              # JWT
|   |
|   +-- execution/               # لایه اجرا
|   |   +-- execution_service.py
|   |   +-- mt5_connector.py
|   |   +-- order_state_machine.py
|   |   +-- position_reconciliation.py
|   |   +-- failure_recovery.py
|   |   +-- semi_auto.py
|   |   +-- order_journal.py
|   |
|   +-- intelligence/            # ML engine
|   |   +-- ml_engine.py
|   |   +-- trade_memory.py
|   |
|   +-- middleware/
|   |   +-- rate_limit.py
|   |   +-- security.py
|   |
|   +-- observability/
|   |   +-- metrics.py
|   |   +-- alert_manager.py
|   |
|   +-- risk/                    # 7 Risk Gates
|   |   +-- risk_orchestrator.py
|   |   +-- lot_sizing.py
|   |   +-- volatility_filter.py
|   |   +-- correlation_filter.py
|   |   +-- equity_protection.py
|   |   +-- daily_limits.py
|   |   +-- exposure_control.py
|   |   +-- news_filter.py
|   |
|   +-- self_learning/
|   |   +-- learning_service.py
|   |   +-- training_pipeline.py
|   |
|   +-- services/
|   |   +-- scheduler.py
|   |   +-- trade_service.py
|   |   +-- audit_service.py
|   |
|   +-- telegram/
|   |   +-- bot.py
|   |   +-- handlers/
|   |
|   +-- tests/                   # 249 test
|       +-- conftest.py
|       +-- test_01_unit_risk.py  # 86 test
|       +-- test_02_unit_execution.py # 59 test
|       +-- test_03_integration.py    # 54 test
|       +-- test_04_security.py       # 50 test
|
+-- supabase/migrations/         # SQL (30+)
+-- mql5/                        # MQL5 EA code
+-- docker-compose.yml
+-- Dockerfile
+-- requirements.txt
+-- .env.example
```

---

## 4. تمام ماژول‌ها <a name="4"></a>

### Core

| فایل | مسئولیت |
|------|----------|
| config.py | تمام تنظیمات از ENV با validation |
| enums.py | 26 Enum مرکزی |
| exceptions.py | AppError > Retryable/NonRetryable |
| interfaces.py | IRiskGate, IOrderBroker, ILotSizer, IAgent |
| logger.py | JSON structured logging + AuditLogger |
| retry.py | @async_retry decorator با exponential backoff |
| deps.py | FastAPI DI |
| auth.py | JWT decode, TokenPayload |

### Risk (7 Gate)

| فایل | Gate | مسئولیت |
|------|------|----------|
| equity_protection.py | 1 | Max Daily/Weekly/Total drawdown |
| daily_limits.py | 2 | حداکثر معامله + P&L روزانه |
| volatility_filter.py | 3 | ATR ratio و spread check |
| news_filter.py | 4 | بلاک 30 دقیقه قبل/بعد اخبار High Impact |
| correlation_filter.py | 5 | Pearson correlation rolling window |
| exposure_control.py | 6 | کل ریسک باز به تفکیک ارز |
| lot_sizing.py | 7 | Kelly Criterion + ATR-adjusted lot |
| risk_orchestrator.py | Orchestrator | Singleton هماهنگ‌کننده |

### Execution

| فایل | مسئولیت |
|------|----------|
| execution_service.py | Pipeline اصلی |
| mt5_connector.py | Thread-safe asyncio wrapper برای MT5 |
| order_state_machine.py | FSM: PENDING -> FILLED -> CLOSED |
| position_reconciliation.py | تطابق با MT5، orphan detection |
| failure_recovery.py | Retry queue + dead-letter |
| semi_auto.py | تأیید دستی با timeout 5دقیقه |
| order_journal.py | Audit trail تمام events |

---

## 5. تمام کلاس‌ها و توابع <a name="5"></a>

### core/exceptions.py

```python
class AppError(Exception)
    error_code: str
    http_status: int
    context: Dict
    to_dict() -> Dict

class RetryableError(AppError)       # retry می‌شوند
class NonRetryableError(AppError)    # retry نمی‌شوند
class OrderSubmissionError(RetryableError)
class BrokerConnectionError(RetryableError)
class DatabaseError(RetryableError)
class OrderDuplicateError(NonRetryableError)   # HTTP 409
class RiskBlockedError(NonRetryableError)      # HTTP 422
class CircuitOpenError(NonRetryableError)      # HTTP 503
```

### core/retry.py

```python
class RetryStrategy(Enum)
    FIXED / EXPONENTIAL / LINEAR

class RetryConfig
    max_attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 60.0
    strategy: RetryStrategy = EXPONENTIAL
    retry_on: tuple = (RetryableError,)

@async_retry(config: RetryConfig)    # decorator
await with_retry_async(fn, config)   # programmatic

# Pre-built:
MT5_RETRY  = RetryConfig(max_attempts=3, base_delay_s=0.5)
DB_RETRY   = RetryConfig(max_attempts=5, base_delay_s=0.2)
RISK_RETRY = RetryConfig(max_attempts=2, base_delay_s=0.1)
```

### core/logger.py

```python
class ContextualLogger
    bind(**kwargs) -> ContextualLogger
    debug/info/warning/error/critical(msg, **kwargs)

class AuditLogger
    record(action, actor, resource, result, **meta)

get_logger(name) -> ContextualLogger
get_audit_logger() -> AuditLogger

# Usage:
log = get_logger(__name__)
log.info("Order submitted", order_id="ORD-1", symbol="EURUSD", lot=0.05)
# JSON: {"ts":"...","level":"INFO","msg":"Order submitted","order_id":"ORD-1",...}
```

### circuit_breaker.py

```python
class BreakerState(Enum)
    CLOSED / OPEN / HALF_OPEN

class BreakerConfig
    failure_threshold: int = 5
    window_seconds: float = 60.0
    reset_timeout_s: float = 120.0
    success_threshold: int = 2

class CircuitBreaker
    can_execute() -> bool
    record_success()
    record_failure(reason)
    force_open(reason) / force_close(reason)
    snapshot() -> Dict
    add_on_open(callback) / add_on_close(callback)

halt_trading(reason: str)
resume_trading(reason: str)
is_trading_halted() -> bool
```

### execution/execution_service.py

```python
class ExecutionService
    __init__(risk, broker, osm, fr, pr, semi_auto, metrics)
    start() / stop()
    execute_signal(signal: Dict) -> Dict
    _pipeline(signal, signal_id, log)
    _run_risk(signal, log) -> Dict
    _create_order(signal, risk_result) -> ManagedOrder
    _submit(order) -> Dict
```

### execution/order_state_machine.py

```python
class OrderState(Enum)
    PENDING / SUBMITTED / FILLED / PARTIAL
    CLOSING / CLOSED / REJECTED / CANCELLED / ERROR

# Valid Transitions:
# PENDING    -> SUBMITTED, CANCELLED, ERROR
# SUBMITTED  -> FILLED, PARTIAL, REJECTED, ERROR
# FILLED     -> CLOSING, CLOSED, ERROR
# CLOSING    -> CLOSED, ERROR

class ManagedOrder
    order_id, signal_id, symbol, direction
    lot_size, stop_loss, take_profit
    state: OrderState
    created_at: datetime

class OrderStateMachine
    transition(order_id, to_state) -> bool
    get_order(order_id) -> Optional[ManagedOrder]
    start() / stop()
```

### agents/voting_engine.py

```python
class VoteDecision(Enum)
    BUY / SELL / HOLD / BLOCK

class VoteResult
    decision: VoteDecision
    confidence: float
    final_confidence() -> float
    passed_threshold(min_conf) -> bool
    blocking_agents() -> List[str]
    to_dict() -> Dict

class VotingEngine
    vote(context: Dict) -> VoteResult
    update_weights(weight_map: Dict)
    enable_agent(name) / disable_agent(name)
    get_weights() -> Dict
```

### intelligence/ml_engine.py

```python
class MLEngine
    predict(features: Dict) -> MLPrediction
    train(contexts: List) -> TrainingResult
    async_train(contexts) / async_predict(features)
    save_models() / load_models()
    is_trained() -> bool

class ConceptDriftDetector
    update(value: float)
    drift_score() -> float
    reset()

class UnifiedMLEngine      # v2 با drift detection
    should_retrain() -> bool
    get_drift_info() -> Dict
```

### api/health.py

```
GET /health        liveness  (Kubernetes probe)
GET /health/ready  readiness (Kubernetes probe)
GET /health/deep   full system check

# Response:
{
  "status": "healthy",
  "components": {
    "database": {"status": "healthy", "latency_ms": 3.2},
    "redis":    {"status": "healthy", "latency_ms": 0.8},
    "mt5":      {"status": "healthy", "latency_ms": 12.1},
    "risk":     {"status": "healthy", "latency_ms": 0.1}
  },
  "uptime_s": 3600.5
}
```

---

## 6. نحوه نصب <a name="6"></a>

### پیش‌نیازها

```
Python     3.11+
Docker     24.0+
Docker Compose  2.20+
MetaTrader 5    (فقط Windows)
Supabase account (رایگان کافی است)
```

### گام 1: دریافت کد

```bash
git clone https://github.com/sani13790000/bot12.git
cd bot12
```

### گام 2: تنظیم متغیرها

```bash
cp .env.example .env
nano .env
```

حداقل **الزامی**:

```bash
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret
JWT_SECRET_KEY=...     # python3 -c "import secrets; print(secrets.token_hex(32))"
TELEGRAM_BOT_TOKEN=123456789:ABC-...
TELEGRAM_ADMIN_IDS=123456789
MQL5_API_TOKEN=your-secure-token
```

### گام 3: نصب وابستگی‌ها

```bash
python3 -m venv venv
source venv/bin/activate    # Linux/Mac
pip install -r requirements.txt
```

### گام 4: Migration دیتابیس

```bash
supabase db push
# یا فایل‌های supabase/migrations/ را مرتب در SQL Editor اجرا کنید
```

### گام 5: تأیید نصب

```bash
python3 -c "from backend.core.config import get_settings; print('OK:', get_settings().ENVIRONMENT)"
```

---

## 7. نحوه اجرا <a name="7"></a>

### Docker Compose (توصیه‌شده)

```bash
docker-compose up --build -d
docker-compose ps
docker-compose logs -f api
docker-compose down
```

### Python مستقیم

```bash
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
python3 -m backend.telegram.bot
streamlit run backend/dashboard/app.py --server.port 8501
```

### تأیید

```bash
curl http://localhost:8000/health/deep | python3 -m json.tool
# http://localhost:8000/docs   Swagger UI
# http://localhost:8501        Dashboard
```

---

## 8. تنظیمات سیستم <a name="8"></a>

### حساب‌های کوچک (< $1,000)

```env
MAX_DAILY_TRADES=5
MAX_DAILY_LOSS_PCT=3.0
RISK_PER_TRADE_PCT=0.5
MAX_LOT_SIZE=0.1
VOTING_THRESHOLD=0.75
```

### حساب‌های متوسط ($1,000-$10,000)

```env
MAX_DAILY_TRADES=10
MAX_DAILY_LOSS_PCT=5.0
RISK_PER_TRADE_PCT=1.0
MAX_LOT_SIZE=1.0
VOTING_THRESHOLD=0.65
```

### حساب‌های بزرگ (> $10,000)

```env
MAX_DAILY_TRADES=20
MAX_DAILY_LOSS_PCT=3.0
RISK_PER_TRADE_PCT=0.5
MAX_LOT_SIZE=10.0
VOTING_THRESHOLD=0.70
```

---

## 9. متغیرهای محیطی ENV <a name="9"></a>

### App
| متغیر | پیش‌فرض | توضیح |
|-------|---------|-------|
| ENVIRONMENT | production | development/staging/production |
| DEBUG | false | debug mode |
| LOG_LEVEL | INFO | DEBUG/INFO/WARNING/ERROR |

### Supabase (الزامی)
| SUPABASE_URL | آدرس پروژه |
| SUPABASE_KEY | service_role key |
| SUPABASE_JWT_SECRET | JWT secret |

### JWT (الزامی)
| JWT_SECRET_KEY | حداقل 64 کاراکتر hex |
| ACCESS_TOKEN_EXPIRE_MINUTES | 30 |
| REFRESH_TOKEN_EXPIRE_DAYS | 30 |

### Redis
| REDIS_URL | redis://redis:6379/0 |
| REDIS_PASSWORD | changeme_redis |
| REDIS_MAX_CONNECTIONS | 20 |

### Telegram (الزامی)
| TELEGRAM_BOT_TOKEN | توکن @BotFather |
| TELEGRAM_ADMIN_IDS | ID ادمین‌ها با کاما |

### MT5
| MQL5_API_TOKEN | توکن EA |
| MT5_PATH | مسیر terminal64.exe |
| MT5_TIMEOUT_SECONDS | 30 |

### ریسک
| RISK_PER_TRADE_PCT | 1.0 | درصد ریسک |
| MAX_DAILY_TRADES | 10 | حد روزانه |
| MAX_DAILY_LOSS_PCT | 5.0 | حد ضرر % |
| MAX_WEEKLY_LOSS_PCT | 10.0 | حد ضرر هفتگی |
| MAX_TOTAL_DRAWDOWN_PCT | 20.0 | حد drawdown کل |
| VOTING_THRESHOLD | 0.65 | حداقل confidence |

> **هشدار:** هرگز از * در ALLOWED_ORIGINS استفاده نکنید - سیستم startup را متوقف می‌کند.

---

## 10. Docker و Docker Compose <a name="10"></a>

### سرویس‌ها

| سرویس | پورت | RAM | توضیح |
|-------|------|-----|-------|
| api | 8000 | 2G | FastAPI backend |
| redis | 6379 | 768M | Cache + Rate Limiting |
| telegram_bot | - | 512M | ربات aiogram |
| dashboard | 8501 | 1G | Streamlit |
| frontend | 3000 | 256M | UI |

### دستورات

```bash
# اجرا
docker-compose up --build -d
# وضعیت
docker-compose ps
# لاگ
docker-compose logs -f api
# restart
docker-compose restart api
# توقف
docker-compose down
docker-compose down -v    # + حذف volumes
# resource usage
docker stats
```

---

## 11. CI/CD Pipeline <a name="11"></a>

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main, develop]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - run: pip install -r requirements.txt
      - run: OTEL_SDK_DISABLED=true pytest backend/tests/ --cov=backend -q

  security:
    runs-on: ubuntu-latest
    steps:
      - run: pip install bandit && bandit -r backend/ -ll -x backend/tests/
```

### بررسی لوکل

```bash
OTEL_SDK_DISABLED=true pytest backend/tests/ -q
python3 -m py_compile backend/core/config.py
pip install bandit && bandit -r backend/ -ll -x backend/tests/
```

---

## 12. نحوه توسعه <a name="12"></a>

### اضافه کردن Agent جدید

```python
# backend/agents/my_agent.py
from backend.agents.base_agent import BaseAgent, VoteResult, VoteSignal

class MyAgent(BaseAgent):
    @property
    def agent_id(self): return "my_agent"

    @property
    def weight(self): return 0.10

    async def _analyze(self, context: dict) -> VoteResult:
        score = 0.6  # منطق تحلیل شما
        signal = VoteSignal.BUY if score > 0.7 else \
                 VoteSignal.SELL if score < 0.3 else VoteSignal.HOLD
        return VoteResult(
            agent_id=self.agent_id,
            signal=signal,
            confidence=min(abs(score-0.5)*2, 1.0),
            reason=f"score={score:.2f}"
        )
```

### اضافه کردن Route جدید

```python
# backend/api/routes/my_route.py
from fastapi import APIRouter, Depends
from backend.core.deps import get_current_user
router = APIRouter(prefix="/my-feature", tags=["my-feature"])

@router.get("/status")
async def get_status(user=Depends(get_current_user)):
    return {"status": "ok"}

# در main.py:
app.include_router(my_router, prefix="/api/v1")
```

### استانداردهای کد

```python
# همیشه type hints
from typing import Optional, Dict, Any, List

# از get_logger استفاده کنید
from backend.core.logger import get_logger
log = get_logger(__name__)
log.info("event", key=value)    # structured
```

---

## 13. نحوه دیباگ <a name="13"></a>

### لاگ‌ها

```bash
docker-compose logs -f api
docker-compose logs api | grep '"level":"ERROR"'
docker-compose logs api | grep 'signal_id.*SIG-123'
```

### Debug Mode

```env
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
```

### بررسی وضعیت

```bash
curl http://localhost:8000/health/deep
curl http://localhost:8000/api/v1/risk/circuit-breaker/status
curl http://localhost:8000/api/v1/observability/metrics/snapshot
```

### دیباگ Python

```python
import asyncio
from backend.core.deps import get_execution_service

async def debug():
    svc = get_execution_service()
    result = await svc.execute_signal({
        "signal_id": "DEBUG-001",
        "symbol": "EURUSD",
        "direction": "BUY",
        "entry_price": 1.0850,
        "stop_loss": 1.0830,
        "take_profit": 1.0890,
    })
    print(result)

asyncio.run(debug())
```

---

## 14. نحوه بکاپ <a name="14"></a>

```bash
# مدل‌ها
docker-compose exec api tar -czf /tmp/models.tar.gz /app/models/
docker cp $(docker-compose ps -q api):/tmp/models.tar.gz ./backups/

# Redis
docker-compose exec redis redis-cli -a changeme_redis BGSAVE

# اسکریپت خودکار - crontab
0 3 * * * /path/to/scripts/backup.sh >> /var/log/backup.log 2>&1
```

---

## 15. نحوه آپدیت <a name="15"></a>

```bash
# 1. کد جدید
git pull origin main

# 2. rebuild
docker-compose build api

# 3. راه‌اندازی
docker-compose up -d

# 4. تأیید
curl http://localhost:8000/health/deep

# Rollback
git log --oneline -10
git checkout [HASH]
docker-compose build api && docker-compose up -d
```

---

## 16. نحوه آموزش مدل‌های ML <a name="16"></a>

### Pipeline

```
معاملات بسته‌شده
       |
Feature Extraction (8 feature: atr, spread, smc_score, win_rate_7d, ...)
       |
Walk-Forward Cross-Validation (5 fold)
       |
XGBoost + Logistic Regression
       |
CalibratedClassifierCV
       |
Concept Drift Detection (ADWIN)
       |
UnifiedMLEngine (production)
```

### شرایط آموزش خودکار (هر 60 دقیقه)

```
1. حداقل 50 معامله جدید
2. Drift score > آستانه
3. دقت < 55% در 7 روز اخیر
4. force_retrain() فراخوانی شده
```

### آموزش دستی

```bash
# API
curl -X POST http://localhost:8000/api/v1/learning/force-retrain \
  -H "Authorization: Bearer ADMIN_TOKEN"

# بررسی عملکرد
curl http://localhost:8000/api/v1/learning/stats
```

---

## 17. نحوه اتصال بروکرها <a name="17"></a>

### MetaTrader 5

```
1. نصب MT5 از https://www.metatrader5.com
2. تنظیم .env: MT5_PATH + MQL5_API_TOKEN
3. کپی mql5/GalaxyVastEA.mq5 در پوشه MQL5\Experts
4. در MetaEditor: F7 (Compile)
5. دراگ EA به نمودار:
   - API_URL: http://YOUR_SERVER:8000
   - API_TOKEN: مقدار MQL5_API_TOKEN
   - MAGIC_NUMBER: عدد منحصربه‌فرد
```

### بروکر سفارشی

```python
# IOrderBroker Protocol را پیاده‌سازی کنید:
class MyBroker:
    async def send_order(self, request) -> MT5OrderResult: ...
    async def get_positions(self) -> list: ...
    async def close_position(self, ticket, ...) -> MT5OrderResult: ...
    async def health_check(self) -> bool: ...
```

---

## 18. مدیریت ریسک <a name="18"></a>

### 7 Gate ریسک

```
سیگنال دریافت شد
  |
[Gate 1] EquityProtection   drawdown بیش از حد?
[Gate 2] DailyLimits        تعداد معامله بیش از حد?
[Gate 3] VolatilityFilter   ATR/spread بیش از حد?
[Gate 4] NewsFilter         خبر High Impact در 30دق?
[Gate 5] CorrelationFilter  همبستگی > 0.7?
[Gate 6] ExposureControl    کل ریسک > حد?
[Gate 7] LotSizer           محاسبه Kelly+ATR
  |
اجرا مجاز است
```

### Circuit Breaker

```
CLOSED  --[5 خطا/60s]--> OPEN (halt)
  ^                              |
  |        [120s انتظار]      |
  |              v              |
  +--[موفق]-- HALF_OPEN <------+
```

### کنترل از API

```bash
# توقف
docker-compose exec api curl -X POST localhost:8000/api/v1/risk/circuit-breaker/halt \
  -d '{"reason":"manual halt"}'
# از سرگیری
curl -X POST localhost:8000/api/v1/risk/circuit-breaker/reset
```

### Semi-Auto Mode

```bash
# سیگنال‌های در انتظار
curl http://localhost:8000/api/v1/signals/pending
# تأیید (تا 5 دقیقه فرصت)
curl -X POST http://localhost:8000/api/v1/signals/SIG-123/approve
```

---

## 19. راهنمای رفع خطا <a name="19"></a>

### خطاهای رایج

| خطا | علت | راه‌حل |
|-----|-----|--------|
| RuntimeError: no running event loop | asyncio.Lock در import time | lazy init بنویسید |
| AttributeError: NoneType.check | singleton مقداردهی نشده | set_mt5() در startup |
| TypeError: float() argument None | float(None) | _safe_float(val, 0.0) |
| Redis connection refused | Redis اجرا نمی‌شود | docker-compose up redis -d |
| Circuit breaker OPEN | خطاهای MT5 | MT5 بررسی + /reset |
| Risk block: daily loss | ضرر به حد رسید | فردا ادامه دهید |

### خطاهای MT5

| کد | معنا | راه‌حل |
|----|------|--------|
| 10004 | Connection lost | MT5 restart |
| 10014 | Invalid volume | min/max lot |
| 10016 | Invalid stops | فاصله SL/TP |
| 10019 | Not enough money | موجودی |

### ریست اضطراری

```bash
curl -X POST localhost:8000/api/v1/risk/circuit-breaker/halt -d '{"reason":"emergency"}'
docker-compose restart api
curl http://localhost:8000/health/deep
curl -X POST localhost:8000/api/v1/risk/circuit-breaker/reset
```

### اجرای تست‌ها

```bash
# همه (249 تست)
OTEL_SDK_DISABLED=true pytest backend/tests/ -v

# با coverage
OTEL_SDK_DISABLED=true pytest backend/tests/ --cov=backend --cov-report=html
```

---

## 20. Glossary <a name="20"></a>

| اصطلاح | توضیح |
|--------|-------|
| SMC | Smart Money Concept |
| FVG | Fair Value Gap |
| Order Block | ناحیه سفارش بزرگ |
| Liquidity | سطوح Stop Loss |
| ATR | Average True Range |
| Kelly Criterion | فرمول حجم بهینه |
| Walk-Forward | آموزش بدون leak آینده |
| Concept Drift | تغییر الگوی بازار |
| Drawdown | کاهش سرمایه از peak |
| Circuit Breaker | توقف خودکار |
| Gate | لایه بررسی ریسک |
| Semi-Auto | تأیید دستی سیگنال |
| Idempotency | فقط یک‌بار اجرا شود |
| Dead Letter Queue | صف سفارات بدون retry |
| Orphan Position | پوزیشن در MT5 ولی در سیستم نیست |
| Singleton | فقط یک نمونه در کل برنامه |
| DI | Dependency Injection |
| RBAC | Role-Based Access Control |
| Spread | تفاوت bid/ask |
| Pip | کوچکترین واحد تغییر قیمت |
| Lot | 1 lot = 100,000 واحد |
| SL | Stop Loss |
| TP | Take Profit |
| R:R | Risk:Reward ratio |
| AUC | Area Under Curve - ML |
| ADWIN | Adaptive Windowing - drift |
| MQL5 | زبان Expert Advisor |
| EA | Expert Advisor - MT5 |
| NFP | Non-Farm Payrolls |

---

*نسخه 2.0.0 | Galaxy Vast AI Trading Platform | 2026-06-25*
