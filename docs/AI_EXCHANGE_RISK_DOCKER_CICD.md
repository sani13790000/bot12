# بخش‌های ۱۲ تا ۱۶ — MASTER_DOCUMENTATION.md
# Galaxy Vast AI Trading Platform

---

# 12. AI Models Documentation

> **برای مبتدی:** سیستم هوش مصنوعی مثل یک تیم تحلیلگر است که بر اساس داده‌های بازار تصمیم می‌گیرد آیا معامله انجام شود یا نه.
> **برای حرفه‌ای:** Multi-agent ensemble با XGBoost + Walk-Forward CV + Concept Drift Detection + Reinforcement Learning + Monte Carlo Risk Simulation.

---

## ۱۲.۱ معماری کلی AI

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         AI / ML PIPELINE                                        │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                     DATA LAYER                                           │   │
│  │                                                                          │   │
│  │  MT5 Raw Candles → FeaturePipeline (38 features) → TradeMemory (DB)     │   │
│  └────────────────────────────┬─────────────────────────────────────────┘   │
│                               │                                             │
│  ┌────────────────────────────▼─────────────────────────────────────────┐   │
│  │                     TRAINING LAYER                                   │   │
│  │                                                                      │   │
│  │  TradeMemory.get_samples() → TrainingPipeline                        │   │
│  │    ├─ XGBClassifier + CalibratedClassifierCV                         │   │
│  │    ├─ StratifiedKFold (5-fold) + Walk-Forward CV                     │   │
│  │    ├─ Drift Detection (PSI + KS test)                                │   │
│  │    └─ ModelManager.register_version()                                │   │
│  └────────────────────────────┬─────────────────────────────────────────┘   │
│                               │                                             │
│  ┌────────────────────────────▼─────────────────────────────────────────┐   │
│  │                     INFERENCE LAYER                                  │   │
│  │                                                                      │   │
│  │  Signal → PredictionService.predict()                                │   │
│  │    ├─ ModelManager.load_best_model(symbol) [LRU cache, 3 models]     │   │
│  │    ├─ FeaturePipeline.build_single(signal)                           │   │
│  │    ├─ model.predict_proba() [asyncio.to_thread - non-blocking]       │   │
│  │    └─ PredictionResult(probability, confidence, risk, is_tradeable)  │   │
│  └────────────────────────────┬─────────────────────────────────────────┘   │
│                               │                                             │
│  ┌────────────────────────────▼─────────────────────────────────────────┐   │
│  │                  AGENT VOTING LAYER (8 Agents)                       │   │
│  │                                                                      │   │
│  │  MLAgent ──────────────┐                                            │   │
│  │  SMCAgent ─────────────┤                                            │   │
│  │  RiskAgent ────────────┤  VotingEngine.vote()                       │   │
│  │  MarketStructureAgent ─┤  → weighted_score + confidence             │   │
│  │  NewsAgent ────────────┤  → VoteDecision: BUY/SELL/NO_TRADE         │   │
│  │  ExecutionAgent ───────┤                                            │   │
│  │  TechnicalAgent ───────┤                                            │   │
│  │  PatternAgent ─────────┘                                            │   │
│  └────────────────────────────┬─────────────────────────────────────────┘   │
│                               │                                             │
│  ┌────────────────────────────▼─────────────────────────────────────────┐   │
│  │                  SELF-LEARNING LAYER                                 │   │
│  │                                                                      │   │
│  │  TradeResult → PerformanceTracker → LearningService                 │   │
│  │    ├─ WeightAdjuster (agent weights update)                         │   │
│  │    ├─ RetrainTrigger (AUC drop / drift / sample count)              │   │
│  │    └─ ModelManager.update_active_version()                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## ۱۲.۲ مدل اصلی — XGBoost Direction Classifier

### مشخصات مدل

| ویژگی | مقدار |
|-------|-------|
| **کتابخانه** | XGBoost + scikit-learn |
| **نوع مسئله** | Binary Classification (BUY=1 / SELL=0) |
| **Calibration** | CalibratedClassifierCV (isotonic) |
| **Cross-Validation** | StratifiedKFold (5-fold) |
| **Walk-Forward** | Embargo 10 bars بین train/test |
| **درخت‌ها** | `n_estimators=500` |
| **حداکثر عمق** | `max_depth=4` |
| **نرخ یادگیری** | `learning_rate=0.05` |
| **Early Stopping** | 30 دور بدون بهبود |
| **حداقل AUC** | 0.55 (مدل رد می‌شود اگر زیر باشد) |
| **حداقل نمونه** | 50 trade |

### فایل‌های مرجع

```
backend/self_learning/training_pipeline.py   — آموزش
backend/intelligence/ml_engine.py            — engine اصلی
backend/ai_prediction/model_manager.py       — مدیریت مدل‌ها
backend/ai_prediction/prediction_service.py  — inference
backend/ai_prediction/feature_pipeline.py   — ساخت features
```

### ورودی — 38 Feature

