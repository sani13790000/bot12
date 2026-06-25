# GALAXY VAST AI TRADING PLATFORM
# PROJECT ANALYSIS REPORT

**Generated:** 2026-06-25 | **Team:** Architect + Senior Dev + Quant + ML + DevOps + Security + QA
**Repository:** github.com/sani13790000/bot12 | **Total Files:** 429 | **Python Files:** 294

---

## 1. هدف پروژه

| | |
|---|---|
| **نام** | Galaxy Vast AI Trading Platform |
| **هدف اصلی** | پلتفرم معاملاتی هوش مصنوعی برای MetaTrader 5 |
| **نوع** | Automated & Semi-Automated Forex/CFD Trading |
| **معماری** | Multi-Agent System + Risk Engine + FastAPI Backend + Telegram Bot |
| **مخاطب** | Retail/Institutional Traders |

**قابلیت‌های اصلی:**
- دریافت سیگنال از EA (Expert Advisor) در MetaTrader 5
- تحلیل چندعاملی (7 agent موازی) با Voting Engine
- مدیریت ریسک چند لایه‌ای (7 gate مستقل)
- اجرای اتوماتیک و نیمه‌اتوماتیک سفارش
- یادگیری ماشین (XGBoost + Walk-Forward CV)
- Self-Learning از نتایج معاملات گذشته
- Institutional-grade analytics (Monte Carlo, VaR, RL)
- Telegram Bot برای کنترل و نظارت
- Streamlit Dashboard برای تحلیل
- Security AI برای تشخیص ناهنجاری

---

## 2. معماری کلی سیستم

```
┌────────────────────────────────────────────────────────────────────┐
│                    MetaTrader 5 (MQL5 EA)                          │
│                 MT5TradingEA_Complete.mq5                           │
│           POST /api/v1/signals/receive (MQL5_API_TOKEN)            │
└─────────────────────────┬──────────────────────────────────────────┘
                          │ HTTP Signal
                          ▼
┌────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (port 8000)                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │               Middleware Stack                               │   │
│  │  SecurityMiddleware → RateLimitMiddleware → ObservabilityMW │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                          │                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │               API Routes (/api/v1/*)                          │  │
│  │  signals│trades│risk│agents│analysis│backtest│dashboard│...  │  │
│  └──────────────────────┬───────────────────────────────────────┘  │
│                          │                                          │
│  ┌──────────────────────▼───────────────────────────────────────┐  │
│  │               Agent Layer                                     │  │
│  │     AgentService → VotingEngine (7 agents parallel)          │  │
│  │  MarketStruct│Liquidity│SMC│AIPred│Risk(veto)│News│Execution │  │
│  └──────────────────────┬───────────────────────────────────────┘  │
│                          │ VoteResult                               │
│  ┌──────────────────────▼───────────────────────────────────────┐  │
│  │               Risk Engine (7 Gates)                            │  │
│  │  EquityProtection→DailyLimits→Volatility→Correlation          │  │
│  │  →Exposure→PortfolioRisk→LotSizer                             │  │
│  │               RiskOrchestrator (Singleton)                     │  │
│  └──────────────────────┬───────────────────────────────────────┘  │
│                          │ RiskDecision + LotSize                   │
│  ┌──────────────────────▼───────────────────────────────────────┐  │
│  │               Execution Layer                                  │  │
│  │  ExecutionService→OSM→MT5Connector→PositionReconciliation     │  │
│  │  →FailureRecovery→CircuitBreaker                               │  │
│  └──────────────────────┬───────────────────────────────────────┘  │
│                          │                                          │
│  ┌──────────────────────▼───────────────────────────────────────┐  │
│  │  Intelligence: MLEngine←TradeMemory←TrainingPipeline          │  │
│  │  Observability: Prometheus+AlertManager+AuditService           │  │
│  └───────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
     │ Telegram Bot (aiogram3)      │ Streamlit Dashboard (8501)
     │ Admin control/alerts         │ Backtest/Analytics
     └──────────────────────────────┘
              │
     Supabase (PostgreSQL) + Redis + FileSystem
```

---

## 3. تمام ماژول‌ها (Packages)

| Package | مسیر | خطوط تقریبی | نقش | وابستگی‌های اصلی |
|---------|------|------------|-----|------------------|
| **core** | `backend/core/` | ~900 | تنظیمات، exceptions، enums، interfaces، auth، deps، logger، retry | pydantic, python-jose |
| **api** | `backend/api/` | ~2,400 | FastAPI routes، main app، websocket، health | fastapi, uvicorn |
| **risk** | `backend/risk/` | ~1,500 | هفت gate مدیریت ریسک | numpy, pandas |
| **execution** | `backend/execution/` | ~1,300 | Order lifecycle، MT5 connection، recovery | asyncio |
| **agents** | `backend/agents/` | ~1,800 | Multi-agent voting system | core, analysis |
| **analysis** | `backend/analysis/` | ~4,000 | Decision engine، SMC، price action | pandas |
| **intelligence** | `backend/intelligence/` | ~1,200 | ML engine، trade memory، learning | sklearn, xgboost |
| **ai_prediction** | `backend/ai_prediction/` | ~800 | Model manager، prediction service | torch, xgboost |
| **self_learning** | `backend/self_learning/` | ~900 | Auto-retraining pipeline | sklearn, pandas |
| **services** | `backend/services/` | ~800 | Trade، signal، audit، RBAC، scheduler | supabase, redis |
| **database** | `backend/database/` | ~400 | Connection، pool monitor، health | asyncpg, supabase |
| **middleware** | `backend/middleware/` | ~700 | Security، rate limit، observability | starlette |
| **observability** | `backend/observability/` | ~500 | Metrics، alerts، tracing، logging | prometheus-client |
| **telegram** | `backend/telegram/` | ~1,800 | Bot، handlers، routers، keyboards | aiogram 3 |
| **institutional** | `backend/institutional/` | ~1,600 | Institutional analytics | numpy, pandas, gymnasium |
| **backtest_engine** | `backend/backtest_engine/` | ~1,200 | Multi-symbol backtesting | pandas, numpy |
| **research** | `backend/research/` | ~600 | Walk-forward، replay engine | pandas |
| **analytics** | `backend/analytics/` | ~500 | Metrics، reporting | pandas |
| **trading** | `backend/trading/` | ~400 | Anti-repaint، market regime | pandas |
| **security_reporting** | `backend/security_reporting/` | ~400 | Security reports، scoring | httpx |
| **contracts** | `backend/contracts/` | ~150 | Decision contract types | dataclasses |
| **circuit_breaker** | `backend/circuit_breaker.py` | ~315 | Circuit breaker pattern | asyncio |
| **dashboard** | `dashboard/` | ~800 | Streamlit pages | streamlit |
| **tests** | `backend/tests/` | ~4,000 | 50+ test files | pytest |

