//+------------------------------------------------------------------+
//|                                                  Helpers.mqh      |
//|                                    MT5 Trading System             |
//|                                    توابع کمکی                     |
//+------------------------------------------------------------------+
#property strict
#include <Trade/Trade.mqh>

//+
// توابع کمکی ریاضی
//+

// تبدیل پوینت به قیمت
double PointsToPrice(const string symbol, const int points) {
   return points * SymbolInfoDouble(symbol, SYMBOL_POINT);
}

// تبدیل قیمت به پوینت
int PriceToPoints(const string symbol, const double price) {
   return (int)(price / SymbolInfoDouble(symbol, SYMBOL_POINT));
}

// محاسبه لات بر اساس ریسک
double CalculateLotSize(
   const string symbol,
   const double riskPercent,
   const double slPoints
) {
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmount = balance * (riskPercent / 100.0);

   double tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);

   if(tickValue == 0 || tickSize == 0) return 0.01;

   double slMoney = slPoints * SymbolInfoDouble(symbol, SYMBOL_POINT) * tickValue / tickSize;

   if(slMoney <= 0) return 0.01;

   double lot = riskAmount / slMoney;

   // اعمال محدودیت‌ها
   double minLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

   lot = MathFloor(lot / stepLot) * stepLot;
   lot = MathMax(lot, minLot);
   lot = MathMin(lot, maxLot);

   return NormalizeDouble(lot, 2);
}

// محاسبه حد ضرر بر اساس ساختار
double CalculateStructureSL(
   const string symbol,
   const ENUM_ORDER_TYPE direction,
   const SMCData &smc
) {
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double currentPrice = SymbolInfoDouble(symbol, direction == ORDER_TYPE_BUY ?
      SYMBOL_ASK : SYMBOL_BID);

   if(direction == ORDER_TYPE_BUY) {
      if(smc.hasOrderBlock) {
         return smc.obLow - (50 * point);
      }
      return currentPrice - (DefaultSL * point);
   } else {
      if(smc.hasOrderBlock) {
         return smc.obHigh + (50 * point);
      }
      return currentPrice + (DefaultSL * point);
   }
}

// محاسبه حد سود بر اساس R:R
double CalculateTPByRR(
   const double entryPrice,
   const double sl,
   const ENUM_ORDER_TYPE direction,
   const double rr = 2.0
) {
   double slDistance = MathAbs(entryPrice - sl);
   if(direction == ORDER_TYPE_BUY) {
      return entryPrice + (slDistance * rr);
   } else {
      return entryPrice - (slDistance * rr);
   }
}

//+
// توابع کمکی زمانی
//+

// بررسی Kill Zone
bool IsInKillZone(const int startHour, const int endHour) {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int hour = dt.hour;

   if(startHour < endHour) {
      return (hour >= startHour && hour < endHour);
   } else {
      return (hour >= startHour || hour < endHour);
   }
}

// دریافت Kill Zone فعال
string GetActiveKillZone() {
   if(UseLondonKZ && IsInKillZone(LondonStart, LondonEnd))
      return "لندن";
   if(UseNYKZ && IsInKillZone(NYStart, NYEnd))
      return "نیویورک";
   if(UseTokyoKZ && IsInKillZone(TokyoStart, TokyoEnd))
      return "توکیو";
   return "هیچکدام";
}

// بررسی زمان ترید
bool IsTradingTime() {
   if(!UseTimeFilter) return true;

   bool inKZ = false;
   if(UseLondonKZ && IsInKillZone(LondonStart, LondonEnd)) inKZ = true;
   if(UseNYKZ && IsInKillZone(NYStart, NYEnd)) inKZ = true;
   if(UseTokyoKZ && IsInKillZone(TokyoStart, TokyoEnd)) inKZ = true;

   return inKZ;
}

//+
// توابع کمکی معاملاتی
//+

// شمارش معاملات باز
int CountOpenTrades(const string symbol = "") {
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      if(PositionSelectByTicket(PositionGetTicket(i))) {
         if(symbol == "" || PositionGetString(POSITION_SYMBOL) == symbol) {
            if(PositionGetInteger(POSITION_MAGIC) == (int)StringToInteger(MagicNumber))
               count++;
         }
      }
   }
   return count;
}

