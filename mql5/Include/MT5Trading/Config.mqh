//+------------------------------------------------------------------+
//|                                                    Config.mqh     |
//|                                    MT5 Trading System             |
//|                                    پیکربندی اصلی سیستم           |
//+------------------------------------------------------------------+
#property strict

//+
// تنظیمات عمومی
//+
input string   __GENERAL__ = "=== تنظیمات عمومی ===";
input string   MagicNumber = "123456";        // شماره مجیک
input int      MaxSpread = 30;                // حداکثر اسپرد مجاز (پوینت)
input int      Slippage = 3;                  // حداکثر اسلیپیج
input bool     UseTimeFilter = true;          // استفاده از فیلتر زمانی

//+
// تنظیمات مدیریت سرمایه
//+
input string   __RISK__ = "=== مدیریت سرمایه ===";
input double   RiskPercent = 1.0;             // ریسک هر معامله (%)
input double   FixedLot = 0.0;                 // لات ثابت (0 = خودکار)
input double   MinLot = 0.01;                  // حداقل لات
input double   MaxLot = 5.0;                   // حداکثر لات
input int      MaxDailyTrades = 5;             // حداکثر معاملات روزانه
input int      MaxOpenTrades = 3;              // حداکثر معاملات همزمان

//+
// تنظیمات حد ضرر و سود
//+
input string   __SLTP__ = "=== حد ضرر و سود ===";
input int      DefaultSL = 500;               // حد ضرر پیش‌فرض (پوینت)
input int      DefaultTP = 1000;               // حد سود پیش‌فرض (پوینت)
input int      MinSL = 100;                    // حداقل حد ضرر (پوینت)
input int      MaxSL = 2000;                   // حداکثر حد ضرر (پوینت)
input bool     UseDynamicSLTP = true;          // استفاده از SL/TP داینامیک

//+
// تنظیمات مدیریت پوزیشن
//+
input string   __POSITION__ = "=== مدیریت پوزیشن ===";
input int      TrailingStop = 200;            // فاصله تریلینگ استاپ (پوینت)
input int      TrailingStep = 20;             // گام تریلینگ استاپ (پوینت)
input int      BreakEvenTrigger = 150;       // تریگر انتقال به BE (پوینت)
input int      BreakEvenOffset = 10;          // آفست BE از قیمت ورود (پوینت)
input double   PartialCloseRR = 2.0;          // R:R تریگر بستن جزئی
input double   PartialClosePercent = 50.0;    // درصد بستن جزئی

//+
// تنظیمات زمانی (Kill Zones)
//+
input string   __TIME__ = "=== Kill Zones (UTC) ===";
input bool     UseLondonKZ = true;             // استفاده از Kill Zone لندن
input int      LondonStart = 8;                // شروع لندن (UTC)
input int      LondonEnd = 11;                 // پایان لندن (UTC)
input bool     UseNYKZ = true;                  // استفاده از Kill Zone نیویورک
input int      NYStart = 13;                    // شروع نیویورک (UTC)
input int      NYEnd = 16;                      // پایان نیویورک (UTC)
input bool     UseTokyoKZ = true;               // استفاده از Kill Zone توکیو
input int      TokyoStart = 0;                  // شروع توکیو (UTC)
input int      TokyoEnd = 3;                    // پایان توکیو (UTC)

//+
// تنظیمات SMC
//+
input string   __SMC__ = "=== تنظیمات SMC ===";
input bool     EnableSMC = true;               // فعال‌سازی تحلیل SMC
input bool     RequireBOS = true;              // نیاز به BOS برای ورود
input bool     RequireCHOCH = false;           // نیاز به CHOCH برای ورود
input int      SwingLookback = 50;             // بازه جستجوی سویینگ
input double   OBThreshold = 0.1;              // آستانه تشخیص Order Block
input int      FVGMinSize = 10;                // حداقل اندازه FVG (پوینت)

//+
// تنظیمات Price Action
//+
input string   __PA__ = "=== تنظیمات Price Action ===";
input bool     EnablePA = true;               // فعال‌سازی تحلیل Price Action
input bool     RequirePinBar = false;          // نیاز به Pin Bar
input bool     RequireEngulfing = true;        // نیاز به Engulfing
input bool     RequireInsideBar = false;       // نیاز به Inside Bar
input double   PinBarBodyRatio = 0.3;          // نسبت بدنه Pin Bar
input double   EngulfingMinRatio = 1.5;        // حداقل نسبت Engulfing

//+
// تنظیمات امتیازدهی
//+
input string   __SCORING__ = "=== سیستم امتیازدهی ===";
input int      MinEntryScore = 65;             // حداقل امتیاز ورود (0-100)
input int      StrongSignalScore = 80;         // امتیاز سیگنال قوی
input int      WeakSignalScore = 50;           // امتیاز سیگنال ضعیف

//+
// تنظیمات اتصال به API
//+
input string   __API__ = "=== تنظیمات API ===";
input string   ApiBaseUrl = "http://localhost:8000/api";  // آدرس API
input int      ApiTimeout = 5000;              // تایم‌اوت API (میلی‌ثانیه)
input bool     EnableTelegram = true;          // فعال‌سازی اعلان‌های تلگرام

//+
// تنظیمات لاگ
//+
input string   __LOG__ = "=== تنظیمات لاگ ===";
input bool     EnableLogging = true;           // فعال‌سازی لاگ
input bool     LogToEmail = false;              // ارسال لاگ به ایمیل
input bool     LogToFile = true;                // ذخیره لاگ در فایل

//+
// ثابت‌های سیستم
//+
#define VERSION "1.0.0"
#define AUTHOR "MT5 Trading Team"

//+
// تایم‌فریم‌های پشتیبانی
//+
enum ENUM_TIMEFRAME_SUPPORT {
   TF_M1 = 1,
   TF_M5 = 5,
   TF_M15 = 15,
   TF_M30 = 30,
   TF_H1 = 60,
   TF_H4 = 240,
   TF_D1 = 1440,
   TF_W1 = 10080
};

//+
// ساختارهای داده
//+

// ساختار تحلیل SMC
struct SMCData {
   bool hasBOS;
   bool hasCHOCH;
   bool hasMSS;
   string trendDirection;
   bool hasOrderBlock;
   string obType;
   double obHigh;
   double obLow;
   bool hasFVG;
   double fvgHigh;
   double fvgLow;
   int smcScore;
};

// ساختارPrice Action
struct PAData {
   bool hasPinBar;
   bool hasEngulfing;
   bool hasInsideBar;
   bool hasFakey;
   string patternBias;
   int paScore;
};

// ساختار سیگنال
struct TradeSignal {
   string symbol;
   string direction;
   double entryPrice;
   double stopLoss;
   double takeProfit;
   double volume;
   int totalScore;
   bool entryAllowed;
   string reason;
   datetime validUntil;
};
//+------------------------------------------------------------------+
