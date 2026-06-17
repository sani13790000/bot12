//+------------------------------------------------------------------+
//|                                              RiskManager.mqh       |
//|                         سیستم معامله‌گری حرفه‌ای MT5               |
//|                                                                    |
//| توضیح فارسی:                                                       |
//| این فایل مسئول مدیریت کامل ریسک معاملاتی است.                     |
//| شامل محاسبه لات، تعیین StopLoss و TakeProfit،                     |
//| کنترل حداکثر ضرر روزانه، Drawdown و توقف اضطراری می‌باشد.         |
//| تمام محاسبات بر اساس موجودی واقعی حساب انجام می‌شود.              |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"
#include "Helpers.mqh"

//+------------------------------------------------------------------+
//| ساختار نتیجه محاسبه لات                                           |
//+------------------------------------------------------------------+
struct LotCalculationResult {
   double lot;                    // حجم محاسبه شده
   double riskAmount;             // مبلغ ریسک (ارز پایه)
   double riskPercent;            // درصد ریسک
   double stopLossDistance;       // فاصله حد ضرر (پوینت)
   double takeProfitDistance;     // فاصله حد سود (پوینت)
   double rewardRiskRatio;        // نسبت سود به ریسک
   bool isValid;                  // آیا معتبر است
   string errorMessage;           // پیام خطا
};

//+------------------------------------------------------------------+
//| ساختار بررسی ریسک                                                  |
//+------------------------------------------------------------------+
struct RiskCheckResult {
   bool allowed;                  // آیا معامله مجاز است
   string reason;                 // دلیل رد
   bool dailyLossLimitReached;    // حد ضرر روزانه
   bool maxPositionsReached;      // حداکثر پوزیشن
   bool maxTradesReached;         // حداکثر معاملات روزانه
   bool maxDrawdownReached;       // حداکثر drawdown
   bool emergencyStop;            // توقف اضطراری
   bool spreadTooHigh;            // اسپرد بالا
   bool marginInsufficient;       // مارجین ناکافی
};

//+------------------------------------------------------------------+
//| ساختار تعیین StopLoss و TakeProfit                                 |
//+------------------------------------------------------------------+
struct SLTPResult {
   double stopLossPrice;          // قیمت StopLoss
   double takeProfitPrice;        // قیمت TakeProfit
   double stopLossPoints;         // فاصله SL به پوینت
   double takeProfitPoints;       // فاصله TP به پوینت
   double riskRewardRatio;        // نسبت سود به ریسک
   bool isValid;                  // آیا معتبر است
   string method;                 // روش محاسبه (ATR/Fixed/Structure/OrderBlock)
};

//+------------------------------------------------------------------+
//| کلاس مدیریت ریسک حرفه‌ای                                          |
//+------------------------------------------------------------------+
class CRiskManager {
private:
   string m_symbol;
   int m_magic;
   double m_dailyStartBalance;
   double m_peakBalance;
   double m_currentDrawdown;
   double m_weeklyStartBalance;
   double m_monthlyStartBalance;
   double m_maxDailyLossPercent;
   double m_maxDrawdownPercent;
   bool m_emergencyStopTriggered;
   int m_atrHandle;
   double m_atrValues[];
   double m_atrMultiplierSL;
   double m_atrMultiplierTP;

   double GetAccountBalance();
   double GetEquity();
   double GetUsedMargin();
   double GetFreeMargin();
   int CountPositionsForSymbol();
   int CountTodayDeals();
   double CalculateTodayPnL();
   double CalculateMaxDrawdown();
   double GetATRValue(const int shift = 1);
   bool IsSpreadAcceptable();
   bool IsMarginAvailable(const double lot);
   double NormalizeLot(const double lot);
   double NormalizePrice(const double price);

public:
   CRiskManager(const string symbol);
   ~CRiskManager();

   void SetMaxDailyLossPercent(const double percent);
   void SetMaxDrawdownPercent(const double percent);
   void SetATRMultipliers(const double slMult, const double tpMult);
   void InitializeATR(const int period = 14, const ENUM_TIMEFRAMES tf = PERIOD_CURRENT);

   LotCalculationResult CalculateLot(const double riskPercent, const double slPoints, const ENUM_POSITION_TYPE direction);
   LotCalculationResult CalculateLotByMoney(const double riskMoney, const double slPoints);
   double ValidateAndAdjustLot(const double lot);