#### گروه SMC (14 feature)
```python
"bos_detected"          # Break of Structure شناسایی شد؟
"choch_detected"        # Change of Character شناسایی شد؟
"ob_quality"            # کیفیت Order Block (0-1)
"ob_size_pips"          # اندازه Order Block به pips
"fvg_size_pips"         # اندازه Fair Value Gap
"fvg_filled_pct"        # درصد پر شدن FVG
"liquidity_swept"       # نقدینگی جارو شد؟
"sweep_type"            # نوع sweep
"premium_discount_zone" # ناحیه Premium یا Discount
"pd_score"              # امتیاز PD zone
"structure_aligned"     # ساختار هم‌راستا است؟
"mss_count"             # تعداد Market Structure Shift
"inducement_detected"   # Inducement شناسایی شد؟
"order_flow_score"      # امتیاز جریان سفارشات
```

#### گروه Price Action (8 feature)
```python
"candle_pattern_score"  # امتیاز الگوی شمع (0-1)
"candle_quality"        # کیفیت شمع
"direction_aligned"     # هم‌جهت با ترند؟
"timeframe_weight"      # وزن تایم‌فریم
"wick_ratio"            # نسبت فتیله
"body_ratio"            # نسبت بدنه شمع
"close_position"        # موقعیت بسته شدن
"engulf_strength"       # قدرت engulfing
```

#### گروه Market (8 feature)
```python
"atr_normalized"     # ATR نرمال‌شده
"spread_ratio"       # نسبت اسپرد به ATR
"volatility_score"   # امتیاز نوسان
"trend_strength"     # قدرت ترند
"adx_value"         # ADX
"rsi_14"            # RSI 14
"macd_histogram"    # MACD histogram
"bb_width_pct"      # عرض Bollinger Bands
```

#### گروه Temporal (8 feature)
```python
"session_score"              # امتیاز session فعلی
"hour_sin"                   # sin(ساعت) — circular encoding
"hour_cos"                   # cos(ساعت) — circular encoding
"day_of_week"                # روز هفته
"is_kill_zone"               # در Kill Zone هستیم؟
"minutes_to_session_open"    # دقیقه تا باز شدن session
"is_news_window"             # پنجره خبر؟
"london_ny_overlap"          # تداخل لندن/نیویورک؟
```

### خروجی — PredictionResult

```python
@dataclass
class PredictionResult:
    probability:  int        # 0-100 — احتمال موفقیت
    confidence:   int        # 0-100 — اطمینان مدل
    risk:         RiskLevel  # LOW / MEDIUM / HIGH / VERY_HIGH
    model_auc:    float      # AUC مدل فعلی (0.5-1.0)
    is_tradeable: bool       # آیا معامله توصیه می‌شود؟
    reason:       str        # دلیل متنی
    is_fallback:  bool       # آیا نتیجه fallback است؟
```

### محاسبه Confidence

```python
def _calc_confidence(raw_prob, model_auc, n_samples, confluence) -> int:
    auc_score    = max(0.0, (model_auc - 0.5) * 2.0)          # 0-1
    sample_score = min(1.0, log1p(n_samples) / log1p(10_000)) # 0-1
    conf_score   = max(0.0, min(1.0, confluence))              # 0-1
    # وزن‌بندی:
    return int((0.40 * auc_score + 0.30 * sample_score + 0.30 * conf_score) * 100)
```

### مثال استفاده

```python
from backend.ai_prediction.prediction_service import PredictionService

svc = PredictionService(min_probability=60, min_confidence=50)
result = await svc.predict(signal)

if result.is_tradeable:
    print(f"✅ معامله: احتمال={result.probability}% اطمینان={result.confidence}%")
else:
    print(f"❌ بدون معامله: {result.reason}")
```

---

## ۱۲.۳ مدیریت مدل‌ها — ModelManager

**فایل:** `backend/ai_prediction/model_manager.py`

```
ModelManager (Singleton)
    ├── _version_registry: Dict[str, List[ModelVersion]]  # symbol → versions
    ├── _cache: OrderedDict[str, _CacheEntry]             # LRU cache (max 3)
    └── _model_dir: Path                                  # مسیر ذخیره مدل‌ها
```

### متدهای کلیدی

| متد | ورودی | خروجی | توضیح |
|-----|-------|-------|-------|
| `load_best_model(symbol)` | symbol: str | model \| None | بهترین مدل active |
| `register_version(meta, model)` | ModelVersion, model | str (version) | ثبت نسخه جدید |
| `get_best_metadata(symbol)` | symbol: str | ModelVersion \| None | متادیتای بهترین مدل |
| `list_versions(symbol)` | symbol: str | List[ModelVersion] | همه نسخه‌ها |
| `evict_stale()` | — | int | حذف مدل‌های قدیمی از cache |
| `get_cache_stats()` | — | Dict | آمار cache |

### ModelVersion dataclass

