//+------------------------------------------------------------------+
//|                                              RiskManager.mqh       |
//|                                    MT5 Trading System             |
//|                                    مدیریت ریسک                    |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"
#include "Helpers.mqh"

//+
// ساختار نتیجه محاسبه لات
//+
struct LotCalculationResult {
   double lot;                    // حجم محاسبه شده
   double riskAmount;             // مبلغ ریسک (ارز پایه)
   double riskPercent;            // درصد ریسک
   double stopLossDistance;        // فاصله حد ضرر (پوینت)
   bool isValid;                  // آیا معتبر است
   string errorMessage;           // پیام خطا
};

//+
// ساختار بررسی ریسک
//+
struct RiskCheckResult {
   bool allowed;                  // آیا معامله مجاز است
   string reason;                 // دلیل رد
   bool dailyLossLimitReached;     // حد ضرر روزانه
   bool maxPositionsReached;       // حداکثر پوزیشن
   bool maxTradesReached;          // حداکثر معاملات روزانه
   bool maxDrawdownReached;        // حداکثر درادون
   bool emergencyStop;             // توقف اضطراری
};

//+
// کلاس مدیریت ریسک
//+
class CRiskManager {
private:
   string m_symbol;
   int m_magic;

   // آمار ریسک
   double m_dailyStartBalance;
   double m_peakBalance;
   double m_currentDrawdown;

   // تنظیمات اضافی
   double m_maxDailyLossPercent;    // درصد حداکثر ضرر روزانه
   double m_maxDrawdownPercent;      // درصد حداکثر درادون
   bool m_emergencyStopTriggered;

   // توابع داخلی
   double GetAccountBalance();
   double GetEquity();
   double GetUsedMargin();
   double GetFreeMargin();
   int CountPositionsForSymbol();
   int CountTodayDeals();
   double CalculateTodayPnL();
   double CalculateMaxDrawdown();
   bool IsSpreadAcceptable();
   bool IsMarginAvailable(const double lot);

public:
   CRiskManager(const string symbol);
   ~CRiskManager();

   // تنظیمات
   void SetMaxDailyLossPercent(const double percent);
   void SetMaxDrawdownPercent(const double percent);
   void SetMaxDailyTrades(const int max);
   void SetMaxPositions(const int max);

   // محاسبه لات
   LotCalculationResult CalculateLot(
      const double riskPercent,
      const double slPoints,
      const ENUM_POSITION_TYPE direction
   );
   LotCalculationResult CalculateLotByMoney(
      const double riskMoney,
      const double slPoints
   );
   double ValidateAndAdjustLot(const double lot);

   // بررسی ریسک
   RiskCheckResult CheckRiskBeforeTrade(const ENUM_POSITION_TYPE direction);
   bool CanOpenTrade();
   bool IsDailyLossLimitReached();
   bool IsMaxPositionsReached();
   bool IsMaxDrawdownReached();
   bool IsEmergencyStop();

   // کنترل ریسک
   void TriggerEmergencyStop();
   void ResetDailyStats();
   void UpdatePeakBalance();

   // آمار و گزارش
   double GetCurrentDrawdown();
   double GetDailyPnL();
   double GetDailyPnLPercent();
   int GetOpenPositionsCount();
   int GetTodayTradesCount();
   double GetRiskPerTrade();
   string GetRiskReport();

   // بررسی‌های نماد
   bool IsSymbolTradeable();
   bool IsSessionAllowed();
   bool ValidateSymbolSettings();
};

//+
// سازنده
//+
CRiskManager::CRiskManager(const string symbol) {
   m_symbol = symbol;
   m_magic = (int)StringToInteger(MagicNumber);

   m_dailyStartBalance = 0;
   m_peakBalance = 0;
   m_currentDrawdown = 0;
   m_maxDailyLossPercent = 5.0;     // 5% پیش‌فرض
   m_maxDrawdownPercent = 10.0;       // 10% پیش‌فرض
   m_emergencyStopTriggered = false;

   // ثبت بالانس اول روز
   m_dailyStartBalance = GetAccountBalance();
   m_peakBalance = m_dailyStartBalance;
}

