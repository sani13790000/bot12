//+------------------------------------------------------------------+
//|                                             TradeManager.mqh       |
//|                                    MT5 Trading System             |
//|                                    مدیریت کامل معاملات            |
//+------------------------------------------------------------------+
#property strict
#include <Trade/Trade.mqh>
#include "Config.mqh"
#include "Helpers.mqh"
#include "RiskManager.mqh"

//+
// نوع سفارش پندینگ
//+
enum ENUM_PENDING_TYPE {
   PENDING_NONE,
   PENDING_LIMIT,
   PENDING_STOP
};

//+
// ساختار نتیجه سفارش
//+
struct OrderResult {
   bool success;
   ulong orderTicket;
   ulong positionTicket;
   double executedPrice;
   double executedVolume;
   int errorCode;
   string errorMessage;
   string warningMessage;
   datetime timestamp;
};

//+
// ساختار درخواست معامله
//+
struct TradeRequest {
   string symbol;
   ENUM_POSITION_TYPE direction;
   double volume;
   double entryPrice;
   double stopLoss;
   double takeProfit;
   ENUM_PENDING_TYPE pendingType;
   string comment;
   ulong magic;
   datetime expiration;
   bool useRetry;
   int maxRetries;
   int retryDelayMs;
};

//+
// کلاس مدیریت معاملات کامل
//+
class CTradeManager {
private:
   CTrade m_trade;
   CRiskManager *m_riskManager;
   string m_symbol;
   int m_magic;
   int m_orderCount;

   // تنظیمات اجرا
   int m_maxSlippage;
   int m_maxRetries;
   int m_retryDelayMs;

   // محدودیت‌های نماد
   double m_stopLevel;
   double m_freezeLevel;
   double m_point;
   int m_digits;

   // آمار
   int m_totalOrders;
   int m_successfulOrders;
   int m_failedOrders;

   // توابع داخلی
   bool ValidateSignal(const TradeSignal &signal);
   double CalculatePositionSize(const TradeSignal &signal);
   bool CheckRiskLimits();
   bool CheckSpread();
   bool CheckMargin(const double volume);
   bool CheckStopLevels(const double price, const double sl, const double tp, const ENUM_POSITION_TYPE direction);
   bool CheckFreezeLevel(const double price, const ENUM_POSITION_TYPE direction);

   double AdjustPriceForStopLevel(const double price, const ENUM_POSITION_TYPE direction);
   double NormalizePrice(const double price);
   double NormalizeVolume(const double volume);

   OrderResult ExecuteMarketOrder(const TradeRequest &request);
   OrderResult ExecuteLimitOrder(const TradeRequest &request);
   OrderResult ExecuteStopOrder(const TradeRequest &request);
   OrderResult ExecuteWithRetry(TradeRequest &request);

   bool FillTradeRequest(TradeRequest &request, const TradeSignal &signal);
   void UpdateOrderStats(const bool success);

public:
   CTradeManager(const string symbol);
   CTradeManager(const string symbol, CRiskManager *riskManager);
   ~CTradeManager();

   // تنظیمات
   void SetRiskManager(CRiskManager *riskManager);
   void SetMaxSlippage(const int points);
   void SetMaxRetries(const int count, const int delayMs);
   void SetMagicNumber(const int magic);

   // اجرای معاملات
   OrderResult OpenMarketOrder(const ENUM_POSITION_TYPE direction, const double volume,
      const double sl = 0, const double tp = 0, const string comment = "");

   OrderResult OpenLimitOrder(const ENUM_POSITION_TYPE direction, const double volume,
      const double price, const double sl = 0, const double tp = 0,
      const string comment = "", const datetime expiration = 0);

   OrderResult OpenStopOrder(const ENUM_POSITION_TYPE direction, const double volume,
      const double price, const double sl = 0, const double tp = 0,
      const string comment = "", const datetime expiration = 0);

   bool OpenTrade(const TradeSignal &signal, string &errorMsg);
   OrderResult OpenTradeEx(const TradeSignal &signal);

   // مدیریت پوزیشن
   bool CloseTrade(const ulong ticket, const string reason = "");
   bool CloseTradePartial(const ulong ticket, const double volume, const string reason = "");
   bool CloseAllTrades(const string direction = "");
   bool CloseAllTradesBySymbol();
   bool CloseProfitableTrades();
   bool CloseLosingTrades();

   // تغییر SL/TP
   bool ModifySlTp(const ulong ticket, const double sl, const double tp);
   bool ModifySl(const ulong ticket, const double sl);
   bool ModifyTp(const ulong ticket, const double tp);
   bool MoveToBreakeven(const ulong ticket);
   bool SetTrailingStop(const ulong ticket, const double distance, const double step = 0);

   // مدیریت سفارش‌های پندینگ
   bool DeletePendingOrder(const ulong ticket);
   bool ModifyPendingOrder(const ulong ticket, const double price,
      const double sl = 0, const double tp = 0);
   int DeleteAllPendingOrders();
   int CountPendingOrders();

   // اطلاعات و آمار
   int GetOpenPositionsCount();
   int GetBuyPositionsCount();
   int GetSellPositionsCount();
   double GetOpenProfit();
   double GetOpenProfitByDirection(const ENUM_POSITION_TYPE direction);
   int GetDailyPnL();
   double GetAverageEntryPrice(const ENUM_POSITION_TYPE direction);

   // گزارش
   string GetTradeReport();
   string GetLastErrorDescription(const int code);
   void PrintOrderResult(const OrderResult &result);

