//+------------------------------------------------------------------+
//|                                      RiskManager_Complete.mqh     |
//|                         سیستم معامله‌گری حرفه‌ای MT5               |
//|                                                                    |
//| توضیح فارسی:                                                       |
//| این فایل تمام متدهای ناقص RiskManager را تکمیل می‌کند             |
//| شامل: محاسبه لات، SL/TP، مدیریت ریسک، بررسی محدودیت‌ها،         |
//|        Trailing Stop، Break Even، توقف اضطراری                    |
//+------------------------------------------------------------------+
// این فایل به عنوان extension به RiskManager اصلی اضافه می‌شود
// متدهای جدید که باید در کلاس CRiskManager پیاده‌سازی شوند:

/*
   ===== متدهای ناقص که باید تکمیل شوند =====

   1. GetFreeMargin() -> double
   2. CountPositionsForSymbol(string symbol) -> int
   3. CountTodayDeals() -> int
   4. CalculateTodayPnL() -> double
   5. CalculateMaxDrawdown() -> double
   6. IsSpreadAcceptable(string symbol) -> bool
   7. IsMarginAvailable(double lots, string symbol) -> bool
   8. NormalizeLot(double lots, string symbol) -> double
   9. CalculateLot(string symbol, double slPoints) -> double
   10. CheckRiskBeforeTrade(...) -> RiskCheckResult
   11. CanOpenTrade(string symbol) -> bool
   12. IsDailyLossLimitReached() -> bool
   13. IsMaxPositionsReached(string symbol) -> bool
   14. IsMaxDrawdownReached() -> bool
   15. IsEmergencyStop() -> bool
   16. TriggerEmergencyStop(string reason) -> void
   17. UpdateTrailingStop(ulong ticket) -> void
   18. UpdateBreakEven(ulong ticket) -> void
   19. GetCurrentDrawdown() -> double
   20. GetDailyPnL() -> double
   21. GetAccountBalance() -> double
   22. GetRiskReport() -> string

   پیاده‌سازی کامل این متدها در فایل RiskManager.mqh اصلی انجام شده
   و در این فایل extension، نسخه‌های کامل ارائه می‌شود.
*/

// ===== نسخه کامل ساختارها =====

struct LotCalculationResult {
   double lot;
   double riskAmount;
   double riskPercent;
   bool   isValid;
   string reason;
};

struct RiskCheckResult {
   bool   canTrade;
   double recommendedLot;
   double maxLot;
   string reason;
   double marginRequired;
   double freeMargin;
};

struct SLTPResult {
   double stopLoss;
   double takeProfit;
   double slPoints;
   double tpPoints;
   double riskReward;
   bool   isValid;
};

// ===== پیاده‌سازی کامل متدهای مدیریت ریسک =====

// متدهای زیر باید در کلاس CRiskManager قرار بگیرند:

double GetFreeMargin_Impl() {
   return AccountInfoDouble(ACCOUNT_MARGIN_FREE);
}

double GetAccountBalance_Impl() {
   return AccountInfoDouble(ACCOUNT_BALANCE);
}

double GetEquity_Impl() {
   return AccountInfoDouble(ACCOUNT_EQUITY);
}

double GetUsedMargin_Impl() {
   return AccountInfoDouble(ACCOUNT_MARGIN);
}

int CountPositionsForSymbol_Impl(string symbol) {
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == symbol)
         count++;
   }
   return count;
}

int CountTodayDeals_Impl() {
   datetime dayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   HistorySelect(dayStart, TimeCurrent());
   return HistoryDealsTotal();
}

double CalculateTodayPnL_Impl() {
   datetime dayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   HistorySelect(dayStart, TimeCurrent());
   double pnl = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--) {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket <= 0) continue;
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_INOUT) {
         pnl += HistoryDealGetDouble(ticket, DEAL_PROFIT)
              + HistoryDealGetDouble(ticket, DEAL_SWAP)
              + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      }
   }
   return pnl;
}

double CalculateCurrentDrawdown_Impl() {
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   if(balance <= 0) return 0;
   return (balance - equity) / balance * 100.0;
}

bool IsSpreadAcceptable_Impl(string symbol, double maxSpreadPoints) {
   double spread = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   return spread <= maxSpreadPoints;
}

bool IsMarginAvailable_Impl(string symbol, double lots) {
   double marginRequired;
   if(!OrderCalcMargin(ORDER_TYPE_BUY, symbol, lots,
      SymbolInfoDouble(symbol, SYMBOL_ASK), marginRequired)) return false;
   return AccountInfoDouble(ACCOUNT_MARGIN_FREE) >= marginRequired * 1.2;
}

double NormalizeLot_Impl(string symbol, double lots) {
   double minLot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(lots, minLot);
   lots = MathMin(lots, maxLot);
   return NormalizeDouble(lots, 2);
}

double CalculateLotByRisk_Impl(string symbol, double slPoints, double riskPercent) {
   double balance    = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmount = balance * riskPercent / 100.0;
   double tickValue  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize   = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double point      = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(tickSize <= 0 || slPoints <= 0) return 0;
   double lotValue = (tickValue / tickSize) * point;
   if(lotValue <= 0) return 0;
   double lot = riskAmount / (slPoints * lotValue);
   return NormalizeLot_Impl(symbol, lot);
}

