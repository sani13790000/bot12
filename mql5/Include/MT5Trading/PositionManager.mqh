//+------------------------------------------------------------------+
//|                                             PositionManager.mqh     |
//|                                    MT5 Trading System              |
//|                                    مدیریت پوزیشن‌ها                 |
//+------------------------------------------------------------------+
#property strict

#include <Trade/Trade.mqh>
#include "Config.mqh"
#include "Helpers.mqh"

//+
// ساختار پوزیشن
//+
struct PositionInfo {
   ulong ticket;
   string symbol;
   ENUM_POSITION_TYPE type;
   double volume;
   double openPrice;
   double currentPrice;
   double sl;
   double tp;
   double profit;
   double swap;
   double commission;
   datetime openTime;
   string comment;
   int magic;
};

//+
// کلاس مدیریت پوزیشن
//+
class CPositionManager {
private:
   CTrade m_trade;
   string m_symbol;
   int m_magic;

   // پوزیشن‌های ردیابی شده
   PositionInfo m_positions[];

   // توابع کمکی
   int FindPosition(const ulong ticket);
   void UpdatePositionInfo(const int index);
   bool ShouldTrailStop(const PositionInfo &pos, double &newSL);
   bool ShouldMoveToBE(const PositionInfo &pos, double &newSL);
   bool ShouldPartialClose(const PositionInfo &pos, double &closeVolume);

public:
   CPositionManager(const string symbol);
   ~CPositionManager();

   // دریافت پوزیشن‌ها
   bool UpdatePositions();
   int GetPositionCount();
   int GetBuyCount();
   int GetSellCount();
   double GetTotalProfit();
   double GetTotalVolume();
   double GetMaxDrawdown();

   // دریافت پوزیشن خاص
   bool GetPosition(const ulong ticket, PositionInfo &pos);
   bool GetFirstPosition(PositionInfo &pos);
   bool GetLastPosition(PositionInfo &pos);
   bool GetBestPosition(PositionInfo &pos);
   bool GetWorstPosition(PositionInfo &pos);

   // مدیریت حد ضرر/سود
   bool MoveToBreakeven(const ulong ticket);
   bool TrailStop(const ulong ticket, const double trailPoints);
   bool SetSlTp(const ulong ticket, const double sl, const double tp);
   bool SetPartialTp(const ulong ticket, const double percent);

   // بستن پوزیشن
   bool ClosePosition(const ulong ticket, const string reason = "");
   bool ClosePositionPartial(const ulong ticket, const double percent);
   bool CloseAllPositions(const string direction = "");
   bool CloseProfitablePositions(const double minProfit = 0);
   bool CloseLosingPositions(const double maxLoss = 0);

   // مدیریت ریسک
   double CalculateRisk(const ulong ticket);
   double CalculateReward(const ulong ticket);
   double CalculateRR(const ulong ticket);
   bool IsAtRisk(const ulong ticket);

   // بررسی‌ها
   bool HasOpenPosition();
   bool HasReachedMaxPositions();
   bool IsPositionAtTP(const ulong ticket);
   bool IsPositionAtSL(const ulong ticket);

   // تریلینگ و مدیریت
   bool ProcessTrailingStops(const double trailPoints, const double stepPoints = 0);
   bool ProcessBreakeven(const double profitPoints = 0);
   bool ProcessPartialClose(const double triggerRR, const double closePercent);

   // گزارش
   string GetPositionReport();
};

//+
// سازنده
//+
CPositionManager::CPositionManager(const string symbol) {
   m_symbol = symbol;
   m_magic = (int)StringToInteger(MagicNumber);
   m_trade.SetExpertMagicNumber(m_magic);
   m_trade.SetDeviationInPoints(Slippage);

   ArraySetAsSeries(m_positions, false);
}

//+
// مخرب
//+
CPositionManager::~CPositionManager() {
}

//+
// یافتن پوزیشن در آرایه
//+
int CPositionManager::FindPosition(const ulong ticket) {
   for(int i = 0; i < ArraySize(m_positions); i++) {
      if(m_positions[i].ticket == ticket) {
         return i;
      }
   }
   return -1;
}

