# 🚀 DEPLOYMENT.md — Galaxy Vast AI Trading Platform

> **نسخه:** 3.0 | **آخرین به‌روزرسانی:** 2026-06-26
> مسیر کامل نصب: **Dev → Staging → Production**

---

> ⚠️ **هشدار ریسک معامله‌گری**
> این نرم‌افزار ابزار اتوماسیون است — نه مشاوره مالی.
> معامله در بازارهای مالی ریسک بالا دارد و ممکن است تمام سرمایه از دست برود.
> فقط با سرمایه‌ای که توانایی از دست دادنش را دارید استفاده کنید.

---

## پیش‌نیازها

| محیط | CPU | RAM | Disk |
|------|-----|-----|------|
| Dev | 2 core | 4 GB | 20 GB |
| Staging | 2 core | 4 GB | 40 GB |
| Production | 4 core | 8 GB | 80 GB SSD |

```bash
docker --version        # Docker 24+
docker compose version  # Compose v2+
python3 --version       # Python 3.11+
```

---

## محیط Development

```bash
git clone https://github.com/sani13790000/bot12 galaxy-vast
cd galaxy-vast
cp .env.example .env

# Generate secrets
python3 -c "import secrets; print('SECRETS_MASTER_KEY=' + secrets.token_hex(32))"
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_hex(32))"
python3 -c "import secrets; print('FIELD_ENCRYPTION_KEY=' + secrets.token_hex(32))"
python3 -c "import secrets; print('LICENSE_SALT=' + secrets.token_hex(16))"

# ویرایش .env
nano .env

# Database migrations
# در Supabase SQL Editor به ترتیب اجرا کنید:
ls supabase/migrations/ | sort

# اجرا
python3 startup_check.py
docker compose up -d --build

# Verify
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

---

## محیط Staging

```bash
# nginx
sudo cp infra/nginx/nginx.conf /etc/nginx/sites-available/galaxy-vast
sudo ln -s /etc/nginx/sites-available/galaxy-vast /etc/nginx/sites-enabled/
sudo certbot --nginx -d staging.yourdomain.com
sudo nginx -t && sudo systemctl reload nginx

# Deploy
git pull origin develop
docker compose pull
docker compose up -d --no-deps api
sleep 20
curl -sf https://staging.yourdomain.com/health/live \
    || (docker compose restart api; exit 1)
```

---

## محیط Production — Blue/Green Deploy

```bash
# Backup اول
bash scripts/backup.sh production

# مرحله ۱: فقط api
docker compose -f docker-compose.prod.yml pull api
docker compose -f docker-compose.prod.yml up -d --no-deps api

# مرحله ۲: Health check
sleep 30
curl -sf https://api.yourdomain.com/health/live \
    || (docker compose -f docker-compose.prod.yml restart api && exit 1)

# مرحله ۳: بقیه
docker compose -f docker-compose.prod.yml up -d
docker image prune -f
```

---

## Database Migrations — ترتیب اجرا

```
001_initial_schema.sql
002_partitioning.sql
003_trading_core.sql → 004 → 005 → 006 → ... → 025
026_phase10_billing.sql
027_phase13_saas_schema.sql   ← آخرین (hardening + RLS)
```

---

## Environment Variables اجباری

```bash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SECRETS_MASTER_KEY=<64-char hex>
JWT_SECRET_KEY=<64-char hex>
FIELD_ENCRYPTION_KEY=<64-char hex>
LICENSE_SALT=<32-char hex>
WEBHOOK_SECRET=<64-char hex>
ENVIRONMENT=production
ALLOWED_ORIGINS=https://yourdomain.com
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-1001234567890
REDIS_URL=redis://:PASSWORD@redis:6379/0
```

---

## Health Checks

| Endpoint | نوع | توضیح |
|----------|-----|---------|
| `GET /health/live` | Liveness | process زنده |
| `GET /health/ready` | Readiness | DB + Redis متصل |
| `GET /health/deep` | Admin | همه components |

```json
{"status": "healthy", "checks": {"db": "ok", "redis": "ok"}}
{"status": "degraded", "checks": {"db": "ok", "redis": "slow"}}  // 200
{"status": "unhealthy", "checks": {"db": "error"}}  // 503
```

---

## Rollback

```bash
# سریع (30 ثانیه)
docker compose -f docker-compose.prod.yml restart api

# به نسخه قبلی
git checkout v3.19
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Backup

```bash
bash scripts/backup.sh production
# Cron: 0 2 * * * bash /opt/galaxy-vast/scripts/backup.sh production
```

---

## Troubleshooting

```bash
# API 503
docker compose logs api --tail=100
docker compose restart api

# Kill Switch فعال شد
# Telegram: /resume
curl -X POST https://api.yourdomain.com/api/v1/risk/resume \
     -H "Authorization: Bearer ADMIN_JWT"

# EA نمی‌تواند connect کند
curl -I https://api.yourdomain.com/health/live
tail -f /var/log/nginx/access.log | grep "429"
```
