//+------------------------------------------------------------------+
//|                                             TradeManager.mqh       |
//|                                    MT5 Trading System             |
//|                                    ÙØ¯ÛØ±ÛØª Ú©Ø§ÙÙ ÙØ¹Ø§ÙÙØ§Øª            |
//+------------------------------------------------------------------+
#property strict
#include <Trade/Trade.mqh>
#include "Config.mqh"
#include "Helpers.mqh"
#include "RiskManager.mqh"

//+
// ÙÙØ¹ Ø³ÙØ§Ø±Ø´ Ù¾ÙØ¯ÛÙÚ¯
//+
enum ENUM_PENDING_TYPE {
   PENDING_NONE,
   PENDING_LIMIT,
   PENDING_STOP
};

//+
// Ø³Ø§Ø®ØªØ§Ø± ÙØªÛØ¬Ù Ø³ÙØ§Ø±Ø´
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
// Ø³Ø§Ø®ØªØ§Ø± Ø¯Ø±Ø®ÙØ§Ø³Øª ÙØ¹Ø§ÙÙÙ
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
// Ú©ÙØ§Ø³ ÙØ¯ÛØ±ÛØª ÙØ¹Ø§ÙÙØ§Øª Ú©Ø§ÙÙ
//+
class CTradeManager {
private:
   CTrade m_trade;
   CRiskManager *m_riskManager;
   string m_symbol;
   int m_magic;
   int m_orderCount;

   // ØªÙØ¸ÛÙØ§Øª Ø§Ø¬Ø±Ø§
   int m_maxSlippage;
   int m_maxRetries;
   int m_retryDelayMs;

   // ÙØ­Ø¯ÙØ¯ÛØªâÙØ§Û ÙÙØ§Ø¯
   double m_stopLevel;
   double m_freezeLevel;
   double m_point;
   int m_digits;

   // Ø¢ÙØ§Ø±
   int m_totalOrders;
   int m_successfulOrders;
   int m_failedOrders;

   // ØªÙØ§Ø¨Ø¹ Ø¯Ø§Ø®ÙÛ
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

   // ØªÙØ¸ÛÙØ§Øª
   void SetRiskManager(CRiskManager *riskManager);
   void SetMaxSlippage(const int points);
   void SetMaxRetries(const int count, const int delayMs);
   void SetMagicNumber(const int magic);

   // Ø§Ø¬Ø±Ø§Û ÙØ¹Ø§ÙÙØ§Øª
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

   // ÙØ¯ÛØ±ÛØª Ù¾ÙØ²ÛØ´Ù
   bool CloseTrade(const ulong ticket, const string reason = "");
   bool CloseTradePartial(const ulong ticket, const double volume, const string reason = "");
   bool CloseAllTrades(const string direction = "");
   bool CloseAllTradesBySymbol();
   bool CloseProfitableTrades();
   bool CloseLosingTrades();

   // ØªØºÛÛØ± SL/TP
   bool ModifySlTp(const ulong ticket, const double sl, const double tp);
   bool ModifySl(const ulong ticket, const double sl);
   bool ModifyTp(const ulong ticket, const double tp);
   bool MoveToBreakeven(const ulong ticket);
   bool SetTrailingStop(const ulong ticket, const double distance, const double step = 0);

   // ÙØ¯ÛØ±ÛØª Ø³ÙØ§Ø±Ø´âÙØ§Û Ù¾ÙØ¯ÛÙÚ¯
   bool DeletePendingOrder(const ulong ticket);
   bool ModifyPendingOrder(const ulong ticket, const double price,
      const double sl = 0, const double tp = 0);
   int DeleteAllPendingOrders();
   int CountPendingOrders();

   // Ø§Ø·ÙØ§Ø¹Ø§Øª Ù Ø¢ÙØ§Ø±
   int GetOpenPositionsCount();
   int GetBuyPositionsCount();
   int GetSellPositionsCount();
   double GetOpenProfit();
   double GetOpenProfitByDirection(const ENUM_POSITION_TYPE direction);
   int GetDailyPnL();
   double GetAverageEntryPrice(const ENUM_POSITION_TYPE direction);

   // Ú¯Ø²Ø§Ø±Ø´
   string GetTradeReport();
   string GetLastErrorDescription(const int code);
   void PrintOrderResult(const OrderResult &result);

   // Ø§Ø¹ØªØ¨Ø§Ø±Ø³ÙØ¬Û
   bool IsMarketOpen();
   bool IsTradeAllowed();
   bool HasOpenPosition(const ENUM_POSITION_TYPE direction = POSITION_TYPE_BUY);
   ulong GetLastPositionTicket();
};

//+
// Ø³Ø§Ø²ÙØ¯Ù
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

   // Ø¯Ø±ÛØ§ÙØª Ø§Ø·ÙØ§Ø¹Ø§Øª ÙÙØ§Ø¯
   m_stopLevel = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
   m_freezeLevel = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   m_point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   m_digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
}