//+
// به‌روزرسانی اطلاعات پوزیشن
//+
void CPositionManager::UpdatePositionInfo(const int index) {
   if(index < 0 || index >= ArraySize(m_positions)) return;

   ulong ticket = m_positions[index].ticket;

   if(!PositionSelectByTicket(ticket)) return;

   m_positions[index].currentPrice = PositionGetDouble(POSITION_PRICE_CURRENT);
   m_positions[index].profit = PositionGetDouble(POSITION_PROFIT);
   m_positions[index].swap = PositionGetDouble(POSITION_SWAP);
   m_positions[index].commission = PositionGetDouble(POSITION_COMMISSION);
}

//+
// بررسی نیاز به تریلینگ
//+
bool CPositionManager::ShouldTrailStop(const PositionInfo &pos, double &newSL) {
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   double trailDistance = TrailingStop * point;
   double step = TrailingStep > 0 ? TrailingStep * point : trailDistance;

   if(pos.type == POSITION_TYPE_BUY) {
      newSL = pos.currentPrice - trailDistance;
      if(newSL > pos.sl + step) {
         return true;
      }
   } else {
      newSL = pos.currentPrice + trailDistance;
      if(pos.sl == 0 || newSL < pos.sl - step) {
         return true;
      }
   }

   return false;
}

//+
// بررسی نیاز به انتقال به BE
//+
bool CPositionManager::ShouldMoveToBE(const PositionInfo &pos, double &newSL) {
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   double beTrigger = BreakEvenTrigger * point;
   double beOffset = BreakEvenOffset * point;

   if(pos.type == POSITION_TYPE_BUY) {
      if(pos.currentPrice >= pos.openPrice + beTrigger) {
         if(pos.sl < pos.openPrice + beOffset) {
            newSL = NormalizeDouble(pos.openPrice + beOffset, digits);
            return true;
         }
      }
   } else {
      if(pos.currentPrice <= pos.openPrice - beTrigger) {
         if(pos.sl == 0 || pos.sl > pos.openPrice - beOffset) {
            newSL = NormalizeDouble(pos.openPrice - beOffset, digits);
            return true;
         }
      }
   }

   return false;
}

//+
// بررسی نیاز به بستن جزئی
//+
bool CPositionManager::ShouldPartialClose(const PositionInfo &pos, double &closeVolume) {
   double rr = CalculateRR(pos.ticket);

   if(rr >= PartialCloseRR) {
      closeVolume = pos.volume * (PartialClosePercent / 100.0);
      double step = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      closeVolume = MathFloor(closeVolume / step) * step;
      closeVolume = MathMax(closeVolume, SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN));
      return closeVolume < pos.volume && closeVolume > 0;
   }

   return false;
}

//+
// به‌روزرسانی همه پوزیشن‌ها
//+
bool CPositionManager::UpdatePositions() {
   // پاک کردن آرایه
   ArrayResize(m_positions, 0);

   int count = 0;

   // دریافت پوزیشن‌های مربوط به این EA
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      // فیلتر Magic Number
      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;

      // فیلتر نماد
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      // ذخیره اطلاعات
      PositionInfo pos;
      pos.ticket = ticket;
      pos.symbol = PositionGetString(POSITION_SYMBOL);
      pos.type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      pos.volume = PositionGetDouble(POSITION_VOLUME);
      pos.openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      pos.currentPrice = PositionGetDouble(POSITION_PRICE_CURRENT);
      pos.sl = PositionGetDouble(POSITION_SL);
      pos.tp = PositionGetDouble(POSITION_TP);
      pos.profit = PositionGetDouble(POSITION_PROFIT);
      pos.swap = PositionGetDouble(POSITION_SWAP);
      pos.commission = PositionGetDouble(POSITION_COMMISSION);
      pos.openTime = (datetime)PositionGetInteger(POSITION_TIME);
      pos.comment = PositionGetString(POSITION_COMMENT);
      pos.magic = (int)PositionGetInteger(POSITION_MAGIC);

      // اضافه به آرایه
      int size = ArraySize(m_positions);
      ArrayResize(m_positions, size + 1);
      m_positions[size] = pos;

      count++;
   }

   return count > 0;
}

