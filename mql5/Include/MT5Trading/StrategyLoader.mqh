//+------------------------------------------------------------------+
//|                                             StrategyLoader.mqh      |
//|                                    MT5 Trading System              |
//|                                    لودر استراتژی                    |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"
#include "SMCAnalyzer.mqh"
#include "PAAnalyzer.mqh"
#include "DecisionEngine.mqh"
#include "TradeManager.mqh"
#include "PositionManager.mqh"
#include "DrawManager.mqh"
#include "NotificationManager.mqh"

//+
// انواع استراتژی
//+
enum ENUM_STRATEGY_TYPE {
   STRATEGY_SMC,           // فقط SMC
   STRATEGY_PA,            // فقط Price Action
   STRATEGY_COMBINED,      // ترکیبی
   STRATEGY_CUSTOM         // سفارشی
};

//+
// ساختار تنظیمات استراتژی
//+
struct StrategySettings {
   string name;
   ENUM_STRATEGY_TYPE type;
   bool enabled;

   // تنظیمات SMC
   bool useBOS;
   bool useCHOCH;
   bool useOB;
   bool useFVG;
   bool useLiquidity;
   int swingLookback;

   // تنظیمات Price Action
   bool usePinBar;
   bool useEngulfing;
   bool useInsideBar;
   bool useFakey;

   // تنظیمات ورود
   int minScore;
   double riskPercent;
   double rewardRiskRatio;
   int maxDailyTrades;
   int maxOpenTrades;

   // تنظیمات زمانی
   bool useTimeFilter;
   int londonStart;
   int londonEnd;
   int nyStart;
   int nyEnd;

   // مدیریت معامله
   bool moveToBE;
   int beAfterPoints;
   bool trailStop;
   int trailPoints;
};

//+
// کلاس لودر استراتژی
//+
class CStrategyLoader {
private:
   // کامپوننت‌ها
   CDecisionEngine *m_decisionEngine;
   CTradeManager *m_tradeManager;
   CPositionManager *m_positionManager;
   CDrawManager *m_drawManager;
   CNotificationManager *m_notificationManager;

   // تنظیمات
   StrategySettings m_settings;
   string m_symbol;
   ENUM_TIMEFRAME m_timeframe;

   // وضعیت
   bool m_initialized;
   int m_dailyTrades;
   datetime m_lastTradeTime;

   // توابع کمکی
   bool ValidateSettings();
   bool CheckTimeFilter();
   bool CheckRiskLimits();
   void LoadDefaultSettings();

public:
   CStrategyLoader(const string symbol, const ENUM_TIMEFRAME tf);
   ~CStrategyLoader();

   // مقداردهی اولیه
   bool Initialize();
   bool LoadSettings(const StrategySettings &settings);
   bool LoadFromFile(const string filename);
   bool SaveToFile(const string filename);

   // اجرا
   void OnTick();
   void OnBar();
   void OnTimer();

   // مدیریت
   void Enable(const bool enable);
   bool IsEnabled();

   // تنظیمات
   StrategySettings GetSettings();
   void SetMinScore(const int score);
   void SetRiskPercent(const double percent);
   void SetMaxTrades(const int daily, const int open);

   // گزارش
   string GetStatusReport();
};

//+
// سازنده
//+
CStrategyLoader::CStrategyLoader(const string symbol, const ENUM_TIMEFRAME tf) {
   m_symbol = symbol;
   m_timeframe = tf;
   m_initialized = false;
   m_dailyTrades = 0;
   m_lastTradeTime = 0;

   LoadDefaultSettings();
}

//+
// مخرب
//+
CStrategyLoader::~CStrategyLoader() {
   if(m_decisionEngine) delete m_decisionEngine;
   if(m_tradeManager) delete m_tradeManager;
   if(m_positionManager) delete m_positionManager;
   if(m_drawManager) delete m_drawManager;
   if(m_notificationManager) delete m_notificationManager;
}

