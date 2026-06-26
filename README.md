# 🌌 Galaxy Vast AI Trading Platform

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)
![MQL5](https://img.shields.io/badge/MQL5-MetaTrader5-orange)
![License](https://img.shields.io/badge/License-Commercial-red)
![Tests](https://img.shields.io/badge/Tests-1286%20PASS-brightgreen)
![Phases](https://img.shields.io/badge/Phases-1--18%20Complete-purple)

**سیستم هوشمند معامله‌گری نهادی — سطح Hedge Fund**

*Smart Money Concept × Price Action × AI Decision Engine × Telegram Control × SaaS License*

</div>

---

> ⚠️ **هشدار ریسک معامله‌گری — اجباری**
>
> این نرم‌افزار صرفاً یک ابزار اتوماسیون است و **هیچ سودی را تضمین نمی‌کند**.
> معامله در بازارهای مالی (Forex، سهام، کریپتو) با ریسک بسیار بالا همراه است.
> **ممکن است تمام سرمایه خود را از دست بدهید.**
> این نرم‌افزار مشاوره مالی یا سرمایه‌گذاری نیست.
> قبل از استفاده با یک مشاور مالی واجد شرایط مشورت کنید.
> فقط با سرمایه‌ای که توانایی از دست دادنش را دارید معامله کنید.

---

## 📋 فهرست مطالب

1. [معرفی سیستم](#معرفی-سیستم)
2. [معماری](#معماری)
3. [راه‌اندازی سریع](#راه‌اندازی-سریع)
4. [مستندات](#مستندات)
5. [وضعیت Phases](#وضعیت-phases)
6. [تست‌ها](#تستها)

---

## 🎯 معرفی سیستم

Galaxy Vast یک پلتفرم SaaS کامل معامله‌گری هوشمند است:

| قابلیت | توضیح |
|--------|-------|
| **تحلیل بازار** | SMC + Price Action + Multi-Timeframe + Order Block |
| **تصمیم‌گیری** | Decision Engine با امتیازدهی چندلایه |
| **اجرای معامله** | MetaTrader 5 EA — خودکار و ایمن |
| **مدیریت ریسک** | Kill Switch + Drawdown Limit + Position Size Cap |
| **SaaS License** | Trial/Basic/Pro/VIP — license per device |
| **Admin Control** | Telegram Bot + Admin Dashboard |
| **امنیت** | AES-256-GCM + JWT + RLS + RBAC |
| **Observability** | Prometheus + Grafana + Structured Logging |

---

## 🏗️ معماری

```
┌─────────────────────────────────────────────────────────┐
│                    Internet / Customers                  │
└───────────────────┬────────────────────┬────────────────┘
                    │                    │
              ┌─────▼──────┐    ┌────────▼───────┐
              │  nginx:443  │    │  MT5 / EA.ex5  │
              │ TLS+HSTS+CSP│    │  (Customer PC) │
              └─────┬──────┘    └────────┬───────┘
                    │                    │ HTTPS
         ┌──────────┼──────────┐         │
         │          │          │         │
   ┌─────▼───┐ ┌────▼────┐ ┌──▼──────┐  │
   │frontend │ │dashboard│ │   api   │◄─┘
   │ :80     │ │ :8501   │ │  :8000  │
   └─────────┘ └─────────┘ └────┬────┘
                                 │
                    ┌────────────┼──────────────┐
                    │            │              │
              ┌─────▼───┐ ┌─────▼──┐ ┌────────▼────┐
              │Supabase │ │ Redis  │ │  Telegram   │
              │  + RLS  │ │ Cache  │ │    Bot      │
              └─────────┘ └────────┘ └─────────────┘
```

---

## ⚡ راه‌اندازی سریع

```bash
# 1. Clone
git clone https://github.com/sani13790000/bot12 galaxy-vast
cd galaxy-vast

# 2. Environment
cp .env.example .env
# ویرایش .env — همه CHANGE_ME را پر کنید

# 3. Generate secrets
python3 -c "import secrets; print('SECRETS_MASTER_KEY=' + secrets.token_hex(32))"
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_hex(32))"

# 4. Docker
python3 startup_check.py
docker compose up -d --build

# 5. Verify
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

> برای Production کامل: [DEPLOYMENT.md](DEPLOYMENT.md)

---

## 📚 مستندات

| فایل | موضوع |
|------|-------|
| [DEPLOYMENT.md](DEPLOYMENT.md) | نصب dev / staging / production کامل |
| [SECURITY.md](SECURITY.md) | معماری امنیتی + گزارش vulnerability |
| [MQL5_INSTALLATION.md](MQL5_INSTALLATION.md) | نصب EA در MetaTrader 5 |
| [docs/SAAS_RELEASE_GUIDE.md](docs/SAAS_RELEASE_GUIDE.md) | راهنمای فروش SaaS + onboarding |
| [docs/ADMIN_MANUAL.md](docs/ADMIN_MANUAL.md) | راهنمای ادمین + trace + alert |
| [docs/RELEASE_GOVERNANCE.md](docs/RELEASE_GOVERNANCE.md) | artifact + token + checksum policy |

---

## 📊 وضعیت Phases

| Phase | موضوع | تست‌ها | وضعیت |
|-------|-------|--------|--------|
| P1-P5 | Core Engine (SMC+PA+Decision+Risk+MT5) | — | ✅ |
| P6 | License System | 96 | ✅ |
| P7 | Telegram Bot | — | ✅ |
| P8 | Auth + RBAC | 92 | ✅ |
| P9 | Dashboard | 88 | ✅ |
| P10 | Billing | 96 | ✅ |
| P11 | Secrets + Encryption | 88 | ✅ |
| P12 | API Security Hardening | 96 | ✅ |
| P13 | Database Hardening | 96 | ✅ |
| P14 | Source Protection + Release | 96 | ✅ |
| P15 | CI/CD + Observability | 210 | ✅ |
| P16 | Full Test Coverage | 232 | ✅ |
| P17 | Docker + Deployment | 96 | ✅ |
| P18 | Documentation | 103 | ✅ |
| **جمع** | | **1,389** | **✅** |

---

## 🧪 تست‌ها

```bash
cd backend
PYTHONPATH=. python -m pytest tests/ -v --tb=short
PYTHONPATH=. python -m pytest tests/ --cov=. --cov-fail-under=70
```

---

## ⚠️ هشدارهای مهم

1. **ریسک مالی**: سیستم می‌تواند در شرایط خاص بازار ضرر کند
2. **حساب Demo اول**: همیشه اول روی Demo تست کنید — حداقل ۳۰ روز
3. **Kill Switch**: آماده باشید فوری متوقف کنید — `/halt` در Telegram
4. **Drawdown Limit**: حداکثر ۱۰٪ تنظیم کنید — هرگز بالاتر
5. **Broker Risk**: انتخاب بروکر معتبر با regulation معتبر ضروری است
6. **Source Code**: هرگز `.mq5` source را با customer share نکنید — فقط `.ex5`