//+
// دریافت تعداد پوزیشن
//+
int CPositionManager::GetPositionCount() {
   return ArraySize(m_positions);
}

//+
// دریافت تعداد خرید
//+
int CPositionManager::GetBuyCount() {
   int count = 0;
   for(int i = 0; i < ArraySize(m_positions); i++) {
      if(m_positions[i].type == POSITION_TYPE_BUY) count++;
   }
   return count;
}

//+
// دریافت تعداد فروش
//+
int CPositionManager::GetSellCount() {
   int count = 0;
   for(int i = 0; i < ArraySize(m_positions); i++) {
      if(m_positions[i].type == POSITION_TYPE_SELL) count++;
   }
   return count;
}

//+
// دریافت سود کل
//+
double CPositionManager::GetTotalProfit() {
   double total = 0;
   for(int i = 0; i < ArraySize(m_positions); i++) {
      total += m_positions[i].profit + m_positions[i].swap + m_positions[i].commission;
   }
   return total;
}

//+
// دریافت حجم کل
//+
double CPositionManager::GetTotalVolume() {
   double total = 0;
   for(int i = 0; i < ArraySize(m_positions); i++) {
      total += m_positions[i].volume;
   }
   return total;
}

//+
// دریافت حداکثر ضرر
//+
double CPositionManager::GetMaxDrawdown() {
   double maxDD = 0;
   double peak = 0;
   double equity = 0;

   // مرتب‌سازی بر اساس زمان
   PositionInfo sorted[];
   ArrayCopy(sorted, m_positions);

   // حذف شد - پیچیدگی زیاد
   // مرتب‌سازی ساده
   for(int i = 0; i < ArraySize(sorted); i++) {
      equity += sorted[i].profit;
      if(equity > peak) peak = equity;
      double dd = peak > 0 ? (peak - equity) / peak * 100 : 0;
      if(dd > maxDD) maxDD = dd;
   }

   return maxDD;
}

//+
// دریافت پوزیشن
//+
bool CPositionManager::GetPosition(const ulong ticket, PositionInfo &pos) {
   int index = FindPosition(ticket);
   if(index < 0) return false;

   pos = m_positions[index];
   return true;
}

//+
// دریافت اولین پوزیشن
//+
bool CPositionManager::GetFirstPosition(PositionInfo &pos) {
   if(ArraySize(m_positions) == 0) return false;

   datetime oldest = D'2100.01.01';
   int oldestIndex = -1;

   for(int i = 0; i < ArraySize(m_positions); i++) {
      if(m_positions[i].openTime < oldest) {
         oldest = m_positions[i].openTime;
         oldestIndex = i;
      }
   }

   if(oldestIndex >= 0) {
      pos = m_positions[oldestIndex];
      return true;
   }

   return false;
}

//+
// دریافت آخرین پوزیشن
//+
bool CPositionManager::GetLastPosition(PositionInfo &pos) {
   if(ArraySize(m_positions) == 0) return false;

   datetime newest = D'1970.01.01';
   int newestIndex = -1;

   for(int i = 0; i < ArraySize(m_positions); i++) {
      if(m_positions[i].openTime > newest) {
         newest = m_positions[i].openTime;
         newestIndex = i;
      }
   }

   if(newestIndex >= 0) {
      pos = m_positions[newestIndex];
      return true;
   }

   return false;
}

//+
// دریافت بهترین پوزیشن
//+
bool CPositionManager::GetBestPosition(PositionInfo &pos) {
   if(ArraySize(m_positions) == 0) return false;

   int bestIndex = 0;
   double bestProfit = m_positions[0].profit;

   for(int i = 1; i < ArraySize(m_positions); i++) {
      if(m_positions[i].profit > bestProfit) {
         bestProfit = m_positions[i].profit;
         bestIndex = i;
      }
   }

   pos = m_positions[bestIndex];
   return true;
}