```python
@dataclass
class ModelVersion:
    version:        str       # "v1.2.0"
    symbol:         str       # "EURUSD"
    model_type:     str       # "direction"
    accuracy:       float     # 0.68
    f1_score:       float     # 0.71
    n_samples:      int       # 1500
    trained_at:     datetime
    file_path:      str       # "models/EURUSD_v1.2.pkl"
    oos_accuracy:   float     # Out-of-sample accuracy
    overfit_ratio:  float     # train_acc / test_acc
    drift_score:    float     # 0.0-1.0 (بالای 0.3 → retrain)
    is_active:      bool
```

---

## ۱۲.۴ Concept Drift Detection

**فایل:** `backend/intelligence/ml_engine.py`

```python
class DriftStatus(str, Enum):
    STABLE  = "stable"    # drift_score < 0.15
    WARNING = "warning"   # 0.15 <= drift_score < 0.30
    DRIFTED = "drifted"   # drift_score >= 0.30 → retrain فوری
```

**محاسبه:**
```
drift_score = weighted average of:
  ├── PSI (Population Stability Index) برای هر feature
  ├── KS-test p-value (distribution shift)
  └── Model accuracy decay (recent 50 trades vs historical)

اگر drift_score >= 0.30:
  └── LearningService → TrainingPipeline → retrain automatic
```

---

## ۱۲.۵ Walk-Forward Cross-Validation

```
Timeline:
  [====TRAIN====][10-bar embargo][==TEST==] Fold 1
               [====TRAIN====][10-bar embargo][==TEST==] Fold 2
                            [====TRAIN====][10-bar embargo][==TEST==] Fold 3

نتیجه:
  avg_oos_accuracy   — میانگین out-of-sample accuracy
  avg_overfit_ratio  — نسبت train/test (هدف: نزدیک به 1.0)
```

---

## ۱۲.۶ Self-Learning Pipeline

**فایل:** `backend/self_learning/learning_service.py`

```
Trade نهایی می‌شود (WIN/LOSS)
    │
    ▼
PerformanceTracker.record_trade(result)
    │
    ├── Retrain Triggers:
    │   1. n_new_samples >= 100
    │   2. model_auc < 0.55
    │   3. drift_score >= 0.30
    │   4. Scheduled: هر روز ساعت ۲ صبح
    │
    ▼
TrainingPipeline.run(symbol, samples)
    ├── XGBClassifier train
    ├── Walk-Forward CV
    ├── Calibration
    ├── Quality check (AUC >= 0.55)
    └── ModelManager.register_version()

WeightAdjuster.update_weights(agent_performance)
→ VotingEngine weights updated
```

---

## ۱۲.۷ TrainingConfig — پارامترهای آموزش

```python
@dataclass
class TrainingConfig:
    n_estimators:          int   = 500
    max_depth:             int   = 4
    learning_rate:         float = 0.05
    subsample:             float = 0.8
    colsample_bytree:      float = 0.8
    min_child_weight:      int   = 5
    gamma:                 float = 0.1
    reg_alpha:             float = 0.1
    reg_lambda:            float = 1.0
    early_stopping_rounds: int   = 30
    cv_folds:              int   = 5
    test_size:             float = 0.2
    min_auc_threshold:     float = 0.55
    min_samples:           int   = 50
```

---

## ۱۲.۸ Sessions و Kill Zones (Feature Pipeline)

```python
SESSIONS = {
    "SYDNEY":   (22, 7),   # UTC
    "TOKYO":    (0,  9),
    "LONDON":   (7,  16),
    "NEW_YORK": (12, 21),
}

KILL_ZONES = {
    "LONDON_OPEN":  (7,  9),
    "NY_OPEN":      (12, 14),
    "ASIA_OPEN":    (0,  2),
    "LONDON_CLOSE": (15, 17),
}
```

---

## ۱۲.۹ Monte Carlo Risk Simulation

**فایل:** `backend/institutional/monte_carlo.py`

```python
# ۱۰,۰۰۰ سناریو برای ارزیابی ریسک
sim = MonteCarloSimulator(n_simulations=10_000)
result = await sim.run(
    win_rate=0.58, avg_rr=1.8, n_trades=100,
    initial_balance=10_000.0,
)
print(f"Probability of Ruin: {result.prob_ruin:.1%}")
print(f"Expected Drawdown (95th): {result.max_dd_p95:.1%}")
```

---

## ۱۲.۱۰ نگهداری مدل‌های AI

```bash
# وضعیت مدل‌ها
curl http://localhost:8000/api/v1/agents/status | python3 -m json.tool

# لاگ training
docker logs galaxyvast_api 2>&1 | grep "TrainingPipeline"

# Retrain دستی
curl -X POST http://localhost:8000/api/v1/learning/train \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "EURUSD", "force": true}'

# بازگشت به مدل قبلی
curl -X PUT http://localhost:8000/api/v1/learning/models/EURUSD/v1.1.0/activate \
  -H "Authorization: Bearer $TOKEN"
```

---

# 13. Exchange Integration Guide

