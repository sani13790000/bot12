# 🌌 Galaxy Vast AI Trading Bot
## راهنمای کامل — صفر تا صد

---

# بخش اول: این ربات چه کار می‌کند؟

## به زبان ساده

**Galaxy Vast** یک ربات هوشمند معاملاتی است که:
- بازار طلا (XAUUSD) را ۲۴ ساعته رصد می‌کند
- با استفاده از هوش مصنوعی تصمیم می‌گیرد خرید کنیم یا بفروشیم
- معاملات را از طریق نرم‌افزار MetaTrader 5 انجام می‌دهد
- از طریق تلگرام شما را آگاه می‌کند
- سود و زیان را ثبت و آنالیز می‌کند

---

## جریان کاری ربات (چطور کار می‌کند؟)

```
[بازار XAUUSD]
       |
       v
[7 Agent هوشمند — موازی]
  |-- SMC Agent      <- ساختار بازار (Order Block / FVG / Liquidity)
  |-- PA Agent       <- Price Action (Pin Bar / Engulfing / Fakey)
  |-- ML Agent       <- مدل یادگیری ماشین (XGBoost)
  |-- Risk Agent     <- ارزیابی ریسک
  |-- News Agent     <- اخبار اقتصادی
  |-- Liquidity Agent<- مناطق نقدینگی
  +-- Execution Agent<- شرایط اجرا
       |
       v
[VotingEngine — رای‌گیری وزن‌دار]
  (اگر امتیاز >= 65 و اطمینان >= 50%)
       |
       v
[DecisionEngine — تصمیم نهایی]
  |-- BUY  -> معامله خرید
  |-- SELL -> معامله فروش
  +-- NO_TRADE -> بدون معامله
       |
       v
[RiskOrchestrator — محاسبه حجم لات]
       |
       v
[MT5Connector — اجرا در MetaTrader 5]
       |
       v
[Telegram — اطلاع‌رسانی به شما]
       |
       v
[Supabase DB — ذخیره همه اطلاعات]
```

---

## بخش‌های اصلی ربات

### 1. موتور تحلیل SMC (Smart Money Concept)
- تشخیص **Order Block** (بلوک‌های سفارش بانک‌ها)
- تشخیص **FVG** (Fair Value Gap)
- تشخیص **BOS/CHOCH** (شکست ساختار بازار)
- تشخیص **Liquidity Sweep** (جارو کردن نقدینگی)
- تشخیص **Breaker Block** و **Mitigation Block**
- تحلیل **Premium/Discount Zones**

### 2. موتور Price Action
- الگوهای شمعی: Pin Bar، Engulfing، Fakey، Inside Bar، Outside Bar
- الگوهای ترکیبی: Morning Star، Evening Star، Three Soldiers
- Breakout، Retest، Compression، Expansion

### 3. هوش مصنوعی (ML Engine)
- مدل **XGBoost** برای پیش‌بینی جهت بازار
- **15 فیچر** از بازار: RSI، MACD، Bollinger، ATR، حجم و...
- **Walk-Forward Validation** (اعتبارسنجی واقعی بدون lookahead bias)
- **Concept Drift Detection** (تشخیص تغییر رفتار بازار)
- آموزش خودکار هر 24 ساعت

### 4. موتور ریسک
- محدودیت ریسک روزانه (پیش‌فرض 1% سرمایه)
- محدودیت تعداد معاملات روزانه
- محاسبه خودکار **Lot Size**
- Gate یکپارچه‌سازی: اگر سرمایه کافی نباشد بدون معامله

### 5. Circuit Breaker
- اگر MT5 قطع شود معاملات متوقف می‌شود
- اگر DB قطع شود معاملات متوقف می‌شود
- بعد از 3 خطا Circuit Breaker باز می‌شود

### 6. Self-Learning Loop (یادگیری خودکار)
```
هر 24 ساعت:
  <- خواندن معاملات گذشته از DB
  <- آموزش مدل ML جدید
  <- مقایسه با مدل قدیمی
  <- اگر بهتر بود جایگزینی
```

### 7. Backtest Engine
- تست استراتژی روی داده‌های تاریخی
- محاسبه Sharpe Ratio، Sortino، Calmar، Max Drawdown
- **Monte Carlo Simulation** — 1000 سناریو
- **Walk-Forward Analysis** — تست روی داده‌های out-of-sample
- **Parameter Optimizer** — پیدا کردن بهترین تنظیمات

### 8. ربات تلگرام
```
/start_bot    -> شروع معاملات
/stop_bot     -> توقف معاملات
/pause_bot    -> مکث موقت
/resume_bot   -> ادامه
/close_all    -> بستن همه معاملات
/close_buy    -> بستن معاملات خرید
/close_sell   -> بستن معاملات فروش
/report_daily -> گزارش امروز
/report_weekly-> گزارش هفتگی
/winrate      -> نرخ موفقیت
/signals      -> سیگنال‌های فعال
/settings     -> تنظیمات
/users        -> مدیریت کاربران (admin)
/add_user     -> اضافه کردن کاربر (admin)
```