---

## 4. تمام کلاس‌ها

### 4.1 core/

| کلاس | فایل | نقش |
|------|------|-----|
| `Settings` | `config.py:20` | تمام تنظیمات از `.env` با pydantic-settings |
| `PermissionLevel` | `enums.py:12` | سطح دسترسی (0=VIEW→100=SUPER_ADMIN) |
| `UserStatus` | `enums.py:22` | active, inactive, suspended, deleted |
| `UserRole` | `enums.py:30` | user, analyst, trader, admin, super_admin |
| `LicenseType` | `enums.py:39` | trial, basic, professional, institutional, enterprise |
| `LicenseStatus` | `enums.py:49` | active, expired, suspended, revoked, pending |
| `LicenseFeature` | `enums.py:58` | ML, backtesting, semi_auto, institutional, API features |
| `TradeDirection` | `enums.py:85` | BUY, SELL, NEUTRAL |
| `TradeType` | `enums.py:92` | MARKET, LIMIT, STOP, STOP_LIMIT |
| `TradeStatus` | `enums.py:100` | PENDING, OPEN, CLOSED, CANCELLED, ERROR |
| `SignalStatus` | `enums.py:110` | ACTIVE, EXPIRED, EXECUTED, CANCELLED, REJECTED, FILLED |
| `OrderStatus` | `enums.py:135` | PENDING, SUBMITTED, PARTIAL, FILLED, REJECTED, CANCELLED |
| `MarketSession` | `enums.py:154` | ASIAN, LONDON, NEW_YORK, OVERLAP, CLOSED |
| `TrendDirection` | `enums.py:199` | BULLISH, BEARISH, NEUTRAL, RANGING, UNDEFINED |
| `TradeQuality` | `enums.py:214` | A_PLUS, A, B, C, D |
| `HealthStatus` | `enums.py:265` | HEALTHY, DEGRADED, UNHEALTHY |
| `AppError` | `exceptions.py` | Base exception با error_code، http_status |
| `RetryableError` | `exceptions.py` | قابل retry |
| `NonRetryableError` | `exceptions.py` | غیر قابل retry |
| `OrderSubmissionError` | `exceptions.py` | خطای ارسال سفارش |
| `BrokerConnectionError` | `exceptions.py` | خطای اتصال به بروکر |
| `RiskBlockedError` | `exceptions.py` | بلاک توسط risk gate |
| `CircuitOpenError` | `exceptions.py` | Circuit breaker open |
| `RetryConfig` | `retry.py` | پیکربندی retry mechanism |
| `ContextualLogger` | `logger.py` | Logger با context binding |
| `AuditLogger` | `logger.py` | Immutable audit trail |

### 4.2 risk/

| کلاس | فایل | نقش |
|------|------|-----|
| `RiskOrchestrator` | `risk_orchestrator.py` | هماهنگ‌کننده تمام gate‌ها |
| `RiskInput` | `risk_orchestrator.py` | ورودی استاندارد برای risk assessment |
| `RiskDecision` | `risk_orchestrator.py` | خروجی نهایی risk assessment |
| `EquityProtectionEngine` | `equity_protection.py:47` | محافظت equity با Drawdown/Halt |
| `EquityProtectionConfig` | `equity_protection.py:16` | تنظیمات equity protection |
| `EquityState` | `equity_protection.py:29` | وضعیت لحظه‌ای equity |
| `ProtectionCheckResult` | `equity_protection.py:40` | نتیجه بررسی equity |
| `ProtectionLevel` | `equity_protection.py:11` | NORMAL, WARNING, CRITICAL, HALT |
| `DailyLimitsEngine` | `daily_limits.py:47` | محدودیت‌های روزانه/هفتگی/ماهانه |
| `TodayTrades` | `daily_limits.py:18` | تعداد و P&L امروز |
| `LimitsCheckResult` | `daily_limits.py:23` | نتیجه بررسی محدودیت‌ها |
| `CorrelationFilter` | `correlation_filter.py:195` | فیلتر همبستگی بین نمادها |
| `RollingCorrelationEngine` | `correlation_filter.py:104` | محاسبه Pearson correlation |
| `ExposureControlEngine` | `exposure_control.py:90` | کنترل exposure کل پرتفولیو |
| `ExposurePosition` | `exposure_control.py:47` | موقعیت باز در پرتفولیو |
| `ExposureSnapshot` | `exposure_control.py:55` | اسنپ‌شات exposure |
| `ExposureCheckResult` | `exposure_control.py:67` | نتیجه بررسی exposure |
| `LotSizer` | `lot_sizing.py:36` | محاسبه حجم معامله با Kelly |
| `LotSizingConfig` | `lot_sizing.py:29` | تنظیمات lot sizing |
| `LotSizeResult` | `lot_sizing.py:33` | نتیجه محاسبه lot |
| `FailMode` | `fail_mode.py` | FAIL_OPEN, FAIL_CLOSED |

### 4.3 execution/

