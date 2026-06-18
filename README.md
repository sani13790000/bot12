# 🌌 Galaxy Vast AI Trading Platform

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green)
![MQL5](https://img.shields.io/badge/MQL5-MetaTrader5-orange)
![License](https://img.shields.io/badge/License-Commercial-red)

**سیستم هوشمند معامله‌گری نهادی — سطح Hedge Fund**

*Smart Money Concept × Price Action × AI Decision Engine × Telegram Control*

</div>

---

## 🎯 معرفی سیستم

Galaxy Vast یک پلتفرم کامل معامله‌گری هوشمند است که:

- **تحلیل می‌کند** — SMC + Price Action + Multi-Timeframe
- **تصمیم می‌گیرد** — Decision Engine با امتیازدهی چندلایه
- **معامله می‌کند** — اجرای خودکار در MetaTrader 5
- **گزارش می‌دهد** — همه چیز از طریق تلگرام
- **یاد می‌گیرد** — آمار و بهبود مستمر

---

## 🏗️ معماری سیستم

```
Telegram Bot ←→ FastAPI ←→ SMC Engine
                    ↓           ↓
              Decision Engine ←→ PA Engine
                    ↓
              MQL5 EA (MT5) ←→ Broker
                    ↓
              Supabase DB + Audit Logs
```

---

## ⚡ راه‌اندازی سریع (Docker)

```bash
git clone https://github.com/sani13790000/bot12 galaxy-vast
cd galaxy-vast
cp .env.example .env
# ویرایش .env با مقادیر واقعی
nano .env
docker compose up -d
```

> 📖 راهنمای کامل: [SETUP.md](./SETUP.md)

---

## 📱 دستورات تلگرام

| دستور | کار | سطح دسترسی |
|---|---|---|
| `/start_bot` | روشن کردن ربات | OPERATOR+ |
| `/stop_bot` | خاموش کردن ربات | OPERATOR+ |
| `/pause_bot` | مکث موقت | OPERATOR+ |
| `/close_all` | بستن همه معاملات | TRADER+ |
| `/report_daily` | گزارش امروز | USER+ |
| `/winrate` | نرخ موفقیت | USER+ |
| `/add_user` | اضافه کردن کاربر | ADMIN+ |
| `/settings` | تنظیمات | ADMIN+ |

---

## 🔐 سطوح دسترسی

```
OWNER(6) → SUPER(5) → ADMIN(4) → TRADER(3) → OPERATOR(2) → USER(1) → VIEWER(0)
```

---

## 📊 قابلیت‌های تحلیل

**Smart Money Concept:**
BOS · CHOCH · MSS · Order Block · Breaker Block · FVG · IFVG
· Liquidity Sweep · Internal/External Liquidity
· Premium/Discount · Kill Zones

**Price Action:**
Pin Bar · Engulfing · Fakey · Inside Bar · Outside Bar
· Morning/Evening Star · Three Soldiers/Crows
· Breakout · Retest · Compression · Expansion

---

## 🛡️ امنیت

- JWT RS256 + Refresh Tokens
- Rate Limiting (100 req/min)
- RBAC — 7 نقش + 56 Permission
- Audit Log کامل
- License Validation آنلاین

---

## 📞 پشتیبانی

- تلگرام: @GalaxyVast_Support

---

*Galaxy Vast AI Trading Platform v2.0.0 — نسخه تجاری*