//+
// دریافت بدترین پوزیشن
//+
bool CPositionManager::GetWorstPosition(PositionInfo &pos) {
   if(ArraySize(m_positions) == 0) return false;

   int worstIndex = 0;
   double worstProfit = m_positions[0].profit;

   for(int i = 1; i < ArraySize(m_positions); i++) {
      if(m_positions[i].profit < worstProfit) {
         worstProfit = m_positions[i].profit;
         worstIndex = i;
      }
   }

   pos = m_positions[worstIndex];
   return true;
}

//+
// انتقال به نقطه سر به سر
//+
bool CPositionManager::MoveToBreakeven(const ulong ticket) {
   if(!PositionSelectByTicket(ticket)) return false;

   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double currentSL = PositionGetDouble(POSITION_SL);
   ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

   // بررسی نیاز به انتقال
   if(type == POSITION_TYPE_BUY) {
      if(currentSL >= openPrice - point) return false;  // قبلاً انتقال یافته
      if(currentSL >= openPrice) return false;

      // انتقال
      return m_trade.PositionModify(ticket, openPrice + point, PositionGetDouble(POSITION_TP));
   } else {
      if(currentSL <= openPrice + point && currentSL > 0) return false;
      if(currentSL <= openPrice && currentSL > 0) return false;

      return m_trade.PositionModify(ticket, openPrice - point, PositionGetDouble(POSITION_TP));
   }

   return false;
}

//+
// تریلینگ استاپ
//+
bool CPositionManager::TrailStop(const ulong ticket, const double trailPoints) {
   if(!PositionSelectByTicket(ticket)) return false;

   double currentPrice = PositionGetDouble(POSITION_PRICE_CURRENT);
   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double currentSL = PositionGetDouble(POSITION_SL);
   double currentTP = PositionGetDouble(POSITION_TP);
   ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   double trailDistance = trailPoints * point;
   double newSL;

   if(type == POSITION_TYPE_BUY) {
      newSL = currentPrice - trailDistance;

      // فقط اگر حد ضرر جدید بالاتر باشد
      if(newSL <= currentSL + point) return false;

      // بررسی حرکت به سود
      if(newSL <= openPrice) return false;

      int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
      return m_trade.PositionModify(ticket, NormalizeDouble(newSL, digits), currentTP);
   } else {
      newSL = currentPrice + trailDistance;

      // فقط اگر حد ضرر جدید پایین‌تر باشد
      if(newSL >= currentSL - point && currentSL > 0) return false;

      // بررسی حرکت به سود
      if(newSL >= openPrice) return false;

      return m_trade.PositionModify(ticket, NormalizeDouble(newSL, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS)), currentTP);
   }

   return false;
}

//+
// تنظیم SL/TP
//+
bool CPositionManager::SetSlTp(const ulong ticket, const double sl, const double tp) {
   if(!PositionSelectByTicket(ticket)) return false;

   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
   double normSL = NormalizeDouble(sl, digits);
   double normTP = NormalizeDouble(tp, digits);

   return m_trade.PositionModify(ticket, normSL, normTP);
}

//+
// تنظیم TP جزئی
//+
bool CPositionManager::SetPartialTp(const ulong ticket, const double percent) {
   if(!PositionSelectByTicket(ticket)) return false;

   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double currentTP = PositionGetDouble(POSITION_TP);
   double currentSL = PositionGetDouble(POSITION_SL);
   ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   double newTP;
   if(type == POSITION_TYPE_BUY) {
      double distance = currentTP - openPrice;
      newTP = openPrice + (distance * percent / 100.0);
   } else {
      double distance = openPrice - currentTP;
      newTP = openPrice - (distance * percent / 100.0);
   }

   newTP = NormalizeDouble(newTP, digits);

   LogMessage(StringFormat("TP جزئی #%I64u: %.5f -> %.5f (%.0f%%)",
      ticket, currentTP, newTP, percent), "TRADE");

   return m_trade.PositionModify(ticket, currentSL, newTP);
}