//+
// Ø³Ø§Ø²ÙØ¯Ù Ø¨Ø§ RiskManager
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
// ÙØ®Ø±Ø¨
//+
CTradeManager::~CTradeManager() {
}

//+
// ØªÙØ¸ÛÙ RiskManager
//+
void CTradeManager::SetRiskManager(CRiskManager *riskManager) {
   m_riskManager = riskManager;
}

//+
// ØªÙØ¸ÛÙ Ø§ÙØ­Ø±Ø§Ù ÙØ¬Ø§Ø²
//+
void CTradeManager::SetMaxSlippage(const int points) {
   m_maxSlippage = MathMax(0, points);
   m_trade.SetDeviationInPoints(m_maxSlippage);
}

//+
// ØªÙØ¸ÛÙ ØªÙØ§Ø´ ÙØ¬Ø¯Ø¯
//+
void CTradeManager::SetMaxRetries(const int count, const int delayMs) {
   m_maxRetries = MathMax(0, MathMin(10, count));
   m_retryDelayMs = MathMax(100, delayMs);
}

//+
// ØªÙØ¸ÛÙ Ø´ÙØ§Ø±Ù ÙØ¬ÛÚ©
//+
void CTradeManager::SetMagicNumber(const int magic) {
   m_magic = magic;
   m_trade.SetExpertMagicNumber(m_magic);
}

//+
// Ø§Ø¹ØªØ¨Ø§Ø±Ø³ÙØ¬Û Ø³ÛÚ¯ÙØ§Ù
//+
bool CTradeManager::ValidateSignal(const TradeSignal &signal) {
   if(signal.totalScore < MinEntryScore) {
      LogMessage("Ø§ÙØªÛØ§Ø² Ø³ÛÚ¯ÙØ§Ù Ú©ÙØªØ± Ø§Ø² Ø­Ø¯ ÙØµØ§Ø¨: " + IntegerToString(signal.totalScore), "WARNING");
      return false;
   }

   if(!signal.entryAllowed) {
      LogMessage("ÙØ±ÙØ¯ ÙØ¬Ø§Ø² ÙÛØ³Øª: " + signal.reason, "WARNING");
      return false;
   }

   return true;
}

//+
// ÙØ­Ø§Ø³Ø¨Ù Ø­Ø¬Ù Ù¾ÙØ²ÛØ´Ù
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
// Ø¨Ø±Ø±Ø³Û ÙØ­Ø¯ÙØ¯ÛØª Ø±ÛØ³Ú©
//+
bool CTradeManager::CheckRiskLimits() {
   if(m_riskManager != NULL) {
      RiskCheckResult result = m_riskManager->CheckRiskBeforeTrade(POSITION_TYPE_BUY);
      if(!result.allowed) {
         LogMessage("ÙØ­Ø¯ÙØ¯ÛØª Ø±ÛØ³Ú©: " + result.reason, "WARNING");
         return false;
      }
      return true;
   }

   if(CountTodayTrades() >= MaxDailyTrades) {
      LogMessage("Ø­Ø¯Ø§Ú©Ø«Ø± ÙØ¹Ø§ÙÙØ§Øª Ø±ÙØ²Ø§ÙÙ", "WARNING");
      return false;
   }

   if(CountOpenTrades(m_symbol) >= MaxOpenTrades) {
      LogMessage("Ø­Ø¯Ø§Ú©Ø«Ø± ÙØ¹Ø§ÙÙØ§Øª ÙÙØ²ÙØ§Ù", "WARNING");
      return false;
   }

   return true;
}

//+
// Ø¨Ø±Ø±Ø³Û Ø§Ø³Ù¾Ø±Ø¯
//+
bool CTradeManager::CheckSpread() {
   int currentSpread = (int)SymbolInfoInteger(m_symbol, SYMBOL_SPREAD);
   if(currentSpread > MaxSpread) {
      LogMessage("Ø§Ø³Ù¾Ø±Ø¯ Ø¨Ø§ÙØ§: " + IntegerToString(currentSpread), "WARNING");
      return false;
   }
   return true;
}

//+
// Ø¨Ø±Ø±Ø³Û ÙØ§Ø±Ø¬ÛÙ
//+
bool CTradeManager::CheckMargin(const double volume) {
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double marginRequired;

   double contractSize = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double leverage = (double)AccountInfoInteger(ACCOUNT_LEVERAGE);

   marginRequired = (volume * contractSize) / leverage;

   if(marginRequired > freeMargin * 0.8) {
      LogMessage(StringFormat("ÙØ§Ø±Ø¬ÛÙ Ú©Ø§ÙÛ ÙÛØ³Øª: ÙÛØ§Ø² $%.2fØ ÙÙØ¬ÙØ¯ $%.2f",
         marginRequired, freeMargin), "WARNING");
      return false;
   }

   return true;
}