> **برای مبتدی:** سیستم با MetaTrader 5 (MT5) صحبت می‌کند. MT5 یک نرم‌افزار معاملاتی است که به broker وصل می‌شود.
> **برای حرفه‌ای:** لایه abstraction با `IOrderBroker` Protocol — هر broker جدید فقط باید این interface را implement کند.

---

## ۱۳.۱ معماری اتصال

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     EXCHANGE INTEGRATION LAYER                           │
│                                                                          │
│   ExecutionService                                                       │
│       │                                                                  │
│       │ uses IOrderBroker (Protocol)                                     │
│       │                                                                  │
│       ├── MT5Connector ──── MetaTrader 5 Terminal ── Broker             │
│       │   (default)         (Windows/Wine/Docker)                       │
│       │                                                                  │
│       └── CustomBroker ──── Any REST/FIX/WebSocket API                  │
│           (implement IOrderBroker)                                       │
│                                                                          │
│   Circuit Breaker ──── 5 failures/60s → OPEN → halt all orders          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## ۱۳.۲ MT5 — راه‌اندازی گام به گام

```bash
# نصب Python library
pip install MetaTrader5

# تست اتصال
python3 -c "
import MetaTrader5 as mt5
mt5.initialize(login=12345678, password='pass', server='BrokerName-Server')
print(mt5.account_info())
mt5.shutdown()
"
```

### تنظیمات `.env`

```bash
MT5_EXE_PATH="C:/Program Files/MetaTrader 5/terminal64.exe"
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=BrokerName-Server
MT5_TIMEOUT=30
MT5_MAX_RETRIES=3
MT5_RETRY_DELAY=1.0
MT5_SLIPPAGE_BASE=10
MT5_SLIPPAGE_MAX=50
```

---

## ۱۳.۳ MT5Connector — Dataclass ها

**فایل:** `backend/execution/mt5_connector.py`

```python
@dataclass
class MT5OrderRequest:
    symbol:     str           # "EURUSD"
    volume:     float         # 0.10 (lot)
    order_type: str           # "BUY" یا "SELL"
    price:      float         # قیمت (0.0 برای market order)
    sl:         float         # Stop Loss price
    tp:         float         # Take Profit price
    deviation:  int  = 20     # max slippage پوینت
    magic:      int  = 234000 # شناسه ربات
    comment:    str  = ""     # توضیح (حداکثر 32 کاراکتر)
    signal_id:  str  = ""     # برای idempotency

@dataclass
class MT5OrderResult:
    success:       bool
    ticket:        Optional[int]   # شماره ticket MT5
    order_id:      str             # UUID داخلی
    volume_filled: float
    price_filled:  float
    error_code:    Optional[int]   # کد خطای MT5
    error_message: Optional[str]
    latency_ms:    float           # زمان ارسال
    retries_used:  int
```

### متدهای اصلی

| متد | ورودی | خروجی | توضیح |
|-----|-------|-------|-------|
| `initialize()` | — | `bool` | اتصال به MT5 |
| `send_order(request)` | `MT5OrderRequest` | `MT5OrderResult` | ارسال order |
| `close_position(ticket, volume)` | `int`, `float` | `bool` | بستن position |
| `get_positions()` | — | `List[MT5Position]` | همه positions باز |
| `health_check()` | — | `bool` | بررسی اتصال |
| `shutdown()` | — | `None` | قطع اتصال |

### جریان ارسال Order

```
send_order(request)
    ├── [Lock] asyncio.Lock (thread-safe)
    ├── validate request
    ├── asyncio.wait_for(timeout=30s)
    │       └── asyncio.to_thread()  ← MT5 blocking API
    │               └── mt5.order_send(request_dict)
    ├── [Success] → MT5OrderResult(success=True, ticket=...)
    └── [Failure] → retry (max 3) → MT5OrderResult(success=False)
```

### مثال استفاده

```python
from backend.execution.mt5_connector import MT5Connector, MT5OrderRequest

connector = MT5Connector(timeout_seconds=30, max_retries=3)
await connector.initialize()

request = MT5OrderRequest(
    symbol="EURUSD", volume=0.10, order_type="BUY",
    price=0.0, sl=1.0850, tp=1.0950, comment="GV_AI_001",
)
result = await connector.send_order(request)
if result.success:
    print(f"Ticket: {result.ticket} | Fill: {result.price_filled}")
```

---

## ۱۳.۴ کدهای خطای MT5

| کد | معنی | راه حل |
|----|------|--------|
| `10004` | Requote | `deviation` را افزایش دهید |
| `10006` | Request rejected | بررسی leverage و margin |
| `10009` | Request executed | موفق |
| `10014` | Invalid volume | `lot_step` را بررسی کنید |
| `10018` | Market is closed | خارج از ساعت معامله |
| `10019` | Insufficient funds | موجودی ناکافی |
| `10030` | Too frequent requests | throttle کنید |

---

## ۱۳.۵ IOrderBroker — Interface برای Broker سفارشی