   SLTPResult CalculateSLTP_ATR(const ENUM_POSITION_TYPE direction, const double entryPrice, const double rrRatio = 2.0);
   SLTPResult CalculateSLTP_Fixed(const ENUM_POSITION_TYPE direction, const double entryPrice, const double slPoints, const double rrRatio = 2.0);
   SLTPResult CalculateSLTP_Structure(const ENUM_POSITION_TYPE direction, const double entryPrice, const double structureLevel, const double rrRatio = 2.0, const double bufferPoints = 5.0);
   SLTPResult CalculateSLTP_OrderBlock(const ENUM_POSITION_TYPE direction, const double entryPrice, const double obHigh, const double obLow, const double rrRatio = 2.0);

   RiskCheckResult CheckRiskBeforeTrade(const ENUM_POSITION_TYPE direction);
   bool CanOpenTrade();
   bool IsDailyLossLimitReached();
   bool IsMaxPositionsReached();
   bool IsMaxDrawdownReached();
   bool IsEmergencyStop();

   void TriggerEmergencyStop();
   void ResetDailyStats();
   void UpdatePeakBalance();
   void ResetWeeklyStats();
   void ResetMonthlyStats();

   bool UpdateTrailingStop(const ulong ticket, const double trailPoints, const double stepPoints);
   bool UpdateBreakEven(const ulong ticket, const double triggerPoints, const double offsetPoints = 1.0);

   double GetCurrentDrawdown();
   double GetDailyPnL();
   double GetDailyPnLPercent();
   double GetWeeklyPnL();
   double GetMonthlyPnL();
   int GetOpenPositionsCount();
   int GetTodayTradesCount();
   double GetRiskPerTrade();
   double GetCurrentATR();
   string GetRiskReport();
   string GetDetailedRiskReport();

   bool IsSymbolTradeable();
   bool IsSessionAllowed();
   bool ValidateSymbolSettings();
};

CRiskManager::CRiskManager(const string symbol) {
   m_symbol = symbol;
   m_magic = MagicNumber;
   m_dailyStartBalance = 0;
   m_peakBalance = 0;
   m_currentDrawdown = 0;
   m_weeklyStartBalance = 0;
   m_monthlyStartBalance = 0;
   m_maxDailyLossPercent = MaxDailyLossPercent;
   m_maxDrawdownPercent = MaxDrawdownPercent;
   m_emergencyStopTriggered = false;
   m_atrHandle = INVALID_HANDLE;
   m_atrMultiplierSL = 1.5;
   m_atrMultiplierTP = 3.0;
   m_dailyStartBalance = GetAccountBalance();
   m_peakBalance = m_dailyStartBalance;
   m_weeklyStartBalance = m_dailyStartBalance;
   m_monthlyStartBalance = m_dailyStartBalance;
   InitializeATR(14, PERIOD_CURRENT);
   LogMessage(StringFormat("مدیریت ریسک آماده | نماد: %s | موجودی: $%.2f", m_symbol, m_dailyStartBalance), "INFO");
}

CRiskManager::~CRiskManager() {
   if(m_atrHandle != INVALID_HANDLE) {
      IndicatorRelease(m_atrHandle);
      m_atrHandle = INVALID_HANDLE;
   }
}

void CRiskManager::InitializeATR(const int period, const ENUM_TIMEFRAMES tf) {
   if(m_atrHandle != INVALID_HANDLE) IndicatorRelease(m_atrHandle);
   m_atrHandle = iATR(m_symbol, tf, period);
   if(m_atrHandle == INVALID_HANDLE) LogMessage("خطا در مقداردهی ATR", "ERROR");
}

double CRiskManager::GetATRValue(const int shift) {
   if(m_atrHandle == INVALID_HANDLE) return 0;
   double atr[];
   ArraySetAsSeries(atr, true);
   if(CopyBuffer(m_atrHandle, 0, 0, shift + 1, atr) <= 0) return 0;
   return atr[shift];
}

void CRiskManager::SetATRMultipliers(const double slMult, const double tpMult) {
   m_atrMultiplierSL = MathMax(0.5, slMult);
   m_atrMultiplierTP = MathMax(1.0, tpMult);
}

