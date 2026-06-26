# 🤖 MQL5_INSTALLATION.md — راهنمای نصب Expert Advisor MT5

> **نسخه:** 3.0 | **آخرین به‌روزرسانی:** 2026-06-26
> **EA:** MT5TradingEA.ex5 (compiled only — source محرمانه است)

---

> ⚠️ **هشدار مهم — حتماً بخوانید**
>
> - این EA **تضمین سود نمی‌دهد** — ریسک از دست دادن سرمایه وجود دارد
> - **اول روی Demo** حداقل ۳۰ روز تست کنید — سپس Real
> - **Drawdown Limit را ۱۰٪ تنظیم کنید** — هرگز بالاتر
> - **Kill Switch را بشناسید**: Telegram `/halt` را حفظ کنید

---

## 📋 فهرست مطالب

1. [پیش‌نیازها](#پیش‌نیازها)
2. [دریافت فایل EA](#دریافت-فایل-ea)
3. [نصب در MetaTrader 5](#نصب-در-metatrader-5)
4. [تنظیم پارامترها](#تنظیم-پارامترها)
5. [تنظیم WebRequest](#تنظیم-webrequest)
6. [تست اتصال](#تست-اتصال)
7. [اجرا روی Demo](#اجرا-روی-demo)
8. [عیب‌یابی](#عیب‌یابی)

---

## پیش‌نیازها

```
MetaTrader 5: Build 3000+
دانلود: https://www.metatrader5.com/en/download
حساب: Demo اول (حداقل ۳۰ روز)

Backend:
curl https://api.yourdomain.com/health/live  # باید: {"status":"alive"}

License:
Dashboard → License → وضعیت باید "active" باشد
```

---

## دریافت فایل EA

```bash
# از Dashboard:
https://dashboard.yourdomain.com → Downloads → Download EA

# Verify checksum:
sha256sum MT5TradingEA_v3.20.ex5
# باید با checksum در Dashboard مطابقت داشته باشد

# یا با verify script:
python3 scripts/verify_release.py MT5TradingEA_v3.20_production_20260626.zip
```

⚠️ فقط `.ex5` دانلود می‌شود — source code `.mq5` محرمانه است و به customer داده نمی‌شود.

---

## نصب در MetaTrader 5

```
1. File → Open Data Folder
2. MQL5 → Experts
3. فایل MT5TradingEA.ex5 را کپی کنید (فقط .ex5)
4. MT5 → Navigator → راست‌کلیک Expert Advisors → Refresh
5. MT5TradingEA را drag کنید روی chart
```

---

## تنظیم پارامترها

### تب Common
```
☑️ Allow live trading
```

### تب Inputs

| پارامتر | مقدار پیشنهادی | توضیح |
|---------|---------------|-------|
| `ApiBaseUrl` | `https://api.yourdomain.com` | آدرس backend |
| `LicenseKey` | `LK-XXXX-XXXX-XXXX-XXXX` | از Dashboard |
| `MaxLotSize` | `0.01` | شروع با حداقل |
| `MaxDrawdownPct` | `10.0` | Kill Switch trigger |
| `RiskPerTrade` | `1.0` | ۱٪ از balance |
| `HeartbeatInterval` | `60` | ثانیه |

---

## تنظیم WebRequest

**اجباری** — بدون این EA نمی‌تواند به backend وصل شود:

```
Tools → Options → Expert Advisors
☑️ Allow WebRequest for listed URL:
  https://api.yourdomain.com
OK
```

---

## تست اتصال

```
View → Terminal (Ctrl+T) → تب Experts

باید ببینید:
[INFO] MT5TradingEA: ✅ License verified: active
[INFO] MT5TradingEA: ✅ Device registered
[INFO] MT5TradingEA: ✅ Ready — waiting for signals
[INFO] MT5TradingEA: ♥ Heartbeat sent
```

---

## اجرا روی Demo

### ۳۰ روز Demo اجباری

```
شاخص‌های موفقیت:
  ✅ Net Profit > 0
  ✅ Max Drawdown < 10٪
  ✅ Profit Factor > 1.3
  ✅ بدون crash
```

### چک‌لیست قبل از Real Account

- [ ] ۳۰ روز Demo با نتایج مثبت
- [ ] Kill Switch را تست کردید (`/halt` و `/resume`)
- [ ] Drawdown Limit را تجربه کردید
- [ ] با مشاور مالی مشورت کردید
- [ ] فقط با سرمایه‌ای که توانایی از دست دادنش را دارید

---

## عیب‌یابی

| مشکل | راه‌حل |
|------|-------|
| EA attach نمی‌شود | MT5 restart + F4 → Refresh |
| ERR_WEBREQUEST | Tools → Options → WebRequest URL اضافه کن |
| License Invalid | LicenseKey را از Dashboard کپی کن (بدون فضای اضافه) |
| Device Limit | Dashboard → License → Device قدیمی را Revoke کن |
| Heartbeat Failed | بررسی اینترنت + `curl https://api.yourdomain.com/health/live` |

---

## Update EA

```
1. EA را از chart detach کنید
2. MT5 را ببندید
3. فایل .ex5 جدید را از Dashboard دانلود کنید
4. در MQL5\Experts جایگزین کنید
5. MT5 باز کنید + attach کنید
```