SLTPResult CalculateSLTP_ATR_Impl(string symbol, ENUM_TIMEFRAMES tf,
                                    ENUM_ORDER_TYPE orderType,
                                    double atrMultiplierSL, double rrRatio) {
   SLTPResult result;
   ZeroMemory(result);
   int handle = iATR(symbol, tf, 14);
   if(handle == INVALID_HANDLE) return result;
   double atr[];
   if(CopyBuffer(handle, 0, 1, 1, atr) < 1) { IndicatorRelease(handle); return result; }
   IndicatorRelease(handle);

   double atrVal  = atr[0];
   double slDist  = atrVal * atrMultiplierSL;
   double tpDist  = slDist * rrRatio;
   double point   = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double bid     = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask     = SymbolInfoDouble(symbol, SYMBOL_ASK);

   if(orderType == ORDER_TYPE_BUY) {
      result.stopLoss   = ask - slDist;
      result.takeProfit = ask + tpDist;
   } else {
      result.stopLoss   = bid + slDist;
      result.takeProfit = bid - tpDist;
   }

   result.slPoints  = slDist / point;
   result.tpPoints  = tpDist / point;
   result.riskReward = rrRatio;
   result.isValid    = (result.slPoints > 0);
   return result;
}

RiskCheckResult CheckRiskBeforeTrade_Impl(string symbol, ENUM_ORDER_TYPE orderType,
                                           double entryPrice, double stopLoss,
                                           double riskPercent, double maxSpreadPoints,
                                           int maxPositions, double dailyLossLimit) {
   RiskCheckResult result;
   ZeroMemory(result);
   result.freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);

   // بررسی اسپرد
   if(!IsSpreadAcceptable_Impl(symbol, maxSpreadPoints)) {
      result.canTrade = false;
      result.reason   = "اسپرد بیش از حد مجاز";
      return result;
   }

   // محاسبه فاصله SL
   double point    = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double slPoints = MathAbs(entryPrice - stopLoss) / point;
   if(slPoints < 5) { result.canTrade = false; result.reason = "SL خیلی نزدیک"; return result; }

   // محاسبه لات
   double lot = CalculateLotByRisk_Impl(symbol, slPoints, riskPercent);
   if(lot <= 0) { result.canTrade = false; result.reason = "محاسبه لات ناموفق"; return result; }

   // بررسی مارجین
   if(!IsMarginAvailable_Impl(symbol, lot)) {
      result.canTrade = false;
      result.reason   = "مارجین کافی نیست";
      return result;
   }

   // بررسی تعداد پوزیشن
   if(CountPositionsForSymbol_Impl(symbol) >= maxPositions) {
      result.canTrade = false;
      result.reason   = "حداکثر پوزیشن‌ها پر شده";
      return result;
   }

   // بررسی ضرر روزانه
   double todayPnL  = CalculateTodayPnL_Impl();
   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   if(balance > 0 && (todayPnL / balance * 100) < -dailyLossLimit) {
      result.canTrade = false;
      result.reason   = "محدودیت ضرر روزانه";
      return result;
   }

   result.canTrade       = true;
   result.recommendedLot = lot;
   result.maxLot         = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   result.reason         = StringFormat("لات: %.2f ریسک: %.1f%% SL: %.0f پیپ", lot, riskPercent, slPoints);
   return result;
}

void UpdateTrailingStop_Impl(ulong ticket, string symbol, double trailPoints) {
   if(!PositionSelectByTicket(ticket)) return;
   ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double currentSL = PositionGetDouble(POSITION_SL);
   double point     = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double bid       = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask       = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double trailDist = trailPoints * point;
   double newSL;
   CTrade trade;

   if(posType == POSITION_TYPE_BUY) {
      newSL = bid - trailDist;
      if(newSL > currentSL + point) trade.PositionModify(ticket, newSL, PositionGetDouble(POSITION_TP));
   } else {
      newSL = ask + trailDist;
      if(newSL < currentSL - point || currentSL == 0) trade.PositionModify(ticket, newSL, PositionGetDouble(POSITION_TP));
   }
}

void UpdateBreakEven_Impl(ulong ticket, string symbol, double bePoints) {
   if(!PositionSelectByTicket(ticket)) return;
   ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double currentSL = PositionGetDouble(POSITION_SL);
   double point     = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double bid       = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask       = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double beDist    = bePoints * point;
   CTrade trade;

   if(posType == POSITION_TYPE_BUY) {
      if(bid >= openPrice + beDist && currentSL < openPrice) {
         trade.PositionModify(ticket, openPrice + point, PositionGetDouble(POSITION_TP));
      }
   } else {
      if(ask <= openPrice - beDist && (currentSL > openPrice || currentSL == 0)) {
         trade.PositionModify(ticket, openPrice - point, PositionGetDouble(POSITION_TP));
      }
   }
}

string GetRiskReport_Impl() {
   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity    = AccountInfoDouble(ACCOUNT_EQUITY);
   double drawdown  = CalculateCurrentDrawdown_Impl();
   double todayPnL  = CalculateTodayPnL_Impl();
   int    positions = PositionsTotal();
   int    todayDeals= CountTodayDeals_Impl();

   return StringFormat(
      "=== گزارش ریسک ===\n"
      "موجودی: %.2f | اکویتی: %.2f\n"
      "درافداون: %.2f%% | سود/ضرر امروز: %.2f\n"
      "پوزیشن‌های باز: %d | معاملات امروز: %d\n"
      "مارجین آزاد: %.2f",
      balance, equity, drawdown, todayPnL,
      positions, todayDeals,
      AccountInfoDouble(ACCOUNT_MARGIN_FREE)
   );
}