double CRiskManager::GetAccountBalance() { return AccountInfoDouble(ACCOUNT_BALANCE); }
double CRiskManager::GetEquity() { return AccountInfoDouble(ACCOUNT_EQUITY); }
double CRiskManager::GetUsedMargin() { return AccountInfoDouble(ACCOUNT_MARGIN); }
double CRiskManager::GetFreeMargin() { return AccountInfoDouble(ACCOUNT_MARGIN_FREE); }

int CRiskManager::CountPositionsForSymbol() {
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      count++;
   }
   return count;
}

int CRiskManager::CountTodayDeals() {
   datetime todayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   int count = 0;
   if(HistorySelect(todayStart, TimeCurrent())) {
      int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++) {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0) continue;
         if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != m_magic) continue;
         if(HistoryDealGetString(ticket, DEAL_SYMBOL) != m_symbol) continue;
         if(HistoryDealGetInteger(ticket, DEAL_ENTRY) == DEAL_ENTRY_IN) count++;
      }
   }
   return count;
}

double CRiskManager::CalculateTodayPnL() {
   double pnl = 0;
   datetime todayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   if(HistorySelect(todayStart, TimeCurrent())) {
      int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++) {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0) continue;
         if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != m_magic) continue;
         if(HistoryDealGetString(ticket, DEAL_SYMBOL) != m_symbol) continue;
         pnl += HistoryDealGetDouble(ticket, DEAL_PROFIT);
         pnl += HistoryDealGetDouble(ticket, DEAL_SWAP);
         pnl += HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      }
   }
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;
      pnl += PositionGetDouble(POSITION_PROFIT);
      pnl += PositionGetDouble(POSITION_SWAP);
   }
   return pnl;
}

double CRiskManager::CalculateMaxDrawdown() {
   if(m_peakBalance <= 0) return 0;
   double equity = GetEquity();
   if(equity > m_peakBalance) { m_peakBalance = equity; return 0; }
   return ((m_peakBalance - equity) / m_peakBalance) * 100.0;
}

bool CRiskManager::IsSpreadAcceptable() {
   return (int)SymbolInfoInteger(m_symbol, SYMBOL_SPREAD) <= MaxSpread;
}

bool CRiskManager::IsMarginAvailable(const double lot) {
   double freeMargin = GetFreeMargin();
   double contractSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double price = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
   double leverage = (double)AccountInfoInteger(ACCOUNT_LEVERAGE);
   if(leverage <= 0) leverage = 100;
   double marginRequired = (lot * contractSize * price) / leverage;
   return marginRequired < (freeMargin * 0.80);
}

double CRiskManager::NormalizeLot(const double lot) {
   double minLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
   if(minLot <= 0 || maxLot <= 0 || stepLot <= 0) return 0;
   double cfgMin = MathMax(minLot, MinLot);
   double cfgMax = MathMin(maxLot, MaxLot);
   double normalized = MathFloor(lot / stepLot) * stepLot;
   normalized = MathMax(normalized, cfgMin);
   normalized = MathMin(normalized, cfgMax);
   return NormalizeDouble(normalized, 2);
}