**فایل:** `backend/core/interfaces.py`

```python
@runtime_checkable
class IOrderBroker(Protocol):
    async def send_order(self, request: Any) -> Any: ...
    async def close_position(self, ticket: int, volume: float) -> bool: ...
    async def get_positions(self) -> List[Any]: ...
    async def health_check(self) -> bool: ...
    async def initialize(self) -> bool: ...
    async def shutdown(self) -> None: ...
```

### پیاده‌سازی Broker سفارشی

```python
class MyCustomBroker:
    """هر broker با پیاده‌سازی IOrderBroker قابل استفاده است."""

    async def initialize(self) -> bool:
        self._session = aiohttp.ClientSession(
            base_url="https://api.mybroker.com",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        return True

    async def send_order(self, request) -> Any:
        payload = {"symbol": request.symbol, "side": request.order_type,
                   "quantity": request.volume, "type": "MARKET"}
        async with self._session.post("/v1/orders", json=payload) as resp:
            data = await resp.json()
            return {"success": resp.status == 201, "ticket": data.get("orderId")}

    async def close_position(self, ticket: int, volume: float) -> bool:
        async with self._session.delete(f"/v1/positions/{ticket}") as resp:
            return resp.status == 200

    async def get_positions(self) -> list:
        async with self._session.get("/v1/positions") as resp:
            return await resp.json()

    async def health_check(self) -> bool:
        async with self._session.get("/v1/ping") as resp:
            return resp.status == 200

    async def shutdown(self) -> None:
        await self._session.close()
```

---

## ۱۳.۶ MQL5 Expert Advisor

**فایل:** `mql5/Experts/GalaxyVast_EA.mq5`

```
MT5 Terminal
    └── GalaxyVast_EA.mq5
            │ POST /api/v1/signals
            ▼
        Galaxy Vast Backend
            └── ExecutionService → MT5Connector → MT5 Terminal
```

### نصب EA

```
1. فایل .mq5 را در MQL5/Experts/ کپی کنید
2. در MT5: File → Open Data Folder → MQL5/Experts/
3. Compile (F7)
4. روی chart مناسب attach کنید
5. تنظیمات: API_URL، API_KEY، MAGIC=234000
```

---

# 14. Risk Management System

> **برای مبتدی:** سیستم ریسک مثل یک دربان است که قبل از هر معامله ۷ بررسی انجام می‌دهد.
> **برای حرفه‌ای:** Pipeline از ۷ gate با Fail-Safe/Fail-Close mode، Circuit Breaker ۳-حالته، Semi-Auto override.

---

## ۱۴.۱ نمودار کامل Risk Pipeline

```
Signal دریافت می‌شود
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        RISK ORCHESTRATOR                                │
│                                                                         │
│  Gate 1: EquityProtectionEngine ── Drawdown > 5%?       → BLOCKED      │
│          │                         Daily Loss > 3%?     → BLOCKED      │
│          │                         Consecutive Loss > 3? → BLOCKED     │
│          ▼                                                              │
│  Gate 2: DailyLimitsEngine ──────  Trades today >= 10?  → BLOCKED      │
│          │                         Weekly loss > 7%?    → BLOCKED      │
│          ▼                                                              │
│  Gate 3: NewsFilterGate ─────────  HIGH news ±30min?    → BLOCKED      │
│          │                         MED news ±15min?     → BLOCKED      │
│          ▼                                                              │
│  Gate 4: VolatilityFilter ───────  ATR > threshold?     → BLOCKED      │
│          │                         Spread > 3×ATR?      → BLOCKED      │
│          ▼                                                              │
│  Gate 5: CorrelationFilter ──────  Correlation > 0.6?   → REDUCE       │
│          │                         Same dir + corr?     → BLOCK        │
│          ▼                                                              │
│  Gate 6: ExposureControlEngine ── Total > 5%?           → BLOCKED      │
│          │                         Per-symbol > 2%?     → BLOCKED      │
│          ▼                                                              │
│  Gate 7: PortfolioRisk ──────────  Portfolio VaR?        → BLOCK/WARN  │
│                                                                         │
│          ▼                                                              │
│  [ALL PASSED] → LotSizer.calculate() → ExecutionService                │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## ۱۴.۲ Gate 1 — Equity Protection

**فایل:** `backend/risk/equity_protection.py`

```python
@dataclass
class EquityProtectionConfig:
    max_drawdown_percent:   float = 5.0   # حداکثر drawdown کل
    max_daily_loss_pct:     float = 3.0   # حداکثر ضرر روزانه
    max_weekly_loss_pct:    float = 7.0   # حداکثر ضرر هفتگی
    max_consecutive_losses: int   = 3     # حداکثر ضرر متوالی
    warning_drawdown_pct:   float = 3.0   # سطح هشدار
    cooldown_minutes:       int   = 60    # زمان cooldown