//+
// Ø¨Ø±Ø±Ø³Û stop level
//+
bool CTradeManager::CheckStopLevels(const double price, const double sl, const double tp, const ENUM_POSITION_TYPE direction) {
   if(sl <= 0 && tp <= 0) return true;

   double stopLevelPrice = m_stopLevel * m_point;
   if(stopLevelPrice <= 0) stopLevelPrice = m_point * 10;

   if(direction == POSITION_TYPE_BUY) {
      if(sl > 0 && price - sl < stopLevelPrice) {
         LogMessage(StringFormat("SL Ø¨Ù ÙÛÙØª ÙØ²Ø¯ÛÚ© Ø§Ø³Øª: ÙØ§ØµÙÙ %.0f < %.0f",
            (price - sl) / m_point, stopLevelPrice / m_point), "WARNING");
         return false;
      }
      if(tp > 0 && tp - price < stopLevelPrice) {
         LogMessage(StringFormat("TP Ø¨Ù ÙÛÙØª ÙØ²Ø¯ÛÚ© Ø§Ø³Øª: ÙØ§ØµÙÙ %.0f < %.0f",
            (tp - price) / m_point, stopLevelPrice / m_point), "WARNING");
         return false;
      }
   } else {
      if(sl > 0 && sl - price < stopLevelPrice) {
         LogMessage(StringFormat("SL Ø¨Ù ÙÛÙØª ÙØ²Ø¯ÛÚ© Ø§Ø³Øª: ÙØ§ØµÙÙ %.0f < %.0f",
            (sl - price) / m_point, stopLevelPrice / m_point), "WARNING");
         return false;
      }
      if(tp > 0 && price - tp < stopLevelPrice) {
         LogMessage(StringFormat("TP Ø¨Ù ÙÛÙØª ÙØ²Ø¯ÛÚ© Ø§Ø³Øª: ÙØ§ØµÙÙ %.0f < %.0f",
            (price - tp) / m_point, stopLevelPrice / m_point), "WARNING");
         return false;
      }
   }

   return true;
}

//+
// Ø¨Ø±Ø±Ø³Û freeze level
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
      LogMessage("ÙÛÙØª Ø¯Ø± ÙØ­Ø¯ÙØ¯Ù freeze level", "WARNING");
      return false;
   }

   return true;
}

//+
// ØªÙØ¸ÛÙ ÙÛÙØª Ø¨Ø±Ø§Û stop level
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
// ÙØ±ÙØ§ÙâØ³Ø§Ø²Û ÙÛÙØª
//+
double CTradeManager::NormalizePrice(const double price) {
   return NormalizeDouble(price, m_digits);
}

//+
// ÙØ±ÙØ§ÙâØ³Ø§Ø²Û Ø­Ø¬Ù
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
// ØªÙØ¸ÛÙ Ø¯Ø±Ø®ÙØ§Ø³Øª ÙØ¹Ø§ÙÙÙ Ø§Ø² Ø³ÛÚ¯ÙØ§Ù
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
// Ø¨ÙâØ±ÙØ²Ø±Ø³Ø§ÙÛ Ø¢ÙØ§Ø± Ø³ÙØ§Ø±Ø´Ø§Øª
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
// Ø§Ø¬Ø±Ø§Û Ø³ÙØ§Ø±Ø´ ÙØ§Ø±Ú©Øª
//+
OrderResult CTradeManager::ExecuteMarketOrder(const TradeRequest &request) {
   OrderResult result;
   ZeroMemory(result);
   result.timestamp = TimeCurrent();

   if(!CheckSpread()) {
      result.success = false;
      result.errorCode = -1;
      result.errorMessage = "Ø§Ø³Ù¾Ø±Ø¯ Ø¨Ø§ÙØ§";
      return result;
   }

   if(!CheckMargin(request.volume)) {
      result.success = false;
      result.errorCode = -2;
      result.errorMessage = "ÙØ§Ø±Ø¬ÛÙ Ú©Ø§ÙÛ ÙÛØ³Øª";
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

   LogMessage(StringFormat("Ø§Ø±Ø³Ø§Ù Ø³ÙØ§Ø±Ø´ ÙØ§Ø±Ú©Øª: %s %.2f @ %.5f | SL: %.5f TP: %.5f",
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

      LogMessage(StringFormat("Ø³ÙØ§Ø±Ø´ ÙÙÙÙ: Ticket #%I64u @ %.5f",
         result.positionTicket, result.executedPrice), "INFO");

      UpdateOrderStats(true);
   } else {
      result.success = false;
      result.errorCode = GetLastError();
      result.errorMessage = GetLastErrorDescription(result.errorCode);

      LogMessage("Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±Ø³Ø§Ù Ø³ÙØ§Ø±Ø´: " + result.errorMessage, "ERROR");
      UpdateOrderStats(false);
   }

   return result;
}

//+
// Ø§Ø¬Ø±Ø§Û Ø³ÙØ§Ø±Ø´ ÙÛÙÛØª
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
         result.errorMessage = "ÙÛÙØª ÙÛÙÛØª Ø®Ø±ÛØ¯ Ø¨Ø§ÛØ¯ Ú©ÙØªØ± Ø§Ø² ÙÛÙØª ÙØ¹ÙÛ Ø¨Ø§Ø´Ø¯";
         return result;
      }
   } else {
      orderType = ORDER_TYPE_SELL_LIMIT;
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      if(price <= currentPrice) {
         result.success = false;
         result.errorCode = -3;
         result.errorMessage = "ÙÛÙØª ÙÛÙÛØª ÙØ±ÙØ´ Ø¨Ø§ÛØ¯ Ø¨ÛØ´ØªØ± Ø§Ø² ÙÛÙØª ÙØ¹ÙÛ Ø¨Ø§Ø´Ø¯";
         return result;
      }
   }

   double volume = NormalizeVolume(request.volume);
   double sl = NormalizePrice(request.stopLoss);
   double tp = NormalizePrice(request.takeProfit);
   datetime expiration = request.expiration > 0 ? request.expiration : 0;

   LogMessage(StringFormat("Ø§Ø±Ø³Ø§Ù Ø³ÙØ§Ø±Ø´ ÙÛÙÛØª: %s %.2f @ %.5f | SL: %.5f TP: %.5f",
      request.direction == POSITION_TYPE_BUY ? "BUY LIMIT" : "SELL LIMIT",
      volume, price, sl, tp), "TRADE");

   bool success = m_trade.OrderPlacement(orderType, volume, m_symbol, price, sl, tp, ORDER_TIME_GTC,
      expiration, request.comment);

   if(success) {
      result.success = true;
      result.orderTicket = m_trade.ResultOrder();
      result.executedPrice = price;
      result.executedVolume = volume;

      LogMessage(StringFormat("Ø³ÙØ§Ø±Ø´ ÙÛÙÛØª Ø«Ø¨Øª Ø´Ø¯: Ticket #%I64u", result.orderTicket), "INFO");
      UpdateOrderStats(true);
   } else {
      result.success = false;
      result.errorCode = GetLastError();
      result.errorMessage = GetLastErrorDescription(result.errorCode);

      LogMessage("Ø®Ø·Ø§ Ø¯Ø± Ø«Ø¨Øª Ø³ÙØ§Ø±Ø´ ÙÛÙÛØª: " + result.errorMessage, "ERROR");
      UpdateOrderStats(false);
   }

   return result;
}