   // اعتبارسنجی
   bool IsMarketOpen();
   bool IsTradeAllowed();
   bool HasOpenPosition(const ENUM_POSITION_TYPE direction = POSITION_TYPE_BUY);
   ulong GetLastPositionTicket();
};

//+
// سازنده
//+
CTradeManager::CTradeManager(const string symbol) {
   m_symbol = symbol;
   m_magic = (int)StringToInteger(MagicNumber);
   m_riskManager = NULL;

   m_maxSlippage = Slippage;
   m_maxRetries = 3;
   m_retryDelayMs = 500;
   m_orderCount = 0;

   m_totalOrders = 0;
   m_successfulOrders = 0;
   m_failedOrders = 0;

   m_trade.SetExpertMagicNumber(m_magic);
   m_trade.SetDeviationInPoints(m_maxSlippage);

   // دریافت اطلاعات نماد
   m_stopLevel = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
   m_freezeLevel = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   m_point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   m_digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
}

//+
// سازنده با RiskManager
//+
CTradeManager::CTradeManager(const string symbol, CRiskManager *riskManager) {
   m_symbol = symbol;
   m_magic = (int)StringToInteger(MagicNumber);
   m_riskManager = riskManager;

   m_maxSlippage = Slippage;
   m_maxRetries = 3;
   m_retryDelayMs = 500;

   m_totalOrders = 0;
   m_successfulOrders = 0;
   m_failedOrders = 0;

   m_trade.SetExpertMagicNumber(m_magic);
   m_trade.SetDeviationInPoints(m_maxSlippage);

   m_stopLevel = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
   m_freezeLevel = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   m_point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   m_digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
}

//+
// مخرب
//+
CTradeManager::~CTradeManager() {
}

//+
// تنظیم RiskManager
//+
void CTradeManager::SetRiskManager(CRiskManager *riskManager) {
   m_riskManager = riskManager;
}

//+
// تنظیم انحراف مجاز
//+
void CTradeManager::SetMaxSlippage(const int points) {
   m_maxSlippage = MathMax(0, points);
   m_trade.SetDeviationInPoints(m_maxSlippage);
}

//+
// تنظیم تلاش مجدد
//+
void CTradeManager::SetMaxRetries(const int count, const int delayMs) {
   m_maxRetries = MathMax(0, MathMin(10, count));
   m_retryDelayMs = MathMax(100, delayMs);
}

//+
// تنظیم شماره مجیک
//+
void CTradeManager::SetMagicNumber(const int magic) {
   m_magic = magic;
   m_trade.SetExpertMagicNumber(m_magic);
}

//+
// اعتبارسنجی سیگنال
//+
bool CTradeManager::ValidateSignal(const TradeSignal &signal) {
   if(signal.totalScore < MinEntryScore) {
      LogMessage("امتیاز سیگنال کمتر از حد نصاب: " + IntegerToString(signal.totalScore), "WARNING");
      return false;
   }

   if(!signal.entryAllowed) {
      LogMessage("ورود مجاز نیست: " + signal.reason, "WARNING");
      return false;
   }

   return true;
}

//+
// محاسبه حجم پوزیشن
//+
double CTradeManager::CalculatePositionSize(const TradeSignal &signal) {
   if(FixedLot > 0) {
      return NormalizeVolume(FixedLot);
   }

   double slPoints = MathAbs(signal.entryPrice - signal.stopLoss) / m_point;

   if(m_riskManager != NULL) {
      LotCalculationResult lotResult = m_riskManager->CalculateLot(RiskPercent, slPoints, signal.direction == "buy" ? POSITION_TYPE_BUY : POSITION_TYPE_SELL);
      if(lotResult.isValid) {
         return lotResult.lot;
      }
   }

   double lot = CalculateLotSize(m_symbol, RiskPercent, (int)slPoints);
   return NormalizeVolume(lot);
}

//+
// بررسی محدودیت ریسک
//+
bool CTradeManager::CheckRiskLimits() {
   if(m_riskManager != NULL) {
      RiskCheckResult result = m_riskManager->CheckRiskBeforeTrade(POSITION_TYPE_BUY);
      if(!result.allowed) {
         LogMessage("محدودیت ریسک: " + result.reason, "WARNING");
         return false;
      }
      return true;
   }

   if(CountTodayTrades() >= MaxDailyTrades) {
      LogMessage("حداکثر معاملات روزانه", "WARNING");
      return false;
   }

   if(CountOpenTrades(m_symbol) >= MaxOpenTrades) {
      LogMessage("حداکثر معاملات همزمان", "WARNING");
      return false;
   }

   return true;
}

//+
// بررسی اسپرد
//+
bool CTradeManager::CheckSpread() {
   int currentSpread = (int)SymbolInfoInteger(m_symbol, SYMBOL_SPREAD);
   if(currentSpread > MaxSpread) {
      LogMessage("اسپرد بالا: " + IntegerToString(currentSpread), "WARNING");
      return false;
   }
   return true;
}

//+
// بررسی مارجین
//+
bool CTradeManager::CheckMargin(const double volume) {
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double marginRequired;

   double contractSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double leverage = (double)AccountInfoInteger(ACCOUNT_LEVERAGE);

   marginRequired = (volume * contractSize) / leverage;

   if(marginRequired > freeMargin * 0.8) {
      LogMessage(StringFormat("مارجین کافی نیست: نیاز $%.2f، موجود $%.2f",
         marginRequired, freeMargin), "WARNING");
      return false;
   }

   return true;
}