```

### حالت‌های Protection

| حالت | معنی |
|------|------|
| `SAFE` | معامله آزاد است |
| `WARNING` | معامله مجاز با هشدار (drawdown 3-5%) |
| `HALTED` | معامله متوقف (cooldown_minutes دقیقه) |

```python
engine = EquityProtectionEngine()
engine.initialize(initial_balance=10_000.0)
engine.update_equity(equity=9_600.0, balance=10_000.0)  # 4% drawdown
result = engine.check()
# result.can_trade = True (زیر 5%)
# result.level = WARNING
```

---

## ۱۴.۳ Gate 2 — Daily Limits

**فایل:** `backend/risk/daily_limits.py`

| پارامتر | پیش‌فرض | توضیح |
|---------|---------|-------|
| `max_daily_trades` | 10 | حداکثر معاملات در روز |
| `max_daily_loss_pct` | 3.0 | حداکثر ضرر روزانه (٪) |
| `max_weekly_loss_pct` | 7.0 | حداکثر ضرر هفتگی |
| `max_monthly_dd_pct` | 15.0 | حداکثر drawdown ماهانه |

---

## ۱۴.۴ Gate 3 — News Filter

**فایل:** `backend/risk/news_filter.py`

```python
@dataclass(frozen=True)  # immutable
class NewsEvent:
    title:      str
    currency:   str          # "USD"
    impact:     NewsImpact   # HIGH / MEDIUM
    event_time: datetime     # UTC
```

| Impact | Blackout Window |
|--------|----------------|
| `HIGH` | ±30 دقیقه |
| `MEDIUM` | ±15 دقیقه |

```python
gate = NewsFilterGate(
    pre_blackout_minutes=30, post_blackout_minutes=30,
    min_impact=NewsImpact.HIGH, blocked_currencies={"USD", "EUR", "GBP"},
)
gate.load_events(events)
result = gate.check(symbol="EURUSD", now=datetime.now(UTC))
```

---

## ۱۴.۵ Gate 5 — Correlation Filter

**فایل:** `backend/risk/correlation_filter.py`

### جدول Static Correlation

| جفت ارز | Correlation |
|---------|------------|
| EURUSD ↔ GBPUSD | 0.85 (بسیار بالا) |
| EURUSD ↔ USDJPY | -0.72 (منفی قوی) |
| GBPUSD ↔ GBPJPY | 0.78 (بالا) |
| AUDUSD ↔ NZDUSD | 0.80 (بالا) |

### قوانین
```
Correlation > 0.6 با positions باز:
  └── ریسک کاهش می‌یابد (penalty)
      اگر > max_correlated_exposure:
          └── BLOCKED
```

---

## ۱۴.۶ Gate 6 — Exposure Control

**فایل:** `backend/risk/exposure_control.py`

| پارامتر | پیش‌فرض | توضیح |
|---------|---------|-------|
| `max_total_exposure_percent` | 5.0 | حداکثر ریسک کل (٪ balance) |
| `max_per_symbol_percent` | 2.0 | حداکثر ریسک هر symbol |
| `max_per_currency_percent` | 3.0 | حداکثر ریسک هر currency |
| `block_same_symbol_same_direction` | True | بلاک duplicate trades |

---

## ۱۴.۷ LotSizer — فرمول Kelly

**فایل:** `backend/risk/lot_sizing.py`

```
Kelly Fraction = (win_rate × avg_rr - (1 - win_rate)) / avg_rr
Kelly Lot = (balance × kelly_fraction × kelly_scale) / (sl_pips × pip_value)

مثال:
  Balance: $10,000 | win_rate: 0.58 | avg_rr: 1.8
  Kelly Fraction = (0.58×1.8 - 0.42) / 1.8 = 0.348
  sl_pips: 20 | pip_value: $1.0/lot
  Kelly Lot = (10000 × 0.348 × 0.5) / (20 × 1.0) = 87 lots
  → clip به max_lot=0.5 → 0.50 lots
```

```python
result = await sizer.calculate(
    balance=10_000.0, stop_loss_pips=20.0, symbol="EURUSD",
    win_rate=0.58, avg_rr=1.8,
)
print(f"Lot: {result.lot_size}")     # 0.05
print(f"Risk: ${result.risk_usd}")  # $10.00
```

---

## ۱۴.۸ Circuit Breaker — State Machine

**فایل:** `backend/circuit_breaker.py`

```
    CLOSED ──(5 failures/60s)──► OPEN
    CLOSED ◄──(3 success probe)── HALF_OPEN
    OPEN   ──(120s timeout)──► HALF_OPEN
```

```python
@dataclass
class BreakerConfig:
    failure_threshold:    int   = 5      # failures برای OPEN
    failure_window_s:     float = 60.0   # پنجره زمانی
    recovery_timeout_s:   float = 120.0  # قبل از HALF_OPEN
    half_open_max_calls:  int   = 3      # probe calls
    success_threshold:    int   = 3      # success برای CLOSED