//+
// Ø§Ø¬Ø±Ø§Û Ø³ÙØ§Ø±Ø´ Ø§Ø³ØªØ§Ù¾
//+
OrderResult CTradeManager::ExecuteStopOrder(const TradeRequest &request) {
   OrderResult result;
   ZeroMemory(result);
   result.timestamp = TimeCurrent();

   double price = NormalizePrice(request.entryPrice);

   if(!CheckFreezeLevel(price, request.direction)) {
      result.success = false;
      result.errorCode = -4;
      result.errorMessage = "ÙÛÙØª Ø¯Ø± ÙØ­Ø¯ÙØ¯Ù freeze level";
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
         result.errorMessage = "ÙÛÙØª Ø§Ø³ØªØ§Ù¾ Ø®Ø±ÛØ¯ Ø¨Ø§ÛØ¯ Ø¨ÛØ´ØªØ± Ø§Ø² ÙÛÙØª ÙØ¹ÙÛ Ø¨Ø§Ø´Ø¯";
         return result;
      }
   } else {
      orderType = ORDER_TYPE_SELL_STOP;
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      if(price >= currentPrice) {
         result.success = false;
         result.errorCode = -3;
         result.errorMessage = "ÙÛÙØª Ø§Ø³ØªØ§Ù¾ ÙØ±ÙØ´ Ø¨Ø§ÛØ¯ Ú©ÙØªØ± Ø§Ø² ÙÛÙØª ÙØ¹ÙÛ Ø¨Ø§Ø´Ø¯";
         return result;
      }
   }

   double volume = NormalizeVolume(request.volume);
   double sl = NormalizePrice(request.stopLoss);
   double tp = NormalizePrice(request.takeProfit);
   datetime expiration = request.expiration > 0 ? request.expiration : 0;

   LogMessage(StringFormat("Ø§Ø±Ø³Ø§Ù Ø³ÙØ§Ø±Ø´ Ø§Ø³ØªØ§Ù¾: %s %.2f @ %.5f | SL: %.5f TP: %.5f",
      request.direction == POSITION_TYPE_BUY ? "BUY STOP" : "SELL STOP",
      volume, price, sl, tp), "TRADE");

   bool success = m_trade.OrderPlacement(orderType, volume, m_symbol, price, sl, tp, ORDER_TIME_GTC,
      expiration, request.comment);

   if(success) {
      result.success = true;
      result.orderTicket = m_trade.ResultOrder();
      result.executedPrice = price;
      result.executedVolume = volume;

      LogMessage(StringFormat("Ø³ÙØ§Ø±Ø´ Ø§Ø³ØªØ§Ù¾ Ø«Ø¨Øª Ø´Ø¯: Ticket #%I64u", result.orderTicket), "INFO");
      UpdateOrderStats(true);
   } else {
      result.success = false;
      result.errorCode = GetLastError();
      result.errorMessage = GetLastErrorDescription(result.errorCode);

      LogMessage("Ø®Ø·Ø§ Ø¯Ø± Ø«Ø¨Øª Ø³ÙØ§Ø±Ø´ Ø§Ø³ØªØ§Ù¾: " + result.errorMessage, "ERROR");
      UpdateOrderStats(false);
   }

   return result;
}