//+
// بررسی stop level
//+
bool CTradeManager::CheckStopLevels(const double price, const double sl, const double tp, const ENUM_POSITION_TYPE direction) {
   if(sl <= 0 && tp <= 0) return true;

   double stopLevelPrice = m_stopLevel * m_point;
   if(stopLevelPrice <= 0) stopLevelPrice = m_point * 10;

   if(direction == POSITION_TYPE_BUY) {
      if(sl > 0 && price - sl < stopLevelPrice) {
         LogMessage(StringFormat("SL به قیمت نزدیک است: فاصله %.0f < %.0f",
            (price - sl) / m_point, stopLevelPrice / m_point), "WARNING");
         return false;
      }
      if(tp > 0 && tp - price < stopLevelPrice) {
         LogMessage(StringFormat("TP به قیمت نزدیک است: فاصله %.0f < %.0f",
            (tp - price) / m_point, stopLevelPrice / m_point), "WARNING");
         return false;
      }
   } else {
      if(sl > 0 && sl - price < stopLevelPrice) {
         LogMessage(StringFormat("SL به قیمت نزدیک است: فاصله %.0f < %.0f",
            (sl - price) / m_point, stopLevelPrice / m_point), "WARNING");
         return false;
      }
      if(tp > 0 && price - tp < stopLevelPrice) {
         LogMessage(StringFormat("TP به قیمت نزدیک است: فاصله %.0f < %.0f",
            (price - tp) / m_point, stopLevelPrice / m_point), "WARNING");
         return false;
      }
   }

   return true;
}

//+
// بررسی freeze level
//+
bool CTradeManager::CheckFreezeLevel(const double price, const ENUM_POSITION_TYPE direction) {
   double freezeLevelPrice = m_freezeLevel * m_point;
   if(freezeLevelPrice <= 0) return true;

   double currentPrice;
   if(direction == POSITION_TYPE_BUY) {
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
   } else {
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
   }

   if(MathAbs(price - currentPrice) < freezeLevelPrice) {
      LogMessage("قیمت در محدوده freeze level", "WARNING");
      return false;
   }

   return true;
}

//+
// تنظیم قیمت برای stop level
//+
double CTradeManager::AdjustPriceForStopLevel(const double price, const ENUM_POSITION_TYPE direction) {
   double stopLevelPrice = m_stopLevel * m_point;
   if(stopLevelPrice <= 0) stopLevelPrice = m_point * 10;

   double currentPrice;
   if(direction == POSITION_TYPE_BUY) {
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      if(price < currentPrice + stopLevelPrice) {
         return currentPrice + stopLevelPrice;
      }
   } else {
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      if(price > currentPrice - stopLevelPrice) {
         return currentPrice - stopLevelPrice;
      }
   }

   return price;
}

//+
// نرمال‌سازی قیمت
//+
double CTradeManager::NormalizePrice(const double price) {
   return NormalizeDouble(price, m_digits);
}

//+
// نرمال‌سازی حجم
//+
double CTradeManager::NormalizeVolume(const double volume) {
   double minLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);

   minLot = MathMax(minLot, MinLot);
   maxLot = MathMin(maxLot, MaxLot);

   double adjustedLot = MathFloor(volume / stepLot) * stepLot;
   adjustedLot = MathMax(adjustedLot, minLot);
   adjustedLot = MathMin(adjustedLot, maxLot);

   return NormalizeDouble(adjustedLot, 2);
}

//+
// تنظیم درخواست معامله از سیگنال
//+
bool CTradeManager::FillTradeRequest(TradeRequest &request, const TradeSignal &signal) {
   request.symbol = m_symbol;

   if(signal.direction == "buy") {
      request.direction = POSITION_TYPE_BUY;
      request.entryPrice = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
   } else if(signal.direction == "sell") {
      request.direction = POSITION_TYPE_SELL;
      request.entryPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
   } else {
      return false;
   }

   request.volume = CalculatePositionSize(signal);
   request.stopLoss = NormalizePrice(signal.stopLoss);
   request.takeProfit = NormalizePrice(signal.takeProfit);
   request.pendingType = PENDING_NONE;
   request.comment = signal.reason;
   request.magic = m_magic;
   request.expiration = 0;
   request.useRetry = true;
   request.maxRetries = m_maxRetries;
   request.retryDelayMs = m_retryDelayMs;

   return true;
}

//+
// به‌روزرسانی آمار سفارشات
//+
void CTradeManager::UpdateOrderStats(const bool success) {
   m_totalOrders++;
   if(success) {
      m_successfulOrders++;
   } else {
      m_failedOrders++;
   }
}

