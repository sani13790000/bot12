# 🚀 DEPLOYMENT.md — راهنمای کامل استقرار bot12

> **نسخه:** 1.0.0 | **آخرین به‌روزرسانی:** 2026-06-18  
> **سیستم:** Enterprise MT5 Trading Ecosystem  
> **معماری:** Python FastAPI + Telegram Bot + React Dashboard + MQL5 EA

---

## 📋 فهرست مطالب

1. [پیش‌نیازها](#پیش‌نیازها)
2. [استقرار با Docker (توصیه‌شده)](#استقرار-با-docker)
3. [استقرار دستی (بدون Docker)](#استقرار-دستی)
4. [تنظیم Supabase](#تنظیم-supabase)
5. [تنظیم فایل .env](#تنظیم-فایل-env)
6. [راه‌اندازی Telegram Bot](#راه‌اندازی-telegram-bot)
7. [راه‌اندازی React Dashboard](#راه‌اندازی-react-dashboard)
8. [نصب MQL5 EA](#نصب-mql5-ea)
9. [تأیید سلامت سیستم](#تأیید-سلامت-سیستم)
10. [عیب‌یابی](#عیب‌یابی)
11. [به‌روزرسانی و Rollback](#به‌روزرسانی-و-rollback)

---

## پیش‌نیازها

### سرور Linux (Ubuntu 22.04 LTS توصیه‌شده)

| منبع | حداقل | توصیه‌شده |
|---|---|---|
| CPU | 2 core | 4 core |
| RAM | 2 GB | 4 GB |
| Disk | 20 GB SSD | 40 GB SSD |
| OS | Ubuntu 20.04+ | Ubuntu 22.04 LTS |
| پورت‌های باز | 22, 80, 443, 8000 | 22, 80, 443, 8000, 3000 |

### نرم‌افزارهای لازم

```bash
# Docker و Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
sudo apt-get install -y docker-compose-plugin

# Git
sudo apt-get install -y git

# تأیید نصب
docker --version        # باید 24.x+ باشد
docker compose version  # باید 2.x+ باشد
git --version
```

---

## استقرار با Docker

### مرحله ۱: دریافت کد

```bash
git clone https://github.com/sani13790000/bot12.git
cd bot12
```

### مرحله ۲: ساخت فایل .env

```bash
cp .env.example .env
nano .env
```

> ⚠️ **مهم:** تمام مقادیر `REPLACE_WITH_...` را با مقادیر واقعی جایگزین کنید.

```bash
# JWT_SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# LICENSE_ENCRYPTION_KEY (دقیقاً ۳۲ کاراکتر)
python3 -c "import secrets; print(secrets.token_hex(16))"

# LICENSE_SIGNATURE_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# API_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### مرحله ۳: Build و اجرا

```bash
# Build همه container ها
docker compose build --no-cache

# اجرا در پس‌زمینه
docker compose up -d

# مشاهده لاگ‌ها
docker compose logs -f
```

### مرحله ۴: تأیید اجرا

```bash
# وضعیت container ها
docker compose ps

# باید خروجی مشابه زیر داشته باشید:
# NAME                STATUS          PORTS
# bot12_api           Up (healthy)    0.0.0.0:8000->8000/tcp
# bot12_telegram      Up
# bot12_redis         Up (healthy)    0.0.0.0:6379->6379/tcp
# bot12_frontend      Up              0.0.0.0:3000->80/tcp

# تست health check
curl http://localhost:8000/health
# باید: {"status": "healthy", ...}
```

---

## استقرار دستی

### مرحله ۱: نصب Python 3.13

```bash
sudo apt-get update
sudo apt-get install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get install -y python3.13 python3.13-venv python3.13-dev

python3.13 --version  # Python 3.13.x
```

### مرحله ۲: ایجاد محیط مجازی

```bash
cd bot12
python3.13 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

### مرحله ۳: تنظیم .env

```bash
cp .env.example .env
nano .env  # مقادیر را پر کنید
```

### مرحله ۴: اجرای API

```bash
source venv/bin/activate
export $(cat .env | xargs)

uvicorn backend.api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 2 \
    --log-level info
```

### مرحله ۵: اجرای Telegram Bot (terminal جداگانه)

```bash
source venv/bin/activate
export $(cat .env | xargs)

python -m backend.telegram.run
```

### مرحله ۶: اجرا با systemd (production)

```bash
sudo nano /etc/systemd/system/bot12-api.service
```

```ini
[Unit]
Description=bot12 Trading API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/bot12
EnvironmentFile=/opt/bot12/.env
ExecStart=/opt/bot12/venv/bin/uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable bot12-api
sudo systemctl start bot12-api
sudo systemctl status bot12-api
```

---

## تنظیم Supabase

### مرحله ۱: ایجاد پروژه Supabase

1. به [app.supabase.com](https://app.supabase.com) بروید
2. **New Project** → نام پروژه، رمز عبور قوی، region نزدیک‌ترین
3. صبر کنید تا پروژه آماده شود (~2 دقیقه)

### مرحله ۲: دریافت کلیدها

1. **Settings** → **API**
2. مقادیر زیر را کپی کنید:
   - `Project URL` → `SUPABASE_URL`
   - `anon public` → `SUPABASE_ANON_KEY`
   - `service_role secret` → `SUPABASE_SERVICE_ROLE_KEY`

### مرحله ۳: اجرای Migration

1. **SQL Editor** در Supabase Dashboard
2. محتوای فایل‌های `supabase/migrations/` را کپی و اجرا کنید

### مرحله ۴: تنظیم RLS

```sql
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
```

### مرحله ۵: دریافت Database URL

1. **Settings** → **Database** → **Connection string** → **URI**
2. در `.env` به عنوان `SUPABASE_DB_URL` وارد کنید

---

## تنظیم فایل .env

```bash
# ===== تلگرام =====
TELEGRAM_BOT_TOKEN=1234567890:AABBccDDeeFFggHH-your-actual-token
TELEGRAM_ADMIN_CHAT_IDS=123456789,987654321

# ===== Supabase =====
SUPABASE_URL=https://abcdefghijklm.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_DB_URL=postgresql://postgres:[PASSWORD]@db.abcdef.supabase.co:5432/postgres

# ===== API =====
API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=<خروجی secrets.token_urlsafe(32)>
API_DEBUG=false
API_BASE_URL=http://YOUR_SERVER_IP:8000

# ===== امنیت JWT =====
JWT_SECRET_KEY=<خروجی secrets.token_hex(32)>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# ===== لایسنس =====
LICENSE_SECRET_KEY=your_license_secret
LICENSE_ENCRYPTION_KEY=<دقیقاً ۳۲ کاراکتر>
LICENSE_SIGNATURE_KEY=<خروجی secrets.token_hex(32)>

# ===== CORS =====
CORS_ORIGINS=https://yourdomain.com,http://YOUR_SERVER_IP:3000

# ===== Redis =====
REDIS_URL=redis://localhost:6379/0

# ===== لاگ =====
LOG_LEVEL=INFO
LOG_FILE_PATH=logs/bot12.log

# ===== معاملات =====
DEFAULT_RISK_PERCENT=1.0
MAX_DAILY_LOSS_PERCENT=5.0
MAX_SIMULTANEOUS_TRADES=3
MIN_RISK_REWARD_RATIO=1.5
MINIMUM_ENTRY_SCORE=65.0
```

---

## راه‌اندازی Telegram Bot

### مرحله ۱: ایجاد Bot

1. به **@BotFather** در تلگرام پیام بدهید
2. `/newbot` → نام انتخاب کنید
3. **Token** را دریافت کنید → در `.env` وارد کنید

### مرحله ۲: دریافت Chat ID ادمین

```
1. به @userinfobot پیام بدهید
2. عدد "Id" را کپی کنید
3. در TELEGRAM_ADMIN_CHAT_IDS وارد کنید
```

### مرحله ۳: تأیید اجرای Bot

```bash
docker compose logs telegram_bot -f
# باید ببینید:
# INFO: Bot started successfully
# INFO: Polling started
```

---

## راه‌اندازی React Dashboard

### با Docker (خودکار)

Dashboard به صورت خودکار روی پورت `3000` اجرا می‌شود:
```
http://YOUR_SERVER_IP:3000
```

### بدون Docker

```bash
cd frontend
npm install

# تنظیم API URL
echo "VITE_API_URL=http://YOUR_SERVER_IP:8000" > .env.production

npm run build
# فایل‌های build در dist/ قرار می‌گیرند
```

---

## تأیید سلامت سیستم

```bash
# ۱. API
curl http://localhost:8000/health
# انتظار: {"status":"healthy","version":"1.0.0"}

# ۲. Redis
docker exec bot12_redis redis-cli ping
# انتظار: PONG

# ۳. تست Rate Limiting
for i in {1..5}; do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health; done
# باید: 200 200 200 200 200

# ۴. لاگ‌های API
docker compose logs api --tail=50

# ۵. لاگ‌های Bot
docker compose logs telegram_bot --tail=50
```

---

## عیب‌یابی

### مشکل ۱: API راه‌اندازی نمی‌شود

```bash
docker compose logs api
# خطای "JWT_SECRET_KEY is required" → فایل .env را بررسی کنید
# خطای اتصال به Supabase → SUPABASE_URL و کلیدها را چک کنید
```

### مشکل ۲: Telegram Bot وصل نمی‌شود

```bash
# بررسی token
curl https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe
# اگر {"ok":false} → token اشتباه است

# بررسی API_BASE_URL در docker-compose
# باید: API_BASE_URL=http://api:8000
```

### مشکل ۳: Docker Compose fail

```bash
docker compose down -v
docker system prune -f
docker compose build --no-cache
docker compose up -d
```

---

## به‌روزرسانی و Rollback

### به‌روزرسانی

```bash
git pull origin main
docker compose build --no-cache
docker compose up -d --force-recreate
docker compose ps
curl http://localhost:8000/health
```

### Rollback

```bash
git log --oneline -10
git checkout <commit-hash>
docker compose build --no-cache
docker compose up -d --force-recreate
```

---

## 🔒 نکات امنیتی Production

1. **هرگز** فایل `.env` را commit نکنید
2. **Firewall** را تنظیم کنید — فقط پورت‌های ضروری باز باشند
3. **SSL/TLS** با Nginx reverse proxy تنظیم کنید
4. **CORS_ORIGINS** را فقط به دامنه‌های مجاز محدود کنید
5. JWT و License کلیدها را هر ۹۰ روز تجدید کنید

```bash
# نمونه تنظیم UFW
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8000/tcp
sudo ufw enable
```

---

*مستندات توسط تیم bot12 تهیه شده — آخرین به‌روزرسانی: 2026-06-18*