//+
// Ø§Ø¬Ø±Ø§Û Ø³ÙØ§Ø±Ø´ Ø¨Ø§ ØªÙØ§Ø´ ÙØ¬Ø¯Ø¯
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
         LogMessage(StringFormat("ØªÙØ§Ø´ ÙØ¬Ø¯Ø¯ %d/%d Ø¨Ø¹Ø¯ Ø§Ø² %d ms", attempts, maxAttempts - 1, request.retryDelayMs), "INFO");
         Sleep(request.retryDelayMs);
      }
   }

   return result;
}

//+
// Ø¨Ø§Ø² Ú©Ø±Ø¯Ù Ø³ÙØ§Ø±Ø´ ÙØ§Ø±Ú©Øª
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
      result.errorMessage = "ÙØ­Ø¯ÙØ¯ÛØª Ø±ÛØ³Ú©";
      return result;
   }

   return ExecuteMarketOrder(request);
}

//+
// Ø¨Ø§Ø² Ú©Ø±Ø¯Ù Ø³ÙØ§Ø±Ø´ ÙÛÙÛØª
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
// Ø¨Ø§Ø² Ú©Ø±Ø¯Ù Ø³ÙØ§Ø±Ø´ Ø§Ø³ØªØ§Ù¾
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
// Ø¨Ø§Ø² Ú©Ø±Ø¯Ù ÙØ¹Ø§ÙÙÙ Ø§Ø² Ø³ÛÚ¯ÙØ§Ù (Ø³Ø§Ø¯Ù)
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
// Ø¨Ø§Ø² Ú©Ø±Ø¯Ù ÙØ¹Ø§ÙÙÙ Ø§Ø² Ø³ÛÚ¯ÙØ§Ù (Ú©Ø§ÙÙ)
//+
OrderResult CTradeManager::OpenTradeEx(const TradeSignal &signal) {
   OrderResult result;
   ZeroMemory(result);

   if(!ValidateSignal(signal)) {
      result.success = false;
      result.errorCode = -6;
      result.errorMessage = "Ø³ÛÚ¯ÙØ§Ù ÙØ§ÙØ¹ØªØ¨Ø±";
      return result;
   }

   if(!CheckRiskLimits()) {
      result.success = false;
      result.errorCode = -5;
      result.errorMessage = "ÙØ­Ø¯ÙØ¯ÛØª Ø±ÛØ³Ú©";
      return result;
   }

   TradeRequest request;
   if(!FillTradeRequest(request, signal)) {
      result.success = false;
      result.errorCode = -7;
      result.errorMessage = "Ø®Ø·Ø§ Ø¯Ø± Ø§ÛØ¬Ø§Ø¯ Ø¯Ø±Ø®ÙØ§Ø³Øª";
      return result;
   }

   return ExecuteWithRetry(request);
}

//+
// Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙÙ
//+
bool CTradeManager::CloseTrade(const ulong ticket, const string reason) {
   if(!PositionSelectByTicket(ticket)) {
      LogMessage("Ù¾ÙØ²ÛØ´Ù ÛØ§ÙØª ÙØ´Ø¯: " + IntegerToString(ticket), "ERROR");
      return false;
   }

   ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double volume = PositionGetDouble(POSITION_VOLUME);

   LogMessage(StringFormat("Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙÙ #%I64u | %s | %.2f | Ø¯ÙÛÙ: %s",
      ticket, posType == POSITION_TYPE_BUY ? "BUY" : "SELL", volume, reason), "TRADE");

   bool success = m_trade.PositionClose(ticket);

   if(!success) {
      int error = GetLastError();
      LogMessage("Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙÙ: " + GetLastErrorDescription(error), "ERROR");
      return false;
   }

   return true;
}

//+
// Ø¨Ø³ØªÙ Ø¬Ø²Ø¦Û ÙØ¹Ø§ÙÙÙ
//+
bool CTradeManager::CloseTradePartial(const ulong ticket, const double volume, const string reason) {
   if(!PositionSelectByTicket(ticket)) {
      LogMessage("Ù¾ÙØ²ÛØ´Ù ÛØ§ÙØª ÙØ´Ø¯: " + IntegerToString(ticket), "ERROR");
      return false;
   }

   double currentVolume = PositionGetDouble(POSITION_VOLUME);
   double closeVolume = NormalizeVolume(MathMin(volume, currentVolume));

   LogMessage(StringFormat("Ø¨Ø³ØªÙ Ø¬Ø²Ø¦Û #%I64u | %.2f Ø§Ø² %.2f | Ø¯ÙÛÙ: %s",
      ticket, closeVolume, currentVolume, reason), "TRADE");

   bool success = m_trade.PositionClose(ticket, closeVolume);

   if(!success) {
      int error = GetLastError();
      LogMessage("Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø³ØªÙ Ø¬Ø²Ø¦Û: " + GetLastErrorDescription(error), "ERROR");
      return false;
   }

   return true;
}

