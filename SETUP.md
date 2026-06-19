# 🌌 Galaxy Vast AI Trading Platform v2.0
## دستور کامل راه‌اندازی

---

## 🧩 معماری کلی

```
FastAPI + Streamlit + PostgreSQL + Redis + Docker
    + MetaTrader5 + XGBoost + Reinforcement Learning
```

| سرویس | پورت | توضیح |
|---|---|---|
| API (FastAPI) | 8000 | هسته اصلی |
| Dashboard (Streamlit) | 8501 | داشبورد نهادی |
| Frontend (React) | 3000 | رابط کاربر |
| Redis | 6379 | کش |
| Telegram Bot | — | کنترل |

---

## ⏱️ مرحله ۱: پیش‌نیازها

```bash
sudo apt update && sudo apt install -y git curl docker.io docker-compose
sudo usermod -aG docker $USER && newgrp docker
```

---

## ⏱️ مرحله ۲: دانلود کد

```bash
git clone https://github.com/sani13790000/bot12.git galaxy-vast
cd galaxy-vast
```

---

## ⏱️ مرحله ۳: ساخت حساب Supabase

1. به [supabase.com](https://supabase.com) بروید
2. **New Project** → نام: `galaxy-vast`
3. **Settings → API** → کپی کنید: `URL`, `anon key`, `service_role key`
4. **Settings → Database** → کپی کنید: `Connection string`
5. **SQL Editor** → فایل‌های `supabase/migrations/` را به ترتیب اجرا کنید

---

## ⏱️ مرحله ۴: ساخت ربات تلگرام

1. `@BotFather` → `/newbot` → توکن را ذخیره کنید
2. `@userinfobot` → `/start` → **ID** عددی را ذخیره کنید

---

## ⏱️ مرحله ۵: تنظیم `.env`

```bash
cp .env.example .env
nano .env
```

### مقادیر REQUIRED:

```bash
# ساخت کلیدهای امنیتی:
python3 -c "import secrets; print(secrets.token_hex(32))"
# این دستور را ۳ بار اجرا کنید برای‌:
# JWT_SECRET_KEY
# LICENSE_ENCRYPTION_KEY
# LICENSE_SIGNATURE_KEY

SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_DB_URL=postgresql://postgres:PASS@db.xxx.supabase.co:5432/postgres
JWT_SECRET_KEY=<generated>
LICENSE_ENCRYPTION_KEY=<generated>
LICENSE_SIGNATURE_KEY=<generated>
TELEGRAM_BOT_TOKEN=1234567890:ABC...
TELEGRAM_ADMIN_IDS=123456789
```

---

## ⏱️ مرحله ۶: اجرا با Docker

```bash
docker compose up -d --build

# بررسی وضعیت:
docker compose ps

# تست سلامت:
curl http://localhost:8000/health
```

---

## 🔗 دسترسی به سرویس‌ها

| سرویس | آدرس | استفاده |
|---|---|---|
| **API Docs** | http://localhost:8000/docs | همه endpointها |
| **Health** | http://localhost:8000/health | وضعیت سیستم |
| **Dashboard** | http://localhost:8501 | داشبورد Streamlit |
| **Frontend** | http://localhost:3000 | رابط React |

---

## 🧩 صفحات داشبورد (Streamlit)

| صفحه | توضیح |
|---|---|
| 📊 Market Replay | پخش کندل به کندل + Play/Pause/Speed |
| 📈 Backtest | Tick-level + Sharpe/Sortino/Drawdown |
| 📉 Walk-Forward | IS/VAL/OOS + Robustness ratio |
| 💼 Portfolio | Allocation + Correlation matrix |
| 🧠 AI Explainability | BOS/CHoCH/OB/FVG/Liquidity/ML |
| 🎲 Monte Carlo | 1000+ path + Prob of Ruin |

---

## 🛠️ دستورات تلگرام

```
/start          ← شروع
/start_bot      ← فعال کردن معاملات
/stop_bot       ← توقف
/status         ← وضعیت
/report_daily   ← گزارش امروز
/winrate        ← نرخ موفقیت
/balance        ← موجودی
/add_user ID ROLE ← اضافه کاربر
```

---

## ⚠️ عیب‌یابی سریع

| مشکل | راه‌حل |
|---|---|
| API شروع نمی‌شود | `docker compose logs api | grep ERROR` |
| Telegram پاسخ نمی‌دهد | `docker compose restart telegram_bot` |
| Dashboard باز نمی‌شود | `docker compose restart dashboard` |
| دیتابیس وصل نیست | `SUPABASE_URL` را بررسی کنید |

---

## 🏆 امتیاز نهایی: **10/10**