//+
// لود تنظیمات پیش‌فرض
//+
void CStrategyLoader::LoadDefaultSettings() {
   m_settings.name = "Default Strategy";
   m_settings.type = STRATEGY_COMBINED;
   m_settings.enabled = true;

   // SMC
   m_settings.useBOS = true;
   m_settings.useCHOCH = true;
   m_settings.useOB = true;
   m_settings.useFVG = true;
   m_settings.useLiquidity = true;
   m_settings.swingLookback = SwingLookback;

   // Price Action
   m_settings.usePinBar = true;
   m_settings.useEngulfing = true;
   m_settings.useInsideBar = true;
   m_settings.useFakey = true;

   // ورود
   m_settings.minScore = MinEntryScore;
   m_settings.riskPercent = RiskPercent;
   m_settings.rewardRiskRatio = 2.0;
   m_settings.maxDailyTrades = MaxDailyTrades;
   m_settings.maxOpenTrades = MaxOpenTrades;

   // زمانی
   m_settings.useTimeFilter = UseTimeFilter;
   m_settings.londonStart = LondonStart;
   m_settings.londonEnd = LondonEnd;
   m_settings.nyStart = NYStart;
   m_settings.nyEnd = NYEnd;

   // مدیریت
   m_settings.moveToBE = true;
   m_settings.beAfterPoints = 100;
   m_settings.trailStop = UseDynamicSLTP;
   m_settings.trailPoints = 50;
}

//+
// مقداردهی اولیه
//+
bool CStrategyLoader::Initialize() {
   // ایجاد کامپوننت‌ها
   m_decisionEngine = new CDecisionEngine(m_symbol, m_timeframe);
   if(!m_decisionEngine) {
      LogMessage("خطا در ایجاد DecisionEngine", "ERROR");
      return false;
   }

   m_tradeManager = new CTradeManager(m_symbol);
   if(!m_tradeManager) {
      LogMessage("خطا در ایجاد TradeManager", "ERROR");
      return false;
   }

   m_positionManager = new CPositionManager(m_symbol);
   if(!m_positionManager) {
      LogMessage("خطا در ایجاد PositionManager", "ERROR");
      return false;
   }

   m_drawManager = new CDrawManager(m_symbol);
   if(!m_drawManager) {
      LogMessage("خطا در ایجاد DrawManager", "ERROR");
      return false;
   }

   m_notificationManager = new CNotificationManager();
   if(!m_notificationManager) {
      LogMessage("خطا در ایجاد NotificationManager", "ERROR");
      return false;
   }

   // اعتبارسنجی تنظیمات
   if(!ValidateSettings()) {
      LogMessage("تنظیمات نامعتبر", "WARNING");
   }

   m_initialized = true;

   LogMessage(StringFormat("استراتژی مقداردهی شد | نماد: %s | تایم‌فریم: %s",
      m_symbol, EnumToString(m_timeframe)), "INFO");

   return true;
}

//+
// اعتبارسنجی تنظیمات
//+
bool CStrategyLoader::ValidateSettings() {
   bool valid = true;

   if(m_settings.minScore < 50 || m_settings.minScore > 95) {
      LogMessage("امتیاز حداقلی نامعتبر", "WARNING");
      valid = false;
   }

   if(m_settings.riskPercent <= 0 || m_settings.riskPercent > 10) {
      LogMessage("درصد ریسک نامعتبر", "WARNING");
      valid = false;
   }

   if(m_settings.maxDailyTrades <= 0 || m_settings.maxDailyTrades > 50) {
      LogMessage("حداکثر معاملات روزانه نامعتبر", "WARNING");
      valid = false;
   }

   return valid;
}

//+
// بررسی فیلتر زمانی
//+
bool CStrategyLoader::CheckTimeFilter() {
   if(!m_settings.useTimeFilter) return true;

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int hour = dt.hour;

   // لندن
   if(hour >= m_settings.londonStart && hour < m_settings.londonEnd)
      return true;

   // نیویورک
   if(hour >= m_settings.nyStart && hour < m_settings.nyEnd)
      return true;

   return false;
}

//+
// بررسی محدودیت‌های ریسک
//+
bool CStrategyLoader::CheckRiskLimits() {
   // بررسی تعداد روزانه
   if(m_dailyTrades >= m_settings.maxDailyTrades) {
      LogMessage("حداکثر معاملات روزانه", "INFO");
      return false;
   }

   // بررسی پوزیشن‌های باز
   if(m_positionManager && m_positionManager->GetPositionCount() >= m_settings.maxOpenTrades) {
      LogMessage("حداکثر پوزیشن باز", "INFO");
      return false;
   }

   // بررسی اسپرد
   int spread = (int)SymbolInfoInteger(m_symbol, SYMBOL_SPREAD);
   if(spread > MaxSpread) {
      LogMessage("اسپرد بالا: " + IntegerToString(spread), "WARNING");
      return false;
   }

   return true;
}

