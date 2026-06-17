"""
Contract خروجی Decision

این فایل ساختار خروجی Decision Engine را مستند می‌کند.
همه سیستم‌ها (MT5, Telegram, Dashboard) باید از این contract پیروی کنند.

نویسنده: MT5 Trading Team
"""

# =====================================================
# Decision Output Contract
# =====================================================

DECISION_OUTPUT_CONTRACT = """
{
    // اطلاعات پایه
    "symbol": "EURUSD",              // نماد معاملاتی (string, required)
    "timeframe": "H1",               // تایم‌فریم (string, required)
    "created_at": "2026-06-17T10:30:00",  // زمان ایجاد ISO 8601 (string, required)

    // تصمیم نهایی
    "decision": "BUY",               // BUY | SELL | NO_TRADE (string, required)
    "direction": "bullish",          // bullish | bearish | neutral (string, required)

    // امتیازها
    "confidence_score": 75,          // 0-100 اعتماد (int, required)
    "quality_score": 72,             // 0-100 کیفیت (int, required)

    // مجوز معامله
    "allowed": true,                 // آیا مجاز است (bool, required)

    // دلایل تصمیم
    "reason_codes": [                // کدهای دلیل (array of string, required)
        "SMC_BULLISH_BOS",
        "PA_BULLISH_ENGULFING"
    ],
    "reasons": [                     // توضیحات فارسی (array of string, required)
        "BOS صعودی تشکیل شد",
        "الگوی Engulfing صعودی"
    ],

    // دلایل بلاک (اگر allowed=false)
    "blocked_reasons": [             // کدهای بلاک (array of string)
        "LICENSE_INVALID",
        "RISK_EXCEEDED"
    ],

    // سطوح معاملاتی (فقط اگر decision=BUY|SELL)
    "trading_levels": {
        "entry_zone": 1.08500,       // ناحیه ورود (float)
        "entry_zone_high": 1.08530,  // بالای ناحیه ورود (float)
        "entry_zone_low": 1.08470,   // پایین ناحیه ورود (float)
        "stop_loss": 1.08250,        // حد ضرر (float)
        "take_profit_1": 1.08900,    // حد سود 1 (float)
        "take_profit_2": 1.09150,    // حد سود 2 (float, optional)
        "take_profit_3": 1.09400,    // حد سود 3 (float, optional)
        "invalidation_level": 1.08100, // سطح ابطال (float)
        "risk_reward_ratio": 2.6    // نسبت ریسک به ریوارد (float)
    },

    // پروفایل ریسک
    "risk_profile": {
        "risk_level": "medium",      // low | medium | high | extreme (string)
        "position_size": 0.01,       // حجم پیشنهادی (float)
        "max_loss_amount": 50.0,     // حداکثر ضرر (float)
        "potential_profit": 130.0,   // سود بالقوه (float)
        "risk_reward_ratio": 2.6    // نسبت R:R (float)
    },

    // تفکیک امتیازها
    "score_breakdown": {
        "smc": 75,                   // امتیاز SMC 0-100 (int)
        "price_action": 70,          // امتیاز PA 0-100 (int)
        "session": 80,               // امتیاز سشن 0-100 (int)
        "mtf": 50,                   // امتیاز چند TF 0-100 (int)
        "liquidity": 60              // امتیاز نقدینگی 0-100 (int)
    },

    // متادیتا
    "metadata": {
        "quality": "good",           // excellent | good | moderate | low | poor
        "confidence": "high",        // high | medium | low
        "conflict": false,           // آیا تعارض بود (bool)
        "block_type": null           // policy | risk | license (string or null)
    }
}
"""

# =====================================================
# Reason Codes Reference
# =====================================================