//+
// مخرب
//+
CRiskManager::~CRiskManager() {
}

//+
// دریافت بالانس حساب
//+
double CRiskManager::GetAccountBalance() {
   return AccountInfoDouble(ACCOUNT_BALANCE);
}

//+
// دریافت اکوئیتی
//+
double CRiskManager::GetEquity() {
   return AccountInfoDouble(ACCOUNT_EQUITY);
}

//+
// دریافت مارجین استفاده شده
//+
double CRiskManager::GetUsedMargin() {
   return AccountInfoDouble(ACCOUNT_MARGIN);
}

//+
// دریافت مارجین آزاد
//+
double CRiskManager::GetFreeMargin() {
   return AccountInfoDouble(ACCOUNT_MARGIN_FREE);
}

//+
// شمارش پوزیشن‌های نماد
//+
int CRiskManager::CountPositionsForSymbol() {
   return CountOpenTrades(m_symbol);
}

//+
// شمارش معاملات امروز
//+
int CRiskManager::CountTodayDeals() {
   return CountTodayTrades();
}

//+
// محاسبه سود/ضرر امروز
//+
double CRiskManager::CalculateTodayPnL() {
   double pnl = 0;
   datetime todayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));

   if(HistorySelect(todayStart, TimeCurrent())) {
      int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++) {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0) continue;

         if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != m_magic) continue;

         double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
         double swap = HistoryDealGetDouble(ticket, DEAL_SWAP);
         double commission = HistoryDealGetDouble(ticket, DEAL_COMMISSION);

         pnl += profit + swap + commission;
      }
   }

   // اضافه کردن سود معاملات باز
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;

      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      pnl += PositionGetDouble(POSITION_PROFIT);
   }

   return pnl;
}

//+
// محاسبه حداکثر درادون
//+
double CRiskManager::CalculateMaxDrawdown() {
   if(m_peakBalance <= 0) return 0;

   double equity = GetEquity();
   if(equity >= m_peakBalance) {
      m_peakBalance = equity;
      return 0;
   }

   return ((m_peakBalance - equity) / m_peakBalance) * 100.0;
}

//+
// بررسی اسپرد
//+
bool CRiskManager::IsSpreadAcceptable() {
   int currentSpread = (int)SymbolInfoInteger(m_symbol, SYMBOL_SPREAD);
   return currentSpread <= MaxSpread;
}

//+
// بررسی مارجین
//+
bool CRiskManager::IsMarginAvailable(const double lot) {
   double freeMargin = GetFreeMargin();
   double marginRequired;

   // محاسبه مارجین مورد نیاز
   double contractSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double leverage = (double)AccountInfoInteger(ACCOUNT_LEVERAGE);

   marginRequired = (lot * contractSize) / leverage;

   // با احتساب سقف 80% مارجین آزاد
   return marginRequired < (freeMargin * 0.8);
}

//+
// تنظیم درصد حداکثر ضرر روزانه
//+
void CRiskManager::SetMaxDailyLossPercent(const double percent) {
   m_maxDailyLossPercent = MathMax(0.1, MathMin(100.0, percent));
}

//+
// تنظیم درصد حداکثر درادون
//+
void CRiskManager::SetMaxDrawdownPercent(const double percent) {
   m_maxDrawdownPercent = MathMax(0.1, MathMin(100.0, percent));
}

//+
// تنظیم حداکثر معاملات روزانه
//+
void CRiskManager::SetMaxDailyTrades(const int max) {
   // استفاده از MaxDailyTrades از Config
}

//+
// تنظیم حداکثر پوزیشن
//+
void CRiskManager::SetMaxPositions(const int max) {
   // استفاده از MaxOpenTrades از Config
}

