//+------------------------------------------------------------------+
//|                                                    Config.mqh      |
//|                         سیستم معامله‌گری حرفه‌ای MT5               |
//|                                                                    |
//| توضیح فارسی:                                                       |
//| این فایل شامل تمام تنظیمات قابل تغییر سیستم معامله‌گری است.        |
//| تمام پارامترها از اینجا خوانده می‌شوند و قابل تنظیم هستند.         |
//| هر گروه از تنظیمات با توضیح فارسی مشخص شده است.                   |
//+------------------------------------------------------------------+
#property strict

//+------------------------------------------------------------------+
//| ===== تنظیمات اصلی ربات =====                                      |
//+------------------------------------------------------------------+
input string   RobotName         = "MT5TradingSystem";  // نام ربات
input int      MagicNumber        = 20240101;            // شماره جادویی
input bool     RobotEnabled       = true;                // ربات فعال باشد
input bool     TradeEnabled       = true;                // معامله فعال باشد

//+------------------------------------------------------------------+
//| ===== تنظیمات نماد =====                                           |
//+------------------------------------------------------------------+
input string   AllowedSymbol      = "XAUUSD";            // نماد مجاز (خالی = نماد فعال)
input bool     UseCurrentSymbol   = true;                // از نماد فعال چارت استفاده کن

//+------------------------------------------------------------------+
//| ===== تنظیمات مدیریت ریسک =====                                   |
//+------------------------------------------------------------------+
input double   RiskPercent        = 1.0;                 // درصد ریسک هر معامله
input double   FixedLot           = 0.0;                 // لات ثابت (0 = محاسبه اتوماتیک)
input double   MinLot             = 0.01;                // حداقل لات
input double   MaxLot             = 10.0;                // حداکثر لات
input bool     UseEquityForRisk   = false;               // استفاده از اکوئیتی برای ریسک
input double   MaxDailyLossPercent = 5.0;                // حداکثر ضرر روزانه (%)
input double   MaxDrawdownPercent = 10.0;                // حداکثر drawdown (%)
input int      MaxOpenTrades      = 3;                   // حداکثر معاملات باز
input int      MaxDailyTrades     = 10;                  // حداکثر معاملات روزانه
input int      MaxSpread          = 30;                  // حداکثر اسپرد مجاز (پوینت)

//+------------------------------------------------------------------+
//| ===== تنظیمات SL/TP =====                                         |
//+------------------------------------------------------------------+
input double   DefaultRR          = 2.0;                 // نسبت پیش‌فرض سود به ریسک
input double   ATRMultiplierSL    = 1.5;                 // ضریب ATR برای StopLoss
input double   ATRMultiplierTP    = 3.0;                 // ضریب ATR برای TakeProfit
input int      ATRPeriod          = 14;                  // دوره ATR
input double   MinRR              = 1.5;                 // حداقل نسبت سود به ریسک

//+------------------------------------------------------------------+
//| ===== تنظیمات Trailing Stop و Break Even =====                    |
//+------------------------------------------------------------------+
input bool     UseTrailingStop    = true;                // استفاده از Trailing Stop
input double   TrailingPoints     = 200;                 // فاصله Trailing Stop (پوینت)
input double   TrailingStep       = 50;                  // گام جابجایی Trailing (پوینت)
input bool     UseBreakEven       = true;                // استفاده از Break Even
input double   BreakEvenTrigger   = 100;                 // فعال شدن BE بعد از (پوینت)
input double   BreakEvenOffset    = 5;                   // بافر Break Even (پوینت)

