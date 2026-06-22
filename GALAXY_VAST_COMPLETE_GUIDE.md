# 🌌 Galaxy Vast AI Trading Platform
## راهنمای کامل — صفر تا صد

> **نسخه:** 2.0.0 | **آخرین بروزرسانی:** ۲۲ خرداد ۱۴۰۵

---

## 📋 فهرست مطالب

1. [معرفی سیستم](#-معرفی-سیستم)
2. [ربات چه کاری انجام می‌دهد](#-ربات-چه-کاری-انجام-میدهد)
3. [معماری کلی](#-معماری-کلی)
4. [اجزای سیستم](#-اجزای-سیستم)
5. [جریان کامل معامله](#-جریان-کامل-معامله)
6. [سیستم هوش مصنوعی](#-سیستم-هوش-مصنوعی)
7. [سیستم مدیریت ریسک](#-سیستم-مدیریت-ریسک)
8. [ربات تلگرام](#-ربات-تلگرام)
9. [پنل وب](#-پنل-وب)
10. [پیش‌نیازها](#-پیشنیازها)
11. [راه‌اندازی گام به گام](#-راهاندازی-گام-به-گام)
12. [فایل .env کامل](#-فایل-env-کامل)
13. [دستورات تلگرام](#-دستورات-تلگرام)
14. [سطوح دسترسی](#-سطوح-دسترسی)
15. [مانیتورینگ و لاگ](#-مانیتورینگ-و-لاگ)
16. [بکاپ و بازیابی](#-بکاپ-و-بازیابی)
17. [رفع مشکلات رایج](#-رفع-مشکلات-رایج)
18. [سوالات متداول](#-سوالات-متداول)

---

## 🎯 معرفی سیستم

**Galaxy Vast** یک پلتفرم کامل معامله‌گری خودکار در سطح Hedge Fund است که با هوش مصنوعی، تحلیل Smart Money Concept و Price Action، معاملات را در MetaTrader 5 اجرا می‌کند.

### مشخصات کلی

| مشخصه | مقدار |
|---|---|
| زبان Backend | Python 3.11+ |
| Framework | FastAPI |
| Frontend | React 18 + TypeScript |
| پلتفرم معاملاتی | MetaTrader 5 (MQL5 EA) |
| دیتابیس | Supabase (PostgreSQL) |
| Cache | Redis 7.4 |
| ارتباطات | Telegram Bot + WebSocket |
| مانیتورینگ | Prometheus + Grafana |

---

## 🤖 ربات چه کاری انجام می‌دهد

### به طور خلاصه:

ربات به صورت **۲۴/۷** بازار فارکس/طلا/کریپتو را تحلیل می‌کند، سیگنال تولید می‌کند، ریسک را می‌سنجد و معاملات را **به طور خودکار** در MetaTrader 5 اجرا می‌کند. همه چیز از طریق **تلگرام** قابل کنترل است.

### قابلیت‌های کامل:

#### 1. تحلیل بازار (Analysis Engine)
- **SMC — Smart Money Concept:** تشخیص BOS، CHOCH، Order Block، FVG، Liquidity Sweep
- **Price Action:** Pin Bar، Engulfing، Fakey، Inside Bar، Morning Star و ۱۵ الگو دیگر
- **Multi-Timeframe:** تحلیل همزمان H4، H1، M15، M5
- **Kill Zones:** تشخیص پنجره‌های معاملاتی بهینه (London Open، NY Open)

#### 2. هوش مصنوعی (AI Engine)
- **۱۳ Agent موازی:** هر agent یک جنبه بازار را بررسی می‌کند
- **Voting Engine:** رای‌گیری از agents و confidence score نهایی
- **XGBoost Model:** پیش‌بینی جهت قیمت با ویژگی‌های استخراجی
- **Self-Learning:** بهبود مستمر بر اساس نتیجه معاملات

#### 3. مدیریت ریسک (Risk Engine)
- **۵ Gate مستقل:** هر معامله باید از ۵ فیلتر رد شود
- **Position Sizing:** محاسبه دقیق lot size بر اساس equity
- **Drawdown Protection:** توقف خودکار در صورت ضرر بیش از حد
- **Circuit Breaker:** قطع اتوماتیک در شرایط بحرانی

#### 4. اجرای معاملات (Execution Engine)
- **MT5 Connector:** اجرای مستقیم Order در MetaTrader 5
- **Order State Machine:** ردیابی کامل وضعیت هر معامله
- **Failure Recovery:** تلاش مجدد خودکار در صورت خطا
- **Semi-Auto Mode:** تایید دستی از طریق تلگرام قبل از اجرا

#### 5. کنترل و گزارش (Telegram Bot)
- کنترل کامل ربات از تلگرام
- گزارش لحظه‌ای معاملات
- هشدارهای اتوماتیک
- مدیریت کاربران و دسترسی‌ها

---

## 🏗️ معماری کلی

```
کاربر (Telegram / Web Dashboard)
           |
      Nginx (TLS + Rate Limit)
           |
    FastAPI Backend (Python)
    |         |         |
  Auth/JWT  REST API  WebSocket
    |         |         |
  Analysis  AI Agents  Risk Engine  Execution
           |
    Supabase DB + Redis
           |
    MetaTrader 5 (MQL5 EA)
```

---

## 🧩 اجزای سیستم

### 1. backend/analysis — موتور تحلیل

| فایل | وظیفه |
|---|---|
| `smc_engine.py` | تشخیص BOS، CHOCH، FVG، Order Block |
| `price_action_engine.py` | تشخیص Pin Bar، Engulfing و... |
| `smc_scoring.py` | امتیازدهی به ستاپ‌های SMC |
| `decision_engine.py` | تصمیم نهایی BUY/SELL/WAIT |

### 2. backend/agents — سیستم AI Agents

| Agent | وظیفه |
|---|---|
| `smc_agent.py` | تحلیل SMC |
| `market_structure_agent.py` | ساختار کلی بازار |
| `liquidity_agent.py` | نقدینگی و Sweep |
| `risk_agent.py` | ارزیابی ریسک |
| `ml_agent.py` | مدل یادگیری ماشین |
| `news_agent.py` | تاثیر اخبار |
| `execution_agent.py` | کیفیت اجرا |
| `ai_prediction_agent.py` | پیش‌بینی AI |
| `security_ai_agent.py` | امنیت معاملات |
| `voting_engine.py` | رای‌گیری نهایی از همه agents |

### 3. backend/risk — موتور ریسک

| فایل | وظیفه |
|---|---|
| `risk_orchestrator.py` | هماهنگ‌کننده — همه gates را اجرا می‌کند |
| `equity_protection.py` | Gate 1: محافظت از equity |
| `daily_limits.py` | Gate 2: محدودیت روزانه |
| `volatility_filter.py` | Gate 3: فیلتر نوسان |
| `correlation_filter.py` | Gate 4: همبستگی بین نمادها |
| `exposure_control.py` | Gate 5: کنترل exposure کلی |
| `lot_sizing.py` | محاسبه حجم معامله per-symbol |
| `portfolio_risk.py` | ریسک کل پورتفولیو |

### 4. backend/execution — موتور اجرا

| فایل | وظیفه |
|---|---|
| `execution_service.py` | هماهنگ‌کننده کل جریان اجرا |
| `mt5_connector.py` | اتصال به MetaTrader 5 + ارسال order |
| `order_state_machine.py` | مدیریت وضعیت (NEW→FILLED→CLOSED) |
| `failure_recovery.py` | retry خودکار + dead-letter queue |
| `position_reconciliation.py` | مقایسه MT5 با DB |
| `semi_auto.py` | حالت نیمه‌خودکار |

### 5. backend/ai_prediction — مدل یادگیری ماشین

| فایل | وظیفه |
|---|---|
| `feature_extractor.py` | استخراج 50+ ویژگی از کندل‌ها |
| `dataset_builder.py` | ساخت dataset از تاریخچه معاملات |
| `xgboost_trainer.py` | آموزش مدل XGBoost |
| `model_manager.py` | مدیریت نسخه‌های مدل |
| `prediction_service.py` | پیش‌بینی real-time |

### 6. backend/services — سرویس‌های اصلی

| فایل | وظیفه |
|---|---|
| `trade_service.py` | CRUD معاملات |
| `signal_service.py` | مدیریت سیگنال‌ها |
| `decision_service.py` | کش و ذخیره تصمیمات |
| `audit_service.py` | لاگ همه رویدادها |
| `rbac_service.py` | مدیریت نقش و دسترسی |
| `session_service.py` | مدیریت session کاربران |
| `license_service.py` | اعتبارسنجی لایسنس |
| `self_healing_service.py` | خوداصلاحی سیستم |

### 7. backend/telegram — ربات تلگرام

| فایل | وظیفه |
|---|---|
| `bot.py` | راه‌اندازی ربات aiogram |
| `handlers/` | پردازش پیام‌ها و دستورات |
| `routers/` | مسیریابی دستورات |
| `rbac.py` | کنترل دسترسی در تلگرام |
| `alerts.py` | ارسال هشدارها |
| `keyboards.py` | کیبوردهای Inline |

### 8. mql5 — Expert Advisor در MetaTrader

| فایل | وظیفه |
|---|---|
| `Experts/GalaxyVast.mq5` | EA اصلی — اجرا در MT5 |
| `Include/` | توابع کمکی |
| `Config.mqh` | تنظیمات EA |

---

## 🔄 جریان کامل معامله

```
STEP 1: دریافت داده
  MT5 EA → POST /api/v1/signals/ingest
  (symbol, timeframe, OHLCV candles)

STEP 2: تحلیل موازی (~50-200ms)
  SMC Engine: BOS/CHOCH/OB/FVG
  PA Engine: الگوهای کندلی
  Feature Extractor: 50+ ویژگی

STEP 3: رای‌گیری AI (13 Agent)
  هر agent: BUY/SELL/WAIT + confidence
  Voting Engine: تصمیم نهایی + score

STEP 4: فیلتر ریسک (5 Gate)
  Gate 1 — Equity Protection: drawdown < 8%?
  Gate 2 — Daily Limits: loss_today < max?
  Gate 3 — Volatility: spread < max_spread?
  Gate 4 — Correlation: overlap < max?
  Gate 5 — Exposure: total < max_exposure?
  همه 5 gate باید سبز باشند

STEP 5: محاسبه Lot Size
  lot = (equity * risk%) / (sl_pips * pip_value)
  pip_value per-symbol (XAUUSD=1.0, EURUSD=10.0)

STEP 6: Dedup Check
  همین signal در 30 ثانیه اخیر؟ → رد

STEP 7: Semi-Auto Check
  SEMI_AUTO_MODE=true → پیام تلگرام به ادمین
  ادمین تایید یا رد می‌کند

STEP 8: ارسال به MT5
  MT5Connector.send_order()
  retry x3 در صورت خطا

STEP 9: Order State Machine
  NEW → PENDING → FILLED → CLOSED

STEP 10: اطلاع‌رسانی
  پیام تلگرام + WebSocket dashboard + Audit Log
```

---

## 🧠 سیستم هوش مصنوعی

### XGBoost Pipeline:

```
داده خام (OHLCV)
    |
Feature Extraction (50+ ویژگی):
  RSI, MACD, BB, ATR, EMA 20/50/200
  SMC: OB strength, FVG size
  Pattern: pin bar ratio, engulfing score
  Session: London/NY/Asia
    |
XGBoost Classifier
    |
Probability: P(BUY), P(SELL), P(WAIT)
    |
Confidence Score (0.0 - 1.0)
```

### Self-Learning Loop:
```
معامله اجرا شد
    |
بسته شد (Win/Loss)
    |
نتیجه به dataset اضافه شد
    |
هر N معامله → re-train مدل
    |
مدل جدید جایگزین (اگر بهتر بود)
```

---

## 🛡️ سیستم مدیریت ریسک

### پارامترهای پیش‌فرض:

| پارامتر | پیش‌فرض | توضیح |
|---|---|---|
| `risk_per_trade` | 1% | درصد equity در هر معامله |
| `max_daily_loss` | 3% | حداکثر ضرر روزانه |
| `max_drawdown` | 8% | حداکثر drawdown کل |
| `max_open_trades` | 5 | حداکثر معاملات همزمان |
| `max_correlation` | 0.7 | حداکثر همبستگی نمادها |
| `max_spread_pips` | 3.0 | حداکثر spread مجاز |

### Circuit Breaker:
```
CLOSED (طبیعی)
  |
3 خطای متوالی
  |
OPEN (قطع)
  |
60 ثانیه
  |
HALF-OPEN (آزمایش)
  |
موفق → CLOSED
شکست → OPEN
```

---

## 📱 ربات تلگرام

### دستورات اصلی:

| دستور | کار |
|---|---|
| `/start` | خوش‌آمدگویی |
| `/status` | وضعیت کلی ربات |
| `/start_bot` | روشن کردن ربات |
| `/stop_bot` | خاموش کردن ربات |
| `/pause_bot` | مکث موقت |
| `/resume_bot` | ادامه بعد از مکث |
| `/close_all` | بستن همه معاملات باز |
| `/trades` | لیست معاملات باز |
| `/report_daily` | گزارش امروز |
| `/report_weekly` | گزارش هفتگی |
| `/winrate` | نرخ موفقیت |
| `/equity` | وضعیت حساب |
| `/risk_status` | وضعیت ریسک |
| `/settings` | تنظیمات (ADMIN) |
| `/add_user` | اضافه کردن کاربر (ADMIN) |
| `/remove_user` | حذف کاربر (ADMIN) |
| `/set_role` | تغییر نقش (ADMIN) |
| `/backup` | گرفتن بکاپ (SUPER) |

---

## 🔐 سطوح دسترسی

```
OWNER   (6) — مالک سیستم — دسترسی کامل
SUPER   (5) — مدیر ارشد
ADMIN   (4) — مدیر — مدیریت کاربران + تنظیمات
TRADER  (3) — معامله‌گر — کنترل معاملات
OPERATOR(2) — اپراتور — start/stop/pause
USER    (1) — کاربر — فقط گزارش
VIEWER  (0) — بیننده — فقط وضعیت
```

### افزودن کاربر جدید:
```
/add_user 987654321 TRADER
```

---

## 📦 پیش‌نیازها

| نیاز | مشخصه |
|---|---|
| VPS | Ubuntu 22.04, 4GB RAM, 2 vCPU, 50GB SSD |
| Python | 3.11+ |
| Docker | 24+ و Docker Compose 2.20+ |
| Git | هر نسخه‌ای |
| Supabase | اکانت رایگان (یا پولی) |
| MetaTrader 5 | نرم‌افزار MT5 از بروکر |
| Telegram Bot | از @BotFather |

---

## 🚀 راه‌اندازی گام به گام

### مرحله 1 — نصب پیش‌نیازها (Ubuntu/Linux)

```bash
# بروزرسانی سیستم
sudo apt update && sudo apt upgrade -y

# نصب Python 3.11
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# نصب Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

# نصب Git
sudo apt install -y git

# بررسی نصب‌ها
docker --version
git --version
```

**از Windows استفاده می‌کنید؟**
1. از python.org نسخه 3.11 را نصب کنید
2. از git-scm.com گیت را نصب کنید
3. از docker.com Docker Desktop را نصب کنید

---

### مرحله 2 — دانلود کد

```bash
# دانلود کد از GitHub
git clone https://github.com/sani13790000/bot12.git galaxy-vast

# ورود به پوشه پروژه
cd galaxy-vast

# بررسی ساختار پوشه‌ها
ls -la
# باید ببینید: backend/ mql5/ supabase/ .env.example README.md
```

---

### مرحله 3 — ساخت حساب Supabase

**Supabase یک دیتابیس رایگان ابری است (رایگان تا 500MB):**

1. به supabase.com بروید
2. روی "Start your project" کلیک کنید
3. با GitHub یا Email ثبت‌نام کنید
4. روی "New Project" کلیک کنید
5. نام: `galaxy-vast`
6. یک رمز قوی برای دیتابیس انتخاب کنید و ذخیره کنید!
7. Region: Frankfurt (یا نزدیک‌ترین به شما)
8. روی "Create new project" کلیک کنید (2 دقیقه صبر کنید)

**گرفتن کلیدهای API:**
1. از منوی چپ روی Settings کلیک کنید
2. روی API کلیک کنید
3. اینها را از صفحه کپی کنید:
   - Project URL -> همان SUPABASE_URL است
   - anon public -> همان SUPABASE_ANON_KEY است
   - service_role secret -> همان SUPABASE_SERVICE_KEY است

**ساخت جداول دیتابیس:**
1. از منوی چپ روی SQL Editor کلیک کنید
2. روی New Query کلیک کنید
3. فایل‌های زیر را به ترتیب اجرا کنید:

```bash
# محتوای این فایل‌ها را کپی کرده و در SQL Editor اجرا کنید:
# backend/database/migrations/schema.sql
# supabase/migrations/20260618_001_*.sql
# supabase/migrations/20260618_002_*.sql
# ... تا 20260618_012_*
```

> مهم: همه فایل‌های migrations را به ترتیب اجرا کنید!

---

### مرحله 4 — ساخت ربات تلگرام

1. در تلگرام روی @BotFather جستجو کنید
2. `/newbot` را ارسال کنید
3. نام ربات: مثلا `Galaxy Vast Trading`
4. username: مثلا `galaxyvast_yourname_bot`
5. توکن را که BotFather می‌دهد ذخیره کنید
   - مثال: `1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ`

**پیدا کردن Chat ID:**
1. @userinfobot را در تلگرام جستجو کنید
2. `/start` ارسال کنید
3. عدد Id را ذخیره کنید — همان TELEGRAM_ADMIN_IDS است

---

### مرحله 5 — تنظیم فایل .env

```bash
# کپی کردن فایل نمونه تنظیمات
cp .env.example .env

# باز کردن فایل برای ویرایش
nano .env
```

```env
# تنظیمات Supabase (از مرحله 3 بگیرید)
SUPABASE_URL=https://xxxxxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIs...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIs...

# تنظیمات تلگرام (از مرحله 4 بگیرید)
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHI...
TELEGRAM_ADMIN_IDS=123456789

# کلیدهای امنیتی (با دستور زیر بسازید)
JWT_SECRET_KEY=your-super-secret-key-min-32-chars
API_SECRET_KEY=your-api-secret-key-min-32-chars
LICENSE_SECRET_KEY=your-license-secret-key
LICENSE_SALT=your-license-salt

# تنظیمات MT5
MT5_EXE_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
MT5_LOGIN=12345678
MT5_PASSWORD=your_mt5_password
MT5_SERVER=YourBroker-Server

# تنظیمات معاملاتی
DEFAULT_SYMBOL=XAUUSD
DEFAULT_RISK_PERCENT=1.0
DEFAULT_MIN_SCORE=0.65
MAX_SPREAD_PIPS=3.0
```

**ساختن کلیدهای امنیتی:**
```bash
# برای هر کلید یک عدد تصادفی امن بسازید:
python3 -c "import secrets; print(secrets.token_hex(32))"
# هر بار اجرا کنید یک مقدار تصادفی می‌دهد — آن را کپی کنید
```

---

### مرحله 6 — نصب MetaTrader 5 (برای اجرای معاملات)

> توجه: MT5 فقط روی Windows اجرا می‌شود.

1. از metatrader5.com نرم‌افزار را نصب کنید
2. نصب کنید و با حساب بروکر وارد شوید
3. روی Tools > Options > Expert Advisors بروید:
   - تیک Allow automated trading را بزنید
   - تیک Allow DLL imports را بزنید
   - تیک Allow WebRequest for listed URL را بزنید
   - آدرس `http://localhost:8000` را اضافه کنید

**نصب EA:**
- فایل‌های `mql5/Include/MTTrading/` را به MQL5/Include/MTTrading/ کپی کنید
- فایل `mql5/Experts/MTTrading/MT5TradingEA_Complete.mq5` را به MQL5/Experts/MTTrading/ کپی کنید
- در MetaEditor فایل را باز کرده و با F7 بسازید (Compile)

---

### مرحله 7 — اجرا با Docker (پیشنهادی)

```bash
# ساخت و اجرای Docker
docker compose up -d --build

# بررسی وضعیت
docker compose ps
# باید api و bot هر دو Up باشند

# دیدن لاگ‌ها
docker compose logs -f api
```

**تست سلامت:**
```bash
curl http://localhost:8000/health
```
باید برگرداند:
```json
{"status": "healthy", "database": {"connected": true}}
```

---

### مرحله 7-b — اجرا بدون Docker

```bash
# ساختن محیط مجازی Python
python3.11 -m venv venv

# فعال کردن
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate       # Windows

# نصب کتابخانه‌ها
pip install --upgrade pip
pip install -r requirements.txt

# اجرای API
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000

# در Terminal جداگانه — اجرای تلگرام
python -m backend.telegram.bot
```

---

### مرحله 8 — تست

```bash
# تست 1: بررسی سلامت
curl http://localhost:8000/health

# تست 2: مستندات API (در مرورگر باز کنید)
http://localhost:8000/docs

# تست 3: در تلگرام
/start
# باید خوش‌آمدگویی بگوید
```

---

### مرحله 9 — اولین معامله نیمه‌خودکار

```
در تلگرام:
1. /start_bot را ارسال کنید تا ربات روشن شود
2. ربات تحلیل می‌کند — XAUUSDرا تحلیل می‌دهد
3. /confirm را ارسال کنید تا اجرا شود
4. ربات خبر می‌دهد که معامله باز شد
```

**نمونه پیام سیگنال:**
```
سیگنال XAUUSD

جهت: BUY
امتیاز: 78.5/100
اطمینان: 72.3%

ورود: 2345.50
Stop Loss: 2340.00
Take Profit: 2356.00
Risk/Reward: 1:2.1

تحلیل:
[OK] SMC: Order Block تایید شد
[OK] ML: احتمال 74% خرید
[OK] News: خبر مهمی نیست
[!] Risk: 1% سرمایه
```

---

### مرحله 10 — سطوح دسترسی

```
ADMIN   -> همه
SUPER   -> همه بجز مدیریت سرور
TRADER  -> معاملات + گزارش
OPERATOR-> کنترل ربات + گزارش
USER    -> فقط گزارش
VIEWER  -> فقط دیدن
```

**افزودن کاربر:**
```
/add_user 987654321 TRADER
```

---

### مرحله 11 — نظارت

```bash
# متریک‌ها
curl http://localhost:8000/observability/metrics/json

# هشدارها
curl http://localhost:8000/observability/alerts

# لاگ‌های Docker
docker compose logs --tail=100 api
```

---

## مدیریت مشکلات رایج

### ربات پاسخ نمی‌دهد
```bash
docker compose logs api | grep ERROR
# احتمالاً: مقادیر .env اشتباه است
# مطمئن شوید JWT_SECRET_KEY حداقل 32 کاراکتر است
```

### MT5 وصل نمی‌شود
```
بررسی کنید:
1. MT5 فقط روی Windows اجرا می‌شود
2. Auto trading فعال است
3. Allow WebRequest فعال است
4. http://localhost:8000 در لیست است
5. مقادیر MT5_LOGIN, MT5_PASSWORD, MT5_SERVER درست است
```

### تلگرام خطا می‌دهد
```bash
docker compose logs bot | grep ERROR
docker compose restart bot
# مطمئن شوید TELEGRAM_BOT_TOKEN درست است
```

### Supabase وصل نمی‌شود
```bash
# تست اتصال
curl $SUPABASE_URL/rest/v1/ -H "apikey: $SUPABASE_ANON_KEY"
# باید {} یا [] برگرداند
```

---

## ساختار فایل‌های مهم

```
galaxy-vast/
|-- backend/
|   |-- agents/          <- 7 Agent هوشمند
|   |-- analysis/        <- SMC + PA + Decision Engine
|   |-- intelligence/    <- ML Engine + Self-Learning
|   |-- backtest_engine/ <- Backtest + Monte Carlo + Walk-Forward
|   |-- execution/       <- MT5 Connector + Order State Machine
|   |-- database/        <- اتصال به Supabase
|   |-- middleware/       <- Security + Rate Limit + Observability
|   |-- observability/   <- Metrics + Logging + Alerts + Tracing
|   |-- risk/            <- Risk Engine
|   |-- analytics/       <- آنالیز معاملات
|   |-- telegram/        <- ربات تلگرام
|   |-- core/            <- Enums + Auth + Logger
|   +-- api/
|       |-- main.py      <- نقطه شروع FastAPI
|       +-- routes/      <- همه endpoint ها
|-- mql5/               <- کد MetaTrader 5
|-- supabase/
|   +-- migrations/      <- ساختار پایه داده فایل‌ها
|-- .env.example         <- نمونه تنظیمات
|-- requirements.txt     <- کتابخانه‌های Python
|-- Dockerfile
+-- docker-compose.yml
```

---

## سوالات متداول

**آیا می‌توان بدون MT5 تست کرد?**
بله — SEMI_AUTO_MODE=true تنظیم کنید. سیستم تحلیل می‌کند ولی به جای اجرا، سیگنال به تلگرام می‌فرستد.

**آیا می‌توان چند نماد را همزمان trade کرد?**
بله. برای هر نماد یک EA در MT5 نصب کنید. Correlation filter از overlap جلوگیری می‌کند.

**آیا Supabase رایگان به اندازه کافی است?**
بله — پلان رایگان 500MB فضا و کافی برای شروع است.

**آیا می‌توان ریسک را تغییر داد?**
بله. در .env مقادیر DEFAULT_RISK_PERCENT و MAX_SPREAD_PIPS را تغییر دهید.

**چطور مدل AI را re-train کنیم?**
بعد از 50+ معامله به طور خودکار re-train می‌شود. یا از `/admin` → AI → Retrain.

---

*Galaxy Vast AI Trading Platform v2.0.0*
*این سند در تاریخ ۲۲ خرداد ۱۴۰۵ تولید شد*