//+
// محاسبه حجم بر اساس درصد ریسک
//+
LotCalculationResult CRiskManager::CalculateLot(
   const double riskPercent,
   const double slPoints,
   const ENUM_POSITION_TYPE direction
) {
   LotCalculationResult result;
   ZeroMemory(result);

   // بررسی ورودی
   if(riskPercent <= 0 || slPoints <= 0) {
      result.lot = 0;
      result.isValid = false;
      result.errorMessage = "پارامترهای ورودی نامعتبر";
      return result;
   }

   // اگر لات ثابت تنظیم شده
   if(FixedLot > 0) {
      result.lot = ValidateAndAdjustLot(FixedLot);
      result.isValid = true;
      return result;
   }

   // دریافت بالانس یا اکوئیتی
   double capital;
   if(true) {  // استفاده از بالانس
      capital = GetAccountBalance();
   } else {
      capital = GetEquity();
   }

   // محاسبه مبلغ ریسک
   double riskMoney = capital * (riskPercent / 100.0);

   // محاسبه ارزش هر پوینت
   double tickValue = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

   if(tickValue == 0 || tickSize == 0) {
      result.isValid = false;
      result.errorMessage = "خطا در دریافت اطلاعات نماد";
      return result;
   }

   // محاسبه ضرر به ازای هر لات
   double pointValue = tickValue * (point / tickSize);
   double slMoneyPerLot = slPoints * pointValue;

   if(slMoneyPerLot <= 0) {
      result.isValid = false;
      result.errorMessage = "خطا در محاسبه ارزش SL";
      return result;
   }

   // محاسبه لات
   double lot = riskMoney / slMoneyPerLot;

   // نرمال‌سازی و اعتبارسنجی
   lot = ValidateAndAdjustLot(lot);

   result.lot = lot;
   result.riskAmount = riskMoney;
   result.riskPercent = riskPercent;
   result.stopLossDistance = slPoints;
   result.isValid = lot > 0;

   // لاگ
   LogMessage(StringFormat("محاسبه لات: %.2f | ریسک: $%.2f (%.1f%%) | SL: %.0f پوینت",
      result.lot, result.riskAmount, result.riskPercent, result.stopLossDistance), "INFO");

   return result;
}

//+
// محاسبه حجم بر اساس مبلغ ثابت
//+
LotCalculationResult CRiskManager::CalculateLotByMoney(
   const double riskMoney,
   const double slPoints
) {
   LotCalculationResult result;
   ZeroMemory(result);

   if(riskMoney <= 0 || slPoints <= 0) {
      result.isValid = false;
      result.errorMessage = "پارامترها نامعتبر";
      return result;
   }

   double tickValue = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

   double pointValue = tickValue * (point / tickSize);
   double slMoneyPerLot = slPoints * pointValue;

   if(slMoneyPerLot <= 0) {
      result.isValid = false;
      result.errorMessage = "خطا در محاسبه";
      return result;
   }

   double lot = riskMoney / slMoneyPerLot;
   lot = ValidateAndAdjustLot(lot);

   result.lot = lot;
   result.riskAmount = riskMoney;
   result.isValid = lot > 0;

   return result;
}

//+
// اعتبارسنجی و تنظیم لات
//+
double CRiskManager::ValidateAndAdjustLot(const double lot) {
   double minLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);

   if(minLot <= 0 || maxLot <= 0 || stepLot <= 0) {
      LogMessage("خطا در دریافت محدودیت‌های حجم نماد", "ERROR");
      return 0;
   }

   // اعمال محدودیت‌های کانفیگ
   minLot = MathMax(minLot, MinLot);
   maxLot = MathMin(maxLot, MaxLot);

   // تنظیم بر اساس step
   double adjustedLot = MathFloor(lot / stepLot) * stepLot;

   // اعمال min/max
   adjustedLot = MathMax(adjustedLot, minLot);
   adjustedLot = MathMin(adjustedLot, maxLot);

   // بررسی مارجین
   if(!IsMarginAvailable(adjustedLot)) {
      LogMessage("مارجین کافی نیست", "WARNING");
      // کاهش لات
      while(adjustedLot > minLot && !IsMarginAvailable(adjustedLot)) {
         adjustedLot -= stepLot;
      }
   }

   return NormalizeDouble(adjustedLot, 2);
}