//+
// Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª
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

      if(CloseTrade(ticket, "Ø¨Ø³ØªÙ ÙÙÙ")) {
         closed++;
      } else {
         failed++;
      }
   }

   LogMessage(StringFormat("Ø¨Ø³ØªÙ Ø´Ø¯: %d | ÙØ§ÙÙÙÙ: %d", closed, failed), "TRADE");

   return failed == 0;
}

//+
// Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª ÙÙØ§Ø¯
//+
bool CTradeManager::CloseAllTradesBySymbol() {
   return CloseAllTrades("");
}

//+
// Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª Ø³ÙØ¯Ø¯Ù
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
         if(CloseTrade(ticket, "Ø¨Ø³ØªÙ Ø³ÙØ¯Ø¯Ù")) {
            closed++;
         }
      }
   }

   LogMessage(StringFormat("ÙØ¹Ø§ÙÙØ§Øª Ø³ÙØ¯Ø¯Ù Ø¨Ø³ØªÙ Ø´Ø¯: %d", closed), "INFO");

   return closed > 0;
}

//+
// Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª Ø²ÛØ§ÙâØ¯Ù
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
         if(CloseTrade(ticket, "Ø¨Ø³ØªÙ Ø²ÛØ§ÙâØ¯Ù")) {
            closed++;
         }
      }
   }

   LogMessage(StringFormat("ÙØ¹Ø§ÙÙØ§Øª Ø²ÛØ§ÙâØ¯Ù Ø¨Ø³ØªÙ Ø´Ø¯: %d", closed), "INFO");

   return closed > 0;
}

//+
// ØªØºÛÛØ± SL Ù TP
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
// ØªØºÛÛØ± SL
//+
bool CTradeManager::ModifySl(const ulong ticket, const double sl) {
   if(!PositionSelectByTicket(ticket)) {
      return false;
   }

   double currentTp = PositionGetDouble(POSITION_TP);
   return ModifySlTp(ticket, sl, currentTp);
}

//+
// ØªØºÛÛØ± TP
//+
bool CTradeManager::ModifyTp(const ulong ticket, const double tp) {
   if(!PositionSelectByTicket(ticket)) {
      return false;
   }

   double currentSl = PositionGetDouble(POSITION_SL);
   return ModifySlTp(ticket, currentSl, tp);
}

//+
// Ø§ÙØªÙØ§Ù Ø¨Ù ÙÙØ·Ù Ø³Ø± Ø¨Ù Ø³Ø±
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

   LogMessage(StringFormat("Ø§ÙØªÙØ§Ù Ø¨Ù BE: #%I64u | %.5f", ticket, newSl), "TRADE");

   return ModifySlTp(ticket, newSl, currentTp);
}

//+
// ØªÙØ¸ÛÙ ØªØ±ÛÙÛÙÚ¯ Ø§Ø³ØªØ§Ù¾
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

   LogMessage(StringFormat("ØªØ±ÛÙÛÙÚ¯: #%I64u | SL: %.5f", ticket, newSl), "TRADE");

   return ModifySlTp(ticket, newSl, currentTp);
}

//+
// Ø­Ø°Ù Ø³ÙØ§Ø±Ø´ Ù¾ÙØ¯ÛÙÚ¯
//+
bool CTradeManager::DeletePendingOrder(const ulong ticket) {
   if(!OrderSelect(ticket)) {
      return false;
   }

   return m_trade.OrderDelete(ticket);
}

//+
// ØªØºÛÛØ± Ø³ÙØ§Ø±Ø´ Ù¾ÙØ¯ÛÙÚ¯
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
// Ø­Ø°Ù ÙÙÙ Ø³ÙØ§Ø±Ø´âÙØ§Û Ù¾ÙØ¯ÛÙÚ¯
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

   LogMessage(StringFormat("Ø³ÙØ§Ø±Ø´âÙØ§Û Ù¾ÙØ¯ÛÙÚ¯ Ø­Ø°Ù Ø´Ø¯: %d", deleted), "INFO");

   return deleted;
}