//+
// اجرای سفارش مارکت
//+
OrderResult CTradeManager::ExecuteMarketOrder(const TradeRequest &request) {
   OrderResult result;
   ZeroMemory(result);
   result.timestamp = TimeCurrent();

   if(!CheckSpread()) {
      result.success = false;
      result.errorCode = -1;
      result.errorMessage = "اسپرد بالا";
      return result;
   }

   if(!CheckMargin(request.volume)) {
      result.success = false;
      result.errorCode = -2;
      result.errorMessage = "مارجین کافی نیست";
      return result;
   }

   double price;
   ENUM_ORDER_TYPE orderType;

   if(request.direction == POSITION_TYPE_BUY) {
      orderType = ORDER_TYPE_BUY;
      price = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
   } else {
      orderType = ORDER_TYPE_SELL;
      price = SymbolInfoDouble(m_symbol, SYMBOL_BID);
   }

   double sl = request.stopLoss;
   double tp = request.takeProfit;

   if(!CheckStopLevels(price, sl, tp, request.direction)) {
      if(request.direction == POSITION_TYPE_BUY) {
         if(sl > 0 && price - sl < m_stopLevel * m_point) {
            sl = NormalizePrice(price - m_stopLevel * m_point - 10 * m_point);
         }
         if(tp > 0 && tp - price < m_stopLevel * m_point) {
            tp = NormalizePrice(price + m_stopLevel * m_point + 10 * m_point);
         }
      } else {
         if(sl > 0 && sl - price < m_stopLevel * m_point) {
            sl = NormalizePrice(price + m_stopLevel * m_point + 10 * m_point);
         }
         if(tp > 0 && price - tp < m_stopLevel * m_point) {
            tp = NormalizePrice(price - m_stopLevel * m_point - 10 * m_point);
         }
      }
   }

   price = NormalizePrice(price);
   double volume = NormalizeVolume(request.volume);

   LogMessage(StringFormat("ارسال سفارش مارکت: %s %.2f @ %.5f | SL: %.5f TP: %.5f",
      request.direction == POSITION_TYPE_BUY ? "BUY" : "SELL",
      volume, price, sl, tp), "TRADE");

   bool success = false;
   if(orderType == ORDER_TYPE_BUY) {
      success = m_trade.Buy(volume, m_symbol, price, sl, tp, request.comment);
   } else {
      success = m_trade.Sell(volume, m_symbol, price, sl, tp, request.comment);
   }

   if(success) {
      result.success = true;
      result.positionTicket = m_trade.ResultOrder();
      result.orderTicket = m_trade.ResultOrder();
      result.executedPrice = m_trade.ResultPrice();
      result.executedVolume = m_trade.ResultVolume();

      LogMessage(StringFormat("سفارش موفق: Ticket #%I64u @ %.5f",
         result.positionTicket, result.executedPrice), "INFO");

      UpdateOrderStats(true);
   } else {
      result.success = false;
      result.errorCode = GetLastError();
      result.errorMessage = GetLastErrorDescription(result.errorCode);

      LogMessage("خطا در ارسال سفارش: " + result.errorMessage, "ERROR");
      UpdateOrderStats(false);
   }

   return result;
}

//+
// اجرای سفارش لیمیت
//+
OrderResult CTradeManager::ExecuteLimitOrder(const TradeRequest &request) {
   OrderResult result;
   ZeroMemory(result);
   result.timestamp = TimeCurrent();

   double price = NormalizePrice(request.entryPrice);

   if(!CheckFreezeLevel(price, request.direction)) {
      price = AdjustPriceForStopLevel(price, request.direction);
   }

   ENUM_ORDER_TYPE orderType;
   double currentPrice;

   if(request.direction == POSITION_TYPE_BUY) {
      orderType = ORDER_TYPE_BUY_LIMIT;
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      if(price >= currentPrice) {
         result.success = false;
         result.errorCode = -3;
         result.errorMessage = "قیمت لیمیت خرید باید کمتر از قیمت فعلی باشد";
         return result;
      }
   } else {
      orderType = ORDER_TYPE_SELL_LIMIT;
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      if(price <= currentPrice) {
         result.success = false;
         result.errorCode = -3;
         result.errorMessage = "قیمت لیمیت فروش باید بیشتر از قیمت فعلی باشد";
         return result;
      }
   }

   double volume = NormalizeVolume(request.volume);
   double sl = NormalizePrice(request.stopLoss);
   double tp = NormalizePrice(request.takeProfit);
   datetime expiration = request.expiration > 0 ? request.expiration : 0;

   LogMessage(StringFormat("ارسال سفارش لیمیت: %s %.2f @ %.5f | SL: %.5f TP: %.5f",
      request.direction == POSITION_TYPE_BUY ? "BUY LIMIT" : "SELL LIMIT",
      volume, price, sl, tp), "TRADE");

   bool success = m_trade.OrderPlacement(orderType, volume, m_symbol, price, sl, tp, ORDER_TIME_GTC,
      expiration, request.comment);

   if(success) {
      result.success = true;
      result.orderTicket = m_trade.ResultOrder();
      result.executedPrice = price;
      result.executedVolume = volume;

      LogMessage(StringFormat("سفارش لیمیت ثبت شد: Ticket #%I64u", result.orderTicket), "INFO");
      UpdateOrderStats(true);
   } else {
      result.success = false;
      result.errorCode = GetLastError();
      result.errorMessage = GetLastErrorDescription(result.errorCode);

      LogMessage("خطا در ثبت سفارش لیمیت: " + result.errorMessage, "ERROR");
      UpdateOrderStats(false);
   }

   return result;
}