//+
// بررسی ریسک قبل از معامله
//+
RiskCheckResult CRiskManager::CheckRiskBeforeTrade(const ENUM_POSITION_TYPE direction) {
   RiskCheckResult result;
   ZeroMemory(result);

   result.allowed = true;

   // بررسی توقف اضطراری
   if(m_emergencyStopTriggered) {
      result.allowed = false;
      result.emergencyStop = true;
      result.reason = "توقف اضطراری فعال";
      return result;
   }

   // بررسی اسپرد
   if(!IsSpreadAcceptable()) {
      result.allowed = false;
      result.reason = "اسپرد بالا";
      return result;
   }

   // بررسی حداکثر پوزیشن
   int openPositions = CountPositionsForSymbol();
   if(openPositions >= MaxOpenTrades) {
      result.allowed = false;
      result.maxPositionsReached = true;
      result.reason = StringFormat("حداکثر پوزیشن رسید: %d/%d", openPositions, MaxOpenTrades);
      return result;
   }

   // بررسی حداکثر معاملات روزانه
   int todayTrades = CountTodayDeals();
   if(todayTrades >= MaxDailyTrades) {
      result.allowed = false;
      result.maxTradesReached = true;
      result.reason = StringFormat("حداکثر معاملات روزانه رسید: %d/%d", todayTrades, MaxDailyTrades);
      return result;
   }

   // بررسی حد ضرر روزانه
   if(IsDailyLossLimitReached()) {
      result.allowed = false;
      result.dailyLossLimitReached = true;
      result.reason = StringFormat("حد ضرر روزانه رسید: %.2f%%", GetDailyPnLPercent());
      return result;
   }

   // بررسی حداکثر درادون
   m_currentDrawdown = CalculateMaxDrawdown();
   if(m_currentDrawdown >= m_maxDrawdownPercent) {
      result.allowed = false;
      result.maxDrawdownReached = true;
      result.reason = StringFormat("حداکثر درادون رسید: %.2f%%", m_currentDrawdown);
      return result;
   }

   return result;
}

//+
// آیا می‌توان معامله باز کرد
//+
bool CRiskManager::CanOpenTrade() {
   RiskCheckResult check = CheckRiskBeforeTrade(POSITION_TYPE_BUY);
   return check.allowed;
}

//+
// بررسی حد ضرر روزانه
//+
bool CRiskManager::IsDailyLossLimitReached() {
   double dailyPnLPercent = GetDailyPnLPercent();
   return dailyPnLPercent <= -m_maxDailyLossPercent;
}

//+
// بررسی حداکثر پوزیشن
//+
bool CRiskManager::IsMaxPositionsReached() {
   return CountPositionsForSymbol() >= MaxOpenTrades;
}

//+
// بررسی حداکثر درادون
//+
bool CRiskManager::IsMaxDrawdownReached() {
   return CalculateMaxDrawdown() >= m_maxDrawdownPercent;
}

//+
// بررسی توقف اضطراری
//+
bool CRiskManager::IsEmergencyStop() {
   return m_emergencyStopTriggered;
}

//+
// فعال‌سازی توقف اضطراری
//+
void CRiskManager::TriggerEmergencyStop() {
   m_emergencyStopTriggered = true;
   LogMessage("توقف اضطراری فعال شد!", "ERROR");
}

//+
// بازنشانی آمار روزانه
//+
void CRiskManager::ResetDailyStats() {
   m_dailyStartBalance = GetAccountBalance();
   m_peakBalance = m_dailyStartBalance;
   m_emergencyStopTriggered = false;

   LogMessage("آمار روزانه بازنشانی شد", "INFO");
}

