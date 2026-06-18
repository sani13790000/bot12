# Galaxy Vast AI Trading Bot — Deployment Guide

## سیستم مورد نیاز

- Python 3.11+
- PostgreSQL (Supabase)
- Redis (optional — for rate limiting)
- MetaTrader 5 (Windows only — for live trading)

---

## مراحل نصب

### ۱. اجرای migrationها

```bash
psql $SUPABASE_DB_URL -f supabase/migrations/20260612155742_001_initial_schema.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_002_partitioning.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_003_missing_tables.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_004_stabilization.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_005_phase3_dedup.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_006_ml_realism.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_007_phase6_backtest.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_008_phase7_execution.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_009_phase8_db_hardening.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_010_phase9_observability.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_011_phase10_security.sql
psql $SUPABASE_DB_URL -f supabase/migrations/20260618_012_final_10_10.sql
```

### ۲. متغیرهای محیط

```bash
cp .env.example .env
# سپس مقادیر واقعی را پر کنید
```

متغیرهای اجباری:
```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
JWT_SECRET=at-least-32-chars-secret-here
```

### ۳. نصب dependencies

```bash
pip install -r requirements.txt
```

### ۴. اجرا تستها

```bash
pytest backend/tests/ -v --asyncio-mode=auto
```

### ۵. اجرا سرور

```bash
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### ۶. اجرا با Docker

```bash
docker build -t galaxy-vast-bot .
docker run -p 8000:8000 --env-file .env galaxy-vast-bot
```

---

## ۱۰ Endpoint مهم

| Endpoint | توضیح |
|---|---|
| `GET /health` | وضعیت DB + circuit breakers + metrics |
| `GET /observability/metrics` | Prometheus format |
| `GET /observability/alerts` | وضعیت alertها |
| `POST /signals/generate` | تولید سیگنال |
| `GET /agents/status` | وضعیت هفت agent |
| `POST /research/backtest` | اجرای backtest |
| `GET /intelligence/status` | وضعیت ML engine |
| `POST /intelligence/retrain` | رترین مدل |
| `GET /analytics/summary` | خلاصه انالیتیکس |
| `GET /risk/status` | وضعیت risk engine |

---

## میگریسیونها انجام شده تاکنون (12 migration)

| شماره | نام | محتوا |
|---|---|---|
| 001 | initial_schema | schema اولیه |
| 002 | partitioning | partitioned tables |
| 003 | missing_tables | جداول گمشده |
| 004 | stabilization | فاز ۱ تثبیت |
| 005 | phase3_dedup | columnهای جدید |
| 006 | ml_realism | جداول ML |
| 007 | phase6_backtest | جداول backtest |
| 008 | phase7_execution | جداول execution |
| 009 | phase8_db_hardening | ۱۰ composite index |
| 010 | phase9_observability | audit log + alert |
| 011 | phase10_security | security + license |
| 012 | final_10_10 | patchهای نهایی |

---

## چکلیست قبل از Deploy

- [ ] همه migrationها اجرا شدند
- [ ] `.env` پر شده (SUPABASE_URL, JWT_SECRET)
- [ ] `GET /health` پاسخ میدهد (`status: healthy`)
- [ ] تستها pass شدند
- [ ] SENTRY_DSN تنظیم شد (optional)
- [ ] TELEGRAM_BOT_TOKEN تنظیم شد (optional)