//+
// اجرای سفارش استاپ
//+
OrderResult CTradeManager::ExecuteStopOrder(const TradeRequest &request) {
   OrderResult result;
   ZeroMemory(result);
   result.timestamp = TimeCurrent();

   double price = NormalizePrice(request.entryPrice);

   if(!CheckFreezeLevel(price, request.direction)) {
      result.success = false;
      result.errorCode = -4;
      result.errorMessage = "قیمت در محدوده freeze level";
      return result;
   }

   ENUM_ORDER_TYPE orderType;
   double currentPrice;

   if(request.direction == POSITION_TYPE_BUY) {
      orderType = ORDER_TYPE_BUY_STOP;
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      if(price <= currentPrice) {
         result.success = false;
         result.errorCode = -3;
         result.errorMessage = "قیمت استاپ خرید باید بیشتر از قیمت فعلی باشد";
         return result;
      }
   } else {
      orderType = ORDER_TYPE_SELL_STOP;
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      if(price >= currentPrice) {
         result.success = false;
         result.errorCode = -3;
         result.errorMessage = "قیمت استاپ فروش باید کمتر از قیمت فعلی باشد";
         return result;
      }
   }

   double volume = NormalizeVolume(request.volume);
   double sl = NormalizePrice(request.stopLoss);
   double tp = NormalizePrice(request.takeProfit);
   datetime expiration = request.expiration > 0 ? request.expiration : 0;

   LogMessage(StringFormat("ارسال سفارش استاپ: %s %.2f @ %.5f | SL: %.5f TP: %.5f",
      request.direction == POSITION_TYPE_BUY ? "BUY STOP" : "SELL STOP",
      volume, price, sl, tp), "TRADE");

   bool success = m_trade.OrderPlacement(orderType, volume, m_symbol, price, sl, tp, ORDER_TIME_GTC,
      expiration, request.comment);

   if(success) {
      result.success = true;
      result.orderTicket = m_trade.ResultOrder();
      result.executedPrice = price;
      result.executedVolume = volume;

      LogMessage(StringFormat("سفارش استاپ ثبت شد: Ticket #%I64u", result.orderTicket), "INFO");
      UpdateOrderStats(true);
   } else {
      result.success = false;
      result.errorCode = GetLastError();
      result.errorMessage = GetLastErrorDescription(result.errorCode);

      LogMessage("خطا در ثبت سفارش استاپ: " + result.errorMessage, "ERROR");
      UpdateOrderStats(false);
   }

   return result;
}

//+
// اجرای سفارش با تلاش مجدد
//+
OrderResult CTradeManager::ExecuteWithRetry(TradeRequest &request) {
   OrderResult result;
   int attempts = 0;
   int maxAttempts = request.useRetry ? request.maxRetries + 1 : 1;

   while(attempts < maxAttempts) {
      attempts++;

      switch(request.pendingType) {
         case PENDING_LIMIT:
            result = ExecuteLimitOrder(request);
            break;
         case PENDING_STOP:
            result = ExecuteStopOrder(request);
            break;
         default:
            result = ExecuteMarketOrder(request);
            break;
      }

      if(result.success) {
         return result;
      }

      if(attempts < maxAttempts) {
         LogMessage(StringFormat("تلاش مجدد %d/%d بعد از %d ms", attempts, maxAttempts - 1, request.retryDelayMs), "INFO");
         Sleep(request.retryDelayMs);
      }
   }

   return result;
}

//+
// باز کردن سفارش مارکت
//+
OrderResult CTradeManager::OpenMarketOrder(const ENUM_POSITION_TYPE direction, const double volume,
   const double sl, const double tp, const string comment) {

   TradeRequest request;
   request.symbol = m_symbol;
   request.direction = direction;
   request.volume = volume;
   request.entryPrice = direction == POSITION_TYPE_BUY ?
      SymbolInfoDouble(m_symbol, SYMBOL_ASK) : SymbolInfoDouble(m_symbol, SYMBOL_BID);
   request.stopLoss = sl;
   request.takeProfit = tp;
   request.pendingType = PENDING_NONE;
   request.comment = comment;
   request.magic = m_magic;
   request.useRetry = true;
   request.maxRetries = m_maxRetries;
   request.retryDelayMs = m_retryDelayMs;

   if(!CheckRiskLimits()) {
      OrderResult result;
      result.success = false;
      result.errorCode = -5;
      result.errorMessage = "محدودیت ریسک";
      return result;
   }

   return ExecuteMarketOrder(request);
}

//+
// باز کردن سفارش لیمیت
//+
OrderResult CTradeManager::OpenLimitOrder(const ENUM_POSITION_TYPE direction, const double volume,
   const double price, const double sl, const double tp, const string comment, const datetime expiration) {

   TradeRequest request;
   request.symbol = m_symbol;
   request.direction = direction;
   request.volume = volume;
   request.entryPrice = price;
   request.stopLoss = sl;
   request.takeProfit = tp;
   request.pendingType = PENDING_LIMIT;
   request.comment = comment;
   request.magic = m_magic;
   request.expiration = expiration;
   request.useRetry = true;
   request.maxRetries = m_maxRetries;
   request.retryDelayMs = m_retryDelayMs;

   return ExecuteLimitOrder(request);
}

//+
// باز کردن سفارش استاپ
//+
OrderResult CTradeManager::OpenStopOrder(const ENUM_POSITION_TYPE direction, const double volume,
   const double price, const double sl, const double tp, const string comment, const datetime expiration) {

   TradeRequest request;
   request.symbol = m_symbol;
   request.direction = direction;
   request.volume = volume;
   request.entryPrice = price;
   request.stopLoss = sl;
   request.takeProfit = tp;
   request.pendingType = PENDING_STOP;
   request.comment = comment;
   request.magic = m_magic;
   request.expiration = expiration;
   request.useRetry = true;
   request.maxRetries = m_maxRetries;
   request.retryDelayMs = m_retryDelayMs;

   return ExecuteStopOrder(request);
}

//+
// باز کردن معامله از سیگنال (ساده)
//+
bool CTradeManager::OpenTrade(const TradeSignal &signal, string &errorMsg) {
   OrderResult result = OpenTradeEx(signal);

   if(!result.success) {
      errorMsg = result.errorMessage;
      return false;
   }

   return true;
}

