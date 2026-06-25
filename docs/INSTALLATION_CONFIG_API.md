# بخش دوم — راهنمای نصب، تنظیمات، API

> **Galaxy Vast AI Trading Platform v2.0.0**
> فایل: `docs/INSTALLATION_CONFIG_API.md`
> بخش‌های ۷ تا ۱۱ از MASTER_DOCUMENTATION.md

---

# فهرست مطالب

- [7. Installation Guide — راهنمای نصب](#7-installation-guide)
- [8. Configuration Guide — راهنمای تنظیمات](#8-configuration-guide)
- [9. Environment Variables — متغیرهای محیطی](#9-environment-variables)
- [10. Database Guide — راهنمای پایگاه داده](#10-database-guide)
- [11. API Documentation — مستندات API](#11-api-documentation)

---

# 7. Installation Guide

## ۷.۱ پیش‌نیازها

> **برای تازه‌کار:** قبل از نصب، مطمئن شوید همه ابزارهای زیر روی سیستم شما نصب است.

| ابزار | نسخه حداقل | بررسی نصب | دانلود |
|-------|-----------|-----------|--------|
| Python | 3.11+ | `python --version` | [python.org](https://python.org) |
| Git | 2.x+ | `git --version` | [git-scm.com](https://git-scm.com) |
| Docker | 24.x+ | `docker --version` | [docker.com](https://docker.com) |
| Docker Compose | 2.x+ | `docker compose version` | همراه Docker Desktop |
| PostgreSQL (Supabase) | — | حساب کاربری رایگان | [supabase.com](https://supabase.com) |

---

## ۷.۲ گام ۱ — Clone کردن پروژه

```bash
git clone https://github.com/sani13790000/bot12.git
cd bot12
ls -la
```

**خروجی انتظاری:**
```
backend/           # کد اصلی Python
dashboard/         # رابط Streamlit
frontend/          # رابط وب
docker-compose.yml
requirements.txt
Dockerfile
.env.example
```

---

## ۷.۳ گام ۲ — ساخت محیط مجازی Python

```bash
# ساخت محیط مجازی
python -m venv venv

# فعال‌سازی در Linux/Mac
source venv/bin/activate

# فعال‌سازی در Windows
venv\Scripts\activate

# تأیید
which python
```

---

## ۷.۴ گام ۳ — نصب کتابخانه‌ها

```bash
pip install --upgrade pip
pip install -r requirements.txt
python -c "import fastapi, pydantic, supabase, redis, torch; print('All OK')"
```

**اگر خطا دیدید:**
```bash
# خطای memory در سرورهای کوچک:
pip install --no-cache-dir -r requirements.txt
```

---

## ۷.۵ گام ۴ — تنظیم فایل `.env`

```bash
cp .env.example .env
nano .env
```

**حداقل تنظیمات ضروری:**
```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_JWT_SECRET=your-super-secret-jwt-key-minimum-32-chars
JWT_SECRET_KEY=another-secret-key-minimum-32-characters
LICENSE_SECRET=your-license-secret-key-here
LICENSE_SALT=your-license-salt-here
REDIS_URL=redis://:changeme_redis@redis:6379/0
REDIS_PASSWORD=changeme_redis
ENVIRONMENT=development
DEBUG=true
```

---

## ۷.۶ گام ۵ — راه‌اندازی Supabase

1. به [supabase.com](https://supabase.com) بروید
2. **New Project** بزنید — نام: `galaxy-vast`
3. از **Settings → API** بگیرید:
   - `Project URL` → مقدار `SUPABASE_URL`
   - `service_role key` → مقدار `SUPABASE_KEY`
4. از **Settings → JWT** بگیرید:
   - `JWT Secret` → مقدار `SUPABASE_JWT_SECRET`

```bash
# اجرای Migrations با Supabase CLI
npm install -g supabase
supabase login
supabase db push --project-ref YOUR_PROJECT_REF
```

---

## ۷.۷ گام ۶ — اجرا با Docker

```bash
docker compose up --build -d
docker compose ps
curl http://localhost:8000/health
```

**خروجی انتظاری:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "environment": "development",
  "checks": {
    "database": {"status": "healthy"},
    "redis": {"status": "healthy"}
  }
}
```

---

## ۷.۸ گام ۷ — اجرا بدون Docker (development)

```bash
# اجرای Redis
docker run -d -p 6379:6379 redis:7.4-alpine \
  redis-server --requirepass changeme_redis

# اجرای API
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## ۷.۹ تأیید نصب کامل

```bash
curl http://localhost:8000/health
open http://localhost:8000/docs
curl http://localhost:8000/api/v1/agents/status
```

---

## ۷.۱۰ عیب‌یابی سریع نصب

| خطا | علت | راه حل |
|-----|-----|--------|
| `Settings validation failed` | `.env` ناقص است | همه فیلدهای ضروری را پر کنید |
| `Connection refused: redis:6379` | Redis اجرا نیست | `docker compose up redis -d` |
| `Could not connect to Supabase` | URL یا KEY اشتباه | مقادیر را از Dashboard بررسی کنید |
| `ModuleNotFoundError` | pip install ناقص | `pip install -r requirements.txt --force-reinstall` |
| Port 8000 already in use | پورت اشغال است | `uvicorn ... --port 8001` |

---

# 8. Configuration Guide

## ۸.۱ ساختار تنظیمات

```
.env
  ↓
backend/core/config.py → class Settings
  ↓
@lru_cache → settings singleton
  ↓
همه ماژول‌ها: from backend.core.config import settings
```

```python
from backend.core.config import settings
print(settings.ENVIRONMENT)       # "production"
print(settings.MT5_SLIPPAGE_BASE) # 10
```

---

## ۸.۲ پروفایل حساب کوچک (تا ۱,۰۰۰ دلار)

```env
INITIAL_ACCOUNT_BALANCE=1000.0
DRIFT_THRESHOLD=0.05
SEMI_AUTO_PENDING_TTL_S=120
MT5_SLIPPAGE_BASE=5
MT5_SLIPPAGE_MAX=20
MT5_REVALIDATE_TIMEOUT=3.0
MT5_REVALIDATE_RETRIES=2
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=WARNING
RECONCILE_INTERVAL_SECONDS=30
BACKTEST_MAX_WORKERS=2
```

## ۸.۳ پروفایل حساب متوسط (۱,۰۰۰ تا ۱۰,۰۰۰ دلار)

```env
INITIAL_ACCOUNT_BALANCE=10000.0
DRIFT_THRESHOLD=0.08
SEMI_AUTO_PENDING_TTL_S=300
MT5_SLIPPAGE_BASE=10
MT5_SLIPPAGE_MAX=50
MT5_REVALIDATE_TIMEOUT=5.0
MT5_REVALIDATE_RETRIES=3
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
RECONCILE_INTERVAL_SECONDS=10
BACKTEST_MAX_WORKERS=4
```

## ۸.۴ پروفایل حساب بزرگ (بالای ۱۰,۰۰۰ دلار)

```env
INITIAL_ACCOUNT_BALANCE=100000.0
DRIFT_THRESHOLD=0.10
SEMI_AUTO_PENDING_TTL_S=600
MT5_SLIPPAGE_BASE=15
MT5_SLIPPAGE_MAX=100
MT5_REVALIDATE_TIMEOUT=8.0
MT5_REVALIDATE_RETRIES=5
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
RECONCILE_INTERVAL_SECONDS=5
BACKTEST_MAX_WORKERS=8
ENABLE_METRICS=true
```

---

## ۸.۵ تنظیمات MT5

```env
MT5_LOGIN=12345678
MT5_PASSWORD=your_mt5_password
MT5_SERVER=YourBroker-Server
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
MT5_SLIPPAGE_BASE=10
MT5_SLIPPAGE_MAX=50
MT5_SLIPPAGE_ATR_MULT=2.0
MT5_SLIPPAGE_SPREAD_MULT=1.5
MT5_REVALIDATE_TIMEOUT=5.0
MT5_REVALIDATE_RETRIES=3
```

---

## ۸.۶ تنظیمات Telegram

```env
TELEGRAM_BOT_TOKEN=123456789:AABBCCDDEEFFaabbccddeeff
TELEGRAM_ADMIN_IDS=123456789,987654321
TELEGRAM_WEBHOOK_SECRET=random-secret-string-here
```

**چگونه آیدی Telegram بیابید:** ربات @userinfobot را پیدا کنید و `/start` بزنید.

---

## ۸.۷ تنظیمات امنیتی

```env
ALLOWED_ORIGINS=https://yourdomain.com,https://dashboard.yourdomain.com
TRUSTED_PROXY_CIDRS=10.0.0.0/8,172.16.0.0/12
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30
```

> ⚠️ در production اگر `ALLOWED_ORIGINS=*` باشد، سیستم خودکار متوقف می‌شود.

---

# 9. Environment Variables

## ۹.۱ جدول کامل همه متغیرها

> **راهنما:** ✅ = ضروری | ⚠️ = اگر feature را استفاده می‌کنید | ❌ = اختیاری

### گروه ۱ — هویت اپلیکیشن

| متغیر | نوع | پیش‌فرض | الزامی | توضیح |
|-------|-----|---------|--------|-------|
| `APP_NAME` | string | `Galaxy Vast AI Trading Platform` | ❌ | نام نمایشی |
| `APP_VERSION` | string | `2.0.0` | ❌ | نسخه — در `/health` نمایش داده می‌شود |
| `ENVIRONMENT` | string | `production` | ❌ | `development`, `staging`, `production` |
| `DEBUG` | bool | `false` | ❌ | در production خودکار `false` می‌شود |
| `LOG_LEVEL` | string | `INFO` | ❌ | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

### گروه ۲ — Supabase

| متغیر | نوع | پیش‌فرض | الزامی | توضیح |
|-------|-----|---------|--------|-------|
| `SUPABASE_URL` | string | — | ✅ | `https://xxx.supabase.co` |
| `SUPABASE_KEY` | string | — | ✅ | کلید `service_role` از Settings → API |
| `SUPABASE_JWT_SECRET` | string | — | ✅ | حداقل ۳۲ کاراکتر — از Settings → JWT |

> ⚠️ **هشدار:** هرگز `SUPABASE_KEY` را در کد یا git commit نگذارید.

### گروه ۳ — JWT

| متغیر | نوع | پیش‌فرض | الزامی | توضیح |
|-------|-----|---------|--------|-------|
| `JWT_SECRET_KEY` | string | — | ✅ | حداقل ۳۲ کاراکتر |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | int | `30` | ❌ | ۵ تا ۱۴۴۰ دقیقه |
| `REFRESH_TOKEN_EXPIRE_DAYS` | int | `30` | ❌ | ۱ تا ۹۰ روز |

```bash
# ساخت JWT_SECRET_KEY امن:
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### گروه ۴ — Redis

| متغیر | نوع | پیش‌فرض | الزامی | توضیح |
|-------|-----|---------|--------|-------|
| `REDIS_URL` | string | `redis://redis:6379/0` | ❌ | `redis://:password@host:port/db` |
| `REDIS_PASSWORD` | string | `changeme_redis` | ⚠️ | در production تغییر دهید |
| `REDIS_MAX_CONNECTIONS` | int | `20` | ❌ | ۵ تا ۱۰۰ |

### گروه ۵ — MT5

| متغیر | نوع | پیش‌فرض | الزامی | توضیح |
|-------|-----|---------|--------|-------|
| `MT5_LOGIN` | int | `null` | ⚠️ | شماره حساب MT5 |
| `MT5_PASSWORD` | string | `null` | ⚠️ | رمز حساب MT5 |
| `MT5_SERVER` | string | `null` | ⚠️ | مثال: `ICMarkets-Live` |
| `MT5_PATH` | string | `null` | ⚠️ | مسیر terminal64.exe (فقط Windows) |
| `MT5_REVALIDATE_TIMEOUT` | float | `5.0` | ❌ | timeout هر تلاش (ثانیه) |
| `MT5_REVALIDATE_RETRIES` | int | `3` | ❌ | تعداد retry: ۱ تا ۱۰ |
| `MT5_SLIPPAGE_BASE` | int | `10` | ❌ | slippage پایه (point) |
| `MT5_SLIPPAGE_MAX` | int | `50` | ❌ | حداکثر slippage مجاز |
| `MT5_SLIPPAGE_ATR_MULT` | float | `2.0` | ❌ | ضریب ATR |
| `MT5_SLIPPAGE_SPREAD_MULT` | float | `1.5` | ❌ | ضریب spread |

### گروه ۶ — مدیریت ریسک

| متغیر | نوع | پیش‌فرض | الزامی | توضیح |
|-------|-----|---------|--------|-------|
| `INITIAL_ACCOUNT_BALANCE` | float | `10000.0` | ❌ | موجودی اولیه برای محاسبه drawdown |
| `RECONCILE_INTERVAL_SECONDS` | int | `10` | ❌ | فاصله reconciliation: ۵ تا ۳۰۰ |
| `DRIFT_THRESHOLD` | float | `0.08` | ❌ | آستانه ML drift: 0 تا 1 |
| `SEMI_AUTO_PENDING_TTL_S` | int | `300` | ❌ | مدت انتظار تأیید manual: ۳۰ تا ۳۶۰۰ |

### گروه ۷ — Telegram

| متغیر | نوع | پیش‌فرض | الزامی | توضیح |
|-------|-----|---------|--------|-------|
| `TELEGRAM_BOT_TOKEN` | string | `null` | ⚠️ | از @BotFather |
| `TELEGRAM_ADMIN_IDS` | string | `""` | ⚠️ | آیدی‌های عددی با کاما: `123,456` |
| `TELEGRAM_WEBHOOK_SECRET` | string | `null` | ❌ | تأیید webhook |

### گروه ۸ — امنیت و شبکه

| متغیر | نوع | پیش‌فرض | الزامی | توضیح |
|-------|-----|---------|--------|-------|
| `ALLOWED_ORIGINS` | string | `*` | ⚠️ | در production دامنه مشخص کنید |
| `TRUSTED_PROXY_CIDRS` | string | `""` | ❌ | CIDR های proxy با کاما |
| `LICENSE_SECRET` | string | — | ✅ | کلید license محصول |
| `LICENSE_SALT` | string | — | ✅ | salt برای hash license |

### گروه ۹ — Observability

| متغیر | نوع | پیش‌فرض | الزامی | توضیح |
|-------|-----|---------|--------|-------|
| `ENABLE_METRICS` | bool | `true` | ❌ | Prometheus metrics |
| `SENTRY_DSN` | string | `null` | ❌ | DSN پروژه Sentry |
| `API_BASE_URL` | string | `http://api:8000` | ❌ | URL داخلی API |

### گروه ۱۰ — Backtest

| متغیر | نوع | پیش‌فرض | الزامی | توضیح |
|-------|-----|---------|--------|-------|
| `BACKTEST_MAX_WORKERS` | int | `4` | ❌ | تعداد worker: ۱ تا ۱۶ |
| `BACKTEST_JOB_TIMEOUT` | int | `300` | ❌ | timeout: ۳۰ تا ۳۶۰۰ ثانیه |

---

## ۹.۲ نمونه فایل `.env` کامل

```env
# === App ===
APP_NAME=Galaxy Vast AI Trading Platform
APP_VERSION=2.0.0
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# === Supabase (ضروری) ===
SUPABASE_URL=https://abcdefghijklmnop.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_JWT_SECRET=your-super-secret-jwt-key-minimum-32-characters-long

# === JWT (ضروری) ===
JWT_SECRET_KEY=another-secret-key-minimum-32-chars-long
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=30

# === Redis ===
REDIS_URL=redis://:changeme_redis@redis:6379/0
REDIS_PASSWORD=changeme_redis
REDIS_MAX_CONNECTIONS=20

# === MT5 ===
MT5_LOGIN=12345678
MT5_PASSWORD=your_broker_password
MT5_SERVER=ICMarkets-Live04
MT5_REVALIDATE_TIMEOUT=5.0
MT5_REVALIDATE_RETRIES=3
MT5_SLIPPAGE_BASE=10
MT5_SLIPPAGE_MAX=50

# === Risk ===
INITIAL_ACCOUNT_BALANCE=10000.0
RECONCILE_INTERVAL_SECONDS=10
DRIFT_THRESHOLD=0.08
SEMI_AUTO_PENDING_TTL_S=300

# === Telegram ===
TELEGRAM_BOT_TOKEN=123456789:AABBCCDDEEFFaabbccddeeff
TELEGRAM_ADMIN_IDS=123456789

# === Security ===
ALLOWED_ORIGINS=https://yourdomain.com,https://dashboard.yourdomain.com
TRUSTED_PROXY_CIDRS=10.0.0.0/8

# === License (ضروری) ===
LICENSE_SECRET=your-license-secret-key
LICENSE_SALT=your-license-salt-value

# === Observability ===
ENABLE_METRICS=true
SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/1234567

# === Backtest ===
BACKTEST_MAX_WORKERS=4
BACKTEST_JOB_TIMEOUT=300
```

---

# 10. Database Guide

## ۱۰.۱ معرفی

این پروژه از **Supabase** (PostgreSQL 15) و **Redis** استفاده می‌کند.

```
Supabase (PostgreSQL 15)
├── signals          — سیگنال‌های معاملاتی
├── trades           — معاملات باز و بسته
├── users            — کاربران سیستم
├── system_health    — وضعیت سلامت سیستم
├── audit_logs       — لاگ‌های حسابرسی
├── agent_votes      — رأی‌های agent‌ها
├── ml_models        — متادیتای مدل‌های ML
├── backtest_results — نتایج backtest
├── risk_events      — رویدادهای ریسک
├── news_events      — رویدادهای خبری
├── user_settings    — تنظیمات کاربر
└── licenses         — اطلاعات مجوز

Redis (DB 0)
├── Rate limiting counters
├── Idempotency store
└── Circuit breaker state
```

---

## ۱۰.۲ جدول `signals`

```sql
CREATE TABLE signals (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id),
    symbol       VARCHAR(20) NOT NULL,
    direction    VARCHAR(4) NOT NULL,        -- BUY | SELL
    entry_price  DECIMAL(18,5) NOT NULL,
    stop_loss    DECIMAL(18,5) NOT NULL,
    take_profit  DECIMAL(18,5) NOT NULL,
    confidence   DECIMAL(5,2) DEFAULT 0.0,   -- 0.00 تا 100.00
    strategy     VARCHAR(50) DEFAULT 'manual',
    status       VARCHAR(20) DEFAULT 'pending', -- pending|active|executed|cancelled|expired
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    executed_at  TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ
);
```

## ۱۰.۳ جدول `trades`

```sql
CREATE TABLE trades (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id),
    signal_id    UUID REFERENCES signals(id),
    symbol       VARCHAR(20) NOT NULL,
    direction    VARCHAR(4) NOT NULL,
    lot_size     DECIMAL(10,2) NOT NULL,
    entry_price  DECIMAL(18,5),
    close_price  DECIMAL(18,5),
    stop_loss    DECIMAL(18,5),
    take_profit  DECIMAL(18,5),
    profit_pips  DECIMAL(10,2),
    profit_money DECIMAL(18,2),
    status       VARCHAR(20) DEFAULT 'open',  -- open | closed | cancelled
    mt5_ticket   BIGINT,
    opened_at    TIMESTAMPTZ DEFAULT NOW(),
    closed_at    TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
```

## ۱۰.۴ جدول `audit_logs`

```sql
CREATE TABLE audit_logs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id),
    action      VARCHAR(50) NOT NULL,
    resource    VARCHAR(50),
    resource_id VARCHAR(100),
    details     JSONB,
    ip_address  INET,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

## ۱۰.۵ جدول `ml_models`

```sql
CREATE TABLE ml_models (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name       VARCHAR(100) NOT NULL,
    model_type       VARCHAR(50),
    version          VARCHAR(20),
    accuracy         DECIMAL(5,4),
    roc_auc          DECIMAL(5,4),
    feature_count    INTEGER,
    training_samples INTEGER,
    is_active        BOOLEAN DEFAULT false,
    model_path       TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

---

## ۱۰.۶ اتصال به پایگاه داده در کد

```python
# روش async (پیشنهادی)
from backend.database.connection import get_db_client

async def my_handler():
    client = await get_db_client()
    result = client.table("signals").select("*").limit(10).execute()
    return result.data

# روش sync (فقط برای legacy)
from backend.database.connection import get_supabase_client_sync
client = get_supabase_client_sync()
```

---

## ۱۰.۷ Migrations

```bash
# مشاهده migrations
ls supabase/migrations/ | sort

# migration جدید
supabase migration new my_migration_name

# apply کردن
supabase db push
```

---

# 11. API Documentation

## ۱۱.۱ اطلاعات کلی

| ویژگی | مقدار |
|-------|-------|
| Base URL | `http://localhost:8000/api/v1` |
| Format | JSON |
| Authentication | Bearer JWT Token |
| Rate Limit | ۱۰۰ req/min |
| مستندات تعاملی | `http://localhost:8000/docs` (non-production) |
| OpenAPI Spec | `http://localhost:8000/openapi.json` |

---

## ۱۱.۲ احراز هویت

```bash
# گام ۱ — دریافت token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "your_password"}'
```

**پاسخ:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

```bash
# گام ۲ — استفاده از token
curl http://localhost:8000/api/v1/signals/ \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## ۱۱.۳ Authentication — `/api/v1/auth`

| Method | Path | Auth | توضیح | بدنه |
|--------|------|------|-------|------|
| `POST` | `/auth/login` | ❌ | ورود و دریافت token | `{email, password}` |
| `POST` | `/auth/register` | ❌ | ثبت‌نام | `{email, password, name}` |
| `POST` | `/auth/refresh` | ❌ | تجدید token | `{refresh_token}` |
| `POST` | `/auth/logout` | ✅ | خروج | — |
| `GET` | `/auth/me` | ✅ | اطلاعات کاربر جاری | — |

---

## ۱۱.۴ Signals — `/api/v1/signals`

| Method | Path | Auth | توضیح | پارامترها |
|--------|------|------|-------|----------|
| `GET` | `/signals/` | ✅ | لیست سیگنال‌ها | `status`, `symbol`, `limit`, `offset` |
| `GET` | `/signals/{id}` | ✅ | جزئیات سیگنال | — |
| `POST` | `/signals/` | ✅ | ایجاد سیگنال | بدنه زیر |
| `POST` | `/signals/{id}/execute` | ✅ | اجرای سیگنال | — |
| `POST` | `/signals/{id}/cancel` | ✅ | لغو سیگنال | — |

**ایجاد سیگنال:**
```bash
curl -X POST http://localhost:8000/api/v1/signals/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "direction": "BUY",
    "entry_price": 1.08500,
    "stop_loss": 1.08000,
    "take_profit": 1.09500,
    "confidence": 75.0,
    "strategy": "smc"
  }'
```

**نمادهای مجاز:** `XAUUSD`, `EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`, `USDCAD`, `NZDUSD`, `GBPJPY`, `EURJPY`, `EURGBP`, `XAGUSD`, `BTCUSD`, `ETHUSD`

---

## ۱۱.۵ Trades — `/api/v1/trades`

| Method | Path | Auth | توضیح | پارامترها |
|--------|------|------|-------|----------|
| `GET` | `/trades/` | ✅ | لیست معاملات | `status`, `symbol`, `direction`, `from_date`, `to_date`, `limit`, `offset` |
| `GET` | `/trades/open` | ✅ | معاملات باز | — |
| `GET` | `/trades/{id}` | ✅ | جزئیات معامله | — |
| `POST` | `/trades/close/{id}` | ✅ | بستن معامله | — |
| `POST` | `/trades/close-all` | ✅ | بستن همه معاملات باز | — |

```bash
curl http://localhost:8000/api/v1/trades/open \
  -H "Authorization: Bearer TOKEN"
```

---

## ۱۱.۶ Agents — `/api/v1/agents`

| Method | Path | Auth | توضیح |
|--------|------|------|-------|
| `GET` | `/agents/status` | ✅ | وضعیت همه agent‌ها |
| `GET` | `/agents/votes` | ✅ | آخرین رأی‌های VotingEngine |
| `POST` | `/agents/analyze` | ✅ | تحلیل دستی یک نماد |
| `GET` | `/agents/config` | ✅ | پیکربندی agent‌ها |
| `PUT` | `/agents/config` | Admin | تغییر وزن agent‌ها |

---

## ۱۱.۷ Risk — `/api/v1/risk`

| Method | Path | Auth | توضیح |
|--------|------|------|-------|
| `POST` | `/risk/assess` | ✅ | ارزیابی ریسک signal |
| `GET` | `/risk/status` | ✅ | وضعیت gate‌های ریسک |
| `GET` | `/risk/exposure` | ✅ | exposure جاری |
| `POST` | `/risk/halt` | Admin | توقف اضطراری |
| `POST` | `/risk/resume` | Admin | از سرگیری |
| `GET` | `/risk/circuit-breaker` | ✅ | وضعیت Circuit Breaker |

**ارزیابی ریسک:**
```bash
curl -X POST http://localhost:8000/api/v1/risk/assess \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"EURUSD","direction":"BUY","lot_size":0.1,"entry_price":1.085,"stop_loss":1.08}'
```

**پاسخ:**
```json
{
  "approved": true,
  "adjusted_lot": 0.1,
  "risk_score": 0.35,
  "gates_passed": ["equity","daily_limits","volatility","correlation","exposure"],
  "gates_failed": [],
  "reason": null
}
```

---

## ۱۱.۸ Users — `/api/v1/users`

| Method | Path | Auth | توضیح |
|--------|------|------|-------|
| `GET` | `/users/profile` | ✅ | پروفایل (بدون اطلاعات حساس) |
| `PATCH` | `/users/profile` | ✅ | ویرایش: `display_name`, `timezone`, `language`, `notification_email` |
| `GET` | `/users/settings` | ✅ | تنظیمات کاربر |
| `PUT` | `/users/settings` | ✅ | ذخیره: `theme`, `default_lot`, `risk_per_trade`, `auto_trade` |
| `DELETE` | `/users/account` | ✅ | حذف حساب (GDPR) |

---

## ۱۱.۹ Health Endpoints

| Method | Path | Auth | مناسب برای |
|--------|------|------|----------|
| `GET` | `/health/live` | ❌ | Kubernetes liveness |
| `GET` | `/health/ready` | ❌ | Kubernetes readiness |
| `GET` | `/health` | ❌ | Monitoring |
| `GET` | `/health/deep` | ❌ | Dashboard |

**پاسخ `/health/deep`:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "uptime_s": 3600.5,
  "components": {
    "database":          {"status": "healthy", "latency_ms": 12.3},
    "redis":             {"status": "healthy", "latency_ms": 0.8},
    "mt5":               {"status": "healthy", "latency_ms": 45.2},
    "risk_orchestrator": {"status": "healthy", "latency_ms": 2.1},
    "equity_protection": {"status": "healthy", "latency_ms": 1.0},
    "circuit_breaker":   {"status": "healthy", "latency_ms": 0.1},
    "scheduler":         {"status": "healthy", "latency_ms": 0.5}
  }
}
```

---

## ۱۱.۱۰ WebSocket

| مسیر | توضیح |
|------|-------|
| `ws://localhost:8000/ws/signals` | real-time سیگنال‌ها |
| `ws://localhost:8000/ws/trades` | وضعیت real-time معاملات |
| `ws://localhost:8000/ws/agents` | رأی‌گیری real-time |

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/signals');
ws.onmessage = (event) => {
  const signal = JSON.parse(event.data);
  console.log('New signal:', signal);
};
```

---

## ۱۱.۱۱ Analytics — `/api/v1/analytics`

| Method | Path | Auth | توضیح |
|--------|------|------|-------|
| `GET` | `/analytics/performance` | ✅ | آمار کلی عملکرد |
| `GET` | `/analytics/pnl` | ✅ | PnL روزانه/هفتگی/ماهانه |
| `GET` | `/analytics/drawdown` | ✅ | تاریخچه drawdown |
| `GET` | `/analytics/win-rate` | ✅ | نرخ موفقیت |
| `GET` | `/analytics/symbols` | ✅ | عملکرد به تفکیک نماد |

---

## ۱۱.۱۲ Observability

| Method | Path | Auth | توضیح |
|--------|------|------|-------|
| `GET` | `/api/v1/metrics` | ❌ | Prometheus metrics |
| `GET` | `/api/v1/alerts` | Admin | هشدارهای فعال |

```bash
curl http://localhost:8000/api/v1/metrics
# galaxy_vast_trades_submitted_total{symbol="EURUSD",direction="BUY"} 42
# galaxy_vast_risk_blocks_total{gate="equity",reason="drawdown"} 3
```

---

## ۱۱.۱۳ کدهای HTTP Response

| کد | معنا | زمان وقوع |
|----|------|----------|
| `200` | OK | درخواست موفق |
| `201` | Created | منبع جدید ایجاد شد |
| `400` | Bad Request | داده نامعتبر |
| `401` | Unauthorized | token وجود ندارد یا منقضی شده |
| `403` | Forbidden | دسترسی کافی ندارید |
| `404` | Not Found | منبع پیدا نشد |
| `409` | Conflict | تداخل — سیگنال قبلاً اجرا شده |
| `422` | Unprocessable Entity | validation fail |
| `429` | Too Many Requests | rate limit |
| `500` | Internal Server Error | خطای داخلی |
| `503` | Service Unavailable | Circuit Breaker باز است |

---

## ۱۱.۱۴ Error Response Format

```json
{
  "detail": "Signal not found",
  "error_code": "SIGNAL_NOT_FOUND",
  "http_status": 404,
  "context": {
    "signal_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

---

## ۱۱.۱۵ Rate Limiting

| نوع کاربر | محدودیت |
|-----------|--------|
| عادی | ۱۰۰ request در دقیقه |
| Admin | ۵۰۰ request در دقیقه |
| WebSocket | ۱۰ پیام در ثانیه |

```json
// HTTP 429 Too Many Requests
{
  "detail": "Rate limit exceeded",
  "retry_after": 45
}
```

---

## ۱۱.۱۶ نکات امنیتی API

```bash
# همیشه HTTPS در production
curl https://api.yourdomain.com/api/v1/signals/

# token در Header — نه در URL
# درست:
curl http://api/api/v1/signals/ -H "Authorization: Bearer eyJ..."

# اشتباه:
curl http://api/signals/?token=eyJ...
```

---

*پایان بخش‌های ۷ تا ۱۱ — بخش بعدی: AI Models, Exchange Integration, Risk Management*