| کلاس | فایل | نقش |
|------|------|-----|
| `ExecutionService` | `execution_service.py:54` | هماهنگ‌کننده اصلی execution |
| `MT5Connector` | `mt5_connector.py:103` | اتصال به MetaTrader 5 C++ API |
| `MT5OrderRequest` | `mt5_connector.py:49` | ساختار سفارش MT5 |
| `MT5OrderResult` | `mt5_connector.py:68` | نتیجه سفارش MT5 |
| `MT5ConnectionStatus` | `mt5_connector.py:41` | DISCONNECTED, CONNECTING, CONNECTED |
| `OrderStateMachine` | `order_state_machine.py:111` | State machine برای lifecycle سفارش |
| `ManagedOrder` | `order_state_machine.py:71` | سفارش با full metadata |
| `OrderState` | `order_state_machine.py:32` | PENDING→SUBMITTED→FILLING→FILLED→CLOSING→CLOSED |
| `FailureRecoveryEngine` | `failure_recovery.py:53` | بازیابی سفارشات شکست‌خورده |
| `FailedOrder` | `failure_recovery.py:42` | سفارش شکست‌خورده با metadata |
| `RecoveryStrategy` | `failure_recovery.py:31` | RETRY, DEAD_LETTER, IGNORE |
| `SemiAutoHandler` | `semi_auto.py` | تأیید دستی معاملات |
| `OrderJournal` | `order_journal.py` | Audit trail سفارشات |

### 4.4 agents/

| کلاس | فایل | وزن | حق وتو |
|------|------|-----|--------|
| `BaseAgent` | `base_agent.py:29` | - | - |
| `VotingEngine` | `voting_engine.py:116` | - | - |
| `AgentService` | `agent_service.py:53` | - | - |
| `VoteResult` | `base_agent.py:15` | - | - |
| `VoteDecision` | `voting_engine.py:35` | - | - |
| `MarketStructureAgent` | `market_structure_agent.py` | 0.20 | خیر |
| `LiquidityAgent` | `liquidity_agent.py` | 0.15 | خیر |
| `SMCAgent` | `smc_agent.py` | 0.20 | خیر |
| `AIPredictionAgent` | `ai_prediction_agent.py` | 0.20 | خیر |
| `RiskAgent` | `risk_agent.py` | 0.15 | **بله** |
| `NewsAgent` | `news_agent.py` | 0.05 | خیر |
| `ExecutionAgent` | `execution_agent.py` | 0.05 | خیر |
| `SecurityAIAgent` | `security_ai_agent.py` | N/A | N/A |

### 4.5 analysis/

| کلاس | فایل | نقش |
|------|------|-----|
| `DecisionEngine` | `decision_engine.py` | موتور تصمیم 6 مرحله‌ای |
| `SMCEngine` | `smc_engine.py` | Smart Money Concepts (3077 خط) |
| `PriceActionEngine` | `price_action_engine.py` | تحلیل price action |
| `SessionManager` | `session_manager.py` | مدیریت سشن‌های بازار |

### 4.6 intelligence/

| کلاس | فایل | نقش |
|------|------|-----|
| `MLEngine` | `ml_engine.py:128` | XGBoost + RF + LR ensemble |
| `MLPrediction` | `ml_engine.py:29` | نتیجه پیش‌بینی ML |
| `TrainingResult` | `ml_engine.py:57` | نتیجه آموزش model |
| `ConceptDriftDetector` | `ml_engine.py:86` | تشخیص drift با ADWIN-style |
| `WalkForwardFold` | `ml_engine.py:45` | نتیجه یک fold از walk-forward CV |

### 4.7 services/

| کلاس | فایل | Singleton | نقش |
|------|------|-----------|-----|
| `TradeService` | `trade_service.py:14` | خیر | CRUD trades در Supabase |
| `SignalService` | `signal_service.py:12` | خیر | CRUD signals |
| `AuditService` | `audit_service.py:78` | بله | Audit trail async |
| `RBACService` | `rbac_service.py` | بله | Role-based access |
| `BackgroundScheduler` | `scheduler.py:38` | بله | Background tasks |
| `LicenseService` | `license_service.py` | بله | License validation |

### 4.8 middleware/

| کلاس | فایل | نقش |
|------|------|-----|
| `SecurityMiddleware` | `security.py:198` | Security headers، XSS scan، IP blocking |
| `RateLimitMiddleware` | `rate_limit.py:93` | Rate limiting با Redis/in-memory |
| `WebSocketRateLimiter` | `rate_limit.py:188` | Rate limit برای WS connections |
| `BurstAwareLimiter` | `rate_limit.py:219` | Token bucket برای burst control |

### 4.9 circuit_breaker/

| کلاس | فایل | نقش |
|------|------|-----|
| `CircuitBreaker` | `circuit_breaker.py:148` | Circuit breaker با state machine |
| `BreakerState` | `circuit_breaker.py:31` | CLOSED, OPEN, HALF_OPEN |
| `BreakerConfig` | `circuit_breaker.py:38` | تنظیمات failure threshold/timeout |
| `CircuitOpenError` | `circuit_breaker.py:300` | Exception زمان OPEN state |

### 4.10 institutional/

| کلاس | فایل | نقش |
|------|------|-----|
| `InstitutionalRiskEngine` | `risk_engine.py:37` | VaR، Sharpe، drawdown، circuit breaker |
| `PortfolioManager` | `portfolio_manager.py:51` | Equal/Risk-Parity/Kelly allocation |
| `AllocationMethod` | `portfolio_manager.py:10` | EQUAL, RISK_PARITY, KELLY, MOMENTUM |

---

## 5. تمام توابع کلیدی

### ExecutionService (execution_service.py)