REASON_CODES = {
    # مثبت - خرید
    "SMC_BULLISH_BOS": "BOS صعودی تشکیل شد",
    "SMC_BULLISH_CHOCH": "CHOCH صعودی تشکیل شد",
    "SMC_BULLISH_MSS": "MSS صعودی تشکیل شد",
    "SMC_BULLISH_OB": "Order Block صعودی فعال",
    "SMC_BULLISH_FVG": "FVG صعودی در حال پر شدن",
    "SMC_LIQUIDITY_SWEEP_BULLISH": "اسویپ نقدینگی صعودی",
    "PA_BULLISH_ENGULFING": "الگوی Engulfing صعودی",
    "PA_BULLISH_PIN_BAR": "الگوی Pin Bar صعودی",
    "PA_BULLISH_FAKEY": "الگوی Fakey صعودی",
    "PA_SUPPORT_HOLD": "سطوح حمایتی حفظ شد",

    # مثبت - فروش
    "SMC_BEARISH_BOS": "BOS نزولی تشکیل شد",
    "SMC_BEARISH_CHOCH": "CHOCH نزولی تشکیل شد",
    "SMC_BEARISH_MSS": "MSS نزولی تشکیل شد",
    "SMC_BEARISH_OB": "Order Block نزولی فعال",
    "SMC_BEARISH_FVG": "FVG نزولی در حال پر شدن",
    "SMC_LIQUIDITY_SWEEP_BEARISH": "اسویپ نقدینگی نزولی",
    "PA_BEARISH_ENGULFING": "الگوی Engulfing نزولی",
    "PA_BEARISH_PIN_BAR": "الگوی Pin Bar نزولی",
    "PA_BEARISH_FAKEY": "الگوی Fakey نزولی",
    "PA_RESISTANCE_HOLD": "سطوح مقاومتی حفظ شد",

    # سشن و همسویی
    "KILLZONE_ACTIVE": "Kill Zone فعال است",
    "SESSION_ALIGNMENT": "همسویی سشن معاملاتی",
    "MTF_ALIGNMENT": "همسویی چند تایم‌فریم",

    # منفی - عدم معامله
    "CONFLICT_SIGNALS": "تعارض بین سیگنال‌ها",
    "LOW_QUALITY": "کیفیت سیگنال پایین",
    "INSUFFICIENT_SCORE": "امتیاز کافی نیست",
    "NO_CLEAR_DIRECTION": "جهت مشخص نیست",
    "OUTSIDE_KILLZONE": "خارج از Kill Zone",
    "HIGH_VOLATILITY": "نوسان بالا",
    "LOW_LIQUIDITY": "نقدینگی پایین",

    # بلاک
    "LICENSE_BLOCKED": "لایسنس نامعتبر",
    "SYMBOL_BLOCKED": "نماد مجاز نیست",
    "RISK_BLOCKED": "ریسک از حد مجاز بیشتر",
    "MAX_TRADES_REACHED": "حداکثر معاملات رسید",
    "COOLDOWN_ACTIVE": "دوره cooldown فعال"
}

# =====================================================
# Block Reasons
# =====================================================

BLOCK_REASONS = {
    "LICENSE_INVALID": "لایسنس نامعتبر است",
    "LICENSE_EXPIRED": "لایسنس منقضی شده است",
    "LICENSE_FEATURE_NOT_ALLOWED": "این ویژگی در لایسنس شما موجود نیست",
    "SYMBOL_NOT_ALLOWED": "معامله این نماد مجاز نیست",
    "RISK_EXCEEDED": "ریسک از حد مجاز فراتر رفته است",
    "DAILY_LOSS_LIMIT": "حد ضرر روزانه رسید",
    "MAX_POSITIONS_REACHED": "حداکثر پوزیشن‌های باز رسید",
    "MAX_TRADES_REACHED": "حداکثر معاملات روزانه رسید",
    "COOLDOWN_PERIOD": "دوره cooldown فعال است",
    "INSUFFICIENT_MARGIN": "مارجین کافی نیست"
}

# =====================================================
# API Endpoints Reference
# =====================================================

