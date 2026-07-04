# 🚀 LIVE_DEPLOY_CHECKLIST.md — اولین Trade واقعی
## Galaxy Vast AI Trading Platform

> **هشدار:** این راهنما برای اولین بار اجرای LIVE روی حساب واقعی MT5 است.
> قبل از این مرحله، `PRODUCTION_CHECKLIST.md` را کامل کنید.
> با کمترین lot size شروع کنید (0.01).

---

## 📋 پیش‌نیازها

| آیتم | وضعیت |
|------|--------|
| `PRODUCTION_CHECKLIST.md` کامل شده | [ ] |
| Demo Account حداقل ۱ هفته تست شده | [ ] |
| Win rate Demo ≥ ۵۵٪ | [ ] |
| Max drawdown Demo < ۵٪ | [ ] |
| Kill Switch تست و کار می‌کند | [ ] |
| سرمایه‌ای که توانایی از دست دادنش را دارید | [ ] |

---

## 🖥️ مرحله ۱ — آماده‌سازی ویندوز (MT5 Gateway)

```powershell
# ۱. باز کردن CMD به عنوان Administrator
# ۲. رفتن به پوشه پروژه
cd "C:\Users\BOOK 15\Downloads\bot12-main"

# ۳. تنظیم env vars
set GATEWAY_API_KEY=your-minimum-16-char-key-here
set MT5_DEMO_MODE=false
set BACKEND_URL=http://YOUR_LINUX_SERVER_IP:8000

# ۴. اجرای gateway
python mt5_gateway\agent.py --login YOUR_MT5_LOGIN --password "YOUR_MT5_PASSWORD" --server "YOUR_BROKER_SERVER"
```

**انتظار:**
```
INFO: MT5 initialized successfully
INFO: Account: YOUR_LOGIN | Balance: XXXX.XX | Leverage: 1:XXX
INFO: Uvicorn running on http://0.0.0.0:8080
```

---

## 🔍 مرحله ۲ — تأیید اتصال Gateway

```bash
# از لینوکس یا هر ماشین دیگر:
GKEY="your-minimum-16-char-key-here"
GW_URL="http://WINDOWS_IP:8080"

# Ping
curl -s -H "X-Gateway-Key: $GKEY" $GW_URL/ping | python3 -m json.tool
```

**انتظار:**
```json
{
  "status": "ok",
  "mt5_connected": true,
  "auth_required": true,
  "account_login": YOUR_LOGIN
}
```

- [ ] `mt5_connected: true` ✅
- [ ] `auth_required: true` ✅

---

## 🏦 مرحله ۳ — تأیید اطلاعات حساب

```bash
curl -s -H "X-Gateway-Key: $GKEY" $GW_URL/account | python3 -m json.tool
```

**انتظار:**
```json
{
  "balance": XXXX.XX,
  "equity": XXXX.XX,
  "margin_free": XXXX.XX,
  "leverage": 100,
  "currency": "USD"
}
```

- [ ] `balance` با موجودی واقعی مطابقت دارد ✅
- [ ] `leverage` با تنظیمات broker مطابقت دارد ✅

---

## 🗑️ مرحله ۴ — تأیید دریافت کندل‌ها

```bash
curl -s -H "X-Gateway-Key: $GKEY" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"EURUSD","timeframe":"M15","count":5}' \
  $GW_URL/candles | python3 -m json.tool
```

**انتظار:** ۵ کندل با `open`, `high`, `low`, `close`, `volume`

- [ ] کندل‌ها دریافت می‌شوند ✅
- [ ] `high >= low` برای همه کندل‌ها ✅
- [ ] timestamp‌ها معقول هستند ✅

---

## ⚙️ مرحله ۵ — تأیید Backend

```bash
BACKEND="http://YOUR_SERVER_IP:8000"

# Health
curl -s $BACKEND/health | python3 -m json.tool

# Live probe
curl -s $BACKEND/live

# Ready probe
curl -s $BACKEND/ready
```

**انتظار:**
- [ ] `/health` → `status: healthy` یا `degraded` (نه `unhealthy`) ✅
- [ ] `/live` → `status: ok` ✅
- [ ] `/ready` → `200 OK` ✅

---

## 🧪 مرحله ۶ — اجرای Live Tests

```bash
cd bot12-main
source .venv/bin/activate

export MT5_GATEWAY_URL="http://WINDOWS_IP:8080"
export GATEWAY_API_KEY="your-key-here"
export MT5_DEMO_MODE=false
export BACKEND_URL="http://localhost:8000"

# Live gateway tests
pytest backend/tests/test_phase_s_live.py -m live -v --tb=short

# Backend http tests
pytest backend/tests/test_phase_s_live.py -m http -v --tb=short
```