### 9. Security و امنیت
- JWT Authentication با الگوریتم HS256
- Rate Limiting: 100 درخواست در دقیقه
- محافظت از SQL Injection و XSS و Path Traversal
- Audit Log برای همه درخواست‌ها
- License Management (پلن‌های Free/Basic/Pro/Enterprise)

### 10. Observability (قابلیت مشاهده)
- **30+ متریک** (HTTP، Trade، ML، DB، MT5)
- **Structured Logging** با JSON
- **10 قانون Alert** (Circuit Breaker، MT5 قطع، Daily Loss)
- **Distributed Tracing** برای debug
- `/health` endpoint برای نظارت

---

# بخش دوم: راه‌اندازی صفر تا صد

## زمان تخمینی: 2-3 ساعت

---

## مرحله 0 — پیش‌نیازها

| چیز | چرا |
|-----|-----|
| VPS یا کامپیوتر با اینترنت | برای اجرای ربات |
| حساب Supabase (رایگان) | پایگاه داده |
| حساب در یک بروکر | برای اتصال به MT5 |
| MetaTrader 5 | نرم‌افزار معاملاتی |
| ربات تلگرام | برای کنترل ربات |
| Python 3.11+ | زبان برنامه‌نویسی |
| Docker | برای اجرای آسان (اختیاری) |
| Git | برای دانلود کد |

---

## مرحله 1 — نصب ابزارهای اولیه (Ubuntu/Linux)

```bash
# بروزرسانی سیستم
sudo apt update && sudo apt upgrade -y

# نصب Python 3.11
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# بررسی نصب Python
python3.11 --version
# باید نشان دهد: Python 3.11.x

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

**اگر از Windows استفاده می‌کنید:**
1. از python.org نسخه 3.11 را نصب کنید
2. از git-scm.com گیت را نصب کنید
3. از docker.com Docker Desktop را نصب کنید

---

## مرحله 2 — دانلود کد

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

## مرحله 3 — ساخت حساب Supabase

**Supabase یک پایگاه داده رایگان آنلاین است.**

1. به supabase.com بروید
2. روی "Start your project" کلیک کنید
3. با GitHub یا Email ثبت‌نام کنید
4. روی "New Project" کلیک کنید
5. نام: `galaxy-vast`
6. یک رمز عبور قوی برای DB بگذارید و ذخیره کنید!
7. Region: Frankfurt یا نزدیک‌ترین به شما
8. روی "Create new project" کلیک کنید (2 دقیقه صبر کنید)

**گرفتن کلیدهای API:**
1. از منوی چپ روی Settings کلیک کنید
2. روی API کلیک کنید
3. این سه مقدار را کپی کنید:
   - Project URL -> همان SUPABASE_URL است
   - anon public -> همان SUPABASE_ANON_KEY است
   - service_role secret -> همان SUPABASE_SERVICE_KEY است

**ساخت جداول پایگاه داده:**
1. از منوی چپ روی SQL Editor کلیک کنید
2. روی New Query کلیک کنید
3. فایل‌های زیر را به ترتیب شماره اجرا کنید:

```bash
# محتوای این فایل‌ها را کپی کنید و در SQL Editor اجرا کنید:
# backend/database/migrations/schema.sql
# supabase/migrations/20260618_001_*.sql
# supabase/migrations/20260618_002_*.sql
# ... تا 20260618_012_*
```

> مهم: همه فایل‌های migrations را به ترتیب شماره اجرا کنید!

---

## مرحله 4 — ساخت ربات تلگرام

1. در تلگرام @BotFather را جستجو کنید
2. `/newbot` را ارسال کنید
3. نام ربات: مثلاً `Galaxy Vast Trading`
4. username: مثلاً `galaxyvast_yourname_bot`
5. توکن را که BotFather می‌دهد ذخیره کنید
   - مثال: `1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ`

**پیدا کردن Chat ID:**
1. @userinfobot را در تلگرام جستجو کنید
2. `/start` ارسال کنید
3. عدد Id را ذخیره کنید — همان TELEGRAM_ADMIN_IDS است

---

## مرحله 5 — تنظیم فایل .env

```bash
# کپی کردن فایل نمونه
cp .env.example .env

# باز کردن برای ویرایش
nano .env
```

```env
# تنظیمات Supabase (از مرحله 3 بگیرید)
SUPABASE_URL=https://xxxxxxxxxxxxxxxx.supabase.co
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

**ساخت کلیدهای امنیتی:**
```bash
# برای هر کلید این دستور را اجرا کنید:
python3 -c "import secrets; print(secrets.token_hex(32))"
# هر بار یک عدد تصادفی می‌دهد — آن را کپی کنید
```

---

## مرحله 6 — نصب MetaTrader 5 (برای معاملات واقعی)

> توجه: MT5 فقط روی Windows کار می‌کند.