| تابع | خط | ورودی | خروجی | نقش |
|------|-----|-------|-------|-----|
| `start()` | 59 | - | None | initialize MT5، OSM، FR، PR |
| `stop()` | 71 | - | None | graceful shutdown |
| `execute_signal(signal)` | 79 | `Dict[str,Any]` | `Dict[str,Any]` | نقطه ورود اصلی |
| `_pipeline(signal, sid, log)` | 90 | - | Dict | risk→lot→order→submit |
| `_run_risk(signal, log)` | 115 | - | Dict | اجرای risk assessment |
| `_create_order(signal, risk, sid)` | 137 | - | ManagedOrder | ساخت سفارش |
| `_submit(order)` | 145 | ManagedOrder | MT5OrderResult | ارسال به MT5 |
| `_retry_execute(metadata)` | 156 | Dict | bool | retry یک سفارش شکست‌خورده |
| `health()` | 175 | - | Dict | وضعیت سلامت سرویس |

### VotingEngine (voting_engine.py)

| تابع | خط | نقش |
|------|-----|-----|
| `vote(context)` | 156 | رأی‌گیری موازی از همه agents |
| `_check_risk_veto(context)` | 220 | بررسی حق وتوی Risk Agent |
| `_run_parallel_safe(agents, ctx)` | 322 | اجرای موازی با timeout |
| `_aggregate(results)` | 362 | جمع وزن‌دهی شده رأی‌ها |
| `update_weights(weight_map)` | 184 | به‌روزرسانی وزن agents |
| `enable_agent(name)` | 195 | فعال‌سازی agent |
| `disable_agent(name)` | 203 | غیرفعال‌سازی agent |

### RiskOrchestrator (risk_orchestrator.py)

| تابع | نقش |
|------|-----|
| `assess(inp)` | ارزیابی کامل ریسک (async) |
| `check(**ctx)` | بررسی تمام gate‌ها |
| `_run_equity_gate(inp, ctx)` | Gate 1: Equity protection |
| `_run_daily_gate(inp, ctx)` | Gate 2: Daily limits |
| `_run_volatility_gate(inp, ctx)` | Gate 3: Volatility |
| `_run_correlation_gate(inp, ctx)` | Gate 4: Correlation |
| `_run_exposure_gate(inp, ctx)` | Gate 5: Exposure |
| `_run_lot_gate(inp, ctx)` | Gate 6: Lot sizing |
| `get_risk_orchestrator()` | Singleton factory |

### MT5Connector (mt5_connector.py)

| تابع | خط | نقش |
|------|-----|-----|
| `initialize()` | 121 | اتصال به MT5 |
| `send_order(request)` | 242 | ارسال سفارش با lock |
| `close_position(ticket)` | 300 | بستن موقعیت |
| `health_check()` | 210 | بررسی سلامت اتصال |
| `get_positions()` | 230 | لیست موقعیت‌های باز |
| `get_account_info()` | 224 | اطلاعات حساب |
| `shutdown()` | 202 | قطع اتصال |

---

## 6. تمام API‌ها

### مسیر پایه: `/api/v1`

| Route | فایل | Method‌ها | Auth | نقش |
|-------|------|---------|------|-----|
| `/signals` | `routes/signals.py` | GET, POST, PUT | JWT | مدیریت سیگنال‌های معاملاتی |
| `/signals/receive` | `routes/signals.py` | POST | MQL5_API_TOKEN | دریافت سیگنال از EA |
| `/trades` | `routes/trades.py` | GET, POST, PUT, DELETE | JWT | مدیریت معاملات |
| `/risk/assess` | `routes/risk.py` | POST | JWT | ارزیابی ریسک |
| `/risk/circuit-breaker` | `routes/risk.py` | GET, POST | Admin | کنترل circuit breaker |
| `/agents/vote` | `routes/agents.py` | POST | JWT | رأی‌گیری agent‌ها |
| `/agents/weights` | `routes/agents.py` | GET, PUT | Admin | وزن‌دهی agents |
| `/analysis/decision` | `routes/analysis.py` | POST | JWT | تحلیل تصمیم |
| `/ai-prediction/predict` | `routes/ai_prediction.py` | POST | JWT | پیش‌بینی ML |
| `/analytics` | `routes/analytics.py` | GET | JWT | گزارش‌های تحلیلی |
| `/backtest` | `routes/backtest.py` | POST, GET | JWT | اجرای backtest |
| `/backtest-engine` | `routes/backtest_engine.py` | POST, GET | JWT | Multi-symbol backtest |
| `/dashboard` | `routes/dashboard.py` | GET | JWT | داده‌های dashboard |
| `/intelligence` | `routes/intelligence.py` | GET, POST | JWT | ML insights |
| `/learning` | `routes/learning.py` | GET, POST | JWT | self-learning control |
| `/institutional` | `routes/institutional.py` | GET, POST | JWT | institutional analytics |
| `/portfolio` | `routes/portfolio.py` | GET | JWT | portfolio analytics |
| `/reports` | `routes/reports.py` | GET | JWT | گزارش‌های معاملاتی |
| `/research` | `routes/research.py` | POST, GET | JWT | تحقیقات backtest |
| `/security-ai` | `routes/security_ai.py` | GET, POST | Admin | Security AI |
| `/self-learning` | `routes/self_learning.py` | GET, POST | JWT | self-learning |
| `/users` | `routes/users.py` | GET, POST, PUT, DELETE | JWT/Admin | مدیریت کاربران |
| `/auth/login` | `routes/auth.py` | POST | - | ورود |
| `/auth/refresh` | `routes/auth.py` | POST | - | تجدید توکن |
| `/auth/logout` | `routes/auth.py` | POST | JWT | خروج |
| `/license` | `routes/license.py` | GET, POST | JWT/Admin | مدیریت license |
| `/health` | `main.py:250` | GET | - | بررسی سلامت کامل |
| `/health/live` | `main.py:235` | GET | - | Liveness probe |
| `/health/ready` | `main.py:239` | GET | - | Readiness probe |
| `/ws/signals` | `websocket_routes.py` | WS | JWT | WebSocket سیگنال‌ها |
| `/metrics` | `observability_routes.py` | GET | - | Prometheus metrics |

