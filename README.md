# 🤖 bot12 — سیستم معامله‌گری حرفه‌ای MetaTrader 5

[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![MQL5](https://img.shields.io/badge/MQL5-MT5-orange)](https://mql5.com)
[![License](https://img.shields.io/badge/License-Commercial-red)](LICENSE)

سیستم معامله‌گری حرفه‌ای Enterprise برای MetaTrader 5 با پشتیبانی کامل از Smart Money Concept، Price Action، Multi-Timeframe Analysis، ربات تلگرام و داشبورد مدیریتی.

---

## 🏗️ معماری سیستم

```
bot12/
├── backend/                    ← سرور Python (FastAPI)
│   ├── analysis/               ← موتورهای تحلیل بازار
│   │   ├── smc_engine.py       ← موتور Smart Money Concept
│   │   ├── price_action_engine.py ← موتور Price Action
│   │   └── decision_engine.py  ← موتور تصمیم‌گیری چندمرحله‌ای
│   ├── api/                    ← REST API endpoints
│   │   └── routes/             ← مسیرهای API
│   ├── core/                   ← هسته مشترک
│   │   ├── config.py           ← تنظیمات
│   │   ├── logger.py           ← سیستم لاگ
│   │   ├── enums.py            ← انواع داده
│   │   └── exceptions.py       ← استثناها
│   ├── database/               ← اتصال دیتابیس Supabase
│   ├── license/                ← سیستم لایسنس
│   ├── services/               ← لایه سرویس‌ها
│   └── telegram/               ← ربات تلگرام (aiogram)
│       └── handlers/           ← هندلرهای دستورات
├── frontend/                   ← داشبورد React + TypeScript
├── mql5/                       ← Expert Advisor برای MT5
│   ├── Experts/MT5Trading/     ← EA اصلی
│   └── Include/MT5Trading/     ← ماژول‌های MQL5
│       ├── TradeManager.mqh    ← مدیریت معاملات
│       ├── RiskManager.mqh     ← مدیریت ریسک
│       ├── PositionManager.mqh ← مدیریت پوزیشن
│       ├── DrawManager.mqh     ← رسم روی چارت
│       ├── DecisionConnector.mqh ← اتصال به API
│       ├── SMCAnalyzer.mqh     ← تحلیل SMC در MT5
│       └── LicenseChecker.mqh  ← بررسی لایسنس
└── supabase/migrations/        ← اسکیمای دیتابیس
```

---

## ⚡ قابلیت‌های اصلی

### 🧠 موتور Smart Money Concept
- Market Structure (BOS، CHOCH، MSS)
- Order Block، Mitigation Block، Breaker Block، Rejection Block
- FVG و IFVG
- Liquidity (Internal و External) و Liquidity Sweep
- Premium/Discount Zone و Equilibrium
- Kill Zones و Session Liquidity
- سیستم امتیازدهی چندلایه

### 📈 موتور Price Action
- ۱۴ الگوی شمعی: Pin Bar، Engulfing، Fakey، Inside/Outside Bar، Doji، Morning/Evening Star، Three Soldiers/Crows، Breakout، Retest، Compression، Expansion
- تشخیص مبتنی بر ساختار بازار
- امتیازدهی کیفیت الگو

### 🎯 موتور تصمیم‌گیری چندمرحله‌ای
- **مرحله ۱:** فیلتر اولیه (نماد، ساعت، اسپرد)
- **مرحله ۲:** تحلیل Multi-Timeframe (HTF → MTF → LTF)
- **مرحله ۳:** امتیازدهی SMC
- **مرحله ۴:** امتیازدهی Price Action
- **مرحله ۵:** فیلتر ریسک (RR، ضرر روزانه، تعداد معاملات)
- **مرحله ۶:** تصمیم نهایی (BUY / SELL / NO_TRADE)

### 📱 ربات تلگرام
| دستور | توضیح | سطح دسترسی |
|-------|--------|------------|
| `/start` | شروع و منوی اصلی | همه |
| `/stop` | توقف ربات | ادمین |
| `/status` | وضعیت فعلی | مدیر |
| `/close_all` | بستن همه معاملات | مدیر |
| `/close_buys` | بستن معاملات خرید | مدیر |
| `/close_sells` | بستن معاملات فروش | مدیر |
| `/pause` | مکث موقت | ادمین |
| `/resume` | ادامه فعالیت | ادمین |
| `/report_daily` | گزارش روزانه | کاربر |
| `/report_weekly` | گزارش هفتگی | کاربر |
| `/report_monthly` | گزارش ماهانه | کاربر |

### هشدارهای خودکار
- 🟢 ورود به معامله (با کامل‌ترین جزئیات)
- 📤 خروج از معامله
- 🛑 فعال شدن Stop Loss
- 🎯 رسیدن به Take Profit
- 🌍 باز/بسته شدن سشن‌های معاملاتی

---

## 🚀 نصب و راه‌اندازی

### پیش‌نیازها
- Python 3.13+
- Node.js 20+
- MetaTrader 5
- حساب Supabase

### مرحله ۱: کلون ریپو
```bash
git clone https://github.com/sani13790000/bot12.git
cd bot12
```

### مرحله ۲: تنظیم متغیرهای محیطی
```bash
cp .env.example .env
# فایل .env را با مقادیر واقعی پر کنید
```

### مرحله ۳: نصب وابستگی‌ها
```bash
pip install -r requirements.txt
```

### مرحله ۴: اجرای مهاجرت دیتابیس
```bash
supabase db push
```

### مرحله ۵: اجرای سرور
```bash
uvicorn backend.api.main:app --reload --port 8000
```

### مرحله ۶: اجرا با Docker
```bash
docker-compose up -d
```

---

## ⚙️ تنظیمات MQL5

1. فایل‌های `mql5/Include/MT5Trading/` را به `MetaTrader5/MQL5/Include/MT5Trading/` کپی کنید
2. فایل `mql5/Experts/MT5Trading/MT5TradingEA.mq5` را به `MetaTrader5/MQL5/Experts/` کپی کنید
3. در MT5، کامپایل کرده و EA را روی چارت اضافه کنید
4. آدرس API را در تنظیمات EA وارد کنید

---

## 🔐 سیستم لایسنس

هر کاربر یک لایسنس جداگانه دارد که شامل:
- تاریخ انقضا
- تعداد نمادهای مجاز
- ماژول‌های فعال
- سطح دسترسی

---

## 📊 ساختار دیتابیس

| جدول | توضیح |
|------|--------|
| `users` | کاربران سیستم |
| `licenses` | لایسنس‌های کاربران |
| `trades` | سابقه معاملات |
| `signals` | سیگنال‌های تولید شده |
| `analysis_logs` | لاگ‌های تحلیل |
| `audit_logs` | لاگ‌های امنیتی |

---

## 🛡️ امنیت

- JWT Authentication
- RBAC (Role-Based Access Control) در تلگرام
- Rate Limiting روی API
- رمزنگاری لایسنس
- Audit Log کامل

---

## 📞 پشتیبانی

برای پشتیبانی و خرید لایسنس با تیم تماس بگیرید.

---

*نسخه ۲.۰.۰ | MT5 Trading Team*
