# 💼 SAAS_RELEASE_GUIDE.md — راهنمای فروش و Onboarding

> **نسخه:** 3.0 | **آخرین به‌روزرسانی:** 2026-06-26

---

## 📋 پلن‌های اشتراک

| پلن | قیمت | دوره | Device | ویژگی |
|-----|------|------|--------|-------|
| **Trial** | رایگان | ۷ روز | ۱ | همه قابلیت‌ها |
| **Basic** | $49/ماه | ماهانه | ۱ | SMC + PA + Risk |
| **Pro** | $99/ماه | ماهانه | ۳ | Basic + Multi-symbol |
| **VIP** | $199/ماه | ماهانه | ۵ | Pro + Dedicated Support |
| **Annual** | $999/سال | سالانه | ۳ | Pro + 16٪ تخفیف |

**پرداخت:** Stripe (USD) | ZarinPal (IRR) | Manual

---

## 🚀 Onboarding Customer جدید

```
۱. ثبت‌نام → Email Verification → Trial خودکار شروع (7 روز)
۲. Dashboard → Billing → Choose Plan → Checkout
۳. Payment Success Webhook → License activate
۴. Email: “License is ready” + Download link
۵. Dashboard → License → Download EA (.ex5 — فقط)
۶. MQL5_INSTALLATION.md را دنبال کنید
```

### Download Token

```bash
python3 scripts/generate_download_token.py \
    --version 3.20 \
    --zip releases/MT5TradingEA_v3.20_production_20260626.zip \
    --customer-id cust_abc123 \
    --ttl 3600

# Token: 1 ساعته — یک‌بار مصرف — HMAC-SHA256 signed
```

---

## 📦 Artifact Table — چه چیزی به Customer داده می‌شود

| Artifact | فرمت | محتوا |
|----------|------|---------|
| `MT5TradingEA_v3.20.ex5` | Compiled binary | ی۰ |
| `CHECKSUMS.txt` | Text | SHA-256 هر فایل |
| `MQL5_INSTALLATION.md` | Markdown | راهنمای نصب |
| `MANIFEST.json` | JSON | version + hash |

### تحویل داده نمی‌شود (محرمانه)

| Artifact | دلیل |
|----------|---------|
| `MT5TradingEA.mq5` | Source code — محرمانه |
| `backend/` | Python source — محرمانه |
| `frontend/` | React source — محرمانه |
| `.env` | Secrets — هرگز |

---

## 🔄 Lifecycle مشترک

```
Trial (7 روز) → ACTIVE (پرداخت) → auto-renew
                                ↓ شکست
                            PAST_DUE → 3 تلاش → SUSPENDED
                                                ↓ 30 روز
                                              REVOKED (terminal)

CANCELLED → دسترسی تا پایان دوره → EXPIRED
```

| Subscription | License | EA کار می‌کند |
|-------------|---------|---|
| TRIAL | active | ✅ |
| ACTIVE | active | ✅ |
| PAST_DUE | active | ✅ grace |
| SUSPENDED | suspended | ❌ |
| REVOKED | revoked | ❌ |
| EXPIRED | expired | ❌ |

---

## 🚪 Offboarding

```bash
# Customer cancel
Dashboard → Billing → Cancel

# Admin suspend
curl -X POST https://api.yourdomain.com/billing/admin/suspend/USER_ID \
     -H "Authorization: Bearer ADMIN_JWT"

# Admin revoke (برگشت‌ناپذیر)
curl -X POST https://api.yourdomain.com/billing/admin/revoke/USER_ID \
     -H "Authorization: Bearer ADMIN_JWT"
```

---

## ❓ FAQ فروش

**Q: آیا customer می‌تواند EA را روی چند MT5 اجرا کند?**
A: بستگی به پلن دارد — Basic: 1، Pro: 3، VIP: 5 device.

**Q: آیا source code به customer می‌رسد?**
A: **خیر.** فقط `.ex5` (binary) — source code `.mq5` محرمانه است.

**Q: اگر customer refund بخواهد?**
A: 7 روز money-back guarantee برای اولین پرداخت.

**Q: آیا نتایج گذشته تضمین آینده است?**
A: **خیر.** هیچ سودی تضمین نمی‌شود. ریسک از دست دادن سرمایه وجود دارد.

**Q: اگر customer EA را به دیگران بدهد?**
A: License شخصی است. اگر detect شود → revoke می‌شود.