//+
// باز کردن معامله از سیگنال (کامل)
//+
OrderResult CTradeManager::OpenTradeEx(const TradeSignal &signal) {
   OrderResult result;
   ZeroMemory(result);

   if(!ValidateSignal(signal)) {
      result.success = false;
      result.errorCode = -6;
      result.errorMessage = "سیگنال نامعتبر";
      return result;
   }

   if(!CheckRiskLimits()) {
      result.success = false;
      result.errorCode = -5;
      result.errorMessage = "محدودیت ریسک";
      return result;
   }

   TradeRequest request;
   if(!FillTradeRequest(request, signal)) {
      result.success = false;
      result.errorCode = -7;
      result.errorMessage = "خطا در ایجاد درخواست";
      return result;
   }

   return ExecuteWithRetry(request);
}

//+
// بستن معامله
//+
bool CTradeManager::CloseTrade(const ulong ticket, const string reason) {
   if(!PositionSelectByTicket(ticket)) {
      LogMessage("پوزیشن یافت نشد: " + IntegerToString(ticket), "ERROR");
      return false;
   }

   ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double volume = PositionGetDouble(POSITION_VOLUME);

   LogMessage(StringFormat("بستن معامله #%I64u | %s | %.2f | دلیل: %s",
      ticket, posType == POSITION_TYPE_BUY ? "BUY" : "SELL", volume, reason), "TRADE");

   bool success = m_trade.PositionClose(ticket);

   if(!success) {
      int error = GetLastError();
      LogMessage("خطا در بستن معامله: " + GetLastErrorDescription(error), "ERROR");
      return false;
   }

   return true;
}

//+
// بستن جزئی معامله
//+
bool CTradeManager::CloseTradePartial(const ulong ticket, const double volume, const string reason) {
   if(!PositionSelectByTicket(ticket)) {
      LogMessage("پوزیشن یافت نشد: " + IntegerToString(ticket), "ERROR");
      return false;
   }

   double currentVolume = PositionGetDouble(POSITION_VOLUME);
   double closeVolume = NormalizeVolume(MathMin(volume, currentVolume));

   LogMessage(StringFormat("بستن جزئی #%I64u | %.2f از %.2f | دلیل: %s",
      ticket, closeVolume, currentVolume, reason), "TRADE");

   bool success = m_trade.PositionClose(ticket, closeVolume);

   if(!success) {
      int error = GetLastError();
      LogMessage("خطا در بستن جزئی: " + GetLastErrorDescription(error), "ERROR");
      return false;
   }

   return true;
}

//+
// بستن همه معاملات
//+
bool CTradeManager::CloseAllTrades(const string direction) {
   int closed = 0;
   int failed = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      if(direction != "") {
         ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         if(direction == "buy" && posType != POSITION_TYPE_BUY) continue;
         if(direction == "sell" && posType != POSITION_TYPE_SELL) continue;
      }

      if(CloseTrade(ticket, "بستن همه")) {
         closed++;
      } else {
         failed++;
      }
   }

   LogMessage(StringFormat("بسته شد: %d | ناموفق: %d", closed, failed), "TRADE");

   return failed == 0;
}

//+
// بستن همه معاملات نماد
//+
bool CTradeManager::CloseAllTradesBySymbol() {
   return CloseAllTrades("");
}

//+
// بستن معاملات سودده
//+
bool CTradeManager::CloseProfitableTrades() {
   int closed = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      double profit = PositionGetDouble(POSITION_PROFIT);

      if(profit > 0) {
         if(CloseTrade(ticket, "بستن سودده")) {
            closed++;
         }
      }
   }

   LogMessage(StringFormat("معاملات سودده بسته شد: %d", closed), "INFO");

   return closed > 0;
}

//+
// بستن معاملات زیان‌ده
//+
bool CTradeManager::CloseLosingTrades() {
   int closed = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      double profit = PositionGetDouble(POSITION_PROFIT);

      if(profit < 0) {
         if(CloseTrade(ticket, "بستن زیان‌ده")) {
            closed++;
         }
      }
   }

   LogMessage(StringFormat("معاملات زیان‌ده بسته شد: %d", closed), "INFO");

   return closed > 0;
}

//+
// تغییر SL و TP
//+
bool CTradeManager::ModifySlTp(const ulong ticket, const double sl, const double tp) {
   if(!PositionSelectByTicket(ticket)) {
      return false;
   }

   double normSl = NormalizePrice(sl);
   double normTp = NormalizePrice(tp);

   ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);

   if(!CheckStopLevels(openPrice, normSl, normTp, posType)) {
      return false;
   }

   return m_trade.PositionModify(ticket, normSl, normTp);
}

//+
// تغییر SL
//+
bool CTradeManager::ModifySl(const ulong ticket, const double sl) {
   if(!PositionSelectByTicket(ticket)) {
      return false;
   }

   double currentTp = PositionGetDouble(POSITION_TP);
   return ModifySlTp(ticket, sl, currentTp);
}

//+
// تغییر TP
//+
bool CTradeManager::ModifyTp(const ulong ticket, const double tp) {
   if(!PositionSelectByTicket(ticket)) {
      return false;
   }

   double currentSl = PositionGetDouble(POSITION_SL);
   return ModifySlTp(ticket, currentSl, tp);
}

//+
// انتقال به نقطه سر به سر
//+
bool CTradeManager::MoveToBreakeven(const ulong ticket) {
   if(!PositionSelectByTicket(ticket)) {
      return false;
   }

   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double currentSl = PositionGetDouble(POSITION_SL);
   double currentTp = PositionGetDouble(POSITION_TP);
   ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double profit = PositionGetDouble(POSITION_PROFIT);

   if(profit < 0) {
      return false;
   }

   double newSl;
   if(posType == POSITION_TYPE_BUY) {
      if(currentSl >= openPrice) {
         return true;
      }
      newSl = NormalizePrice(openPrice + 10 * m_point);
   } else {
      if(currentSl > 0 && currentSl <= openPrice) {
         return true;
      }
      newSl = NormalizePrice(openPrice - 10 * m_point);
   }

   LogMessage(StringFormat("انتقال به BE: #%I64u | %.5f", ticket, newSl), "TRADE");

   return ModifySlTp(ticket, newSl, currentTp);
}