**انتظار:**
- [ ] `TestGatewayLive` — همه ۶ تست pass ✅
- [ ] `TestBackendLive` — همه ۵ تست pass ✅

---

## 📈 مرحله ۷ — اولین Trade آزمایشی (MANUAL)

> **مهم:** این trade را دستی و با کمترین lot size بزنید.

```bash
# باز کردن یک position دستی (EURUSD, 0.01 lot)
curl -s -X POST \
  -H "X-Gateway-Key: $GKEY" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EURUSD",
    "action": "BUY",
    "lot": 0.01,
    "sl_pips": 20,
    "tp_pips": 40,
    "comment": "live_test_U"
  }' \
  $GW_URL/order | python3 -m json.tool
```

**انتظار:**
```json
{
  "ok": true,
  "ticket": 123456789,
  "symbol": "EURUSD",
  "lot": 0.01
}
```

- [ ] `ok: true` ✅
- [ ] `ticket` عدد معتبر دارد ✅
- [ ] Position در MT5 Terminal دیده می‌شود ✅

---

## 🔒 مرحله ۸ — تست Kill Switch

```bash
# فعال‌سازی Kill Switch از Telegram Bot
# دستور: /killswitch یا /emergency_stop

# یا از API:
curl -s -X POST \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  $BACKEND/api/v1/risk/kill-switch/activate \
  -H "Content-Type: application/json" \
  -d '{"reason": "live_test"}' | python3 -m json.tool
```

- [ ] Kill Switch فعال می‌شود ✅
- [ ] Telegram alert دریافت می‌شود ✅
- [ ] هیچ trade جدیدی باز نمی‌شود ✅
- [ ] Kill Switch غیرفعال می‌شود ✅

---

## 📊 مرحله ۹ — تأیید Dashboard

```
۱. مرورگر → https://your-dashboard-domain
۲. Login با admin credentials
۳. بررسی:
```

- [ ] Dashboard load می‌شود ✅
- [ ] WebSocket متصل است (نشانگر سبز) ✅
- [ ] Trade آزمایشی در لیست trades دیده می‌شود ✅
- [ ] Balance و Equity نمایش داده می‌شود ✅

---

## 🤖 مرحله ۱۰ — فعال‌سازی Automated Trading

> **فقط بعد از موفقیت همه مراحل قبل**

```bash
# ۱. بستن trade آزمایشی دستی
curl -s -X POST \
  -H "X-Gateway-Key: $GKEY" \
  -H "Content-Type: application/json" \
  -d '{"ticket": TICKET_NUMBER, "lot": 0.01}' \
  $GW_URL/close | python3 -m json.tool

# ۲. اطمینان از Kill Switch غیرفعال
# ۳. اطمینان از scheduler فعال
# ۴. مانیتور اولین signal
```

- [ ] Trade دستی بسته شد ✅
- [ ] Kill Switch غیرفعال است ✅
- [ ] اولین signal از SMC Engine دریافت شد ✅
- [ ] اولین automated trade باز شد ✅

---

## ⚠️ مرحله ۱۱ — مانیتورینگ ۲۴ ساعت اول

```bash
# در ترمینال مجزا — log مستمر
tail -f logs/trading.log | grep -E "TRADE|ERROR|WARNING|KILL"

# بررسی drawdown هر ساعت
curl -s $BACKEND/api/v1/risk/status | python3 -m json.tool
```

**حد‌های توقف اضطراری:**
| شرط | اقدام |
|-----|-------|
| Drawdown > 3٪ | Kill Switch فعال کنید |
| ۳ loss پشت سر هم | ۲۴ ساعت توقف |
| Error rate > 10٪ | Kill Switch + بررسی logs |
| Gateway disconnect | MT5 restart |

- [ ] ۲۴ ساعت بدون مشکل بحرانی ✅
- [ ] Drawdown < 3٪ ✅
- [ ] همه alerts از Telegram دریافت شد ✅

---

## ✅ چک‌لیست نهایی LIVE

```
□ Gateway ویندوز روشن و متصل
□ Backend لینوکس در حال اجرا
□ Dashboard قابل دسترسی
□ Kill Switch آماده
□ Telegram Bot فعال
□ Supabase متصل
□ Sentry فعال
□ Lot size محافظه‌کارانه (0.01)
□ Max daily loss تنظیم شده (≤ 2٪)
□ شماره تماس broker در دسترس
```

---

**آخرین به‌روزرسانی:** فاز U — راهنمای کامل اولین LIVE trade
**نویسنده:** Galaxy Vast AI Trading Platform