```

```python
cb = await get_breaker("mt5", BreakerConfig(failure_threshold=5))
async with cb:   # اگر OPEN → raise CircuitOpenError
    result = await mt5.send_order(request)
```

### Halt دستی

```bash
# Halt
curl -X POST http://localhost:8000/api/v1/risk/halt \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"reason": "Manual halt"}'

# Resume
curl -X POST http://localhost:8000/api/v1/risk/resume \
  -H "Authorization: Bearer $TOKEN"
```

---

## ۱۴.۹ Semi-Auto Mode

```
Signal → Risk Gates → [PASSED] → Telegram:
  "EURUSD BUY | Score: 82% | Lot: 0.10 | SL: 20p | TP: 36p
   [✅ تأیید] [❌ رد] [⏰ 5 دقیقه]"
         │
         ├── تأیید → ExecutionService.execute()
         ├── رد    → Signal.status = REJECTED
         └── Timeout → Signal.status = EXPIRED
```

```bash
# .env
SEMI_AUTO_MODE=true
SEMI_AUTO_TIMEOUT=300  # ثانیه
```

---

## ۱۴.۱۰ RiskOrchestrator — نقطه ورود اصلی

**فایل:** `backend/risk/risk_orchestrator.py`

```python
orchestrator = await get_risk_orchestrator()  # Singleton

result = await orchestrator.assess(RiskInput(
    symbol="EURUSD", direction="BUY",
    signal_score=82.0, account_balance=10_000.0,
    account_equity=9_800.0,
    today_trades=TodayTrades(count=3, pnl_usd=150.0),
    open_positions=[...],
))

if result.approved:
    print(f"Approved | Lot: {result.lot_size} | Score: {result.risk_score}")
else:
    print(f"Blocked: {result.blocked_by} | {result.reason}")
```

---

# 15. Docker Guide

> **برای مبتدی:** Docker مثل یک جعبه است که همه چیز داخل خودش دارد.
> **برای حرفه‌ای:** Multi-service Compose با resource limits، health checks، non-root user، multi-stage build.

---

## ۱۵.۱ سرویس‌های Docker

| سرویس | Image | Port | RAM | CPU | وابستگی |
|--------|-------|------|-----|-----|----------|
| `redis` | `redis:7.4-alpine` | 6379 | 768M | 0.5 | — |
| `api` | از `Dockerfile` | 8000 | 2G | 2.0 | redis |
| `telegram_bot` | از `Dockerfile.bot` | — | 512M | 1.0 | api |
| `dashboard` | از `dashboard/Dockerfile` | 8501 | 1G | 1.0 | api |
| `frontend` | از `frontend/Dockerfile` | 3000 | 256M | 0.5 | api |

---

## ۱۵.۲ Dockerfile — Multi-Stage Build

```dockerfile
# ──── Stage 1: Builder ─────────────────────────────────────────────────
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# ──── Stage 2: Runtime ────────────────────────────────────────────────
FROM python:3.11-slim AS runtime
LABEL version="2.0.0"
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY --from=builder /install /install

# کاربر غیر root (Security)
RUN groupadd -r galaxyvast && useradd -r -g galaxyvast -d /app galaxyvast
WORKDIR /app
COPY backend/ /app/backend/
RUN mkdir -p /app/logs /app/models && chown -R galaxyvast:galaxyvast /app
USER galaxyvast

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--timeout-graceful-shutdown", "30"]
```

---

## ۱۵.۳ شبکه Docker

```yaml
networks:
  galaxyvast_net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/24
# همه سرویس‌ها در یک subnet ایزوله
# فقط پورت‌های لازم به 127.0.0.1 باند می‌شوند (نه 0.0.0.0)
```

---

## ۱۵.۴ دستورات اصلی Docker

### راه‌اندازی

```bash
# ساخت و راه‌اندازی
docker compose up --build -d

# فقط API و Redis
docker compose up --build -d api redis

# وضعیت
docker compose ps
```

### لاگ‌ها

```bash
docker compose logs api -f                  # realtime
docker compose logs api --timestamps -f    # با timestamp
docker compose logs api --tail=100          # آخرین 100 خط
```

### مدیریت

```bash
# ری‌استارت
docker compose restart api

# توقف
docker compose stop
docker compose down         # containers حذف (نه volumes)
docker compose down -v      # همه چیز حذف (شامل volumes!)

# shell در container
docker compose exec api bash

# مصرف منابع
docker stats
```

### بروزرسانی

```bash
git pull
docker compose build --no-cache api
docker compose up -d api
docker compose logs api -f
```

---

## ۱۵.۵ Health Checks

```bash
# Liveness
curl http://localhost:8000/health/live
# {"status": "ok"}

# Readiness
curl http://localhost:8000/health/ready
# {"status": "ready", "checks": {"redis": "ok", "database": "ok"}}

# Deep Health
curl http://localhost:8000/health/deep | python3 -m json.tool
```

---

## ۱۵.۶ Volumes و Backup

```bash
# backup Redis
docker compose exec redis redis-cli -a $REDIS_PASSWORD BGSAVE
docker cp bot12-redis-1:/data/dump.rdb ./backup/redis_$(date +%Y%m%d).rdb