---

## 7. تمام سرویس‌ها

| سرویس | فایل | Singleton | نقش |
|--------|------|-----------|-----|
| `TradeService` | `services/trade_service.py` | خیر | CRUD trades در Supabase |
| `SignalService` | `services/signal_service.py` | خیر | CRUD signals |
| `AuditService` | `services/audit_service.py` | بله | Audit trail async |
| `RBACService` | `services/rbac_service.py` | بله | Role-based access |
| `BackgroundScheduler` | `services/scheduler.py` | بله | Background tasks |
| `LicenseService` | `services/license_service.py` | بله | License validation |
| `DecisionService` | `services/decision_service.py` | خیر | Decision pipeline |
| `ThreatIntelligenceService` | `services/threat_intelligence_service.py` | بله | Threat detection |
| `SelfHealingService` | `services/self_healing_service.py` | بله | Auto-recovery |
| `RiskOrchestrator` | `risk/risk_orchestrator.py` | بله | Risk management |
| `ExecutionService` | `execution/execution_service.py` | بله | Trade execution |
| `MetricsRegistry` | `observability/metrics.py` | بله | Prometheus metrics |
| `AlertManager` | `observability/alert_manager.py` | بله | Alert routing |

---

## 8. تمام Worker‌ها (Background Tasks)

| Worker | ثبت‌کننده | Interval | نقش |
|--------|-----------|----------|-----|
| `reconciliation_loop` | `main.py` | 60s | تطبیق positions با MT5 |
| `daily_reset_loop` | `main.py` | 3600s | Reset daily limits |
| `orphan_cleanup_loop` | `main.py` | 3600s | پاکسازی orphan positions |
| `signal_cleanup_loop` | `main.py` | 300s | پاکسازی signals منقضی |
| `equity_sync_loop` | `main.py` | 30s | Sync equity با MT5 |
| `retry_loop` | `failure_recovery.py` | async queue | بازارسال سفارشات شکست‌خورده |
| `monitor_loop` | `order_state_machine.py` | 60s | بررسی timeout سفارشات |
| `flush_loop` | `audit_service.py` | 5s | Flush audit buffer به DB |
| `retraining_loop` | `self_learning/retraining_service.py` | دوره‌ای | Retrain ML models |
| `pool_monitor_loop` | `database/connection_pool_monitor.py` | 30s | مانیتور connection pool |
| `security_report_scheduler` | `security_reporting/` | daily | گزارش امنیتی روزانه |

---

## 9. تمام Agent‌ها

| Agent | فایل | وزن | ورودی | خروجی | وتو؟ |
|-------|------|-----|-------|-------|------|
| `MarketStructureAgent` | `market_structure_agent.py` | 0.20 | OHLCV + symbol | VoteResult | خیر |
| `LiquidityAgent` | `liquidity_agent.py` | 0.15 | OHLCV + positions | VoteResult | خیر |
| `SMCAgent` | `smc_agent.py` | 0.20 | OHLCV + SMC context | VoteResult | خیر |
| `AIPredictionAgent` | `ai_prediction_agent.py` | 0.20 | features dict | VoteResult | خیر |
| `RiskAgent` | `risk_agent.py` | 0.15 | signal + portfolio | VoteResult | **بله** |
| `NewsAgent` | `news_agent.py` | 0.05 | symbol + datetime | VoteResult | خیر |
| `ExecutionAgent` | `execution_agent.py` | 0.05 | spread + session | VoteResult | خیر |
| `SecurityAIAgent` | `security_ai_agent.py` | N/A | request context | SecurityScore | N/A |

**نحوه voting:**
1. Risk Agent بررسی veto (اگر BLOCKED → همه چیز متوقف)
2. سایر agents موازی با asyncio.gather (timeout 5s)
3. Weighted sum: score = Σ(confidence × weight) برای BUY و SELL
4. اگر |BUY_w - SELL_w| < 0.01 → TIE → NO_TRADE
5. اگر winner score >= threshold (0.6) → تأیید

---

## 10. تمام مدل‌های هوش مصنوعی

| مدل | الگوریتم | فایل | هدف |
|-----|---------|------|-----|
| `direction_model` | XGBoost | `ml_engine.py` | پیش‌بینی BUY/SELL |
| `confidence_model` | Random Forest | `ml_engine.py` | سطح اطمینان |
| `risk_model` | Logistic Regression | `ml_engine.py` | سطح ریسک |
| `xgboost_main` | XGBoost | `ai_prediction/xgboost_trainer.py` | Directional prediction |
| `rl_agent` | PPO (stable-baselines3) | `institutional/rl_agent.py` | Optimal execution timing |
| `calibrated_ensemble` | CalibratedClassifierCV | `self_learning/training_pipeline.py` | Calibrated probabilities |

**Training Pipeline:**
```
TradeMemory → DatasetBuilder → TrainingPipeline → WalkForwardCV (embargo=5)
→ ConceptDriftDetector (ADWIN) → ModelManager (save/load)
```

**Trigger برای Retrain:**
- trades جدید >= threshold (پیش‌فرض 50)
- Drift Status = DRIFTED
- Win rate < 40%
- دستی از /api/v1/self-learning/retrain

---

## 11. تمام مدل‌های Database