//+
// تنظیم تریلینگ استاپ
//+
bool CTradeManager::SetTrailingStop(const ulong ticket, const double distance, const double step) {
   if(!PositionSelectByTicket(ticket)) {
      return false;
   }

   ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   double currentSl = PositionGetDouble(POSITION_SL);
   double currentTp = PositionGetDouble(POSITION_TP);
   double currentPrice = PositionGetDouble(POSITION_PRICE_CURRENT);

   double trailDistance = distance * m_point;
   double trailStep = step > 0 ? step * m_point : trailDistance;

   double newSl;

   if(posType == POSITION_TYPE_BUY) {
      newSl = currentPrice - trailDistance;
      newSl = NormalizePrice(newSl);

      if(newSl <= currentSl + trailStep) {
         return true;
      }
   } else {
      newSl = currentPrice + trailDistance;
      newSl = NormalizePrice(newSl);

      if(newSl >= currentSl - trailStep || currentSl == 0) {
         if(currentSl == 0) {
            newSl = NormalizePrice(currentPrice + trailDistance);
         } else {
            return true;
         }
      }
   }

   LogMessage(StringFormat("تریلینگ: #%I64u | SL: %.5f", ticket, newSl), "TRADE");

   return ModifySlTp(ticket, newSl, currentTp);
}

//+
// حذف سفارش پندینگ
//+
bool CTradeManager::DeletePendingOrder(const ulong ticket) {
   if(!OrderSelect(ticket)) {
      return false;
   }

   return m_trade.OrderDelete(ticket);
}

//+
// تغییر سفارش پندینگ
//+
bool CTradeManager::ModifyPendingOrder(const ulong ticket, const double price, const double sl, const double tp) {
   if(!OrderSelect(ticket)) {
      return false;
   }

   double normPrice = NormalizePrice(price);
   double normSl = NormalizePrice(sl);
   double normTp = NormalizePrice(tp);

   return m_trade.OrderModify(ticket, normPrice, normSl, normTp, ORDER_TIME_GTC, 0);
}

//+
// حذف همه سفارش‌های پندینگ
//+
int CTradeManager::DeleteAllPendingOrders() {
   int deleted = 0;

   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      ulong ticket = OrderGetTicket(i);

      if(OrderGetInteger(ORDER_MAGIC) != m_magic) continue;
      if(OrderGetString(ORDER_SYMBOL) != m_symbol) continue;

      if(DeletePendingOrder(ticket)) {
         deleted++;
      }
   }

   LogMessage(StringFormat("سفارش‌های پندینگ حذف شد: %d", deleted), "INFO");

   return deleted;
}

//+
// شمارش سفارش‌های پندینگ
//+
int CTradeManager::CountPendingOrders() {
   int count = 0;

   for(int i = OrdersTotal() - 1; i >= 0; i--) {
      ulong ticket = OrderGetTicket(i);

      if(OrderGetInteger(ORDER_MAGIC) != m_magic) continue;
      if(OrderGetString(ORDER_SYMBOL) != m_symbol) continue;

      count++;
   }

   return count;
}

//+
// تعداد پوزیشن‌های باز
//+
int CTradeManager::GetOpenPositionsCount() {
   int count = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) == m_magic &&
         PositionGetString(POSITION_SYMBOL) == m_symbol) {
         count++;
      }
   }

   return count;
}

//+
// تعداد پوزیشن خرید
//+
int CTradeManager::GetBuyPositionsCount() {
   int count = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      if(posType == POSITION_TYPE_BUY) {
         count++;
      }
   }

   return count;
}

//+
// تعداد پوزیشن فروش
//+
int CTradeManager::GetSellPositionsCount() {
   int count = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      if(posType == POSITION_TYPE_SELL) {
         count++;
      }
   }

   return count;
}

//+
// سود معاملات باز
//+
double CTradeManager::GetOpenProfit() {
   double profit = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) == m_magic &&
         PositionGetString(POSITION_SYMBOL) == m_symbol) {
         profit += PositionGetDouble(POSITION_PROFIT);
      }
   }

   return profit;
}

//+
// سود معاملات باز بر اساس جهت
//+
double CTradeManager::GetOpenProfitByDirection(const ENUM_POSITION_TYPE direction) {
   double profit = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      if(posType == direction) {
         profit += PositionGetDouble(POSITION_PROFIT);
      }
   }

   return profit;
}

//+
// سود/ضرر امروز
//+
int CTradeManager::GetDailyPnL() {
   double pnl = 0;
   datetime todayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));

   if(HistorySelect(todayStart, TimeCurrent())) {
      for(int i = HistoryDealsTotal() - 1; i >= 0; i--) {
         ulong ticket = HistoryDealGetTicket(i);

         if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != m_magic) continue;

         double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
         double swap = HistoryDealGetDouble(ticket, DEAL_SWAP);
         double commission = HistoryDealGetDouble(ticket, DEAL_COMMISSION);

         pnl += profit + swap + commission;
      }
   }

   return (int)(pnl * 100);
}