// شمارش معاملات امروز
int CountTodayTrades() {
   int count = 0;
   datetime todayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));

   if(HistorySelect(todayStart, TimeCurrent())) {
      for(int i = HistoryDealsTotal() - 1; i >= 0; i--) {
         ulong ticket = HistoryDealGetTicket(i);
         if(HistoryDealGetInteger(ticket, DEAL_MAGIC) == (int)StringToInteger(MagicNumber)) {
            if(HistoryDealGetInteger(ticket, DEAL_ENTRY) == DEAL_ENTRY_IN) {
               count++;
            }
         }
      }
   }
   return count;
}

// بررسی وجود پوزیشن خورده
bool HasLiquiditySweep(const string symbol, const int lookback = 20) {
   double high[], low[];
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);

   if(CopyHigh(symbol, PERIOD_CURRENT, 1, lookback, high) < lookback) return false;
   if(CopyLow(symbol, PERIOD_CURRENT, 1, lookback, low) < lookback) return false;

   double currentHigh = high[0];
   double currentLow = low[0];

   for(int i = 1; i < lookback - 1; i++) {
      if(currentHigh > high[i] && high[0] < high[i]) return true;
      if(currentLow < low[i] && low[0] > low[i]) return true;
   }

   return false;
}

//+
// توابع کمکی قیمتی
//+

// دریافت قیمت High/Low دوره
void GetSwingHighLow(
   const string symbol,
   const ENUM_TIMEFRAME timeframe,
   const int lookback,
   double &swingHigh,
   double &swingLow
) {
   double high[], low[];
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);

   CopyHigh(symbol, timeframe, 1, lookback, high);
   CopyLow(symbol, timeframe, 1, lookback, low);

   swingHigh = high[ArrayMaximum(high)];
   swingLow = low[ArrayMinimum(low)];
}

// محاسبه ATR
double CalculateATR(const string symbol, const ENUM_TIMEFRAME tf, const int period = 14) {
   double atr[];
   ArraySetAsSeries(atr, true);

   int handle = iATR(symbol, tf, period);
   if(handle == INVALID_HANDLE) return 0;

   if(CopyBuffer(handle, 0, 0, 1, atr) < 1) {
      IndicatorRelease(handle);
      return 0;
   }

   IndicatorRelease(handle);
   return atr[0];
}

//+
// توابع کمکی لاگ
//+

// لاگ پیام
void LogMessage(const string message, const string level = "INFO") {
   if(!EnableLogging) return;

   string logText = StringFormat("[%s] [%s] %s: %s",
      TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES|TIME_SECONDS),
      level,
      Symbol(),
      message
   );

   // همیشه به فایل log می‌نویسیم (اگر LogToFile=true)
   if(LogToFile) {
      int fileHandle = FileOpen("MT5Trading.log", FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI);
      if(fileHandle != INVALID_HANDLE) {
         FileSeek(fileHandle, 0, SEEK_END);
         FileWrite(fileHandle, logText);
         FileClose(fileHandle);
      }
   }
   // در حالت DEBUG، در Expert tab نمایش می‌دهیم
   if(DebugMode) {
      Print(logText);
   }
}

// لاگ معاملون
void LogTrade(
   const string action,
   const string symbol,
   const ENUM_ORDER_TYPE type,
   const double volume,
   const double price,
   const double sl,
   const double tp,
   const string reason = ""
) {
   string direction = (type == ORDER_TYPE_BUY) ? "خرید" : "فروش";
   string message = StringFormat(
      "%s | نماد: %s | جهت: %s | حجم: %.2f | قیمت: %.5f | SL: %.5f | TP: %.5f | دلیل: %s",
      action, symbol, direction, volume, price, sl, tp, reason
   );
   LogMessage(message, "TRADE");
}

//+
// توابع کمکی API
//+

// ارسال درخواست HTTP
string SendApiRequest(
   const string endpoint,
   const string method = "GET",
   const string body = ""
) {
   char data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";

   string url = ApiBaseUrl + endpoint;

   int timeout = ApiTimeout / 1000;
   int res;

   if(method == "GET") {
      res = WebRequest("GET", url, headers, timeout, data, result, headers);
   } else if(method == "POST") {
      StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);
      res = WebRequest("POST", url, headers, timeout, data, result, headers);
   } else {
      return "";
   }

   if(res == -1) {
      LogMessage("خطا در ارتباط با API: " + GetLastError(), "ERROR");
      return "";
   }

   string response = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   return response;
}
//+------------------------------------------------------------------+