//+------------------------------------------------------------------+
//| ===== تنظیمات Smart Money Concept =====                            |
//+------------------------------------------------------------------+
input bool     SMCEnabled         = true;                // SMC فعال باشد
input bool     DetectBOS          = true;                // تشخیص Break of Structure
input bool     DetectCHOCH        = true;                // تشخیص Change of Character
input bool     DetectOrderBlocks  = true;                // تشخیص Order Block
input bool     DetectFVG          = true;                // تشخیص Fair Value Gap
input bool     DetectLiquidity    = true;                // تشخیص نقدینگی
input bool     DetectKillZones    = true;                // تشخیص Kill Zones
input int      SMCLookback        = 100;                 // تعداد کندل برای بررسی SMC
input double   MinSMCScore        = 60.0;                // حداقل امتیاز SMC برای ورود
input bool     SMCMultiTimeframe  = true;                // بررسی چند تایم‌فریم

//+------------------------------------------------------------------+
//| ===== تنظیمات Price Action =====                                   |
//+------------------------------------------------------------------+
input bool     PAEnabled          = true;                // Price Action فعال باشد
input bool     DetectPinBar       = true;                // تشخیص Pin Bar
input bool     DetectEngulfing    = true;                // تشخیص Engulfing
input bool     DetectFakey        = true;                // تشخیص Fakey
input bool     DetectInsideBar    = true;                // تشخیص Inside Bar
input double   MinPAScore         = 50.0;                // حداقل امتیاز PA برای ورود
input int      PALookback         = 50;                  // تعداد کندل برای بررسی PA

//+------------------------------------------------------------------+
//| ===== تنظیمات Decision Engine =====                                |
//+------------------------------------------------------------------+
input double   MinTotalScore      = 65.0;                // حداقل امتیاز کل برای ورود
input double   WeightSMC          = 0.35;                // وزن امتیاز SMC
input double   WeightMTF          = 0.25;                // وزن همسویی تایم‌فریم
input double   WeightPA           = 0.20;                // وزن امتیاز Price Action
input double   WeightRisk         = 0.10;                // وزن ریسک
input double   WeightSession      = 0.10;                // وزن سشن

//+------------------------------------------------------------------+
//| ===== تنظیمات Multi-Timeframe =====                               |
//+------------------------------------------------------------------+
input ENUM_TIMEFRAMES HTF_Period  = PERIOD_H4;           // تایم‌فریم بالا (HTF)
input ENUM_TIMEFRAMES MTF_Period  = PERIOD_H1;           // تایم‌فریم میانی (MTF)
input ENUM_TIMEFRAMES LTF_Period  = PERIOD_M15;          // تایم‌فریم پایین (LTF)
input bool     RequireHTFAlign    = true;                // الزام همسویی HTF
input bool     RequireMTFAlign    = true;                // الزام همسویی MTF

//+------------------------------------------------------------------+
//| ===== تنظیمات فیلتر زمانی و سشن =====                            |
//+------------------------------------------------------------------+
input bool     UseTimeFilter      = true;                // فیلتر زمانی فعال باشد
input bool     TradeAsianSession  = false;               // معامله در سشن آسیا
input bool     TradeLondonSession = true;                // معامله در سشن لندن
input bool     TradeNYSession     = true;                // معامله در سشن نیویورک
input int      LondonOpenHour     = 8;                   // ساعت باز شدن لندن (UTC)
input int      LondonCloseHour    = 17;                  // ساعت بسته شدن لندن (UTC)
input int      NYOpenHour         = 13;                  // ساعت باز شدن نیویورک (UTC)
input int      NYCloseHour        = 22;                  // ساعت بسته شدن نیویورک (UTC)
input int      AsianOpenHour      = 23;                  // ساعت باز شدن آسیا (UTC)
input int      AsianCloseHour     = 8;                   // ساعت بسته شدن آسیا (UTC)

//+------------------------------------------------------------------+
//| ===== تنظیمات Kill Zones =====                                     |
//+------------------------------------------------------------------+
input bool     TradeLondonKZ      = true;                // معامله در London Kill Zone
input bool     TradeNYKZ          = true;                // معامله در NY Kill Zone
input bool     TradeLondonCloseKZ = false;               // معامله در London Close KZ
input int      LKZ_StartHour      = 8;                   // شروع London KZ
input int      LKZ_EndHour        = 10;                  // پایان London KZ
input int      NYKZ_StartHour     = 13;                  // شروع NY KZ
input int      NYKZ_EndHour       = 15;                  // پایان NY KZ