//+
// بستن پوزیشن
//+
bool CPositionManager::ClosePosition(const ulong ticket, const string reason) {
   if(!PositionSelectByTicket(ticket)) {
      LogMessage("پوزیشن یافت نشد: " + IntegerToString(ticket), "ERROR");
      return false;
   }

   ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double volume = PositionGetDouble(POSITION_VOLUME);

   string dir = (type == POSITION_TYPE_BUY) ? "خرید" : "فروش";
   LogMessage("بستن پوزیشن: #" + IntegerToString(ticket) + " | " + dir + " | " + reason, "TRADE");

   if(m_trade.PositionClose(ticket)) {
      LogMessage("پوزیشن بسته شد", "INFO");
      return true;
   }

   LogMessage("خطا در بستن پوزیشن: " + IntegerToString(GetLastError()), "ERROR");
   return false;
}

//+
// بستن بخشی پوزیشن
//+
bool CPositionManager::ClosePositionPartial(const ulong ticket, const double percent) {
   if(!PositionSelectByTicket(ticket)) return false;

   double volume = PositionGetDouble(POSITION_VOLUME);
   double closeVolume = volume * (percent / 100.0);

   // نرمال‌سازی حجم
   double step = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
   closeVolume = MathFloor(closeVolume / step) * step;
   closeVolume = MathMax(closeVolume, SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN));

   ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

   if(type == POSITION_TYPE_BUY) {
      return m_trade.PositionClose(ticket, closeVolume);
   } else {
      return m_trade.PositionClose(ticket, closeVolume);
   }

   return false;
}

//+
// بستن همه پوزیشن‌ها
//+
bool CPositionManager::CloseAllPositions(const string direction) {
   int closed = 0;
   int failed = 0;

   UpdatePositions();

   for(int i = ArraySize(m_positions) - 1; i >= 0; i--) {
      PositionInfo pos = m_positions[i];

      // فیلتر جهت
      if(direction == "buy" && pos.type != POSITION_TYPE_BUY) continue;
      if(direction == "sell" && pos.type != POSITION_TYPE_SELL) continue;

      if(ClosePosition(pos.ticket, "بستن همه")) {
         closed++;
      } else {
         failed++;
      }
   }

   LogMessage(StringFormat("پوزیشن‌ها بسته شدند: %d موفق | %d ناموفق", closed, failed), "TRADE");

   return failed == 0;
}

//+
// بستن پوزیشن‌های سودده
//+
bool CPositionManager::CloseProfitablePositions(const double minProfit) {
   int closed = 0;

   UpdatePositions();

   for(int i = ArraySize(m_positions) - 1; i >= 0; i--) {
      if(m_positions[i].profit >= minProfit) {
         if(ClosePosition(m_positions[i].ticket, "بستن سودده")) {
            closed++;
         }
      }
   }

   return closed > 0;
}

//+
// بستن پوزیشن‌های زیان‌ده
//+
bool CPositionManager::CloseLosingPositions(const double maxLoss) {
   int closed = 0;

   UpdatePositions();

   for(int i = ArraySize(m_positions) - 1; i >= 0; i--) {
      if(m_positions[i].profit <= maxLoss) {
         if(ClosePosition(m_positions[i].ticket, "بستن زیان‌ده")) {
            closed++;
         }
      }
   }

   return closed > 0;
}

//+
// محاسبه ریسک
//+
double CPositionManager::CalculateRisk(const ulong ticket) {
   int index = FindPosition(ticket);
   if(index < 0) return 0;

   PositionInfo pos = m_positions[index];

   double diff;
   if(pos.type == POSITION_TYPE_BUY) {
      diff = pos.openPrice - pos.sl;
   } else {
      diff = pos.sl - pos.openPrice;
   }

   return MathAbs(diff * pos.volume * 100000);  // مقدار به دلار
}

//+
// محاسبه سود بالقوه
//+
double CPositionManager::CalculateReward(const ulong ticket) {
   int index = FindPosition(ticket);
   if(index < 0) return 0;

   PositionInfo pos = m_positions[index];

   double diff;
   if(pos.type == POSITION_TYPE_BUY) {
      diff = pos.tp - pos.openPrice;
   } else {
      diff = pos.openPrice - pos.tp;
   }

   return MathAbs(diff * pos.volume * 100000);
}