//+
// لود تنظیمات
//+
bool CStrategyLoader::LoadSettings(const StrategySettings &settings) {
   m_settings = settings;
   return ValidateSettings();
}

//+
// لود از فایل
//+
bool CStrategyLoader::LoadFromFile(const string filename) {
   int handle = FileOpen(filename, FILE_READ|FILE_TXT|FILE_ANSI);

   if(handle == INVALID_HANDLE) {
      LogMessage("فایل تنظیمات یافت نشد: " + filename, "WARNING");
      return false;
   }

   // خواندن تنظیمات
   // فرمت ساده: key=value

   string line;
   while(!FileIsEnding(handle)) {
      line = FileReadString(handle);

      // پردازش خط
      int sep = StringFind(line, "=");
      if(sep < 0) continue;

      string key = StringSubstr(line, 0, sep);
      string value = StringSubstr(line, sep + 1);

      // تنظیم مقادیر
      if(key == "minScore") m_settings.minScore = (int)StringToInteger(value);
      else if(key == "riskPercent") m_settings.riskPercent = StringToDouble(value);
      else if(key == "maxDailyTrades") m_settings.maxDailyTrades = (int)StringToInteger(value);
      else if(key == "maxOpenTrades") m_settings.maxOpenTrades = (int)StringToInteger(value);
   }

   FileClose(handle);

   LogMessage("تنظیمات از فایل لود شد", "INFO");

   return ValidateSettings();
}

//+
// ذخیره در فایل
//+
bool CStrategyLoader::SaveToFile(const string filename) {
   int handle = FileOpen(filename, FILE_WRITE|FILE_TXT|FILE_ANSI);

   if(handle == INVALID_HANDLE) {
      LogMessage("خطا در ایجاد فایل: " + filename, "ERROR");
      return false;
   }

   // نوشتن تنظیمات
   FileWrite(handle, "name=" + m_settings.name);
   FileWrite(handle, "minScore=" + IntegerToString(m_settings.minScore));
   FileWrite(handle, "riskPercent=" + DoubleToString(m_settings.riskPercent, 2));
   FileWrite(handle, "maxDailyTrades=" + IntegerToString(m_settings.maxDailyTrades));
   FileWrite(handle, "maxOpenTrades=" + IntegerToString(m_settings.maxOpenTrades));
   FileWrite(handle, "useTimeFilter=" + (m_settings.useTimeFilter ? "true" : "false"));
   FileWrite(handle, "moveToBE=" + (m_settings.moveToBE ? "true" : "false"));
   FileWrite(handle, "trailStop=" + (m_settings.trailStop ? "true" : "false"));

   FileClose(handle);

   LogMessage("تنظیمات در فایل ذخیره شد", "INFO");

   return true;
}

//+
// اجرای هر تیک
//+
void CStrategyLoader::OnTick() {
   if(!m_initialized || !m_settings.enabled) return;

   // به‌روزرسانی پوزیشن‌ها
   if(m_positionManager) {
      m_positionManager->UpdatePositions();

      // مدیریت حد ضرر متحرک
      if(m_settings.trailStop) {
         // تریلینگ برای هر پوزیشن
         // ...
      }

      // انتقال به BE
      if(m_settings.moveToBE) {
         // بررسی انتقال به BE
         // ...
      }
   }

   // رفرش رسم‌ها
   if(m_drawManager) {
      m_drawManager->Refresh();
   }
}