| جدول | Migration | فیلدهای اصلی | نقش |
|------|-----------|------------|-----|
| `users` | `014_users_table.sql` | id, email, role, status | کاربران |
| `trades` | `001_initial_schema.sql` | id, user_id, signal_id, symbol, direction, lot_size, pnl | معاملات |
| `signals` | `001_initial_schema.sql` | id, user_id, symbol, direction, entry, sl, tp, status | سیگنال‌ها |
| `audit_logs` | `001_initial_schema.sql` | id, user_id, action, resource, metadata | Audit trail |
| `ml_models` | `006_ml_realism.sql` | id, model_type, version, accuracy, path | ML model registry |
| `backtest_results` | `007_phase6_backtest.sql` | id, config, metrics | نتایج backtest |
| `security_events` | `011_phase10_security.sql` | id, type, severity, ip, user_id | رویدادهای امنیتی |
| `licenses` | `initial_schema` | id, user_id, type, status, expires_at | license‌ها |
| `dead_letter_queue` | `008_phase7_execution.sql` | id, order_id, failure_reason, attempts | سفارشات شکست‌خورده |
| `threat_intelligence` | `016_phase13_14_security_ai.sql` | id, ip, threat_type, score | اطلاعات تهدید |
| `rbac_permissions` | `020_auth_hardening.sql` | id, user_id, resource, action, level | مجوزها |

---

## 12. تمام تنظیمات (Settings)

```python
class Settings(BaseSettings):  # backend/core/config.py
    # App
    ENVIRONMENT: str = "production"          # development|staging|production
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    APP_VERSION: str = "1.0.0"

    # Supabase (REQUIRED)
    SUPABASE_URL: str
    SUPABASE_KEY: str                        # service_role key
    SUPABASE_JWT_SECRET: str                 # min 32 chars

    # JWT (REQUIRED)
    JWT_SECRET_KEY: str                      # min 32 chars
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20

    # CORS (REQUIRED in production)
    ALLOWED_ORIGINS: List[str]

    # Telegram (REQUIRED)
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_ADMIN_IDS: List[int]
    TELEGRAM_WEBHOOK_SECRET: str

    # MQL5 EA (REQUIRED)
    MQL5_API_TOKEN: str

    # Risk Management
    DEFAULT_RISK_PCT: float = 1.0
    MAX_DAILY_TRADES: int = 10
    MAX_DAILY_LOSS_PCT: float = 3.0
    MAX_WEEKLY_LOSS_PCT: float = 7.0
    MAX_MONTHLY_DD_PCT: float = 15.0
    MAX_CORRELATION: float = 0.7
    MAX_TOTAL_EXPOSURE_PCT: float = 10.0

    # MT5
    MT5_LOGIN: Optional[int] = None
    MT5_PASSWORD: Optional[str] = None
    MT5_SERVER: Optional[str] = None
    MT5_EXE_PATH: Optional[str] = None
    MT5_ORDER_FILLING: str = "ORDER_FILLING_IOC"

    # Licensing (REQUIRED)
    LICENSE_SECRET: str
    LICENSE_SALT: str

    # Observability
    ENABLE_METRICS: bool = True
    SENTRY_DSN: Optional[str] = None

    # Backtest
    BACKTEST_MAX_WORKERS: int = 4
    BACKTEST_JOB_TIMEOUT: int = 300
```

---

## 13. تمام فایل‌های Config

| فایل | نقش |
|------|-----|
| `.env` | تنظیمات محیطی (از `.env.example` کپی شود) |
| `.env.example` | نمونه تمام متغیرها با توضیح |
| `pyproject.toml` | project metadata، ruff، mypy |
| `requirements.txt` | وابستگی‌های Python pinned |
| `backend/core/security_rules.json` | قوانین امنیتی (patterns، blocklist) |
| `infra/prometheus/prometheus.yml` | تنظیمات Prometheus scrape |
| `infra/prometheus/alerts.yml` | قوانین alert Prometheus |
| `infra/grafana/dashboards/galaxyvast.json` | Grafana dashboard |
| `frontend/tsconfig.json` | TypeScript config |
| `frontend/package.json` | npm dependencies |

---

## 14. تمام متغیرهای ENV

| متغیر | نوع | الزامی | پیش‌فرض | توضیح |
|-------|-----|---------|---------|-------|
| `ENVIRONMENT` | str | خیر | production | development\|staging\|production |
| `DEBUG` | bool | خیر | false | حالت debug |
| `LOG_LEVEL` | str | خیر | INFO | DEBUG\|INFO\|WARNING\|ERROR |
| `SUPABASE_URL` | str | **بله** | - | آدرس پروژه Supabase |
| `SUPABASE_KEY` | str | **بله** | - | service_role key |
| `SUPABASE_JWT_SECRET` | str | **بله** | - | JWT secret از Supabase |
| `JWT_SECRET_KEY` | str | **بله** | - | کلید JWT برنامه |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | int | خیر | 30 | مدت اعتبار access token |
| `REFRESH_TOKEN_EXPIRE_DAYS` | int | خیر | 30 | مدت اعتبار refresh token |
| `REDIS_URL` | str | خیر | redis://redis:6379/0 | آدرس Redis |
| `REDIS_PASSWORD` | str | خیر | - | رمز Redis |
| `REDIS_MAX_CONNECTIONS` | int | خیر | 20 | حداکثر connection های Redis |
| `ALLOWED_ORIGINS` | str | **بله (prod)** | - | CORS origins |
| `TELEGRAM_BOT_TOKEN` | str | **بله** | - | توکن Telegram Bot |
| `TELEGRAM_ADMIN_IDS` | str | **بله** | - | ID های admin |
| `TELEGRAM_WEBHOOK_SECRET` | str | **بله** | - | Secret برای webhook |
| `MQL5_API_TOKEN` | str | **بله** | - | توکن احراز هویت EA |
| `LICENSE_SECRET` | str | **بله** | - | کلید رمزنگاری license |
| `LICENSE_SALT` | str | **بله** | - | Salt برای hashing |
| `MT5_LOGIN` | int | خیر | - | شماره حساب MT5 |
| `MT5_PASSWORD` | str | خیر | - | رمز MT5 |
| `MT5_SERVER` | str | خیر | - | نام سرور بروکر |
| `MT5_EXE_PATH` | str | خیر | - | مسیر MetaTrader5.exe |
| `MT5_ORDER_FILLING` | str | خیر | ORDER_FILLING_IOC | نوع filling سفارش |
| `DEFAULT_RISK_PCT` | float | خیر | 1.0 | درصد ریسک پیش‌فرض |
| `MAX_DAILY_TRADES` | int | خیر | 10 | حداکثر معاملات روزانه |
| `MAX_DAILY_LOSS_PCT` | float | خیر | 3.0 | حداکثر ضرر روزانه % |
| `MAX_WEEKLY_LOSS_PCT` | float | خیر | 7.0 | حداکثر ضرر هفتگی % |
| `MAX_MONTHLY_DD_PCT` | float | خیر | 15.0 | حداکثر drawdown ماهانه % |
| `ENABLE_METRICS` | bool | خیر | true | فعال‌سازی Prometheus |
| `SENTRY_DSN` | str | خیر | - | DSN برای Sentry |
| `BACKTEST_MAX_WORKERS` | int | خیر | 4 | تعداد worker های backtest |
| `BACKTEST_JOB_TIMEOUT` | int | خیر | 300 | timeout backtest (ثانیه) |
| `API_BASE_URL` | str | خیر | http://api:8000 | آدرس API داخلی |