//+
// محاسبه R:R
//+
double CPositionManager::CalculateRR(const ulong ticket) {
   double risk = CalculateRisk(ticket);
   double reward = CalculateReward(ticket);

   if(risk == 0) return 0;
   return reward / risk;
}

//+
// بررسی پوزیشن در ریسک
//+
bool CPositionManager::IsAtRisk(const ulong ticket) {
   int index = FindPosition(ticket);
   if(index < 0) return false;

   UpdatePositionInfo(index);

   // بررسی اگر قیمت به حد ضرر نزدیک است (کمتر از 20% فاصله)
   PositionInfo pos = m_positions[index];

   double entryToSL, currentToSL;

   if(pos.type == POSITION_TYPE_BUY) {
      entryToSL = MathAbs(pos.openPrice - pos.sl);
      currentToSL = MathAbs(pos.currentPrice - pos.sl);
   } else {
      entryToSL = MathAbs(pos.sl - pos.openPrice);
      currentToSL = MathAbs(pos.sl - pos.currentPrice);
   }

   return currentToSL < (entryToSL * 0.2);
}

//+
// بررسی وجود پوزیشن باز
//+
bool CPositionManager::HasOpenPosition() {
   return ArraySize(m_positions) > 0;
}

//+
// بررسی سقف پوزیشن
//+
bool CPositionManager::HasReachedMaxPositions() {
   return ArraySize(m_positions) >= MaxOpenTrades;
}

//+
// بررسی رسیدن به TP
//+
bool CPositionManager::IsPositionAtTP(const ulong ticket) {
   int index = FindPosition(ticket);
   if(index < 0) return false;

   UpdatePositionInfo(index);
   PositionInfo pos = m_positions[index];

   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

   if(pos.type == POSITION_TYPE_BUY) {
      return pos.currentPrice >= pos.tp - (point * 5);
   } else {
      return pos.currentPrice <= pos.tp + (point * 5);
   }

   return false;
}

//+
// بررسی رسیدن به SL
//+
bool CPositionManager::IsPositionAtSL(const ulong ticket) {
   int index = FindPosition(ticket);
   if(index < 0) return false;

   UpdatePositionInfo(index);
   PositionInfo pos = m_positions[index];

   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

   if(pos.type == POSITION_TYPE_BUY) {
      return pos.currentPrice <= pos.sl + (point * 5);
   } else {
      return pos.currentPrice >= pos.sl - (point * 5);
   }

   return false;
}

//+
// پردازش تریلینگ استاپ برای همه پوزیشن‌ها
//+
bool CPositionManager::ProcessTrailingStops(const double trailPoints, const double stepPoints) {
   int modified = 0;
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   for(int i = 0; i < ArraySize(m_positions); i++) {
      PositionInfo pos = m_positions[i];
      UpdatePositionInfo(i);

      double trailDistance = trailPoints * point;
      double step = stepPoints > 0 ? stepPoints * point : trailDistance;

      double currentSL = m_positions[i].sl;
      double currentTP = m_positions[i].tp;
      double newSL;

      if(pos.type == POSITION_TYPE_BUY) {
         newSL = m_positions[i].currentPrice - trailDistance;

         if(newSL > currentSL + step) {
            if(PositionSelectByTicket(pos.ticket)) {
               if(m_trade.PositionModify(pos.ticket, NormalizeDouble(newSL, digits), currentTP)) {
                  modified++;
                  LogMessage(StringFormat("تریلینگ BUY #%I64u: SL %.5f -> %.5f",
                     pos.ticket, currentSL, newSL), "TRADE");
               }
            }
         }
      } else {
         newSL = m_positions[i].currentPrice + trailDistance;

         if(newSL < currentSL - step || currentSL == 0) {
            if(PositionSelectByTicket(pos.ticket)) {
               if(m_trade.PositionModify(pos.ticket, NormalizeDouble(newSL, digits), currentTP)) {
                  modified++;
                  LogMessage(StringFormat("تریلینگ SELL #%I64u: SL %.5f -> %.5f",
                     pos.ticket, currentSL, newSL), "TRADE");
               }
            }
         }
      }
   }

   return modified > 0;
}