//+
// Ø´ÙØ§Ø±Ø´ Ø³ÙØ§Ø±Ø´âÙØ§Û Ù¾ÙØ¯ÛÙÚ¯
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
// ØªØ¹Ø¯Ø§Ø¯ Ù¾ÙØ²ÛØ´ÙâÙØ§Û Ø¨Ø§Ø²
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
// ØªØ¹Ø¯Ø§Ø¯ Ù¾ÙØ²ÛØ´Ù Ø®Ø±ÛØ¯
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
// ØªØ¹Ø¯Ø§Ø¯ Ù¾ÙØ²ÛØ´Ù ÙØ±ÙØ´
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
// Ø³ÙØ¯ ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²
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
// Ø³ÙØ¯ ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø² Ø¨Ø± Ø§Ø³Ø§Ø³ Ø¬ÙØª
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
// Ø³ÙØ¯/Ø¶Ø±Ø± Ø§ÙØ±ÙØ²
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
// ÙÛØ§ÙÚ¯ÛÙ ÙÛÙØª ÙØ±ÙØ¯
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
// Ø¢ÛØ§ Ø¨Ø§Ø²Ø§Ø± Ø¨Ø§Ø² Ø§Ø³Øª
//+
bool CTradeManager::IsMarketOpen() {
   long sessionFlags = SymbolInfoInteger(m_symbol, SYMBOL_SESSION_MODE);
   return sessionFlags > 0;
}

//+
// Ø¢ÛØ§ ÙØ¹Ø§ÙÙÙ ÙØ¬Ø§Ø² Ø§Ø³Øª
//+
bool CTradeManager::IsTradeAllowed() {
   if(!SymbolInfoInteger(m_symbol, SYMBOL_TRADE_MODE)) {
      return false;
   }

   return CheckRiskLimits() && CheckSpread();
}

//+
// Ø¢ÛØ§ Ù¾ÙØ²ÛØ´Ù Ø¨Ø§Ø² Ø¯Ø§Ø±Ø¯
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
// Ø¢Ø®Ø±ÛÙ Ù¾ÙØ²ÛØ´Ù
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
// Ú¯Ø²Ø§Ø±Ø´ ÙØ¹Ø§ÙÙØ§Øª
//+
string CTradeManager::GetTradeReport() {
   string report = "ð Ú¯Ø²Ø§Ø±Ø´ ÙØ¹Ø§ÙÙØ§Øª\n\n";

   report += StringFormat("ÙØ¹Ø§ÙÙØ§Øª Ø§ÙØ±ÙØ²: %d\n", CountTodayTrades());
   report += StringFormat("Ù¾ÙØ²ÛØ´ÙâÙØ§Û Ø¨Ø§Ø²: %d\n", GetOpenPositionsCount());
   report += StringFormat("Ø®Ø±ÛØ¯: %d | ÙØ±ÙØ´: %d\n", GetBuyPositionsCount(), GetSellPositionsCount());
   report += StringFormat("Ø³ÙØ¯/Ø¶Ø±Ø± Ø¨Ø§Ø²: $%.2f\n", GetOpenProfit());

   if(m_riskManager != NULL) {
      report += "\n" + m_riskManager.GetRiskReport();
   }

   report += StringFormat("\n Ø¢ÙØ§Ø± Ø§Ø¬Ø±Ø§:\n");
   report += StringFormat("Ú©Ù Ø³ÙØ§Ø±Ø´Ø§Øª: %d\n", m_totalOrders);
   report += StringFormat("ÙÙÙÙ: %d | ÙØ§ÙÙÙÙ: %d\n", m_successfulOrders, m_failedOrders);

   return report;
}

