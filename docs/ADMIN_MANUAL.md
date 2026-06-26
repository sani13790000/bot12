# 🛠️ ADMIN_MANUAL.md — راهنمای ادمین

> **نسخه:** 3.0 | **آخرین به‌روزرسانی:** 2026-06-26
> مخصوص: Admin و Super Admin

---

## 📱 Telegram Admin Bot

### Trading Control

```
/halt          ← Kill Switch — فوری همه سیگنال‌ها متوقف
/resume        ← Kill Switch غیرفعال
/status        ← وضعیت کلی سیستم
/positions     ← معاملات open
/equity        ← equity همه users
```

### License

```
/license <email>     ← وضعیت license
/suspend <email>     ← تعلیق اشتراک
/revoke <email>      ← revoke دائمی
/extend <email> 30   ← 30 روز اضافه
```

### System

```
/health        ← health check
/alerts        ← آخرین 10 alert
/metrics       ← KPI ها
/backup        ← backup فوری
```

---

## 📈 Observability

### Grafana Dashboard

```
https://grafana.yourdomain.com
Dashboards → Galaxy Vast v15
  Panel 1: Kill Switch Status
  Panel 2: License Failures/hour
  Panel 3: Heartbeat Losses/hour
  Panel 4: Active Subscriptions
  Panel 5: API Error Rate
  Panel 6: Response Time P95
  Panel 7: Drawdown Alerts
  Panel 8: Reconciliation Mismatches
```

### Structured Logs

```bash
docker compose logs api --tail=100 --follow
docker compose logs api | grep '"level":"error"'
docker compose logs api | grep '"user_id":"user_abc"'
```

---

## 🔍 Issue Trace — پیدا کردن مشکل سریع

```bash
# Timeline کامل یک user
export ADMIN_JWT="eyJ..."
curl "https://api.yourdomain.com/admin/trace?user_id=USER_ID&limit=200" \
     -H "Authorization: Bearer $ADMIN_JWT"

# فقط CRITICAL
curl "https://api.yourdomain.com/admin/trace?level=CRITICAL&limit=50" \
     -H "Authorization: Bearer $ADMIN_JWT"

# Export CSV
curl "https://api.yourdomain.com/admin/trace/export.csv" \
     -H "Authorization: Bearer $ADMIN_JWT" -o trace.csv
```

### جدول سریع — مشکل → دستور

| مشکل | دستور | زمان |
|------|-------|------|
| EA offline | `/admin/trace?event=heartbeat_loss` | 30s |
| License invalid | `/admin/licenses?user_id=X` | 15s |
| Kill Switch | `/admin/health/deep` | 10s |
| Payment مشکل | `/admin/billing?user_id=X` | 15s |

---

## 🔑 License Management

```bash
# Suspend
curl -X POST https://api.yourdomain.com/admin/licenses/LIC_ID/suspend \
     -H "Authorization: Bearer $ADMIN_JWT" \
     -d '{"reason": "payment_failure"}'

# Revoke (دائمی)
curl -X POST https://api.yourdomain.com/admin/licenses/LIC_ID/revoke \
     -H "Authorization: Bearer $ADMIN_JWT" \
     -d '{"reason": "terms_violation"}'

# تمدید دستی
curl -X POST https://api.yourdomain.com/admin/licenses/LIC_ID/extend \
     -H "Authorization: Bearer $ADMIN_JWT" \
     -d '{"days": 30}'
```

---

## 💳 Billing Management

```bash
# تأیید پرداخت دستی
curl -X POST https://api.yourdomain.com/billing/admin/confirm/INVOICE_ID \
     -H "Authorization: Bearer $ADMIN_JWT" \
     -d '{"payment_method":"manual","reference":"RECEIPT","amount":99.0,"currency":"USD"}'
```

---

## ⚠️ Risk Control

```bash
# Kill Switch فعال
curl -X POST https://api.yourdomain.com/api/v1/risk/halt \
     -H "Authorization: Bearer $ADMIN_JWT" \
     -d '{"reason": "abnormal_drawdown"}'

# وضعیت
curl https://api.yourdomain.com/api/v1/risk/kill-switch/status \
     -H "Authorization: Bearer $ADMIN_JWT"

# Resume
curl -X POST https://api.yourdomain.com/api/v1/risk/resume \
     -H "Authorization: Bearer $ADMIN_JWT"
```

---

## 📓 Runbook‌ها

### RB-001: License Failure Spike

```
علائم: > 5 license failure در 5 دقیقه

1. curl /admin/trace?event=license_failure&limit=50
   → کدام users? کدام error?

2. اگر یک user → مشکل license آن کاربر
   curl /admin/licenses?user_id=X

3. اگر همه users → مشکل سرور
   docker compose logs api | grep "license"

4. بررسی LICENSE_SALT در .env تغییر نکرده باشد
```

### RB-002: Heartbeat Loss Spike

```
علائم: EA‌ها offline می‌شوند

1. curl /health/live → API زنده است?
2. docker compose logs nginx | tail -50
3. tail -f /var/log/nginx/access.log | grep "429"  # rate limit?
4. اگر همه users → docker compose restart api nginx
```

### RB-003: Kill Switch خودکار فعال شد

```
علائم: drawdown > 10٪ → auto-trigger

1. /positions در Telegram
2. /equity بررسی کن — در چه سطحی هستی
3. اگر بازار نرمال → /resume
4. اگر بازار volatile → صبر کنید
⚠️ قبل از resume: مطمئن شوید علت رفع شده
```

### RB-004: Payment Webhook Failed

```
علائم: customer پرداخت کرده ولی license active نشد

1. curl /admin/billing?user_id=X
2. اگر event نرسیده → تأیید دستی:
   curl -X POST /billing/admin/confirm/INVOICE_ID \
        -d '{"payment_method":"manual","reference":"RECEIPT"}'
```

### RB-005: Reconciliation Mismatch

```
علائم: position در MT5 با DB تطابق ندارد

1. curl /admin/risk/reconciliation
   → کدام symbol? چقدر فرق?
2. با user تماس بگیرید — MT5 را verify کنید
3. Ghost position: curl -X POST /admin/risk/close-ghost/POS_ID
4. Missing position: curl -X POST /admin/risk/sync/USER_ID
```