//+
// پردازش انتقال به نقطه سر به سر
//+
bool CPositionManager::ProcessBreakeven(const double profitPoints) {
   int modified = 0;
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   for(int i = 0; i < ArraySize(m_positions); i++) {
      PositionInfo pos = m_positions[i];
      UpdatePositionInfo(i);

      double triggerProfit = profitPoints > 0 ? profitPoints * point : 0;

      if(pos.type == POSITION_TYPE_BUY) {
         double currentSL = m_positions[i].sl;

         if(m_positions[i].currentPrice >= pos.openPrice + triggerProfit) {
            if(currentSL < pos.openPrice) {
               double newSL = NormalizeDouble(pos.openPrice + 5 * point, digits);

               if(PositionSelectByTicket(pos.ticket)) {
                  if(m_trade.PositionModify(pos.ticket, newSL, m_positions[i].tp)) {
                     modified++;
                     LogMessage(StringFormat("BE BUY #%I64u: SL -> %.5f", pos.ticket, newSL), "TRADE");
                  }
               }
            }
         }
      } else {
         double currentSL = m_positions[i].sl;

         if(m_positions[i].currentPrice <= pos.openPrice - triggerProfit) {
            if(currentSL > pos.openPrice || currentSL == 0) {
               double newSL = NormalizeDouble(pos.openPrice - 5 * point, digits);

               if(PositionSelectByTicket(pos.ticket)) {
                  if(m_trade.PositionModify(pos.ticket, newSL, m_positions[i].tp)) {
                     modified++;
                     LogMessage(StringFormat("BE SELL #%I64u: SL -> %.5f", pos.ticket, newSL), "TRADE");
                  }
               }
            }
         }
      }
   }

   return modified > 0;
}

//+
// پردازش بستن جزئی
//+
bool CPositionManager::ProcessPartialClose(const double triggerRR, const double closePercent) {
   int closed = 0;

   for(int i = 0; i < ArraySize(m_positions); i++) {
      PositionInfo pos = m_positions[i];
      UpdatePositionInfo(i);

      double rr = CalculateRR(pos.ticket);

      if(rr >= triggerRR) {
         double closeVolume = pos.volume * (closePercent / 100.0);
         double step = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);

         closeVolume = MathFloor(closeVolume / step) * step;
         closeVolume = MathMax(closeVolume, SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN));

         if(closeVolume < pos.volume && closeVolume > 0) {
            if(ClosePositionPartial(pos.ticket, (closeVolume / pos.volume) * 100)) {
               closed++;
               LogMessage(StringFormat("بستن جزئی #%I64u: %.2f (R:R=%.1f)",
                  pos.ticket, closeVolume, rr), "TRADE");
            }
         }
      }
   }

   return closed > 0;
}

//+
// گزارش پوزیشن
//+
string CPositionManager::GetPositionReport() {
   string report = "📊 گزارش پوزیشن‌ها\n\n";

   report += StringFormat("تعداد کل: %d\n", GetPositionCount());
   report += StringFormat("خرید: %d | فروش: %d\n", GetBuyCount(), GetSellCount());
   report += StringFormat("سود کل: $%.2f\n", GetTotalProfit());
   report += StringFormat("حجم کل: %.2f\n\n", GetTotalVolume());

   if(ArraySize(m_positions) > 0) {
      report += "───────────────────\n";

      for(int i = 0; i < ArraySize(m_positions); i++) {
         PositionInfo pos = m_positions[i];

         report += StringFormat("#%d %s %s\n",
            pos.ticket,
            pos.type == POSITION_TYPE_BUY ? "BUY" : "SELL",
            pos.symbol
         );
         report += StringFormat("سود: $%.2f | حجم: %.2f\n",
            pos.profit,
            pos.volume
         );
         report += StringFormat("SL: %.5f | TP: %.5f\n", pos.sl, pos.tp);
         report += "───────────────────\n";
      }
   }

   return report;
}
//+------------------------------------------------------------------+