# backup logs
docker cp bot12-api-1:/app/logs ./backup/logs_$(date +%Y%m%d)/
```

---

# 16. CI/CD Guide

> **برای مبتدی:** هر بار که کد push می‌کنید، سیستم خودکار آن را تست می‌کند.
> **برای حرفه‌ای:** GitHub Actions با 5 job، matrix testing، Docker layer caching، zero-downtime deployment.

---

## ۱۶.۱ نمودار Pipeline

```
Git Push / PR
      │
      ▼
┌──────────────────────────────────────────────────────────┐
│              GITHUB ACTIONS PIPELINE                     │
│                                                          │
│  Job 1: lint     Job 2: test    Job 3: security         │
│  black --check   pytest 249     bandit -r backend/       │
│  isort --check   coverage >=80  safety check             │
│  flake8          matrix:3.11/12                          │
│       └──────────────┴──────────────┘                    │
│                      │                                   │
│  Job 4: build        │      Job 5: deploy               │
│  docker build        │      SSH → server                │
│  docker push         │      git pull                    │
│  trivy scan          │      docker compose up           │
│                      │      health check verify         │
└──────────────────────────────────────────────────────────┘
```

---

## ۱۶.۲ GitHub Actions Workflow

**فایل:** `.github/workflows/ci.yml`

```yaml
name: Galaxy Vast CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11", cache: pip}
      - run: pip install black isort flake8 mypy && pip install -r requirements.txt
      - run: black --check backend/
      - run: isort --check-only backend/
      - run: flake8 backend/ --max-line-length=100
      - run: mypy backend/ --ignore-missing-imports

  test:
    runs-on: ubuntu-latest
    needs: lint
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "${{ matrix.python-version }}", cache: pip}
      - run: pip install -r requirements.txt pytest pytest-asyncio pytest-cov
      - run: |
          pytest backend/tests/ --timeout=120 \
            --cov=backend --cov-report=xml --cov-fail-under=80 -v
        env:
          OTEL_SDK_DISABLED: "true"
          ENVIRONMENT: "testing"
          SUPABASE_URL: "https://test.supabase.co"
          SUPABASE_SERVICE_KEY: "test_key"
          JWT_SECRET_KEY: "test-secret-key-minimum-32-characters!!"

  security:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - run: pip install bandit safety
      - run: bandit -r backend/ -ll -x backend/tests/
      - run: safety check -r requirements.txt

  build:
    runs-on: ubuntu-latest
    needs: [test, security]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - uses: aquasecurity/trivy-action@master
        with:
          image-ref: ghcr.io/${{ github.repository }}:latest
          severity: CRITICAL,HIGH
          exit-code: 1

  deploy:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main'
    environment: production
    steps:
      - uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/galaxyvast
            git pull origin main
            docker compose pull
            docker compose up -d --no-deps api
            sleep 15
            curl -f http://localhost:8000/health/ready || exit 1
```

---

## ۱۶.۳ GitHub Secrets

```
Settings → Secrets and variables → Actions:

  SERVER_HOST      — IP سرور
  SERVER_USER      — username SSH
  SSH_PRIVATE_KEY  — محتوای ~/.ssh/id_rsa
```

---

## ۱۶.۴ بررسی Local قبل از Push

```bash
# formatting
black --check backend/
isort --check-only backend/

# types
mypy backend/ --ignore-missing-imports

# tests
OTEL_SDK_DISABLED=true pytest backend/tests/ -v

# security
bandit -r backend/ -ll

# docker
docker build -t galaxyvast:test .
```

---

## ۱۶.۵ Branch Strategy

```
main        ── production (protected)
  ├── develop        ── integration
  │     ├── feature/new-agent
  │     ├── fix/correlation-bug
  │     └── docs/update-readme
  └── hotfix/critical ── فقط برای critical bugs
```

### قوانین PR

```
✅ حداقل 1 review تأیید
✅ همه CI jobs موفق
✅ Coverage کاهش نیافته
✅ Branch از main/develop up-to-date
```

---

## ۱۶.۶ Rollback

```bash
ssh user@server
cd /opt/galaxyvast

# آخرین commits
git log --oneline -5

# برگشت به commit موفق
git checkout <commit_sha>
docker compose build api
docker compose up -d api
curl -f http://localhost:8000/health/ready
```

---

## ۱۶.۷ Monitoring Pipeline

```bash
# وضعیت pipeline
gh run list --repo sani13790000/bot12 --limit 5

# جزئیات آخرین run
gh run view --log

# لاگ job خاص
gh run view --job=test --log
```

---

*بخش‌های بعدی: 17. Development Guide — 18. Debugging Guide — 19. Backup & Recovery — 20. Update Guide — 21. Troubleshooting — 22. FAQ — 23. Production Deployment — 24. Security — 25. Maintenance*
