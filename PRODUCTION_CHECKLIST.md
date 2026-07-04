# ✅ چک‌لیست Production — Galaxy Vast AI Trading Platform

> این چک‌لیست را **قبل از هر بار deploy** کامل کنید.
> هیچ مرحله‌ای را رد نکنید.

---

## ⚙️ ۱. محیط و تنظیمات (Environment)

- [ ] `APP_ENV=production` تنظیم شده
- [ ] `JWT_SECRET` حداقل ۳۲ کاراکتر تصادفی دارد
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- [ ] `LICENSE_SECRET` حداقل ۳۲ کاراکتر تصادفی دارد
- [ ] `SUPABASE_URL` و `SUPABASE_SERVICE_ROLE_KEY` تنظیم شده
- [ ] `TELEGRAM_BOT_TOKEN` و `TELEGRAM_CHAT_ID` تنظیم شده
- [ ] `MT5_GATEWAY_URL` به gateway ویندوز اشاره می‌کند (نه localhost)
- [ ] `MT5_DEMO_MODE=false` تنظیم شده (برای LIVE)
- [ ] `GATEWAY_API_KEY` حداقل ۱۶ کاراکتر تصادفی دارد
- [ ] `CORS_ORIGINS` فقط شامل domain‌های واقعی است (بدون `*`)
- [ ] `ADMIN_IP_ALLOWLIST` تنظیم شده
- [ ] `SENTRY_DSN` تنظیم شده
- [ ] validator اجرا شده:
  ```bash
  python -m backend.core.startup_validator
  ```

---

## 🗄️ ۲. Database (Supabase)

- [ ] همه migration‌ها اجرا شده: `supabase db push`
- [ ] RLS (Row Level Security) فعال است روی همه جداول
- [ ] Backup خودکار Supabase فعال است
- [ ] اتصال به Supabase تست شده:
  ```bash
  python -c "from backend.database.connection import get_db; print('OK')"
  ```

---

## 🔒 ۳. امنیت

- [ ] HTTPS فعال است (reverse proxy: nginx/caddy)
- [ ] HSTS header ارسال می‌شود
- [ ] CSP header تنظیم شده
- [ ] Rate limiting فعال است
- [ ] Admin IP allowlist تنظیم شده
- [ ] JWT expiry معقول است (≤ ۶۰ دقیقه)
- [ ] هیچ secret در کد یا log نیست
- [ ] تست امنیت:
  ```bash
  pytest backend/tests/test_04_security.py -v
  ```

---

## 🖥️ ۴. MT5 Gateway (ویندوز)

- [ ] MT5 Terminal باز است و به broker وصل است
- [ ] Gateway اجرا شده:
  ```powershell
  set GATEWAY_API_KEY=your-secret-key
  set MT5_DEMO_MODE=false
  python mt5_gateway\agent.py --login YOUR_LOGIN --password YOUR_PASS --server YOUR_SERVER
  ```
- [ ] `/ping` endpoint پاسخ می‌دهد:
  ```bash
  curl -H "X-Gateway-Key: your-secret-key" http://WINDOWS_IP:8080/ping
  ```
- [ ] `mt5_connected: true` در پاسخ ping است
- [ ] یک order آزمایشی در Demo Account موفق بوده

---

## 🧪 ۵. تست‌ها

- [ ] `pytest backend/tests/test_01_smoke.py -v` — همه pass
- [ ] `pytest backend/tests/test_02_unit_execution.py -v` — همه pass
- [ ] `pytest backend/tests/test_03_integration.py -v` — همه pass
- [ ] `pytest backend/tests/test_04_security.py -v` — همه pass
- [ ] `pytest backend/tests/test_05_mt5_bridge.py -v -k "not gateway"` — همه pass
- [ ] `pytest backend/tests/test_06_e2e.py -v` — همه pass
- [ ] `pytest backend/tests/test_phase_q.py -v` — همه pass
- [ ] `pytest backend/tests/test_phase_s_live.py -m http -v` — همه pass
- [ ] `python -m compileall backend/ -q` — ۰ خطا

---

## 🖼️ ۶. Frontend

- [ ] `npm run build` بدون خطا
- [ ] `VITE_API_URL` به production backend اشاره می‌کند
- [ ] `VITE_WS_URL` به production backend اشاره می‌کند (بدون localhost)
- [ ] Login/Logout کار می‌کند
- [ ] Dashboard load می‌شود
- [ ] WebSocket در Dashboard متصل می‌شود (نشانگر سبز)

---

## 📊 ۷. Monitoring

- [ ] Sentry errors دریافت می‌شود
- [ ] Prometheus metrics در `/metrics` قابل دسترسی است
- [ ] Log‌ها در JSON format هستند
- [ ] Alert‌های drawdown تست شده

---

## 🚀 ۸. فرآیند Deploy

```bash
# ۱. کد آخرین
git pull origin main

# ۲. نصب وابستگی‌ها
pip install -r requirements.txt

# ۳. اجرای validator
python -m backend.core.startup_validator
# انتظار: همه OK یا WARNING — هیچ BLOCKED نباشد

# ۴. اجرای سرور
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --workers 2

# ۵. Health check
curl https://yourdomain.com/health
curl https://yourdomain.com/live
curl https://yourdomain.com/ready

# ۶. یک trade آزمایشی در Demo Account
# (طبق LIVE_DEPLOY_CHECKLIST.md)

# ۷. مانیتور ۲۴ ساعت قبل از LIVE
```

---

## ⚡ ۹. قبل از LIVE

- [ ] حداقل ۱ هفته روی Demo Account کامل تست شده
- [ ] Win rate روی Demo ≥ ۵۵٪
- [ ] Max drawdown روی Demo < ۵٪
- [ ] Kill Switch تست شده و کار می‌کند
- [ ] Lot size روی حداقل تنظیم شده (0.01)
- [ ] Max daily loss ≤ ۲٪ تنظیم شده
- [ ] **LIVE_DEPLOY_CHECKLIST.md** کامل اجرا شده

---

**آخرین به‌روزرسانی:** فاز U — Production Checklist کامل (فارسی)