//+------------------------------------------------------------------+
//| ===== تنظیمات تلگرام =====                                         |
//+------------------------------------------------------------------+
input bool     TelegramEnabled    = false;               // تلگرام فعال باشد
input string   TelegramToken      = "";                  // توکن ربات تلگرام
input string   TelegramChatId     = "";                  // شناسه چت تلگرام
input bool     NotifyOnEntry      = true;                // اعلام ورود
input bool     NotifyOnExit       = true;                // اعلام خروج
input bool     NotifyOnSL         = true;                // اعلام StopLoss
input bool     NotifyOnTP         = true;                // اعلام TakeProfit
input bool     NotifyOnSession    = true;                // اعلام سشن
input bool     SendDailyReports   = true;                // ارسال گزارش روزانه
input int      DailyReportHour    = 22;                  // ساعت گزارش روزانه

//+------------------------------------------------------------------+
//| ===== تنظیمات رسم روی چارت =====                                  |
//+------------------------------------------------------------------+
input bool     DrawEnabled        = true;                // رسم روی چارت فعال باشد
input bool     DrawOrderBlocks    = true;                // رسم Order Block
input bool     DrawFVG            = true;                // رسم Fair Value Gap
input bool     DrawBOSCHOCH       = true;                // رسم BOS/CHOCH
input bool     DrawLiquidity      = true;                // رسم سطوح نقدینگی
input bool     DrawKillZones      = true;                // رسم Kill Zones
input bool     DrawEntryArrows    = true;                // رسم فلش‌های ورود
input color    ColorBullish       = clrLime;             // رنگ صعودی
input color    ColorBearish       = clrRed;              // رنگ نزولی
input color    ColorNeutral       = clrGray;             // رنگ خنثی
input color    ColorFVG           = clrCyan;             // رنگ FVG
input color    ColorKillZone      = clrYellow;           // رنگ Kill Zone
input int      LabelFontSize      = 8;                   // اندازه فونت برچسب‌ها

//+------------------------------------------------------------------+
//| ===== تنظیمات لایسنس =====                                        |
//+------------------------------------------------------------------+
input string   LicenseKey         = "";                  // کلید لایسنس
input string   LicenseServer      = "https://api.yourserver.com"; // سرور لایسنس
input bool     CheckLicenseOnline = true;                // بررسی آنلاین لایسنس

//+------------------------------------------------------------------+
//| ===== تنظیمات API =====                                           |
//+------------------------------------------------------------------+
input string   APIBaseURL         = "http://localhost:8000"; // آدرس API
input string   APIKey             = "";                  // کلید API
input bool     APIEnabled         = false;               // API فعال باشد
input int      APITimeoutMs       = 5000;                // timeout درخواست (میلی‌ثانیه)

//+------------------------------------------------------------------+
//| ===== تنظیمات لاگ =====                                           |
//+------------------------------------------------------------------+
input bool     LogEnabled         = true;                // لاگ فعال باشد
input bool     LogToFile          = true;                // لاگ به فایل
input string   LogFileName        = "MT5Trading.log";    // نام فایل لاگ
input bool     LogDebug           = false;               // لاگ دیباگ

//+------------------------------------------------------------------+
//| ===== تنظیمات اطلاعات روی چارت =====                              |
//+------------------------------------------------------------------+
input bool     ShowDashboard      = true;                // نمایش داشبورد روی چارت
input bool     ShowScore          = true;                // نمایش امتیاز
input bool     ShowRiskInfo       = true;                // نمایش اطلاعات ریسک
input bool     ShowSessionInfo    = true;                // نمایش اطلاعات سشن
input int      DashboardX         = 10;                  // موقعیت افقی داشبورد
input int      DashboardY         = 30;                  // موقعیت عمودی داشبورد
//+------------------------------------------------------------------+