---

## 15. تمام Docker Files

| فایل | سرویس | Port | Memory Limit | نقش |
|------|--------|------|-------------|-----|
| `Dockerfile` | api | 8000 | 2GB | FastAPI backend |
| `Dockerfile.bot` | telegram_bot | - | 512MB | Telegram bot |
| `dashboard/Dockerfile` | dashboard | 8501 | 1GB | Streamlit dashboard |
| `frontend/Dockerfile` | frontend | - | - | Frontend |
| `docker-compose.yml` | همه | - | - | Development/Production |
| `docker-compose.prod.yml` | همه | - | - | Production overrides |

**Services در docker-compose.yml:**

| سرویس | Image | Port | Health Check |
|--------|-------|------|-------------|
| `redis` | redis:7.4-alpine | 127.0.0.1:6379 | redis-cli ping |
| `api` | build: Dockerfile | 127.0.0.1:8000 | GET /health/live |
| `telegram_bot` | build: Dockerfile.bot | - | python sys.exit(0) |
| `dashboard` | build: dashboard/Dockerfile | 127.0.0.1:8501 | GET /_stcore/health |
| `prometheus` | prom/prometheus | 127.0.0.1:9090 | - |
| `grafana` | grafana/grafana | 127.0.0.1:3000 | - |

---

## 16. تمام CI/CD Files

### `.github/workflows/ci-cd.yml`

**Jobs:**

| Job | Platform | نقش | Triggers |
|-----|---------|-----|----------|
| `backend` | ubuntu-latest | pytest + ruff + mypy + bandit | push/PR به main,develop |
| `frontend` | ubuntu-latest | ESLint + TypeScript + Build | push/PR |
| `build` | ubuntu-latest | Docker build + push GHCR | push به main و tags |
| `deploy-staging` | ubuntu-latest | SSH deploy به staging | push به develop |
| `deploy-production` | ubuntu-latest | SSH deploy به production | tags v*.*.* |

**Pipeline:**
```
push → backend tests → frontend build → docker build → deploy staging → deploy production
```

**Coverage:** minimum 60% (pytest-cov)

---

## 17. ساختار کامل پوشه‌ها

```
bot12/
├── .env.example
├── .github/workflows/ci-cd.yml
├── Dockerfile, Dockerfile.bot
├── docker-compose.yml, docker-compose.prod.yml
├── requirements.txt, pyproject.toml
├── startup_check.py
│
├── backend/
│   ├── circuit_breaker.py
│   ├── core/          (config, enums, exceptions, interfaces, deps, logger, retry, auth)
│   ├── api/           (main.py + 29 routes + websocket + health)
│   ├── risk/          (orchestrator + 7 gates: equity,daily,vol,corr,exposure,portfolio,lot)
│   ├── execution/     (service, mt5, osm, recovery, reconcile, semi_auto, journal)
│   ├── agents/        (base + voting + service + 7 agents + security)
│   ├── analysis/      (decision_engine 747L, smc_engine 3077L, price_action, session)
│   ├── intelligence/  (ml_engine, trade_memory, learning, weight_adjuster)
│   ├── ai_prediction/ (model_manager, prediction_service, feature_pipeline, xgboost)
│   ├── self_learning/ (training_pipeline, retraining, performance_tracker, dataset_gen)
│   ├── services/      (trade, signal, audit, rbac, scheduler, decision, license, session)
│   ├── database/      (connection, health, pool_monitor, query_optimizer)
│   ├── middleware/     (security, rate_limit, observability, secret_manager)
│   ├── observability/ (metrics, alert_manager, structured_logger, tracing)
│   ├── telegram/      (bot + 11 handlers + 7 routers + keyboards + alerts)
│   ├── institutional/ (risk_engine, portfolio_manager, monte_carlo, rl_agent, backtest)
│   ├── backtest_engine/ (multi_symbol, monte_carlo_adv, walk_forward_adv, optimizer)
│   ├── research/      (backtest/engine, replay/engine, walk_forward/analyzer)
│   ├── analytics/     (analytics_service, metrics_engine, report_generator)
│   ├── trading/       (anti_repaint, market_regime, walk_forward)
│   ├── security_reporting/ (report_service, scorer, scheduler, exporter)
│   ├── contracts/     (decision_contract)
│   ├── license/       (manager)
│   └── tests/         (conftest + 50+ test files)
│
├── dashboard/          (Streamlit: backtest, explainability, monte_carlo, portfolio)
├── frontend/           (React/Vue frontend)
├── mql5/               (MT5TradingEA_Complete.mq5)
├── infra/              (prometheus/ + grafana/)
└── supabase/migrations/ (25+ SQL files)
```

---

## 18. وابستگی‌های پروژه

### Core Web
| Package | Version | نقش |
|---------|---------|-----|
| `fastapi` | 0.115.0 | Web framework |
| `uvicorn[standard]` | 0.30.6 | ASGI server |
| `pydantic` | 2.9.2 | Data validation |
| `pydantic-settings` | 2.5.2 | Settings management |