//+
// ØªÙØ¶ÛØ­ Ø®Ø·Ø§
//+
string CTradeManager::GetLastErrorDescription(const int code) {
   switch(code) {
      case 0: return "Ø¨Ø¯ÙÙ Ø®Ø·Ø§";
      case 4756: return "Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±Ø³Ø§Ù Ø¯Ø±Ø®ÙØ§Ø³Øª";
      case 10004: return "Ø¯Ø±Ø®ÙØ§Ø³Øª Ø¯Ø± Ø­Ø§Ù Ù¾Ø±Ø¯Ø§Ø²Ø´";
      case 10006: return "Ø¯Ø±Ø®ÙØ§Ø³Øª Ø±Ø¯ Ø´Ø¯";
      case 10007: return "Ø¯Ø±Ø®ÙØ§Ø³Øª ÙØºÙ Ø´Ø¯";
      case 10010: return "ÙÙØ· Ø¨Ø®Ø´Û Ø§Ø² Ø¯Ø±Ø®ÙØ§Ø³Øª Ø§Ø¬Ø±Ø§ Ø´Ø¯";
      case 10011: return "Ø®Ø·Ø§Û ØªØ¬Ø§Ø±Û";
      case 10012: return "Ø¯Ø±Ø®ÙØ§Ø³Øª Ø¯Ø± Ø§ÙØªØ¸Ø§Ø±";
      case 10013: return "Ø¯Ø±Ø®ÙØ§Ø³Øª ÙØ§ÙØ¹ØªØ¨Ø±";
      case 10014: return "Ø­Ø¬Ù ÙØ§ÙØ¹ØªØ¨Ø±";
      case 10015: return "ÙÛÙØª ÙØ§ÙØ¹ØªØ¨Ø±";
      case 10016: return "Ø³Ø·ÙØ­ ÙØ§ÙØ¹ØªØ¨Ø±";
      case 10017: return "Ø®Ø¨Ø± Ø§ÙØªØµØ§Ø¯Û";
      case 10018: return "Ø¨Ø§Ø²Ø§Ø± Ø¨Ø³ØªÙ";
      case 10019: return "ÙØ§Ø±Ø¬ÛÙ Ú©Ø§ÙÛ ÙÛØ³Øª";
      case 10020: return "ÙÙØ¬ÙØ¯Û Ú©Ø§ÙÛ ÙÛØ³Øª";
      case 10021: return "ÙØ±ÙØ´ ÙÙÙÙØ¹";
      case 10022: return "Ø®Ø±ÛØ¯ ÙÙÙÙØ¹";
      case 10023: return "Ø³ÙØ§Ø±Ø´ ØªÚ©Ø±Ø§Ø±Û";
      case 10024: return "Ø¯Ø±Ø®ÙØ§Ø³Øª Ã§ok Ø²ÛØ§Ø¯";
      case 10025: return "ØªØºÛÛØ±Ø§Øª ÙØ§ÙØ¹ØªØ¨Ø±";
      case 10026: return "ÙØ¹Ø§ÙÙÙ ØºÛØ±ÙØ¹Ø§Ù";
      case 10027: return "Ø§ØªÙÙØ§Øª ØºÛØ±ÙØ¹Ø§Ù";
      case 10028: return "Ø¯Ø±Ø®ÙØ§Ø³Øª ÙØ­Ø¯ÙØ¯";
      case 10029: return "Ø§ØªØµØ§Ù ÙØ·Ø¹";
      case 10030: return "ÙÙØ· Ø¨Ø±Ø§Û ÙØ§ÙØ¹Û";
      case 10031: return "Ø¯Ø± Ø§ÙØªØ¸Ø§Ø± Ø®Ø¨Ø±";
      case 10032: return "ÙÙØ¹ Ø³ÙØ§Ø±Ø´ ÙØ§ÙØ¹ØªØ¨Ø±";
      case 10033: return "Ø´ÙØ§Ø³Ù ÙØ§ÙØ¹ØªØ¨Ø±";
      case 10034: return "Ø¨Ø§Ø² Ø´Ø¯Ù ÙØ¬Ø§Ø² ÙÛØ³Øª";
      case 10035: return "ØªØ§Ø±ÛØ® ÙØ§ÙØ¹ØªØ¨Ø±";
      case 10036: return "Ø³ÙØ§Ø±Ø´ ØªÚ©Ø±Ø§Ø±Û";
      case 10038: return "ÙÙØ¯Ø§Ø± ÙØ§ÙØ¹ØªØ¨Ø±";
      case 10039: return "Ù¾ÙØ²ÛØ´Ù Ø¨Ø³ØªÙ";
      case 10040: return "Ø³ÙØ§Ø±Ø´ Ø¨Ø³ØªÙ";
      case 10041: return "ÙÙØ· Ø¨Ø³ØªÙ ÙØ¬Ø§Ø²";
      case -1: return "Ø§Ø³Ù¾Ø±Ø¯ Ø¨Ø§ÙØ§";
      case -2: return "ÙØ§Ø±Ø¬ÛÙ Ú©Ø§ÙÛ ÙÛØ³Øª";
      case -3: return "ÙÛÙØª Ø³ÙØ§Ø±Ø´ Ù¾ÙØ¯ÛÙÚ¯ ÙØ§ÙØ¹ØªØ¨Ø±";
      case -4: return "ÙÛÙØª Ø¯Ø± ÙØ­Ø¯ÙØ¯Ù freeze level";
      case -5: return "ÙØ­Ø¯ÙØ¯ÛØª Ø±ÛØ³Ú©";
      case -6: return "Ø³ÛÚ¯ÙØ§Ù ÙØ§ÙØ¹ØªØ¨Ø±";
      case -7: return "Ø®Ø·Ø§ Ø¯Ø± Ø§ÛØ¬Ø§Ø¯ Ø¯Ø±Ø®ÙØ§Ø³Øª";
      default: return "Ø®Ø·Ø§Û ÙØ§ÙØ´Ø®Øµ: " + IntegerToString(code);
   }
}

//+
// ÚØ§Ù¾ ÙØªÛØ¬Ù Ø³ÙØ§Ø±Ø´
//+
void CTradeManager::PrintOrderResult(const OrderResult &result) {
   if(result.success) {
      LogMessage("✅ سفارش موفق", "TRADE");
      LogMessage(StringFormat("   Ticket: #%I64u", result.positionTicket), "TRADE");
      LogMessage(StringFormat("   Price: %.5f", result.executedPrice), "TRADE");
      LogMessage(StringFormat("   Volume: %.2f", result.executedVolume), "TRADE");
   } else {
      LogMessage("❌ سفارش ناموفق", "ERROR");
      LogMessage(StringFormat("   Error: %s", result.errorMessage), "ERROR");
      LogMessage(StringFormat("   Code: %d", result.errorCode), "ERROR");
   }
}
//+------------------------------------------------------------------+
