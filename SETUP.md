# 🚀 راهنمای کامل راه‌اندازی MT5 Trading OS
### صفر تا صد — مو به مو | نسخه Production

---

## 📋 فهرست مطالب

1. [پیش‌نیازها](#۱-پیش‌نیازها)
2. [دریافت کد](#۲-دریافت-کد)
3. [تنظیم محیط Python](#۳-تنظیم-محیط-python)
4. [تنظیم Supabase](#۴-تنظیم-supabase)
5. [تنظیم ربات تلگرام](#۵-تنظیم-ربات-تلگرام)
6. [تنظیم فایل .env](#۶-تنظیم-فایل-env)
7. [راه‌اندازی با Docker](#۷-راه‌اندازی-با-docker)
8. [راه‌اندازی دستی بدون Docker](#۸-راه‌اندازی-دستی-بدون-docker)
9. [نصب و تنظیم MQL5 EA](#۹-نصب-و-تنظیم-mql5-ea)
10. [تست و تأیید سیستم](#۱۰-تست-و-تأیید-سیستم)
11. [دستورات تلگرام](#۱۱-دستورات-تلگرام)
12. [مشکلات رایج](#۱۲-مشکلات-رایج)

---

## ۱. پیش‌نیازها

### سرور / VPS
| منبع | حداقل | پیشنهادی |
|---|---|---|
| CPU | 2 هسته | 4 هسته |
| RAM | 4 GB | 8 GB |
| دیسک | 20 GB SSD | 50 GB SSD |
| سیستم‌عامل | Ubuntu 22.04 | Ubuntu 22.04 LTS |

### نرم‌افزارهای لازم
```bash
# بررسی نصب بودن Python
python3 --version   # باید 3.11+ باشد

# بررسی نصب بودن Docker
docker --version    # باید 24.0+ باشد
docker compose version  # باید 2.0+ باشد

# بررسی نصب بودن Git
git --version
```

### نصب Python 3.11 (اگر ندارید)
```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install -y python3.11 python3.11-venv python3.11-dev
sudo ln -sf /usr/bin/python3.11 /usr/bin/python3
```

### نصب Docker (اگر ندارید)
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
```

---

## ۲. دریافت کد

```bash
# کلون کردن پروژه
git clone https://github.com/sani13790000/bot12.git
cd bot12

# بررسی ساختار
ls -la
```

**خروجی مورد انتظار:**
```
backend/
mql5/
frontend/
docker/
.env.example
DEPLOYMENT.md
MQL5_INSTALLATION.md
SETUP.md
README.md
```

---

## ۳. تنظیم محیط Python

```bash
# ساخت virtual environment
python3.11 -m venv venv

# فعال‌سازی
source venv/bin/activate   # Linux/Mac
# یا
venv\Scripts\activate      # Windows

# نصب کتابخانه‌ها
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### محتوای requirements.txt (مرجع)
```
fastapi==0.115.0
uvicorn[standard]==0.32.0
aiogram==3.13.0
supabase==2.10.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-dotenv==1.0.0
pydantic-settings==2.6.0
httpx==0.27.0
redis==5.2.0
numpy==2.1.0
pandas==2.2.0
cryptography==43.0.0
aiofiles==24.1.0
pytest==8.3.0
pytest-asyncio==0.24.0
```

---

## ۴. تنظیم Supabase

### مرحله ۱ — ایجاد پروژه
1. به [supabase.com](https://supabase.com) بروید
2. **New Project** بزنید
3. نام پروژه: `mt5-trading`
4. رمز دیتابیس را **یادداشت کنید** (بعداً نیاز دارید)
5. Region: نزدیک‌ترین به سرور شما

### مرحله ۲ — دریافت کلیدها
در داشبورد Supabase:
1. **Settings → API** بروید
2. این مقادیر را کپی کنید:
   - `Project URL` → برای `SUPABASE_URL`
   - `anon public` → برای `SUPABASE_ANON_KEY`
   - `service_role secret` → برای `SUPABASE_SERVICE_KEY`

### مرحله ۳ — اجرای Schema
در داشبورد Supabase به **SQL Editor** بروید و محتوای فایل زیر را اجرا کنید:

```bash
# محتوای فایل را نمایش دهید
cat backend/database/migrations/schema.sql
```

آن را **کپی** کنید و در SQL Editor Supabase **Run** بزنید.

**تأیید:** باید ۱۰ جدول ایجاد شود:
- users, user_sessions, permissions, audit_log
- trades, signals, licenses, subscriptions
- settings, notifications

---

## ۵. تنظیم ربات تلگرام

### مرحله ۱ — ساخت ربات
1. در تلگرام به [@BotFather](https://t.me/BotFather) بروید
2. دستور `/newbot` بزنید
3. نام ربات: `MT5 Trading Bot` (یا هر چیز دیگر)
4. یوزرنیم: مثلاً `mt5_trading_yourname_bot`
5. **توکن** را کپی کنید → برای `TELEGRAM_BOT_TOKEN`

### مرحله ۲ — دریافت Chat ID ادمین
```
روش ۱ — استفاده از @userinfobot:
  1. به @userinfobot در تلگرام پیام بدهید
  2. Chat ID شما را نمایش می‌دهد

روش ۲ — استفاده از @RawDataBot:
  1. به @RawDataBot پیام بدهید
  2. در پاسخ JSON، مقدار id را پیدا کنید
```

### مرحله ۳ — تنظیم دستورات ربات (اختیاری)
در BotFather دستور `/setcommands` بزنید و متن زیر را بفرستید:
```
start - شروع و منوی اصلی
help - راهنما
status - وضعیت سیستم
start_bot - شروع ربات معاملاتی
stop_bot - توقف ربات معاملاتی
pause_bot - مکث ربات
resume_bot - ادامه ربات
close_all - بستن همه معاملات
close_buy - بستن معاملات خرید
close_sell - بستن معاملات فروش
report_daily - گزارش روزانه
report_weekly - گزارش هفتگی
report_monthly - گزارش ماهانه
signals - سیگنال‌های فعال
settings - تنظیمات
users - مدیریت کاربران
```

---

## ۶. تنظیم فایل .env

```bash
# کپی از نمونه
cp .env.example .env

# ویرایش
nano .env
```

### محتوای کامل .env
```env
# ═══════════════════════════════════════════
# تنظیمات API
# ═══════════════════════════════════════════
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false
API_SECRET_KEY=your-super-secret-key-min-32-chars-change-this

# ═══════════════════════════════════════════
# تنظیمات JWT
# ═══════════════════════════════════════════
JWT_SECRET_KEY=your-jwt-secret-key-min-32-chars-change-this
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# ═══════════════════════════════════════════
# تنظیمات Supabase
# ═══════════════════════════════════════════
SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# ═══════════════════════════════════════════
# تنظیمات تلگرام
# ═══════════════════════════════════════════
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_ADMIN_IDS=123456789,987654321

# ═══════════════════════════════════════════
# تنظیمات لاگ
# ═══════════════════════════════════════════
LOG_LEVEL=INFO
LOG_FILE=logs/mt5trading.log
LOG_TO_FILE=true

# ═══════════════════════════════════════════
# تنظیمات معاملات (مقادیر پیش‌فرض)
# ═══════════════════════════════════════════
DEFAULT_SYMBOL=EURUSD
DEFAULT_RISK_PERCENT=1.0
DEFAULT_MIN_SCORE=0.65
MAX_SPREAD_PIPS=3.0

# ═══════════════════════════════════════════
# تنظیمات لایسنس
# ═══════════════════════════════════════════
LICENSE_SECRET_KEY=your-license-secret-key-change-this
LICENSE_SALT=your-license-salt-change-this

# ═══════════════════════════════════════════
# Redis (اختیاری — برای cache)
# ═══════════════════════════════════════════
REDIS_URL=redis://localhost:6379/0
```

### تولید کلیدهای امن
```bash
# تولید API_SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# تولید JWT_SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# تولید LICENSE_SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## ۷. راه‌اندازی با Docker

**سریع‌ترین روش — توصیه‌شده برای production:**

```bash
# ساخت و اجرا
docker compose -f docker/docker-compose.yml up -d --build

# بررسی وضعیت
docker compose -f docker/docker-compose.yml ps

# مشاهده لاگ‌ها
docker compose -f docker/docker-compose.yml logs -f

# لاگ یک سرویس خاص
docker compose -f docker/docker-compose.yml logs -f api
docker compose -f docker/docker-compose.yml logs -f bot
```

### تأیید راه‌اندازی
```bash
# تست health check
curl http://localhost:8000/health

# خروجی مورد انتظار:
# {"status":"healthy","version":"1.0.0","timestamp":"..."}
```

### توقف سیستم
```bash
docker compose -f docker/docker-compose.yml down
```

---

## ۸. راه‌اندازی دستی بدون Docker

**اگر نمی‌خواهید از Docker استفاده کنید:**

### ترمینال ۱ — API Server
```bash
cd bot12
source venv/bin/activate

# ساخت پوشه لاگ
mkdir -p logs

# راه‌اندازی API
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
```

**خروجی مورد انتظار:**
```
INFO: MT5 Trading API شروع به کار کرد
INFO: ربات تلگرام راه‌اندازی شد
INFO: SessionAlertService شروع به کار کرد
INFO: Uvicorn running on http://0.0.0.0:8000
```

### تأیید
```bash
# در ترمینال جدید
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health/details
```

### راه‌اندازی به عنوان سرویس systemd
```bash
# ایجاد فایل سرویس
sudo nano /etc/systemd/system/mt5trading.service
```

```ini
[Unit]
Description=MT5 Trading OS API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/bot12
Environment="PATH=/home/ubuntu/bot12/venv/bin"
ExecStart=/home/ubuntu/bot12/venv/bin/uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# فعال‌سازی و شروع سرویس
sudo systemctl daemon-reload
sudo systemctl enable mt5trading
sudo systemctl start mt5trading

# بررسی وضعیت
sudo systemctl status mt5trading
```

---

## ۹. نصب و تنظیم MQL5 EA

### مرحله ۱ — پیدا کردن پوشه داده MetaTrader 5
در MT5:
1. **File → Open Data Folder** بزنید
2. پوشه باز می‌شود

### مرحله ۲ — کپی فایل‌های Include
```
از پوشه پروژه:        به MT5 Data Folder:
mql5/Include/MT5Trading/  →  MQL5/Include/MT5Trading/

فایل‌های زیر را کپی کنید:
✅ Config.mqh
✅ Helpers.mqh
✅ ExecutionEngine.mqh
✅ TradeManager.mqh
✅ PositionManager.mqh
✅ RiskManager.mqh
✅ RiskManager_Complete.mqh
✅ DrawManager.mqh
✅ NotificationManager.mqh
✅ StrategyLoader.mqh
✅ LicenseChecker.mqh
✅ DecisionConnector.mqh
✅ SMCAnalyzer.mqh
✅ PAAnalyzer.mqh
✅ SessionManager.mqh
```

### مرحله ۳ — کپی فایل EA
```
از پوشه پروژه:                              به MT5 Data Folder:
mql5/Experts/MT5Trading/MT5TradingEA_Complete.mq5  →  MQL5/Experts/MT5Trading/
```

⚠️ **توجه:** فقط `MT5TradingEA_Complete.mq5` را نصب کنید. `MT5TradingEA.mq5` منسوخ شده است.

### مرحله ۴ — تنظیم Config.mqh
فایل `MQL5/Include/MT5Trading/Config.mqh` را در MetaEditor باز کنید:

```mql5
// ─── آدرس Python Backend ───────────────────────────────
// اگر MT5 روی همان سرور است:
#define API_BASE_URL "http://localhost:8000/api/v1"

// اگر MT5 روی ویندوز محلی است و سرور روی VPS:
#define API_BASE_URL "http://YOUR_VPS_IP:8000/api/v1"

// مثال:
// #define API_BASE_URL "http://123.456.789.012:8000/api/v1"
```

### مرحله ۵ — Compile کردن
1. در MetaEditor فایل `MT5TradingEA_Complete.mq5` را باز کنید
2. **F7** بزنید یا دکمه **Compile** را بزنید
3. در پنل **Errors** نباید هیچ خطایی باشد (Warning قابل قبول است)

### مرحله ۶ — فعال کردن WebRequest
⚠️ **این مرحله بسیار مهم است — بدون آن EA کار نمی‌کند:**

در MT5:
1. **Tools → Options → Expert Advisors** بروید
2. تیک **Allow WebRequest for listed URL** را بزنید
3. آدرس را اضافه کنید: `http://localhost:8000` (یا آدرس VPS شما)
4. **OK** بزنید

### مرحله ۷ — نصب روی چارت
1. نماد مورد نظر را باز کنید (مثلاً EURUSD)
2. تایم‌فریم H1 یا M15 را انتخاب کنید
3. در Navigator پنل، EA را پیدا کنید: `MT5Trading → MT5TradingEA_Complete`
4. روی چارت Drag & Drop کنید
5. در پنجره تنظیمات:
   - **Allow live trading** را تیک بزنید
   - **Allow WebRequest** را تیک بزنید
   - تنظیمات دلخواه را اعمال کنید

### پارامترهای مهم EA
| پارامتر | پیش‌فرض | توضیح |
|---|---|---|
| `ApiBaseUrl` | `http://localhost:8000/api/v1` | آدرس Python Backend |
| `LicenseKey` | `` | کلید لایسنس (اگر دارید) |
| `RiskPercent` | `1.0` | درصد ریسک هر معامله |
| `MinScore` | `0.65` | حداقل امتیاز برای ورود |
| `MaxSpreadPips` | `3.0` | حداکثر اسپرد مجاز |
| `DrawOB` | `true` | رسم Order Block روی چارت |
| `DrawFVG` | `true` | رسم FVG روی چارت |
| `DrawBOS` | `true` | رسم BOS/CHOCH روی چارت |
| `DrawKillZones` | `true` | رسم Kill Zones روی چارت |
| `DebugMode` | `false` | نمایش لاگ‌های debug |

---

## ۱۰. تست و تأیید سیستم

### تست ۱ — API در حال اجرا است؟
```bash
curl http://localhost:8000/health
# انتظار: {"status":"healthy"}
```

### تست ۲ — اتصال Supabase برقرار است؟
```bash
curl http://localhost:8000/api/v1/health/details
# انتظار: {...,"database":"connected",...}
```

### تست ۳ — SMC Engine کار می‌کند؟
```bash
curl -X POST http://localhost:8000/api/v1/analysis/smc/EURUSD \
  -H "Content-Type: application/json" \
  -d '{"candles": [...], "timeframe": "H1"}'
```

### تست ۴ — تلگرام جواب می‌دهد؟
1. به ربات تلگرام پیام `/start` بفرستید
2. باید منوی اصلی نمایش داده شود

### تست ۵ — EA به API وصل است؟
در Expert tab MT5 باید ببینید:
```
[INFO] MT5TradingEA_Complete راه‌اندازی شد
[INFO] لایسنس معتبر است
[INFO] اتصال به Python Backend برقرار شد
```

### چک‌لیست نهایی
```
☐ API روی پورت 8000 در حال اجرا است
☐ curl /health پاسخ {"status":"healthy"} می‌دهد
☐ Supabase connect است (health/details)
☐ ربات تلگرام به /start پاسخ می‌دهد
☐ MT5 EA بدون خطا Compile شده
☐ WebRequest در MT5 فعال شده
☐ EA روی چارت نصب شده
☐ Expert tab MT5 پیام موفقیت نشان می‌دهد
☐ نواحی SMC روی چارت رسم شده‌اند (اگر DrawOB=true)
```

---

## ۱۱. دستورات تلگرام

| دستور | نقش لازم | توضیح |
|---|---|---|
| `/start` | همه | منوی اصلی |
| `/help` | همه | راهنما |
| `/status` | VIEWER+ | وضعیت سیستم |
| `/report_daily` | VIEWER+ | گزارش روزانه |
| `/report_weekly` | VIEWER+ | گزارش هفتگی |
| `/report_monthly` | VIEWER+ | گزارش ماهانه |
| `/signals` | USER+ | سیگنال‌های فعال |
| `/start_bot` | OPERATOR+ | شروع ربات معاملاتی |
| `/stop_bot` | OPERATOR+ | توقف ربات |
| `/pause_bot` | OPERATOR+ | مکث ربات |
| `/resume_bot` | OPERATOR+ | ادامه ربات |
| `/close_all` | TRADER+ | بستن همه معاملات |
| `/close_buy` | TRADER+ | بستن معاملات خرید |
| `/close_sell` | TRADER+ | بستن معاملات فروش |
| `/settings` | ADMIN+ | تنظیمات سیستم |
| `/users` | ADMIN+ | مدیریت کاربران |
| `/add_user` | ADMIN+ | افزودن کاربر |
| `/remove_user` | ADMIN+ | حذف کاربر |
| `/set_role` | ADMIN+ | تغییر نقش کاربر |

### هشدارهای خودکار (بدون دستور)
| هشدار | زمان ارسال |
|---|---|
| 🟢 ورود به معامله | هنگام باز شدن پوزیشن |
| 🔴 خروج از معامله | هنگام بسته شدن پوزیشن |
| 🛑 SL زده شد | هنگام فعال شدن Stop Loss |
| 🎯 TP رسید | هنگام رسیدن به Take Profit |
| 🇬🇧 سشن لندن باز شد | ۰۸:۰۰ UTC |
| 🇺🇸 سشن نیویورک باز شد | ۱۳:۰۰ UTC |
| 🎯 Kill Zone فعال شد | مطابق جدول Kill Zones |
| ⚠️ خطای سیستم | در صورت بروز خطای بحرانی |

---

## ۱۲. مشکلات رایج

### ❌ `ModuleNotFoundError: No module named 'backend'`
```bash
# مطمئن شوید در پوشه اصلی پروژه هستید
cd /path/to/bot12

# تنظیم PYTHONPATH
export PYTHONPATH=/path/to/bot12

# یا اجرا با python -m
python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

### ❌ `connection refused` در MT5
```
دلایل احتمالی:
1. Python Backend در حال اجرا نیست → uvicorn را اجرا کنید
2. Firewall پورت 8000 را بسته → sudo ufw allow 8000
3. آدرس API در Config.mqh اشتباه است → IP/Port را بررسی کنید
4. WebRequest در MT5 فعال نیست → Tools → Options → Expert Advisors
```

### ❌ `ربات تلگرام جواب نمی‌دهد`
```bash
# بررسی توکن
grep TELEGRAM_BOT_TOKEN .env

# بررسی لاگ ربات
docker compose logs bot | tail -50
# یا
journalctl -u mt5trading -n 50

# تست مستقیم توکن
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

### ❌ `Supabase connection failed`
```bash
# بررسی URL و کلیدها در .env
grep SUPABASE .env

# تست اتصال مستقیم
curl -H "apikey: YOUR_ANON_KEY" "https://YOUR_PROJECT.supabase.co/rest/v1/"
```

### ❌ `EA compile error: cannot open include file`
```
مشکل: فایل‌های Include کپی نشده‌اند
راه‌حل:
1. File → Open Data Folder در MT5
2. پوشه MQL5/Include/MT5Trading/ را بررسی کنید
3. مطمئن شوید همه ۱۵ فایل .mqh وجود دارند
```

### ❌ `Rate limit exceeded`
```
مشکل: درخواست‌های زیاد از یک IP
راه‌حل: در تنظیمات EA، تایمر را از 5 ثانیه به 10 ثانیه افزایش دهید
```

---

## 📞 پشتیبانی

در صورت بروز مشکل:
1. لاگ‌های سیستم را بررسی کنید: `logs/mt5trading.log`
2. لاگ Expert tab در MT5 را بررسی کنید
3. Health endpoint را چک کنید: `GET /api/v1/health/details`

---

*راهنمای SETUP.md — MT5 Trading OS v1.0 | Production Ready*