### Database
| Package | Version | نقش |
|---------|---------|-----|
| `supabase` | 2.9.1 | PostgreSQL client |
| `redis` | 5.1.1 | Cache/rate limiting |
| `asyncpg` | 0.29.0 | Async PostgreSQL |

### Auth
| Package | Version | نقش |
|---------|---------|-----|
| `python-jose[cryptography]` | 3.3.0 | JWT tokens |
| `passlib[bcrypt]` | 1.7.4 | Password hashing |

### AI/ML
| Package | Version | نقش |
|---------|---------|-----|
| `torch` | 2.4.1+cpu | Deep learning |
| `numpy` | >=1.26.0,<2.0 | Numerical |
| `pandas` | >=2.2.0,<3.0 | Data manipulation |
| `scikit-learn` | 1.5.2 | ML algorithms |
| `xgboost` | 2.1.1 | Gradient boosting |
| `shap` | 0.46.0 | Explainability |
| `pandas-ta` | 0.3.14b | Technical indicators |
| `stable-baselines3` | 2.3.2 | Reinforcement learning |
| `gymnasium` | 0.29.1 | RL environment |

### Telegram
| Package | Version | نقش |
|---------|---------|-----|
| `aiogram` | 3.13.1 | Telegram bot |

### Observability
| Package | Version | نقش |
|---------|---------|-----|
| `prometheus-client` | 0.21.0 | Metrics |
| `loguru` | 0.7.2 | Logging |
| `tenacity` | 9.0.0 | Retry |

---

## 19. نحوه ارتباط ماژول‌ها با یکدیگر

### Dependency Direction (Clean Architecture)

```
core/ ← (همه از core import می‌کنند، core از هیچ‌کس import نمی‌کند)

api/ ← services/ ← database/
api/ ← core/deps.py ← execution/ ← risk/
api/ ← agents/ ← analysis/ ← intelligence/

observability/ ← (همه از observability import می‌کنند)
telegram/ ← alerts ← observability/alert_manager
```

### Data Flow کامل یک Signal

```
1. MQL5 EA (MT5) → POST /api/v1/signals/receive
   Body: {symbol, direction, entry_price, sl, tp, timeframe, signal_id}

2. SecurityMiddleware: XSS scan, IP check, security headers
   RateLimitMiddleware: 100 req/min per IP (Redis-backed)

3. routes/signals.py: JWT auth → validate input → SignalService.create_signal()

4. AgentService.vote(context) → VotingEngine:
   - Risk Agent: بررسی veto اول (اگر BLOCKED → stop)
   - 6 agents موازی (asyncio.gather, timeout=5s each)
   - Weighted aggregation → VoteResult{decision, confidence, direction}

5. ExecutionService.execute_signal(signal):
   a. Idempotency check (signal_id → _IDEMPOTENCY_STORE)
   b. RiskOrchestrator.assess(RiskInput):
      Gate1: EquityProtection.check() → halt if drawdown exceeded
      Gate2: DailyLimits.check_limits() → block if daily/weekly/monthly exceeded
      Gate3: VolatilityFilter.check() → block if ATR too high / news event
      Gate4: CorrelationFilter.check() → block if corr > 0.7 with open positions
      Gate5: ExposureControl.check() → block if total exposure > 10%
      Gate6: PortfolioRisk.check() → block if portfolio risk exceeded
      Gate7: LotSizer.calculate() → Kelly-based lot size
   c. All 7 gates PASS → proceed

6. OrderStateMachine.create_order(ManagedOrder{state=PENDING})

7. MT5Connector.send_order(MT5OrderRequest) [with self._lock]:
   → asyncio.to_thread(mt5.order_send(request))
   → MT5OrderResult{ticket, retcode, status}

8. OSM.transition(order_id, PENDING→SUBMITTED→FILLING→FILLED)

9. PositionReconciliation.run_once():
   → MT5.get_positions() vs DB → detect orphans/discrepancies

10. TradeService.create_trade() → Supabase insert

11. MetricsRegistry.trade_filled(symbol, direction, latency_s)
    AuditService.log(AuditEntry{action=TRADE_EXECUTED})
    AlertManager.fire("trade_filled") → Telegram.send_admin_message()

12. On failure: FailureRecovery.handle_failure():
    → classify: RETRY / DEAD_LETTER / IGNORE
    → RETRY: queue for retry with exponential backoff (max 3)
    → DEAD_LETTER: alert + store for manual review
```

---

## 20. خلاصه آماری

```
┌─────────────────────────────────────────────────────────┐
│           GALAXY VAST AI TRADING PLATFORM                │
│                   Project Statistics                      │
├─────────────────────────────────────────────────────────┤
│  Total Files:              429                           │
│  Python Files:             294                           │
│  Test Files:               50+                           │
│  SQL Migrations:           25+                           │
│  MQL5 Files:               1 (full EA ~2000 lines)      │
│  Lines of Code (Python):   ~45,000                      │
│  Lines of Tests:           ~4,000                       │
│                                                         │
│  API Endpoints:            35+                          │
│  Background Workers:       11                           │
│  AI Agents:                7 (voting) + 1 (security)   │
│  Risk Gates:               7                            │
│  ML Models:                6                            │
│  Database Tables:          15+                          │
│  Docker Services:          6                            │
│                                                         │
│  Architecture:  Clean Architecture + SOLID              │
│  Testing:       Unit + Integration + Security + Load    │
│  Observability: Prometheus + Grafana + Sentry + Audit   │
│  Security:      JWT + RBAC + Rate Limit + Security AI   │
└─────────────────────────────────────────────────────────┘
```

---

*گزارش از تحلیل 294 فایل Python و 135 فایل دیگر تولید شده است.*
*تاریخ: 2026-06-25 | نسخه: 1.0.0*