API_ENDPOINTS = """
# Health
GET  /health                    # بررسی سلامت (无需认证)
GET  /health/details            # جزئیات سلامت (无需认证)

# Decision
POST /api/v1/decision/request   # درخواست تصمیم جدید (نیاز به auth)
GET  /api/v1/decision/latest    # آخرین تصمیم‌ها (نیاز به auth)
GET  /api/v1/decision/{id}      # جزئیات تصمیم (نیاز به auth)

# Signals
GET  /api/v1/decision/signals/          # لیست سیگنال‌ها (نیاز به auth)
GET  /api/v1/decision/signals/active    # سیگنال‌های فعال (نیاز به auth)
GET  /api/v1/decision/signals/{id}      # جزئیات سیگنال (نیاز به auth)
POST /api/v1/decision/signals/{id}/execute  # علامت اجرا (نیاز به auth)
GET  /api/v1/decision/signals/stats/summary  # آمار سیگنال‌ها (نیاز به auth)

# License
POST /api/v1/license/validate   # اعتبارسنجی لایسنس (بدون auth)
POST /api/v1/license/activate   # فعال‌سازی دستگاه (بدون auth)
POST /api/v1/license/deactivate # غیرفعال‌سازی دستگاه (بدون auth)
POST /api/v1/license/feature-check  # بررسی ویژگی (بدون auth)
GET  /api/v1/license/my         # لایسنس کاربر (نیاز به auth)
GET  /api/v1/license/stats      # آمار لایسنس (نیاز به auth)

# Trade Report
GET  /api/v1/trade-report/               # لیست معاملات (نیاز به auth)
GET  /api/v1/trade-report/open            # معاملات باز (نیاز به auth)
GET  /api/v1/trade-report/{id}            # جزئیات معامله (نیاز به auth)
POST /api/v1/trade-report/report          # گزارش معامله جدید (نیاز به auth)
POST /api/v1/trade-report/{id}/close       # بستن معامله (نیاز به auth)
POST /api/v1/trade-report/close-all       # بستن همه (نیاز به auth)
GET  /api/v1/trade-report/stats/summary   # آمار معاملات (نیاز به auth)
GET  /api/v1/trade-report/stats/daily     # تفکیک روزانه (نیاز به auth)

# Dashboard
GET  /api/v1/dashboard/summary      # خلاصه داشبورد (نیاز به auth)
GET  /api/v1/dashboard/performance  # عملکرد (نیاز به auth)
GET  /api/v1/dashboard/quick-stats  # آمار سریع (نیاز به auth)
GET  /api/v1/dashboard/balance      # اطلاعات موجودی (نیاز به auth)
GET  /api/v1/dashboard/activity     # فعالیت‌ها (نیاز به auth)
"""

# =====================================================
# Integration Notes
# =====================================================

INTEGRATION_NOTES = """
# یکپارچگی با MQL5 EA

## ارسال درخواست تصمیم:
1. EA داده کندل‌ها و SMC/PA analysis را جمع‌آوری می‌کند
2. POST /api/v1/decision/request را فراخوانی می‌کند
3. Authorization: Bearer {user_token}
4. Response را پردازش و تصمیم را اجرا می‌کند

## مثال:
```mql5
string json = "{\"symbol\":\"EURUSD\",\"timeframe\":\"H1\",\"current_price\":1.0850, ...}";
string response = WebRequest("POST", "/api/v1/decision/request", json);
DecisionOutput decision = ParseDecision(response);
if(decision.decision == "BUY") {
    // اجرای معامله
}
```

# یکپارچگی با Telegram Bot

## دریافت سیگنال‌ها:
1. Bot سیگنال‌های فعال را از API می‌گیرد
2. به کاربر نمایش می‌دهد
3. کاربر می‌تواند سیگنال را اجرا کند

## گزارش معامله:
1. هنگام بسته شدن معامله
2. POST /api/v1/trade-report/report
3. اطلاعات کامل معامله ارسال می‌شود

# یکپارچگی با Dashboard

## خلاصه:
- GET /api/v1/dashboard/summary برای صفحه اصلی

## نمودارها:
- GET /api/v1/dashboard/balance برای equity curve
- GET /api/v1/trade-report/stats/daily برای تفکیک روزانه
"""