//+
// میانگین قیمت ورود
//+
double CTradeManager::GetAverageEntryPrice(const ENUM_POSITION_TYPE direction) {
   double totalValue = 0;
   double totalVolume = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      if(posType == direction) {
         double volume = PositionGetDouble(POSITION_VOLUME);
         double price = PositionGetDouble(POSITION_PRICE_OPEN);

         totalValue += volume * price;
         totalVolume += volume;
      }
   }

   if(totalVolume == 0) return 0;

   return NormalizePrice(totalValue / totalVolume);
}

//+
// آیا بازار باز است
//+
bool CTradeManager::IsMarketOpen() {
   long sessionFlags = SymbolInfoInteger(m_symbol, SYMBOL_SESSION_MODE);
   return sessionFlags > 0;
}

//+
// آیا معامله مجاز است
//+
bool CTradeManager::IsTradeAllowed() {
   if(!SymbolInfoInteger(m_symbol, SYMBOL_TRADE_MODE)) {
      return false;
   }

   return CheckRiskLimits() && CheckSpread();
}

//+
// آیا پوزیشن باز دارد
//+
bool CTradeManager::HasOpenPosition(const ENUM_POSITION_TYPE direction) {
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      if(direction == POSITION_TYPE_BUY || direction == POSITION_TYPE_SELL) {
         ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         if(posType == direction) return true;
      } else {
         return true;
      }
   }

   return false;
}

//+
// آخرین پوزیشن
//+
ulong CTradeManager::GetLastPositionTicket() {
   ulong lastTicket = 0;
   datetime lastTime = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);

      if(!PositionSelectByTicket(ticket)) continue;

      if(PositionGetInteger(POSITION_MAGIC) != m_magic) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;

      datetime time = (datetime)PositionGetInteger(POSITION_TIME);

      if(time > lastTime) {
         lastTime = time;
         lastTicket = ticket;
      }
   }

   return lastTicket;
}

//+
// گزارش معاملات
//+
string CTradeManager::GetTradeReport() {
   string report = "📊 گزارش معاملات\n\n";

   report += StringFormat("معاملات امروز: %d\n", CountTodayTrades());
   report += StringFormat("پوزیشن‌های باز: %d\n", GetOpenPositionsCount());
   report += StringFormat("خرید: %d | فروش: %d\n", GetBuyPositionsCount(), GetSellPositionsCount());
   report += StringFormat("سود/ضرر باز: $%.2f\n", GetOpenProfit());

   if(m_riskManager != NULL) {
      report += "\n" + m_riskManager.GetRiskReport();
   }

   report += StringFormat("\n آمار اجرا:\n");
   report += StringFormat("کل سفارشات: %d\n", m_totalOrders);
   report += StringFormat("موفق: %d | ناموفق: %d\n", m_successfulOrders, m_failedOrders);

   return report;
}

//+
// توضیح خطا
//+
string CTradeManager::GetLastErrorDescription(const int code) {
   switch(code) {
      case 0: return "بدون خطا";
      case 4756: return "خطا در ارسال درخواست";
      case 10004: return "درخواست در حال پردازش";
      case 10006: return "درخواست رد شد";
      case 10007: return "درخواست لغو شد";
      case 10010: return "فقط بخشی از درخواست اجرا شد";
      case 10011: return "خطای تجاری";
      case 10012: return "درخواست در انتظار";
      case 10013: return "درخواست نامعتبر";
      case 10014: return "حجم نامعتبر";
      case 10015: return "قیمت نامعتبر";
      case 10016: return "سطوح نامعتبر";
      case 10017: return "خبر اقتصادی";
      case 10018: return "بازار بسته";
      case 10019: return "مارجین کافی نیست";
      case 10020: return "موجودی کافی نیست";
      case 10021: return "فروش ممنوع";
      case 10022: return "خرید ممنوع";
      case 10023: return "سفارش تکراری";
      case 10024: return "درخواست çok زیاد";
      case 10025: return "تغییرات نامعتبر";
      case 10026: return "معامله غیرفعال";
      case 10027: return "اتومات غیرفعال";
      case 10028: return "درخواست محدود";
      case 10029: return "اتصال قطع";
      case 10030: return "فقط برای واقعی";
      case 10031: return "در انتظار خبر";
      case 10032: return "نوع سفارش نامعتبر";
      case 10033: return "شناسه نامعتبر";
      case 10034: return "باز شدن مجاز نیست";
      case 10035: return "تاریخ نامعتبر";
      case 10036: return "سفارش تکراری";
      case 10038: return "مقدار نامعتبر";
      case 10039: return "پوزیشن بسته";
      case 10040: return "سفارش بسته";
      case 10041: return "فقط بستن مجاز";
      case -1: return "اسپرد بالا";
      case -2: return "مارجین کافی نیست";
      case -3: return "قیمت سفارش پندینگ نامعتبر";
      case -4: return "قیمت در محدوده freeze level";
      case -5: return "محدودیت ریسک";
      case -6: return "سیگنال نامعتبر";
      case -7: return "خطا در ایجاد درخواست";
      default: return "خطای نامشخص: " + IntegerToString(code);
   }
}

//+
// چاپ نتیجه سفارش
//+
void CTradeManager::PrintOrderResult(const OrderResult &result) {
   if(result.success) {
      Print("✅ سفارش موفق");
      Print(StringFormat("   Ticket: #%I64u", result.positionTicket));
      Print(StringFormat("   Price: %.5f", result.executedPrice));
      Print(StringFormat("   Volume: %.2f", result.executedVolume));
   } else {
      Print("❌ سفارش ناموفق");
      Print(StringFormat("   Error: %s", result.errorMessage));
      Print(StringFormat("   Code: %d", result.errorCode));
   }
}
//+------------------------------------------------------------------+