1. از metatrader5.com نرم‌افزار را دانلود کنید
2. نصب کنید و با حساب بروکر وارد شوید
3. روی Tools > Options > Expert Advisors بروید:
   - تیک Allow automated trading را بزنید
   - تیک Allow DLL imports را بزنید
   - تیک Allow WebRequest for listed URL را بزنید
   - آدرس `http://localhost:8000` را اضافه کنید

**نصب EA:**
- فایل‌های `mql5/Include/MTTrading/` را به MQL5/Include/MTTrading/ کپی کنید
- فایل `mql5/Experts/MTTrading/MT5TradingEA_Complete.mq5` را به MQL5/Experts/MTTrading/ کپی کنید
- در MetaEditor فایل را باز کنید و F7 بزنید (Compile)

---

## مرحله 7 — اجرا با Docker (پیشنهادی)

```bash
# ساخت و اجرای Docker
docker compose up -d --build

# بررسی وضعیت
docker compose ps
# باید: api و bot هر دو Up باشند

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

## مرحله 7-ب — اجرا بدون Docker

```bash
# ساخت محیط مجازی Python
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

## مرحله 8 — تست اجرا

```bash
# تست 1: بررسی سلامت
curl http://localhost:8000/health

# تست 2: مستندات API (در مرورگر)
http://localhost:8000/docs

# تست 3: در تلگرام
/start
# باید خوش‌آمد بگوید
```

---

## مرحله 9 — اولین اجرای ربات

```
در تلگرام:
1. /start_bot را ارسال کنید
2. ربات تایید می‌خواهد
3. /confirm را ارسال کنید
4. ربات شروع به تحلیل می‌کند
```

**نمونه پیام سیگنال:**
```
سیگنال جدید — XAUUSD

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

## مرحله 10 — سطح‌های دسترسی

```
ADMIN    -> همه چیز
SUPER    -> همه بجز تنظیمات سرور
TRADER   -> معاملات + گزارش
OPERATOR -> کنترل ربات + گزارش
USER     -> فقط گزارش
VIEWER   -> فقط دیدن
```

**اضافه کردن کاربر:**
```
/add_user 987654321 TRADER
```

---

## مرحله 11 — نظارت

```bash
# متریک‌ها
curl http://localhost:8000/observability/metrics/json

# هشدارها
curl http://localhost:8000/observability/alerts

# لاگ‌های Docker
docker compose logs --tail=100 api
```

---

## مشکلات رایج

### ربات شروع نمی‌شود
```bash
docker compose logs api | grep ERROR
# احتمالاً مشکل .env است
# مطمئن شوید JWT_SECRET_KEY حداقل 32 کاراکتر است
```

### MT5 وصل نمی‌شود
```
بررسی کنید:
1. MT5 روی Windows اجرا است
2. Auto trading فعال است
3. Allow WebRequest فعال است
4. http://localhost:8000 در لیست URL است
5. مقادیر MT5_LOGIN, MT5_PASSWORD, MT5_SERVER درست است
```

### تلگرام پاسخ نمی‌دهد
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

## ساختار پوشه‌ها

```
galaxy-vast/
|-- backend/
|   |-- agents/          <- 7 Agent هوشمند
|   |-- analysis/        <- SMC + PA + Decision Engine
|   |-- intelligence/    <- ML Engine + Self-Learning
|   |-- backtest_engine/ <- Backtest + Monte Carlo + Walk-Forward
|   |-- execution/       <- MT5 Connector + Order State Machine
|   |-- database/        <- اتصال به Supabase
|   |-- middleware/      <- Security + Rate Limit + Observability
|   |-- observability/   <- Metrics + Logging + Alerts + Tracing
|   |-- risk/            <- Risk Engine
|   |-- analytics/       <- آنالیز معاملات
|   |-- telegram/        <- ربات تلگرام
|   |-- core/            <- Enums + Auth + Logger
|   +-- api/
|       |-- main.py      <- نقطه شروع اصلی
|       +-- routes/      <- همه endpoint ها
|-- mql5/                <- کد MetaTrader 5
|-- supabase/
|   +-- migrations/      <- ساختار پایگاه داده
|-- .env.example         <- نمونه تنظیمات
|-- requirements.txt     <- کتابخانه‌های Python
|-- Dockerfile
+-- docker-compose.yml
```

---

## سوالات متداول

**آیا می‌توانم بدون MT5 استفاده کنم?**
بله — ربات سیگنال می‌دهد و شما دستی معامله می‌کنید.

**آیا ربات 100% سود می‌دهد?**
خیر — هیچ ربات معاملاتی 100% موفق نیست. ریسک معاملات وجود دارد.

**آیا Supabase رایگان است?**
بله — برای استفاده شخصی پلن رایگان کافی است.

**آیا می‌توانم با چند نماد معامله کنم?**
بله — Multi-Symbol Engine وجود دارد.

---

*Galaxy Vast AI Trading Platform v2.0.0*
