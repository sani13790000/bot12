# 🤖 MQL5_INSTALLATION.md — راهنمای نصب Expert Advisor MT5

> **نسخه:** 1.0.0 | **آخرین به‌روزرسانی:** 2026-06-18  
> **EA:** MT5TradingEA.mq5  
> **نیاز:** MetaTrader 5 Build 3000+ | Python Backend اجرا شده

---

## 📋 فهرست مطالب

1. [پیش‌نیازها](#پیش‌نیازها)
2. [کپی فایل‌های EA به MT5](#کپی-فایل‌های-ea-به-mt5)
3. [تنظیم آدرس API در Config.mqh](#تنظیم-آدرس-api)
4. [Compile کردن EA](#compile-کردن-ea)
5. [نصب EA روی چارت](#نصب-ea-روی-چارت)
6. [تنظیم پارامترهای ورودی](#تنظیم-پارامترهای-ورودی)
7. [تنظیم WebRequest در MT5](#تنظیم-webrequest)
8. [تست اتصال به API](#تست-اتصال-به-api)
9. [اجرای روی حساب Demo](#اجرای-روی-حساب-demo)
10. [لاگ‌های MT5](#لاگ‌های-mt5)
11. [عیب‌یابی](#عیب‌یابی)

---

## پیش‌نیازها

### MetaTrader 5

- **نسخه:** Build 3000 یا بالاتر (برای WebRequest کامل)
- **دانلود:** [metatrader5.com](https://www.metatrader5.com/en/download)
- **حساب:** Demo یا Real نزد یک بروکر معتبر

### Python Backend

قبل از نصب EA، مطمئن شوید:

```bash
# API اجرا شده و در دسترس است
curl http://YOUR_SERVER_IP:8000/health
# باید: {"status": "healthy"}
```

> ⚠️ **EA بدون اتصال به API کار نمی‌کند.** ابتدا DEPLOYMENT.md را دنبال کنید.

---

## کپی فایل‌های EA به MT5

### مرحله ۱: پیدا کردن پوشه Data MT5

در MT5:
```
File → Open Data Folder
```

یا دستی:
```
Windows: C:\Users\[USERNAME]\AppData\Roaming\MetaQuotes\Terminal\[HASH]\
```

### مرحله ۲: کپی فایل‌های Include

فایل‌های `mql5/Include/MT5Trading/` را به این مسیر کپی کنید:

```
[MT5 Data Folder]\MQL5\Include\MT5Trading\
```

فایل‌هایی که باید کپی شوند:
```
✅ Config.mqh
✅ Helpers.mqh
✅ DecisionConnector.mqh
✅ SMCAnalyzer.mqh
✅ PAAnalyzer.mqh
✅ RiskManager.mqh
✅ TradeManager.mqh
✅ PositionManager.mqh
✅ LicenseChecker.mqh
✅ ExecutionEngine.mqh
✅ NotificationManager.mqh
```

### مرحله ۳: کپی فایل EA

فایل `mql5/Experts/MT5Trading/MT5TradingEA.mq5` را به این مسیر کپی کنید:

```
[MT5 Data Folder]\MQL5\Experts\MT5Trading\MT5TradingEA.mq5
```

### ساختار نهایی پوشه‌ها

```
[MT5 Data Folder]\MQL5\
├── Experts\
│   └── MT5Trading\
│       └── MT5TradingEA.mq5       ← فایل اصلی EA
└── Include\
    └── MT5Trading\
        ├── Config.mqh              ← تنظیمات (آدرس API اینجاست)
        ├── Helpers.mqh
        ├── DecisionConnector.mqh
        ├── SMCAnalyzer.mqh
        ├── PAAnalyzer.mqh
        ├── RiskManager.mqh
        ├── TradeManager.mqh
        ├── PositionManager.mqh
        ├── LicenseChecker.mqh
        ├── ExecutionEngine.mqh
        └── NotificationManager.mqh
```

---

## تنظیم آدرس API

### ویرایش Config.mqh

فایل `[MT5 Data Folder]\MQL5\Include\MT5Trading\Config.mqh` را باز کنید.

**خط مربوط به API را پیدا کنید:**

```mql5
// قبل (پیش‌فرض - باید تغییر کند):
input string ApiBaseUrl = "http://YOUR_SERVER_IP:8000";
```

**آدرس واقعی سرور خود را وارد کنید:**

```mql5
// بعد از تغییر:
input string ApiBaseUrl = "http://192.168.1.100:8000";
// یا اگر دامنه دارید:
input string ApiBaseUrl = "https://api.yourdomain.com";
```

> 📝 این مقدار به عنوان input parameter در پنجره تنظیمات EA ظاهر می‌شود و بدون compile مجدد قابل تغییر است.

---

## Compile کردن EA

### در MT5 MetaEditor

1. در MT5: **Tools → MetaEditor** (یا F4)
2. در Navigator سمت چپ:
   ```
   Experts → MT5Trading → MT5TradingEA.mq5
   ```
3. دو بار کلیک کنید تا فایل باز شود
4. کلید **F7** یا دکمه **Compile** را کلیک کنید
5. در پنجره Errors/Warnings:
   ```
   ✅ 0 errors, 0 warnings → آماده نصب
   ❌ اگر خطا دیدید → بخش عیب‌یابی را ببینید
   ```

---

## نصب EA روی چارت

### مرحله ۱: انتخاب نماد و تایم‌فریم

```
نماد پیشنهادی:  XAUUSD (طلا) یا EURUSD
تایم‌فریم:      H1 (پیشنهاد) یا M15
```

### مرحله ۲: باز کردن چارت

```
File → New Chart → [نماد خود را انتخاب کنید]
```

### مرحله ۳: کشیدن EA روی چارت

در **Navigator** (Ctrl+N):
```
Expert Advisors → MT5Trading → MT5TradingEA
```

EA را **Drag & Drop** روی چارت کنید.

---

## تنظیم پارامترهای ورودی

### پارامترهای اصلی (تب Inputs)

| پارامتر | مقدار پیشنهادی | توضیح |
|---|---|---|
| `RobotEnabled` | `true` | ربات فعال باشد |
| `TradeEnabled` | `false` | **ابتدا false بگذارید!** |
| `ApiBaseUrl` | `http://YOUR_SERVER_IP:8000` | آدرس سرور API |
| `LicenseKey` | `your-license-key` | کلید لایسنس |
| `MagicNumber` | `20240101` | عدد یکتا برای این EA |

### پارامترهای مدیریت ریسک

| پارامتر | مقدار پیشنهادی | توضیح |
|---|---|---|
| `RiskPercent` | `1.0` | ریسک هر معامله (% از بالانس) |
| `MaxDailyLossPercent` | `5.0` | حداکثر ضرر روزانه |
| `MaxOpenTrades` | `3` | حداکثر پوزیشن باز همزمان |
| `MaxSpread` | `30` | حداکثر اسپرد (برای طلا: 50) |
| `MinLot` | `0.01` | حداقل حجم |
| `MaxLot` | `1.0` | حداکثر حجم |

### پارامترهای لاگ

| پارامتر | مقدار پیشنهادی | توضیح |
|---|---|---|
| `DebugMode` | `true` | نمایش لاگ در Expert tab |
| `LogToFile` | `true` | ذخیره لاگ در فایل |

### تأیید تنظیمات

- تب **Common**:
  - ✅ **Allow live trading** فعال باشد
  - ✅ **Allow DLL imports** فعال باشد

کلیک کنید: **OK**

---

## تنظیم WebRequest

> 🔴 **این مرحله بسیار مهم است!** بدون این تنظیم EA نمی‌تواند به Python Backend وصل شود.

در MT5:
```
Tools → Options → Expert Advisors
```

1. تیک **Allow WebRequest for listed URL** را بزنید
2. روی **Add** کلیک کنید
3. آدرس سرور API را وارد کنید:
   ```
   http://YOUR_SERVER_IP:8000
   ```
4. **OK** کنید

### مثال برای چند آدرس

```
http://192.168.1.100:8000
https://api.yourdomain.com
http://localhost:8000
```

---

## تست اتصال به API

### بررسی Expert Tab

بعد از نصب EA، در MT5 پنجره **Terminal** را باز کنید (Ctrl+T):

باید پیام‌های مشابه زیر ببینید:
```
[INFO] MT5TradingEA v1.0 راه‌اندازی شد
[INFO] License checked: valid
[INFO] Decision Connector initialized: http://192.168.1.100:8000
[INFO] Waiting for next candle...
```

---

## اجرای روی حساب Demo

### ترتیب توصیه‌شده

```
مرحله ۱: TradeEnabled = false
         → EA وصل می‌شود، تحلیل می‌کند، اما معامله نمی‌زند
         → لاگ‌ها را بررسی کنید (حداقل 24 ساعت)

مرحله ۲: TradeEnabled = true + حساب Demo
         → با حجم کم (MinLot = 0.01) شروع کنید
         → یک هفته روی Demo تست کنید

مرحله ۳: بررسی نتایج Demo
         → اگر رفتار مطلوب بود → حساب Real با سرمایه کم

مرحله ۴: حساب Real
         → RiskPercent = 0.5 (نیم درصد برای شروع)
         → MaxLot را محدود نگه دارید
```

### نکات مهم قبل از Real

- ⚠️ **هرگز** بدون تست کامل Demo روی Real اجرا نکنید
- ⚠️ حداقل ۱۰۰ معامله روی Demo تست کنید
- ⚠️ Drawdown تاریخچه را بررسی کنید

---

## لاگ‌های MT5

### مشاهده لاگ‌های EA

```
در MT5 Terminal (Ctrl+T):
تب "Experts" → لاگ‌های EA
تب "Journal" → لاگ‌های کلی MT5
```

### فایل لاگ

اگر `LogToFile = true` باشد:

```
[MT5 Data Folder]\MQL5\Files\MT5Trading.log
```

### فرمت لاگ

```
[2026-06-18 10:30:15] [INFO]  XAUUSD: تحلیل شروع شد
[2026-06-18 10:30:16] [INFO]  XAUUSD: SMC Score = 82.5
[2026-06-18 10:30:16] [TRADE] XAUUSD: BUY Signal | Entry=2350.00 SL=2340.00 TP=2370.00
[2026-06-18 10:30:17] [TRADE] XAUUSD: Order opened | Ticket=12345678 | Lot=0.10
```

### سطوح لاگ

| سطح | معنی |
|---|---|
| `[INFO]` | اطلاعات عادی |
| `[TRADE]` | رویدادهای معاملاتی |
| `[WARN]` | هشدار، نیاز به توجه |
| `[ERROR]` | خطا، باید بررسی شود |

---

## عیب‌یابی

### EA روی چارت ظاهر نمی‌شود

```
علت: Compile موفق نبوده
راه‌حل:
1. MetaEditor → Compile → بررسی خطاها
2. مطمئن شوید همه فایل‌های Include در مسیر درست هستند
3. MT5 را restart کنید
```

### خطای "AutoTrading disabled"

```
علت: دکمه AutoTrading در MT5 خاموش است
راه‌حل: در نوار ابزار MT5 روی دکمه "AutoTrading" کلیک کنید
        (باید سبز رنگ باشد)
```

### خطای WebRequest (error 4060)

```
علت: آدرس API در لیست مجاز MT5 نیست
راه‌حل: Tools → Options → Expert Advisors → URL را اضافه کنید
```

### خطای License

```
پیام: "License invalid or expired"
راه‌حل:
1. LicenseKey را در تنظیمات EA بررسی کنید
2. مطمئن شوید API اجرا شده
3. docker compose logs api | grep license
```

### خطای Spread

```
پیام: "Spread too high: 45 > MaxSpread: 30"
راه‌حل: MaxSpread را افزایش دهید (برای XAUUSD مقدار 50 مناسب است)
```

### معامله باز نمی‌شود

```
بررسی کنید:
1. TradeEnabled = true باشد
2. RobotEnabled = true باشد
3. لاگ Expert را بررسی کنید
4. Score پایین‌تر از MinEntryScore است؟
5. MaxOpenTrades رسیده؟
```

---

## نکات پیشرفته

### اجرای چند EA همزمان روی چند نماد

```
XAUUSD Chart: MagicNumber = 20240101
EURUSD Chart: MagicNumber = 20240102
GBPUSD Chart: MagicNumber = 20240103
```

### Backup تنظیمات

```
در پنجره تنظیمات EA:
Save → نام پروفایل → OK
```

---

*مستندات توسط تیم bot12 تهیه شده — آخرین به‌روزرسانی: 2026-06-18*