double CRiskManager::NormalizePrice(const double price) {
   return NormalizeDouble(price, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
}

void CRiskManager::SetMaxDailyLossPercent(const double percent) { m_maxDailyLossPercent = MathMax(0.1, MathMin(100.0, percent)); }
void CRiskManager::SetMaxDrawdownPercent(const double percent) { m_maxDrawdownPercent = MathMax(0.1, MathMin(100.0, percent)); }

LotCalculationResult CRiskManager::CalculateLot(const double riskPercent, const double slPoints, const ENUM_POSITION_TYPE direction) {
   LotCalculationResult result;
   ZeroMemory(result);
   if(riskPercent <= 0 || slPoints <= 0) { result.isValid = false; result.errorMessage = "پارامترهای ورودی نامعتبر"; return result; }
   if(FixedLot > 0) { result.lot = NormalizeLot(FixedLot); result.isValid = (result.lot > 0); return result; }
   double capital = UseEquityForRisk ? GetEquity() : GetAccountBalance();
   if(capital <= 0) { result.isValid = false; result.errorMessage = "موجودی صفر"; return result; }
   double riskMoney = capital * (riskPercent / 100.0);
   double tickValue = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   if(tickValue <= 0 || tickSize <= 0) { result.isValid = false; result.errorMessage = "خطا در دریافت اطلاعات نماد"; return result; }
   double pointValue = tickValue * (point / tickSize);
   double slMoneyPerLot = slPoints * pointValue;
   if(slMoneyPerLot <= 0) { result.isValid = false; result.errorMessage = "خطا در محاسبه ارزش SL"; return result; }
   double lot = riskMoney / slMoneyPerLot;
   lot = NormalizeLot(lot);
   if(!IsMarginAvailable(lot)) {
      double stepLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      double minLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
      while(lot > minLot && !IsMarginAvailable(lot)) { lot -= stepLot; lot = NormalizeDouble(lot, 2); }
      if(!IsMarginAvailable(lot)) { result.isValid = false; result.errorMessage = "مارجین کافی نیست"; return result; }
   }
   result.lot = lot; result.riskAmount = riskMoney; result.riskPercent = riskPercent;
   result.stopLossDistance = slPoints; result.isValid = (lot > 0);
   LogMessage(StringFormat("محاسبه لات: %.2f | ریسک: $%.2f (%.1f%%) | SL: %.0f پوینت", result.lot, result.riskAmount, result.riskPercent, result.stopLossDistance), "INFO");
   return result;
}

LotCalculationResult CRiskManager::CalculateLotByMoney(const double riskMoney, const double slPoints) {
   LotCalculationResult result;
   ZeroMemory(result);
   if(riskMoney <= 0 || slPoints <= 0) { result.isValid = false; result.errorMessage = "پارامترها نامعتبر"; return result; }
   double tickValue = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   double pointValue = tickValue * (point / tickSize);
   double slMoneyPerLot = slPoints * pointValue;
   if(slMoneyPerLot <= 0) { result.isValid = false; result.errorMessage = "خطا در محاسبه"; return result; }
   double lot = NormalizeLot(riskMoney / slMoneyPerLot);
   result.lot = lot; result.riskAmount = riskMoney; result.stopLossDistance = slPoints; result.isValid = (lot > 0);
   return result;
}

double CRiskManager::ValidateAndAdjustLot(const double lot) {
   double adjusted = NormalizeLot(lot);
   if(!IsMarginAvailable(adjusted)) {
      double stepLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      double minLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
      while(adjusted > minLot && !IsMarginAvailable(adjusted)) { adjusted -= stepLot; adjusted = NormalizeDouble(adjusted, 2); }
   }
   return adjusted;
}

SLTPResult CRiskManager::CalculateSLTP_ATR(const ENUM_POSITION_TYPE direction, const double entryPrice, const double rrRatio) {
   SLTPResult result;
   ZeroMemory(result);
   result.method = "ATR";
   double atr = GetATRValue(1);
   if(atr <= 0) { result.isValid = false; return result; }
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   double slDistance = atr * m_atrMultiplierSL;
   double tpDistance = slDistance * rrRatio;
   if(direction == POSITION_TYPE_BUY) {
      result.stopLossPrice = NormalizePrice(entryPrice - slDistance);
      result.takeProfitPrice = NormalizePrice(entryPrice + tpDistance);
   } else {
      result.stopLossPrice = NormalizePrice(entryPrice + slDistance);
      result.takeProfitPrice = NormalizePrice(entryPrice - tpDistance);
   }
   result.stopLossPoints = slDistance / point;
   result.takeProfitPoints = tpDistance / point;
   result.riskRewardRatio = rrRatio;
   result.isValid = (result.stopLossPrice > 0 && result.takeProfitPrice > 0);
   LogMessage(StringFormat("SL/TP بر اساس ATR | ATR: %.5f | SL: %.5f | TP: %.5f | RR: 1:%.1f", atr, result.stopLossPrice, result.takeProfitPrice, rrRatio), "INFO");
   return result;
}

SLTPResult CRiskManager::CalculateSLTP_Fixed(const ENUM_POSITION_TYPE direction, const double entryPrice, const double slPoints, const double rrRatio) {
   SLTPResult result;
   ZeroMemory(result);
   result.method = "Fixed";
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   double slDistance = slPoints * point;
   double tpDistance = slDistance * rrRatio;
   if(direction == POSITION_TYPE_BUY) {
      result.stopLossPrice = NormalizePrice(entryPrice - slDistance);
      result.takeProfitPrice = NormalizePrice(entryPrice + tpDistance);
   } else {
      result.stopLossPrice = NormalizePrice(entryPrice + slDistance);
      result.takeProfitPrice = NormalizePrice(entryPrice - tpDistance);
   }
   result.stopLossPoints = slPoints;
   result.takeProfitPoints = slPoints * rrRatio;
   result.riskRewardRatio = rrRatio;
   result.isValid = (result.stopLossPrice > 0 && result.takeProfitPrice > 0);
   return result;
}

SLTPResult CRiskManager::CalculateSLTP_Structure(const ENUM_POSITION_TYPE direction, const double entryPrice, const double structureLevel, const double rrRatio, const double bufferPoints) {
   SLTPResult result;
   ZeroMemory(result);
   result.method = "Structure";
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   double buffer = bufferPoints * point;
   double atr = GetATRValue(1);
   double atrBuffer = (atr > 0) ? atr * 0.1 : buffer;
   if(direction == POSITION_TYPE_BUY) {
      result.stopLossPrice = NormalizePrice(structureLevel - MathMax(buffer, atrBuffer));
      double slDistance = entryPrice - result.stopLossPrice;
      result.takeProfitPrice = NormalizePrice(entryPrice + (slDistance * rrRatio));
   } else {
      result.stopLossPrice = NormalizePrice(structureLevel + MathMax(buffer, atrBuffer));
      double slDistance = result.stopLossPrice - entryPrice;
      result.takeProfitPrice = NormalizePrice(entryPrice - (slDistance * rrRatio));
   }
   result.stopLossPoints = MathAbs(entryPrice - result.stopLossPrice) / point;
   result.takeProfitPoints = MathAbs(entryPrice - result.takeProfitPrice) / point;
   result.riskRewardRatio = rrRatio;
   result.isValid = (result.stopLossPoints >= 5 && result.takeProfitPoints >= 5);
   return result;
}

SLTPResult CRiskManager::CalculateSLTP_OrderBlock(const ENUM_POSITION_TYPE direction, const double entryPrice, const double obHigh, const double obLow, const double rrRatio) {
   SLTPResult result;
   ZeroMemory(result);
   result.method = "OrderBlock";
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   double atr = GetATRValue(1);
   double buffer = (atr > 0) ? atr * 0.1 : 5 * point;
   if(direction == POSITION_TYPE_BUY) {
      result.stopLossPrice = NormalizePrice(obLow - buffer);
      double slDistance = entryPrice - result.stopLossPrice;
      result.takeProfitPrice = NormalizePrice(entryPrice + (slDistance * rrRatio));
   } else {
      result.stopLossPrice = NormalizePrice(obHigh + buffer);
      double slDistance = result.stopLossPrice - entryPrice;
      result.takeProfitPrice = NormalizePrice(entryPrice - (slDistance * rrRatio));
   }
   result.stopLossPoints = MathAbs(entryPrice - result.stopLossPrice) / point;
   result.takeProfitPoints = MathAbs(entryPrice - result.takeProfitPrice) / point;
   result.riskRewardRatio = rrRatio;
   result.isValid = (result.stopLossPoints >= 5 && result.takeProfitPoints >= 5);
   LogMessage(StringFormat("SL/TP بر اساس OB | SL: %.5f | TP: %.5f | RR: 1:%.1f", result.stopLossPrice, result.takeProfitPrice, rrRatio), "INFO");
   return result;
}

RiskCheckResult CRiskManager::CheckRiskBeforeTrade(const ENUM_POSITION_TYPE direction) {
   RiskCheckResult result;
   ZeroMemory(result);
   result.allowed = true;
   if(m_emergencyStopTriggered) { result.allowed = false; result.emergencyStop = true; result.reason = "توقف اضطراری فعال است"; return result; }
   if(!IsSpreadAcceptable()) { result.allowed = false; result.spreadTooHigh = true; result.reason = StringFormat("اسپرد بالا: %d", (int)SymbolInfoInteger(m_symbol, SYMBOL_SPREAD)); return result; }
   int openPositions = CountPositionsForSymbol();
   if(openPositions >= MaxOpenTrades) { result.allowed = false; result.maxPositionsReached = true; result.reason = StringFormat("حداکثر پوزیشن: %d/%d", openPositions, MaxOpenTrades); return result; }
   int todayTrades = CountTodayDeals();
   if(todayTrades >= MaxDailyTrades) { result.allowed = false; result.maxTradesReached = true; result.reason = StringFormat("حداکثر معاملات: %d/%d", todayTrades, MaxDailyTrades); return result; }
   if(IsDailyLossLimitReached()) { result.allowed = false; result.dailyLossLimitReached = true; result.reason = StringFormat("حد ضرر روزانه: %.2f%%", GetDailyPnLPercent()); return result; }
   m_currentDrawdown = CalculateMaxDrawdown();
   if(m_currentDrawdown >= m_maxDrawdownPercent) { result.allowed = false; result.maxDrawdownReached = true; result.reason = StringFormat("حداکثر drawdown: %.2f%%", m_currentDrawdown); TriggerEmergencyStop(); return result; }
   return result;
}

bool CRiskManager::CanOpenTrade() { return CheckRiskBeforeTrade(POSITION_TYPE_BUY).allowed; }
bool CRiskManager::IsDailyLossLimitReached() { return GetDailyPnLPercent() <= -m_maxDailyLossPercent; }
bool CRiskManager::IsMaxPositionsReached() { return CountPositionsForSymbol() >= MaxOpenTrades; }
bool CRiskManager::IsMaxDrawdownReached() { return CalculateMaxDrawdown() >= m_maxDrawdownPercent; }
bool CRiskManager::IsEmergencyStop() { return m_emergencyStopTriggered; }

void CRiskManager::TriggerEmergencyStop() {
   m_emergencyStopTriggered = true;
   LogMessage("⚠️ توقف اضطراری فعال شد!", "ERROR");
}

void CRiskManager::ResetDailyStats() {
   m_dailyStartBalance = GetAccountBalance();
   m_peakBalance = MathMax(m_peakBalance, m_dailyStartBalance);
   m_emergencyStopTriggered = false;
   LogMessage(StringFormat("آمار روزانه بازنشانی شد | موجودی: $%.2f", m_dailyStartBalance), "INFO");
}

void CRiskManager::ResetWeeklyStats() { m_weeklyStartBalance = GetAccountBalance(); }
void CRiskManager::ResetMonthlyStats() { m_monthlyStartBalance = GetAccountBalance(); }
void CRiskManager::UpdatePeakBalance() { double eq = GetEquity(); if(eq > m_peakBalance) m_peakBalance = eq; }

bool CRiskManager::UpdateTrailingStop(const ulong ticket, const double trailPoints, const double stepPoints) {
   if(!PositionSelectByTicket(ticket)) return false;
   string symbol = PositionGetString(POSITION_SYMBOL);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double currentSL = PositionGetDouble(POSITION_SL);
   double currentTP = PositionGetDouble(POSITION_TP);
   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double trailDistance = trailPoints * point;
   double stepDistance = stepPoints * point;
   MqlTradeRequest request;
   MqlTradeResult  tradeResult;
   ZeroMemory(request); ZeroMemory(tradeResult);
   request.action = TRADE_ACTION_SLTP;
   request.symbol = symbol;
   request.position = ticket;
   request.tp = currentTP;
   if(posType == POSITION_TYPE_BUY) {
      double newSL = bid - trailDistance;
      if(newSL > currentSL + stepDistance && newSL > openPrice) {
         request.sl = NormalizeDouble(newSL, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
         if(OrderSend(request, tradeResult)) { LogMessage(StringFormat("Trailing Stop به‌روز شد | Ticket: %d | SL: %.5f", ticket, newSL), "INFO"); return true; }
      }
   } else {
      double newSL = ask + trailDistance;
      if((currentSL == 0 || newSL < currentSL - stepDistance) && newSL < openPrice) {
         request.sl = NormalizeDouble(newSL, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
         if(OrderSend(request, tradeResult)) { LogMessage(StringFormat("Trailing Stop به‌روز شد | Ticket: %d | SL: %.5f", ticket, newSL), "INFO"); return true; }
      }
   }
   return false;
}

bool CRiskManager::UpdateBreakEven(const ulong ticket, const double triggerPoints, const double offsetPoints) {
   if(!PositionSelectByTicket(ticket)) return false;
   string symbol = PositionGetString(POSITION_SYMBOL);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double currentSL = PositionGetDouble(POSITION_SL);
   double currentTP = PositionGetDouble(POSITION_TP);
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double triggerDistance = triggerPoints * point;
   double offsetDistance = offsetPoints * point;
   double newSL = 0;
   bool shouldUpdate = false;
   if(posType == POSITION_TYPE_BUY) {
      if(bid >= openPrice + triggerDistance) { newSL = openPrice + offsetDistance; if(newSL > currentSL) shouldUpdate = true; }
   } else {
      if(ask <= openPrice - triggerDistance) { newSL = openPrice - offsetDistance; if(currentSL == 0 || newSL < currentSL) shouldUpdate = true; }
   }
   if(shouldUpdate && newSL > 0) {
      MqlTradeRequest req; MqlTradeResult res; ZeroMemory(req); ZeroMemory(res);
      req.action = TRADE_ACTION_SLTP; req.symbol = symbol; req.position = ticket;
      req.sl = NormalizeDouble(newSL, digits); req.tp = currentTP;
      if(OrderSend(req, res)) { LogMessage(StringFormat("Break Even فعال شد | Ticket: %d | SL: %.5f", ticket, newSL), "INFO"); return true; }
   }
   return false;
}

double CRiskManager::GetCurrentDrawdown() { m_currentDrawdown = CalculateMaxDrawdown(); return m_currentDrawdown; }
double CRiskManager::GetDailyPnL() { return CalculateTodayPnL(); }
double CRiskManager::GetDailyPnLPercent() { if(m_dailyStartBalance <= 0) return 0; return (CalculateTodayPnL() / m_dailyStartBalance) * 100.0; }
double CRiskManager::GetWeeklyPnL() { return (m_weeklyStartBalance > 0) ? GetAccountBalance() - m_weeklyStartBalance + CalculateTodayPnL() : 0; }
double CRiskManager::GetMonthlyPnL() { return (m_monthlyStartBalance > 0) ? GetAccountBalance() - m_monthlyStartBalance + CalculateTodayPnL() : 0; }
int CRiskManager::GetOpenPositionsCount() { return CountPositionsForSymbol(); }
int CRiskManager::GetTodayTradesCount() { return CountTodayDeals(); }
double CRiskManager::GetRiskPerTrade() { return RiskPercent; }
double CRiskManager::GetCurrentATR() { return GetATRValue(1); }
bool CRiskManager::IsSymbolTradeable() { return SymbolInfoInteger(m_symbol, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_DISABLED && IsSpreadAcceptable(); }
bool CRiskManager::IsSessionAllowed() { if(!UseTimeFilter) return true; return IsTradingTime(); }
bool CRiskManager::ValidateSymbolSettings() { return MaxSpread > 0; }

string CRiskManager::GetRiskReport() {
   string r = "📊 گزارش ریسک\n\n";
   r += StringFormat("💰 موجودی: $%.2f\n", GetAccountBalance());
   r += StringFormat("📈 اکوئیتی: $%.2f\n", GetEquity());
   r += StringFormat("📅 سود/ضرر امروز: $%.2f (%.2f%%)\n", GetDailyPnL(), GetDailyPnLPercent());
   r += StringFormat("📉 Drawdown فعلی: %.2f%%\n\n", GetCurrentDrawdown());
   r += StringFormat("🔢 پوزیشن‌ها: %d/%d\n", GetOpenPositionsCount(), MaxOpenTrades);
   r += StringFormat("📋 معاملات امروز: %d/%d\n", GetTodayTradesCount(), MaxDailyTrades);
   r += StringFormat("🔀 اسپرد: %d (حداکثر: %d)\n", (int)SymbolInfoInteger(m_symbol, SYMBOL_SPREAD), MaxSpread);
   if(m_emergencyStopTriggered) r += "\n⚠️ توقف اضطراری فعال است!";
   return r;
}

string CRiskManager::GetDetailedRiskReport() {
   string r = GetRiskReport();
   r += StringFormat("\n\nATR فعلی: %.5f\n", GetCurrentATR());
   r += StringFormat("ضریب SL: %.1fx | ضریب TP: %.1fx\n", m_atrMultiplierSL, m_atrMultiplierTP);
   r += StringFormat("📆 سود هفتگی: $%.2f\n", GetWeeklyPnL());
   r += StringFormat("📆 سود ماهانه: $%.2f\n", GetMonthlyPnL());
   r += StringFormat("🔝 اوج موجودی: $%.2f\n", m_peakBalance);
   return r;
}
//+------------------------------------------------------------------+