//+
// به‌روزرسانی بالانس اوج
//+
void CRiskManager::UpdatePeakBalance() {
   double equity = GetEquity();
   if(equity > m_peakBalance) {
      m_peakBalance = equity;
   }
}

//+
// دریافت درادون فعلی
//+
double CRiskManager::GetCurrentDrawdown() {
   return m_currentDrawdown;
}

//+
// دریافت سود/ضرر روزانه
//+
double CRiskManager::GetDailyPnL() {
   return CalculateTodayPnL();
}

//+
// دریافت درصد سود/ضرر روزانه
//+
double CRiskManager::GetDailyPnLPercent() {
   if(m_dailyStartBalance <= 0) return 0;

   double pnl = CalculateTodayPnL();
   return (pnl / m_dailyStartBalance) * 100.0;
}

//+
// دریافت تعداد پوزیشن باز
//+
int CRiskManager::GetOpenPositionsCount() {
   return CountPositionsForSymbol();
}

//+
// دریافت تعداد معاملات امروز
//+
int CRiskManager::GetTodayTradesCount() {
   return CountTodayDeals();
}

//+
// دریافت ریسک هر معامله
//+
double CRiskManager::GetRiskPerTrade() {
   return RiskPercent;
}

//+
// بررسی قابل معامله بودن نماد
//+
bool CRiskManager::IsSymbolTradeable() {
   // بررسی ساعت معاملاتی
   if(!SymbolInfoInteger(m_symbol, SYMBOL_TRADE_MODE)) {
      return false;
   }

   // بررسی اسپرد
   if(!IsSpreadAcceptable()) {
      return false;
   }

   return true;
}

//+
// بررسی جلسه مجاز
//+
bool CRiskManager::IsSessionAllowed() {
   if(!UseTimeFilter) return true;
   return IsTradingTime();
}

//+
// اعتبارسنجی تنظیمات نماد
//+
bool CRiskManager::ValidateSymbolSettings() {
   // بررسی MinLot
   double minLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
   if(MinLot < minLot) {
      LogMessage(StringFormat("MinLot تنظیم شده (%.2f) کمتر از حداقل نماد (%.2f)",
         MinLot, minLot), "WARNING");
      return false;
   }

   // بررسی MaxLot
   double maxLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
   if(MaxLot > maxLot) {
      LogMessage(StringFormat("MaxLot تنظیم شده (%.2f) بیشتر از حداکثر نماد (%.2f)",
         MaxLot, maxLot), "WARNING");
      return false;
   }

   // بررسی اسپرد
   if(MaxSpread <= 0) {
      return false;
   }

   return true;
}

//+
// گزارش ریسک
//+
string CRiskManager::GetRiskReport() {
   string report = "📊 گزارش ریسک\n\n";

   report += StringFormat("💰 بالانس: $%.2f\n", GetAccountBalance());
   report += StringFormat("📈 اکوئیتی: $%.2f\n", GetEquity());
   report += StringFormat("📊 سود/ضرر امروز: $%.2f (%.2f%%)\n",
      GetDailyPnL(), GetDailyPnLPercent());
   report += StringFormat("📉 درادون فعلی: %.2f%%\n\n", GetCurrentDrawdown());

   report += StringFormat("🔢 پوزیشن‌ها: %d/%d\n",
      GetOpenPositionsCount(), MaxOpenTrades);
   report += StringFormat("📅 معاملات امروز: %d/%d\n",
      GetTodayTradesCount(), MaxDailyTrades);
   report += StringFormat("📊 اسپرد فعلی: %d (حداکثر: %d)\n",
      SymbolInfoInteger(m_symbol, SYMBOL_SPREAD), MaxSpread);

   if(m_emergencyStopTriggered) {
      report += "\n⚠️ توقف اضطراری فعال است!";
   }

   return report;
}
//+------------------------------------------------------------------+