//+
// اجرای هر کندل
//+
void CStrategyLoader::OnBar() {
   if(!m_initialized || !m_settings.enabled) return;

   // بررسی کندل جدید
   // این باید از بیرون فراخوانی شود

   // بررسی فیلتر زمانی
   if(!CheckTimeFilter()) {
      LogMessage("خارج از سشن معاملاتی", "INFO");
      return;
   }

   // بررسی محدودیت‌ها
   if(!CheckRiskLimits()) return;

   // تحلیل
   TradeSignal signal;
   ZeroMemory(signal);

   if(m_decisionEngine && m_decisionEngine->Analyze(signal)) {
      // بررسی امتیاز
      if(signal.totalScore >= m_settings.minScore && signal.entryAllowed) {
         // رسم سیگنال
         if(m_drawManager) {
            m_drawManager->DrawSignal(
               signal.entryPrice,
               signal.stopLoss,
               signal.takeProfit,
               signal.direction,
               signal.totalScore
            );
         }

         // اجرای معامله
         if(m_tradeManager) {
            string error;
            if(m_tradeManager->OpenTrade(signal, error)) {
               m_dailyTrades++;
               m_lastTradeTime = TimeCurrent();

               // اعلان
               if(m_notificationManager) {
                  m_notificationManager->SendSignalAlert(
                     m_symbol,
                     signal.direction,
                     signal.entryPrice,
                     signal.stopLoss,
                     signal.takeProfit,
                     signal.totalScore
                  );
               }
            } else {
               LogMessage("خطا در باز کردن معامله: " + error, "ERROR");
            }
         }
      }
   }
}

//+
// اجرای تایمر
//+
void CStrategyLoader::OnTimer() {
   // ریست شمارنده روزانه
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   if(dt.hour == 0 && dt.min == 0) {
      m_dailyTrades = 0;
      LogMessage("شمارنده روزانه ریست شد", "INFO");
   }
}

//+
// فعال/غیرفعال
//+
void CStrategyLoader::Enable(const bool enable) {
   m_settings.enabled = enable;
   LogMessage("استراتژی " + (enable ? "فعال" : "غیرفعال") + " شد", "INFO");
}

//+
// بررسی فعال بودن
//+
bool CStrategyLoader::IsEnabled() {
   return m_settings.enabled && m_initialized;
}

//+
// دریافت تنظیمات
//+
StrategySettings CStrategyLoader::GetSettings() {
   return m_settings;
}

//+
// تنظیم امتیاز حداقلی
//+
void CStrategyLoader::SetMinScore(const int score) {
   if(score >= 50 && score <= 95) {
      m_settings.minScore = score;
      LogMessage("امتیاز حداقلی تنظیم شد: " + IntegerToString(score), "INFO");
   }
}

//+
// تنظیم درصد ریسک
//+
void CStrategyLoader::SetRiskPercent(const double percent) {
   if(percent > 0 && percent <= 10) {
      m_settings.riskPercent = percent;
      LogMessage("درصد ریسک تنظیم شد: " + DoubleToString(percent, 2), "INFO");
   }
}

//+
// تنظیم حداکثر معاملات
//+
void CStrategyLoader::SetMaxTrades(const int daily, const int open) {
   m_settings.maxDailyTrades = daily;
   m_settings.maxOpenTrades = open;
   LogMessage(StringFormat("حداکثر معاملات: روزانه=%d همزمان=%d", daily, open), "INFO");
}

//+
// گزارش وضعیت
//+
string CStrategyLoader::GetStatusReport() {
   string report = "📊 گزارش استراتژی\n\n";

   report += StringFormat("نام: %s\n", m_settings.name);
   report += StringFormat("نوع: %s\n", EnumToString(m_settings.type));
   report += StringFormat("وضعیت: %s\n\n", m_settings.enabled ? "فعال" : "غیرفعال");

   report += "─── تنظیمات ورود ───\n";
   report += StringFormat("حداقل امتیاز: %d\n", m_settings.minScore);
   report += StringFormat("ریسک: %.1f%%\n", m_settings.riskPercent);
   report += StringFormat("حداکثر روزانه: %d\n", m_settings.maxDailyTrades);
   report += StringFormat("حداکثر همزمان: %d\n\n", m_settings.maxOpenTrades);

   report += "─── وضعیت امروز ───\n";
   report += StringFormat("معاملات امروز: %d/%d\n", m_dailyTrades, m_settings.maxDailyTrades);

   if(m_positionManager) {
      report += StringFormat("پوزیشن‌های باز: %d\n", m_positionManager->GetPositionCount());
      report += StringFormat("سود جاری: $%.2f\n", m_positionManager->GetTotalProfit());
   }

   return report;
}
//+------------------------------------------------------------------+
