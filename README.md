# 🤖 MT5 Trading OS — اکوسیستم معاملاتی حرفه‌ای

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python)
![MQL5](https://img.shields.io/badge/MQL5-MetaTrader5-orange?style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?style=for-the-badge&logo=fastapi)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue?style=for-the-badge&logo=telegram)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-darkgreen?style=for-the-badge&logo=supabase)
![Docker](https://img.shields.io/badge/Docker-Compose-blue?style=for-the-badge&logo=docker)

**سیستم معاملاتی هوشمند مبتنی بر Smart Money Concept + Price Action + Decision Engine**

</div>

---

## 📋 فهرست مطالب

- [معماری سیستم](#معماری-سیستم)
- [پیش‌نیازها](#پیش‌نیازها)
- [راه‌اندازی سریع](#راه‌اندازی-سریع)
- [راه‌اندازی دستی](#راه‌اندازی-دستی)
- [تنظیم MQL5](#تنظیم-mql5)
- [دستورات تلگرام](#دستورات-تلگرام)
- [ساختار پروژه](#ساختار-پروژه)
- [API Endpoints](#api-endpoints)
- [سطوح دسترسی](#سطوح-دسترسی)
- [عیب‌یابی](#عیب‌یابی)

---

## 🏗️ معماری سیستم

```
MT5 Terminal (MQL5)
      │
      │ WebRequest (JSON)
      ▼
FastAPI Server (:8000)
      │
      ├── SMC Engine       ← Smart Money Concept (19 مفهوم)
      ├── Price Action     ← 14 الگو با امتیازدهی
      ├── Decision Engine  ← Pipeline 6 مرحله‌ای
      │
      ├── Telegram Bot     ← دستورات + هشدارها
      ├── Supabase DB      ← 10 جدول + RLS
      └── License System   ← اعتبارسنجی آنلاین
```

**جریان معامله:**
```
MT5 OnTimer (5s) → POST /api/v1/decision/{symbol}
                → Decision Engine (6 stages)
                → BUY/SELL/NO_TRADE + SL/TP/Lot
                → MT5 ExecutionEngine → SendOrder
                → Telegram Alert → کاربر
```

---

## ⚙️ پیش‌نیازها

| ابزار | نسخه | کاربرد |
|---|---|---|
| Python | 3.11+ | Backend + Telegram Bot |
| MetaTrader 5 | Build 3000+ | اجرای معاملات |
| Docker + Compose | Latest | اجرای سریع |
| Supabase | Cloud/Self-hosted | دیتابیس |
| Git | Latest | مدیریت کد |

---

## 🚀 راه‌اندازی سریع (Docker — توصیه‌شده)

### مرحله ۱ — دریافت کد

```bash
git clone https://github.com/sani13790000/bot12.git
cd bot12
```

### مرحله ۲ — تنظیم متغیرهای محیطی

```bash
cp .env.example .env
nano .env
```

**حداقل تنظیمات اجباری:**

```env
# ─── Telegram ──────────────────────────────────
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_ADMIN_IDS=123456789,987654321

# ─── Supabase ──────────────────────────────────
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# ─── Security ──────────────────────────────────
SECRET_KEY=your-super-secret-key-min-32-chars-long
LICENSE_SECRET=your-license-secret-key

# ─── App ───────────────────────────────────────
ENVIRONMENT=production
DEBUG=false
```

**تولید SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### مرحله ۳ — اجرا با Docker

```bash
docker compose up -d --build
```

### مرحله ۴ — تأیید سلامت سیستم

```bash
# بررسی وضعیت container ها
docker compose ps

# بررسی سلامت API
curl http://localhost:8000/health

# مشاهده لاگ‌ها
docker compose logs -f api
docker compose logs -f bot
```

**پاسخ موفق:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "api": "healthy",
    "database": "healthy"
  }
}
```

### مرحله ۵ — تنظیم دیتابیس

در **Supabase Dashboard** → **SQL Editor** این دستور را اجرا کنید:

```bash
# از طریق Supabase CLI:
npx supabase db push

# یا محتوای این فایل را در SQL Editor اجرا کنید:
# supabase/migrations/20260612155742_001_initial_schema.sql
```

### مرحله ۶ — اضافه کردن OWNER اول

در **Supabase SQL Editor**:
```sql
-- YOUR_TELEGRAM_ID را با Telegram ID خود جایگزین کنید
INSERT INTO user_profiles (telegram_id, role, is_active)
VALUES (YOUR_TELEGRAM_ID, 'owner', true)
ON CONFLICT (telegram_id) DO UPDATE SET role = 'owner';
```

**دریافت Telegram ID:** به [@userinfobot](https://t.me/userinfobot) پیام بدهید.

---

## 🔧 راه‌اندازی دستی (بدون Docker)

### مرحله ۱ — محیط Python

```bash
cd bot12
python -m venv venv

# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate

pip install -r requirements.txt
```

### مرحله ۲ — اجرای API Server

```bash
cd backend
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

> ربات تلگرام به صورت خودکار توسط API Server در background راه‌اندازی می‌شود.

### مرحله ۳ — اجرای Frontend (اختیاری)

```bash
cd frontend
npm install
npm run dev
```

---

## 🎮 تنظیم MQL5 در MetaTrader 5

### مرحله ۱ — کپی فایل‌ها

مسیر Data Folder را پیدا کنید:
```
MetaTrader 5 → File → Open Data Folder
```

فایل‌ها را کپی کنید:
```
MQL5/Experts/MT5Trading/
    └── MT5TradingEA_Complete.mq5  ✅ (فقط این فایل)

MQL5/Include/MT5Trading/
    ├── Config.mqh
    ├── Helpers.mqh
    ├── ExecutionEngine.mqh
    ├── TradeManager.mqh
    ├── PositionManager.mqh
    ├── RiskManager.mqh
    ├── RiskManager_Complete.mqh
    ├── DrawManager.mqh
    ├── NotificationManager.mqh
    ├── StrategyLoader.mqh
    ├── LicenseChecker.mqh
    ├── DecisionConnector.mqh
    ├── SMCAnalyzer.mqh
    ├── PAAnalyzer.mqh
    └── SessionManager.mqh
```

### مرحله ۲ — فعال‌سازی WebRequest

```
Tools → Options → Expert Advisors
✅ Allow WebRequest for listed URL
آدرس: http://localhost:8000
```

### مرحله ۳ — Compile و نصب

1. `MT5TradingEA_Complete.mq5` را در MetaEditor باز کنید
2. کلید **F7** → باید **0 errors** ببینید
3. چارت را باز کنید → EA را Drag & Drop کنید

### مرحله ۴ — پارامترهای مهم

| پارامتر | مقدار | توضیح |
|---|---|---|
| `API_BASE_URL` | `http://localhost:8000` | آدرس سرور Python |
| `LICENSE_KEY` | کلید لایسنس | اعتبارسنجی |
| `RISK_PERCENT` | `1.0` | درصد ریسک |
| `MAX_SPREAD_POINTS` | `30` | حداکثر spread |
| `DebugMode` | `false` | لاگ debug |
| `LogToFile` | `true` | ذخیره لاگ |
| `DrawOB` | `true` | رسم Order Blocks |
| `DrawFVG` | `true` | رسم FVG |
| `DrawBOS` | `true` | رسم BOS/CHOCH |

### مرحله ۵ — تأیید اتصال

در تب **Expert** باید ببینید:
```
[INFO] ربات تلگرام MT5 Trading راه‌اندازی شد
[INFO] اتصال به API: موفق
[INFO] لایسنس: معتبر
[INFO] شروع تحلیل بازار...
```

---

## 📱 دستورات تلگرام

### شروع کار
```
/start    ← منوی اصلی
/help     ← راهنما
/status   ← وضعیت سیستم
```

### کنترل ربات (OPERATOR+)
```
/bot_start    ← شروع معاملات خودکار
/bot_stop     ← توقف معاملات خودکار
/bot_pause    ← مکث موقت
/bot_resume   ← ادامه بعد از مکث
```

### معاملات (TRADER+)
```
/close_all    ← بستن همه معاملات
/close_buy    ← بستن معاملات خرید
/close_sell   ← بستن معاملات فروش
```

### گزارش‌ها (USER+)
```
/report_daily    ← گزارش روزانه
/report_weekly   ← گزارش هفتگی
/report_monthly  ← گزارش ماهانه
/report_profit   ← گزارش سود
/report_loss     ← گزارش ضرر
/report_winrate  ← نرخ برد
/report_trades   ← لیست معاملات
```

### مدیریت کاربران (ADMIN+)
```
/users           ← لیست کاربران
/add_user        ← اضافه کردن کاربر
/remove_user     ← حذف کاربر
/set_role        ← تغییر نقش کاربر
```

### هشدارهای خودکار

| رویداد | هشدار |
|---|---|
| باز شدن معامله | ✅ ورود + SL/TP/Lot/Score |
| بسته شدن معامله | 📊 خروج + سود/ضرر |
| SL زده شد | 🛑 Stop Loss Hit |
| TP زده شد | 🎯 Take Profit Hit |
| London Open | 🇬🇧 سشن لندن باز شد |
| NY Open | 🇺🇸 سشن نیویورک باز شد |
| Kill Zone | ⚡ Kill Zone فعال |
| سشن بسته شد | 🔒 Session Close |

---

## 📊 API Endpoints

**Base URL:** `http://localhost:8000/api/v1`

| Endpoint | Method | توضیح |
|---|---|---|
| `/health` | GET | سلامت سیستم |
| `/auth/login` | POST | ورود |
| `/analysis/smc/{symbol}` | POST | تحلیل SMC |
| `/analysis/price-action/{symbol}` | POST | تحلیل PA |
| `/decision/{symbol}` | POST | تصمیم نهایی |
| `/signals` | GET | سیگنال‌ها |
| `/trades` | GET | معاملات |
| `/reports/daily` | GET | گزارش روزانه |
| `/dashboard/stats` | GET | آمار |
| `/license/validate` | POST | اعتبارسنجی لایسنس |
| `/users` | GET | کاربران |

**مستندات:** `http://localhost:8000/docs` (فقط DEBUG mode)

---

## 👥 سطوح دسترسی

| نقش | سطح | دسترسی‌ها |
|---|---|---|
| `VIEWER` | 0 | فقط گزارش‌های پایه |
| `USER` | 1 | گزارش + سیگنال‌ها |
| `OPERATOR` | 2 | کنترل ربات |
| `TRADER` | 3 | بستن معاملات + همه عملیات |
| `ADMIN` | 4 | مدیریت کاربران + تنظیمات |
| `SUPER_ADMIN` | 5 | مدیریت لایسنس |
| `OWNER` | 6 | همه چیز + API Keys |

---

## 🏗️ ساختار پروژه

```
bot12/
├── backend/
│   ├── analysis/
│   │   ├── smc_engine.py          ← SMC (19 مفهوم)
│   │   ├── price_action_engine.py ← PA (14 الگو)
│   │   ├── decision_engine.py     ← Pipeline 6 مرحله
│   │   └── smc_scoring.py        ← امتیازدهی
│   ├── api/
│   │   ├── main.py               ← FastAPI + Lifespan
│   │   └── routes/               ← 10 route جداگانه
│   ├── services/
│   │   ├── decision_service.py
│   │   ├── trade_service.py
│   │   ├── signal_service.py
│   │   ├── rbac_service.py
│   │   ├── license_service.py
│   │   └── session_alert_service.py
│   ├── telegram/
│   │   ├── bot.py                ← TelegramBot
│   │   ├── rbac.py               ← 7 نقش + 50 Permission
│   │   └── handlers/             ← 9 هندلر
│   ├── database/connection.py
│   └── core/
│       ├── config.py
│       ├── logger.py
│       └── exceptions.py
├── mql5/
│   ├── Experts/MT5Trading/
│   │   └── MT5TradingEA_Complete.mq5
│   └── Include/MT5Trading/
│       └── *.mqh (15 ماژول)
├── frontend/
├── supabase/migrations/
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 📈 موتورهای تحلیل

### SMC Engine (19 مفهوم)
```
Market Structure: BOS، CHOCH، MSS
Zones: Order Block، Breaker Block، Mitigation Block
Gaps: FVG، IFVG
Liquidity: Internal + External + Sweep
Context: Premium/Discount، Equilibrium
Time: Kill Zones، Session Liquidity
```

### Price Action Engine (14 الگو)
```
Candle: Pin Bar، Engulfing، Doji، Fakey
Multi: Inside Bar، Outside Bar
Reversal: Morning Star، Evening Star
Continuation: Three Soldiers، Three Crows
Structure: Breakout، Retest، Compression، Expansion
```

### Decision Engine (Pipeline 6 مرحله)
```
Stage 1: Spread Filter     ← spread > max → NO_TRADE
Stage 2: Session Filter    ← خارج سشن → NO_TRADE
Stage 3: Multi-TF Score    ← HTF(40%) + Main(25%) + LTF(5%)
Stage 4: Combined Score    ← SMC(40%) + PA(25%) + Session(10%)
Stage 5: Min Score Gate    ← score < threshold → NO_TRADE
Stage 6: Direction Confirm ← 2 از 3 تأیید → BUY/SELL
```

---

## 🔐 امنیت

- JWT Authentication (RS256)
- Rate Limiting (100 req/min عمومی، 10 auth)
- RBAC با 7 نقش و 50+ Permission
- Row Level Security در Supabase
- Audit Log برای تمام عملیات
- License Validation آنلاین
- CORS Policy
- Input Validation با Pydantic

---

## 🔍 عیب‌یابی

### خطا: `Connection refused`
```bash
curl http://localhost:8000/health
docker compose ps
docker compose logs api
```

### خطا: `TELEGRAM_BOT_TOKEN not set`
```bash
cat .env | grep TELEGRAM
```

### خطا: `WebRequest failed` در MT5
```
Tools → Options → Expert Advisors
✅ Allow WebRequest for listed URL
آدرس: http://localhost:8000
```

### خطا: `Database connection failed`
```
SUPABASE_URL و SUPABASE_SERVICE_ROLE_KEY را در .env بررسی کنید
```

### مشاهده لاگ‌های MQL5
```
MQL5/Logs/MT5Trading.log
```

### چک‌لیست راه‌اندازی

```
□ .env کپی و تنظیم شده
□ docker compose up -d اجرا شده
□ curl /health جواب 200 می‌دهد
□ Supabase migration اجرا شده
□ OWNER در دیتابیس ثبت شده
□ /start در تلگرام کار می‌کند
□ MQL5 فایل‌ها کپی شده
□ WebRequest فعال شده
□ EA روی چارت نصب شده
□ تب Expert لاگ موفق نشان می‌دهد
```

---

<div align="center">

**MT5 Trading OS** | Production Grade | Enterprise Architecture

*ساخته‌شده برای معامله‌گران حرفه‌ای*

</div>
