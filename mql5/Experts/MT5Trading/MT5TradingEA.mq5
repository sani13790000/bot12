//+------------------------------------------------------------------+
//|                                                MT5TradingEA.mq5   |
//|                                    MT5 Trading System             |
//|                                    Ø§Ú©Ø³Ù¾Ø±Øª Ø§Ø¯ÙØ§ÛØ²Ø± Ø§ØµÙÛ            |
//+------------------------------------------------------------------+
#property copyright "MT5 Trading Team"
#property link      "https://mt5trading.com"
#property version   "1.00"
#property strict

#include <MT5Trading/Config.mqh>
#include <MT5Trading/Helpers.mqh>
#include <MT5Trading/SMCAnalyzer.mqh>
#include <MT5Trading/PAAnalyzer.mqh>
#include <MT5Trading/RiskManager.mqh>
#include <MT5Trading/TradeManager.mqh>
#include <MT5Trading/PositionManager.mqh>
#include <MT5Trading/LicenseChecker.mqh>
#include <MT5Trading/DecisionConnector.mqh>

//+
// ÙØªØºÛØ±ÙØ§Û Ú¯ÙÙØ¨Ø§Ù
//+

// ÙØ¯ÛØ±ÛØª
CRiskManager *g_riskManager = NULL;
CTradeManager *g_tradeManager = NULL;
CPositionManager *g_positionManager = NULL;
CDecisionConnector *g_decisionConnector = NULL;
CLicenseChecker *g_licenseChecker = NULL;

// ØªØ­ÙÛÙÚ¯Ø±ÙØ§
CSMCAnalyzer *g_smcAnalyzer = NULL;
CPAAnalyzer *g_paAnalyzer = NULL;

// ÙØ¶Ø¹ÛØª
datetime g_lastAnalysisTime = 0;
int g_analysisInterval = 60;
datetime g_lastLicenseCheck = 0;
int g_licenseCheckInterval = 3600;

bool g_tradeEnabled = true;
bool g_licenseValid = false;
bool g_emergencyStopActive = false;

// Ø¢ÙØ§Ø±
int g_dailyTrades = 0;
double g_dailyPnL = 0;
datetime g_dayStart = 0;

//+
// ØªØ§Ø¨Ø¹ initialization
//+
int OnInit() {
   // Ø¨Ø±Ø±Ø³Û ÙÙØ§Ø¯
   if(Symbol() == "") {
       LogMessage("خطا: نماد تعیین نشده", "ERROR");
      return INIT_PARAMETERS_INCORRECT;
   }

   // Ø§ÛØ¬Ø§Ø¯ ÙØ¯ÛØ±ÛØª Ø±ÛØ³Ú©
   g_riskManager = new CRiskManager(Symbol());

   if(g_riskManager == NULL) {
       LogMessage("خطا: ایجاد مدیر ریسک ناموفق", "ERROR");
      return INIT_FAILED;
   }

   // Ø§ÛØ¬Ø§Ø¯ ÙØ¯ÛØ± ÙØ¹Ø§ÙÙØ§Øª
   g_tradeManager = new CTradeManager(Symbol(), g_riskManager);

   if(g_tradeManager == NULL) {
       LogMessage("خطا: ایجاد مدیر معاملات ناموفق", "ERROR");
      CleanupOnInit();
      return INIT_FAILED;
   }

   // Ø§ÛØ¬Ø§Ø¯ ÙØ¯ÛØ± Ù¾ÙØ²ÛØ´Ù
   g_positionManager = new CPositionManager(Symbol());

   if(g_positionManager == NULL) {
       LogMessage("خطا: ایجاد مدیر پوزیشن ناموفق", "ERROR");
      CleanupOnInit();
      return INIT_FAILED;
   }

   // Ø§ÛØ¬Ø§Ø¯ Ø§ØªØµØ§Ù Ø¨Ù Decision Engine
   g_decisionConnector = new CDecisionConnector();

   if(g_decisionConnector == NULL) {
       LogMessage("خطا: ایجاد Decision Connector ناموفق", "ERROR");
      CleanupOnInit();
      return INIT_FAILED;
   }

   g_decisionConnector.SetApiUrl(ApiBaseUrl);
   g_decisionConnector.SetTimeout(ApiTimeout);

   // Ø§ÛØ¬Ø§Ø¯ Ø¨Ø±Ø±Ø³Û ÙØ§ÛØ³ÙØ³
   g_licenseChecker = new CLicenseChecker();

   if(g_licenseChecker == NULL) {
       LogMessage("خطا: ایجاد بررسی لایسنس ناموفق", "ERROR");
      CleanupOnInit();
      return INIT_FAILED;
   }

   // Ø§ÛØ¬Ø§Ø¯ ØªØ­ÙÛÙÚ¯Ø±ÙØ§
   g_smcAnalyzer = new CSMCAnalyzer(Symbol(), PERIOD_CURRENT);

   if(g_smcAnalyzer == NULL) {
       LogMessage("خطا: ایجاد تحلیلگر SMC ناموفق", "ERROR");
      CleanupOnInit();
      return INIT_FAILED;
   }

   g_paAnalyzer = new CPAAnalyzer(Symbol(), PERIOD_CURRENT);

   if(g_paAnalyzer == NULL) {
       LogMessage("خطا: ایجاد تحلیلگر PA ناموفق", "ERROR");
      CleanupOnInit();
      return INIT_FAILED;
   }

   // Ø¨Ø±Ø±Ø³Û Ø§ÙÙÛÙ ÙØ§ÛØ³ÙØ³
   if(!CheckLicense()) {
       LogMessage("هشدار: لایسنس معتبر نیست", "WARN");
   }

   // Ø±Ø§ÙâØ§ÙØ¯Ø§Ø²Û ÙØªØºÛØ±ÙØ§
   g_dayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   g_lastLicenseCheck = TimeCurrent();

   // ÙØ§Ú¯ Ø±Ø§ÙâØ§ÙØ¯Ø§Ø²Û
   LogMessage(StringFormat("Ø§Ú©Ø³Ù¾Ø±Øª Ø±Ø§ÙâØ§ÙØ¯Ø§Ø²Û Ø´Ø¯ | ÙÙØ§Ø¯: %s | ØªØ§ÛÙâÙØ±ÛÙ: %s | ÙØ³Ø®Ù: %s",
      Symbol(), EnumToString(Period()), VERSION));

   PrintStatus();

   return INIT_SUCCEEDED;
}

//+
// Ù¾Ø§Ú©Ø³Ø§Ø²Û Ø¯Ø± OnInit
//+
void CleanupOnInit() {
   if(g_riskManager) delete g_riskManager;
   if(g_tradeManager) delete g_tradeManager;
   if(g_positionManager) delete g_positionManager;
   if(g_decisionConnector) delete g_decisionConnector;
   if(g_licenseChecker) delete g_licenseChecker;
   if(g_smcAnalyzer) delete g_smcAnalyzer;
   if(g_paAnalyzer) delete g_paAnalyzer;
}

//+
// ØªØ§Ø¨Ø¹ deinitialization
//+
void OnDeinit(const int reason) {
   // Ø­Ø°Ù Ø¢Ø¨Ø¬Ú©ØªâÙØ§
   if(g_riskManager) delete g_riskManager;
   if(g_tradeManager) delete g_tradeManager;
   if(g_positionManager) delete g_positionManager;
   if(g_decisionConnector) delete g_decisionConnector;
   if(g_licenseChecker) delete g_licenseChecker;
   if(g_smcAnalyzer) delete g_smcAnalyzer;
   if(g_paAnalyzer) delete g_paAnalyzer;

   LogMessage("Ø§Ú©Ø³Ù¾Ø±Øª ÙØªÙÙÙ Ø´Ø¯ | Ø¯ÙÛÙ: " + GetDeinitReason(reason));
}

//+
// Ø¯Ø±ÛØ§ÙØª Ø¯ÙÛÙ ØªÙÙÙ
//+
string GetDeinitReason(const int reason) {
   switch(reason) {
      case REASON_PROGRAM:     return "Ø¨Ø±ÙØ§ÙÙ";
      case REASON_REMOVE:      return "Ø­Ø°Ù";
      case REASON_RECOMPILE:   return "Ú©Ø§ÙÙ¾Ø§ÛÙ ÙØ¬Ø¯Ø¯";
      case REASON_CHARTCHANGE: return "ØªØºÛÛØ± ÚØ§Ø±Øª";
      case REASON_CHARTCLOSE:  return "Ø¨Ø³ØªÙ ÚØ§Ø±Øª";
      case REASON_PARAMETERS:  return "ØªØºÛÛØ± Ù¾Ø§Ø±Ø§ÙØªØ±";
      case REASON_ACCOUNT:     return "ØªØºÛÛØ± Ø­Ø³Ø§Ø¨";
      default: return IntegerToString(reason);
   }
}

//+
// Ø¨Ø±Ø±Ø³Û ÙØ§ÛØ³ÙØ³
//+
bool CheckLicense() {
   if(g_licenseChecker == NULL) return false;

   // Ø¨Ø±Ø±Ø³Û Ø¯ÙØ±ÙâØ§Û
   if(TimeCurrent() - g_lastLicenseCheck > g_licenseCheckInterval) {
      g_lastLicenseCheck = TimeCurrent();

      if(!g_licenseChecker.Verify()) {
         g_licenseValid = false;
         LogMessage("ÙØ§ÛØ³ÙØ³ ÙØ§ÙØ¹ØªØ¨Ø±", "ERROR");
         return false;
      }
   }

   g_licenseValid = g_licenseChecker.IsValid();
   return g_licenseValid;
}

//+
// ØªØ§Ø¨Ø¹ Ø§ØµÙÛ ØªÛÚ©
//+
void OnTick() {
   // Ø¨Ø±Ø±Ø³Û Ø±ÙØ² Ø¬Ø¯ÛØ¯
   CheckNewDay();

   // Ø¨Ø±Ø±Ø³Û Ø§ØªØµØ§Ù
   if(!TerminalInfoInteger(TERMINAL_CONNECTED)) {
      LogMessage("Ø¹Ø¯Ù Ø§ØªØµØ§Ù Ø¨Ù Ø³Ø±ÙØ±", "WARNING");
      return;
   }

   // Ø¨Ø±Ø±Ø³Û ÙØ§ÛØ³ÙØ³
   if(!g_licenseValid && !CheckLicense()) {
      // Ø§Ø¯Ø§ÙÙ Ø¨Ø¯ÙÙ ÙØ¹Ø§ÙÙÙ
      ManageExistingPositions();
      return;
   }

   // Ø¨Ø±Ø±Ø³Û ØªÙÙÙ Ø§Ø¶Ø·Ø±Ø§Ø±Û
   if(g_emergencyStopActive || g_riskManager.IsEmergencyStop()) {
      g_tradeEnabled = false;
      ManageExistingPositions();
      return;
   }

   // Ø¨ÙâØ±ÙØ²Ø±Ø³Ø§ÙÛ Ù¾ÙØ²ÛØ´ÙâÙØ§
   g_positionManager.UpdatePositions();

   // Ø¨Ø±Ø±Ø³Û ÙØ­Ø¯ÙØ¯ÛØªâÙØ§Û Ø±ÛØ³Ú© Ø±ÙØ²Ø§ÙÙ
   if(g_riskManager.IsDailyLossLimitReached()) {
      LogMessage("Ø­Ø¯ Ø¶Ø±Ø± Ø±ÙØ²Ø§ÙÙ Ø±Ø³ÛØ¯", "WARNING");
      g_tradeEnabled = false;
   }

   // ÙØ¯ÛØ±ÛØª Ù¾ÙØ²ÛØ´ÙâÙØ§Û ÙÙØ¬ÙØ¯
   ManageExistingPositions();

   // ØªØ­ÙÛÙ Ù ÙØ¹Ø§ÙÙÙ (Ø¯Ø± Ú©ÙØ¯Ù Ø¬Ø¯ÛØ¯)
   if(g_tradeEnabled && IsNewBar()) {
      AnalyzeAndTrade();
   }

   // Ø¨ÙâØ±ÙØ²Ø±Ø³Ø§ÙÛ Ø¢ÙØ§Ø±
   UpdateDailyStats();
}

//+
// Ø¨Ø±Ø±Ø³Û Ø±ÙØ² Ø¬Ø¯ÛØ¯
//+
void CheckNewDay() {
   datetime todayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));

   if(todayStart != g_dayStart) {
      g_dayStart = todayStart;
      g_dailyTrades = 0;
      g_dailyPnL = 0;

      // Ø¨Ø§Ø²ÙØ´Ø§ÙÛ Ø¢ÙØ§Ø± Ø±ÛØ³Ú©
      g_riskManager.ResetDailyStats();

      // Ø¨Ø§Ø²ÙØ´Ø§ÙÛ ÙØ§ÛØ³ÙØ³ ÚÚ©
      g_licenseCheckInterval = 3600;

      LogMessage("Ø±ÙØ² Ø¬Ø¯ÛØ¯ Ø´Ø±ÙØ¹ Ø´Ø¯", "INFO");

      // ÙØ¹Ø§ÙâØ³Ø§Ø²Û ÙØ¬Ø¯Ø¯
      if(!g_riskManager.IsEmergencyStop()) {
         g_tradeEnabled = true;
      }
   }
}

//+
// Ø¨ÙâØ±ÙØ²Ø±Ø³Ø§ÙÛ Ø¢ÙØ§Ø± Ø±ÙØ²Ø§ÙÙ
//+
void UpdateDailyStats() {
   g_dailyPnL = g_riskManager.GetDailyPnL();
   g_dailyTrades = g_riskManager.GetTodayTradesCount();
}

//+
// Ø¨Ø±Ø±Ø³Û Ú©ÙØ¯Ù Ø¬Ø¯ÛØ¯
//+
bool IsNewBar() {
   static datetime lastBarTime = 0;

   datetime currentBarTime = iTime(Symbol(), PERIOD_CURRENT, 0);

   if(currentBarTime != lastBarTime) {
      lastBarTime = currentBarTime;
      return true;
   }

   return false;
}

//+
// ØªØ­ÙÛÙ Ù ÙØ¹Ø§ÙÙÙ
//+
void AnalyzeAndTrade() {
   if(g_tradeManager == NULL || g_riskManager == NULL) {
      return;
   }

   // Ø¨Ø±Ø±Ø³Û ÙÛÙØªØ± Ø²ÙØ§ÙÛ
   if(UseTimeFilter && !IsTradingTime()) {
      LogMessage("Ø®Ø§Ø±Ø¬ Ø§Ø² Ø²ÙØ§Ù ÙØ¹Ø§ÙÙØ§ØªÛ", "INFO");
      return;
   }

   // ØªØ­ÙÛÙ SMC
   SMCData smcData;
   ZeroMemory(smcData);

   if(EnableSMC && g_smcAnalyzer != NULL) {
      if(!g_smcAnalyzer.Analyze(smcData)) {
         LogMessage("ØªØ­ÙÛÙ SMC ÙØ§ÙÙÙÙ", "WARNING");
      }
   }

   // ØªØ­ÙÛÙ Price Action
   PAData paData;
   ZeroMemory(paData);

   if(EnablePA && g_paAnalyzer != NULL) {
      if(!g_paAnalyzer.Analyze(paData)) {
         LogMessage("ØªØ­ÙÛÙ PA ÙØ§ÙÙÙÙ", "WARNING");
      }
   }

   // Ø¯Ø±ÛØ§ÙØª ØªØµÙÛÙ Ø§Ø² API
   DecisionResponse decision = GetDecisionFromAPI(smcData, paData);

   // Ø§Ø¹ØªØ¨Ø§Ø±Ø³ÙØ¬Û ØªØµÙÛÙ
   if(!g_decisionConnector.ValidateDecision(decision)) {
      return;
   }

   // Ø³Ø§Ø®Øª Ø³ÛÚ¯ÙØ§Ù
   TradeSignal signal;
   BuildSignalFromDecision(decision, signal);

   // ÙØ§Ú¯ ØªØ­ÙÛÙ
   LogMessage(StringFormat("ØªØµÙÛÙ: %s | Ø§ÙØªÛØ§Ø²: %d | Ø¬ÙØª: %s",
      decision.decision, decision.confidenceScore, decision.direction));

   // Ø¨Ø±Ø±Ø³Û Ù Ø§Ø¬Ø±Ø§
   if(decision.allowed && decision.decision != "NO_TRADE") {
      ExecuteTrade(signal);
   }
}

//+
// Ø¯Ø±ÛØ§ÙØª ØªØµÙÛÙ Ø§Ø² API
//+
DecisionResponse GetDecisionFromAPI(SMCData &smcData, PAData &paData) {
   DecisionRequest request;
   ZeroMemory(request);

   request.symbol = Symbol();
   request.timeframe = EnumToString(Period());
   request.currentPrice = SymbolInfoDouble(Symbol(), SYMBOL_BID);

   // SMC Data
   request.hasBOS = smcData.hasBOS;
   request.hasCHOCH = smcData.hasCHOCH;
   request.hasMSS = smcData.hasMSS;
   request.trendDirection = smcData.trendDirection;
   request.hasOrderBlock = smcData.hasOrderBlock;
   request.obType = smcData.obType;
   request.obHigh = smcData.obHigh;
   request.obLow = smcData.obLow;
   request.hasFVG = smcData.hasFVG;
   request.fvgHigh = smcData.fvgHigh;
   request.fvgLow = smcData.fvgLow;

   // PA Data
   request.hasPinBar = paData.hasPinBar;
   request.hasEngulfing = paData.hasEngulfing;
   request.hasInsideBar = paData.hasInsideBar;
   request.hasFakey = paData.hasFakey;
   request.patternBias = paData.patternBias;

   request.session = GetCurrentSession();
   request.requestTime = TimeCurrent();

   return g_decisionConnector.RequestDecision(request);
}

//+
// Ø³Ø§Ø®Øª Ø³ÛÚ¯ÙØ§Ù Ø§Ø² ØªØµÙÛÙ
//+
void BuildSignalFromDecision(DecisionResponse &decision, TradeSignal &signal) {
   ZeroMemory(signal);

   signal.symbol = Symbol();
   signal.direction = decision.direction == "bullish" ? "buy" : "sell";
   signal.entryPrice = decision.entryZone > 0 ? decision.entryZone : SymbolInfoDouble(Symbol(), SYMBOL_ASK);
   signal.stopLoss = decision.stopLoss;
   signal.takeProfit = decision.takeProfit1;
   signal.totalScore = decision.confidenceScore;
   signal.entryAllowed = decision.allowed;
   signal.reason = decision.decision + " | Score: " + IntegerToString(decision.confidenceScore);
   signal.validUntil = TimeCurrent() + 3600;
}

//+
// Ø¬ÙØ³Ù ÙØ¹ÙÛ
//+
string GetCurrentSession() {
   int hour = (int)TimeCurrent() % 86400 / 3600;

   if(hour >= LondonStart && hour < LondonEnd && UseLondonKZ) {
      return "london";
   }

   if(hour >= NYStart && hour < NYEnd && UseNYKZ) {
      return "new_york";
   }

   if(hour >= TokyoStart && hour < TokyoEnd && UseTokyoKZ) {
      return "tokyo";
   }

   return "off_hours";
}

//+
// Ø§Ø¬Ø±Ø§Û ÙØ¹Ø§ÙÙÙ
//+
void ExecuteTrade(TradeSignal &signal) {
   if(g_tradeManager == NULL) return;

   // Ø¨Ø±Ø±Ø³Û ÙØ­Ø¯ÙØ¯ÛØª Ø±ÛØ³Ú©
   RiskCheckResult riskCheck = g_riskManager.CheckRiskBeforeTrade(
      signal.direction == "buy" ? POSITION_TYPE_BUY : POSITION_TYPE_SELL);

   if(!riskCheck.allowed) {
      LogMessage("ØªØµÙÛÙ Ø±Ø¯ Ø´Ø¯: " + riskCheck.reason, "WARNING");
      return;
   }

   OrderResult result = g_tradeManager.OpenTradeEx(signal);

   if(result.success) {
      g_dailyTrades++;

      LogMessage(StringFormat("ÙØ¹Ø§ÙÙÙ Ø¨Ø§Ø² Ø´Ø¯: #%I64u | %.2f @ %.5f",
         result.positionTicket, result.executedVolume, result.executedPrice), "TRADE");

      // Ø§Ø±Ø³Ø§Ù Ø§Ø¹ÙØ§Ù
      if(EnableTelegram) {
         SendTelegramNotification(signal, result);
      }
   } else {
      LogMessage("Ø®Ø·Ø§ Ø¯Ø± ÙØ¹Ø§ÙÙÙ: " + result.errorMessage, "ERROR");
   }
}

//+
// ÙØ¯ÛØ±ÛØª Ù¾ÙØ²ÛØ´ÙâÙØ§Û ÙÙØ¬ÙØ¯
//+
void ManageExistingPositions() {
   if(g_positionManager == NULL) return;

   // Ø¨ÙâØ±ÙØ²Ø±Ø³Ø§ÙÛ Ù¾ÙØ²ÛØ´ÙâÙØ§
   g_positionManager.UpdatePositions();

   // ØªØ±ÛÙÛÙÚ¯ Ø§Ø³ØªØ§Ù¾
   if(TrailingStop > 0) {
      g_positionManager.ProcessTrailingStops(TrailingStop, TrailingStep);
   }

   // Ø§ÙØªÙØ§Ù Ø¨Ù BE
   if(BreakEvenTrigger > 0) {
      g_positionManager.ProcessBreakeven(BreakEvenTrigger);
   }

   // Ø¨Ø³ØªÙ Ø¬Ø²Ø¦Û
   if(PartialCloseRR > 0 && PartialClosePercent > 0) {
      g_positionManager.ProcessPartialClose(PartialCloseRR, PartialClosePercent);
   }

   // Ø¨ÙâØ±ÙØ²Ø±Ø³Ø§ÙÛ peak balance
   g_riskManager.UpdatePeakBalance();
}

//+
// Ø§Ø±Ø³Ø§Ù Ø§Ø¹ÙØ§Ù ØªÙÚ¯Ø±Ø§Ù
//+
void SendTelegramNotification(TradeSignal &signal, OrderResult &result) {
   string directionStr = signal.direction == "buy" ? "Ø®Ø±ÛØ¯" : "ÙØ±ÙØ´";
   string directionEmoji = signal.direction == "buy" ? "ð¢" : "ð´";

   string message = StringFormat(
      "ð ÙØ¹Ø§ÙÙÙ Ø¬Ø¯ÛØ¯\n\n" +
      "ð ÙÙØ§Ø¯: %s\n" +
      "ð¯ Ø¬ÙØª: %s %s\n" +
      "ð Ø§ÙØªÛØ§Ø²: %d\n\n" +
      "ð ÙØ±ÙØ¯: %.5f\n" +
      "ð¡ Ø­Ø¯ Ø¶Ø±Ø±: %.5f\n" +
      "ð¯ Ø­Ø¯ Ø³ÙØ¯: %.5f\n\n" +
      "ð Ticket: #%I64u\n" +
      "â° %s",
      signal.symbol,
      directionStr, directionEmoji,
      signal.totalScore,
      result.executedPrice,
      signal.stopLoss,
      signal.takeProfit,
      result.positionTicket,
      TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES)
   );

   SendApiRequest("/telegram/send", "POST", StringFormat("{\"message\":\"%s\"}", message));
}

//+
// Ø§Ø±Ø³Ø§Ù Ø¯Ø±Ø®ÙØ§Ø³Øª API
//+
void SendApiRequest(const string endpoint, const string method, const string body) {
   string url = ApiBaseUrl + endpoint;

   char data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";

   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);

   int res = WebRequest(method, url, headers, ApiTimeout / 1000, data, result, headers);

   if(res == -1) {
      LogMessage("Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±Ø³Ø§Ù Ø¯Ø±Ø®ÙØ§Ø³Øª API: " + IntegerToString(GetLastError()), "ERROR");
   }
}

//+
// ÚØ§Ù¾ ÙØ¶Ø¹ÛØª
//+
void PrintStatus() {
   LogMessage("═══════════════════════════════════════", "INFO");
   LogMessage("    MT5 Trading System v" + VERSION, "INFO");
   LogMessage("═══════════════════════════════════════", "INFO");
   LogMessage("نماد: " + Symbol(), "INFO");
   LogMessage("تایم‌فریم: " + EnumToString(Period()), "INFO");
   LogMessage(StringFormat("Magic: %d", MagicNumber), "INFO");
   LogMessage("═══════════════════════════════════════", "INFO");
}

//+
// Ø¯Ø³ØªÙØ±Ø§Øª Ø¯Ú©ÙÙâØ§Û
//+
void OnChartEvent(
   const int id,
   const long &lparam,
   const double &dparam,
   const string &sparam
) {
   if(id == CHARTEVENT_CUSTOM + 1) {
      // Ø¯Ø³ØªÙØ± Ø¨Ø³ØªÙ ÙÙÙ
      g_tradeManager.CloseAllTrades();
   }

   if(id == CHARTEVENT_CUSTOM + 2) {
      // Ø¯Ø³ØªÙØ± ØªÙÙÙ Ø§Ø¶Ø·Ø±Ø§Ø±Û
      g_riskManager.TriggerEmergencyStop();
      g_tradeEnabled = false;
   }

   if(id == CHARTEVENT_CUSTOM + 3) {
      // Ú¯Ø²Ø§Ø±Ø´
      PrintReport();
   }
}

//+
// ÚØ§Ù¾ Ú¯Ø²Ø§Ø±Ø´
//+
void PrintReport() {
   LogMessage(g_riskManager.GetRiskReport(), "INFO");
   LogMessage(g_tradeManager.GetTradeReport(), "INFO");
   LogMessage(g_positionManager.GetPositionReport(), "INFO");
   LogMessage(g_decisionConnector.GetConnectorReport(), "INFO");
}

//+
// ØªØ§Ø¨Ø¹ ØªØ³Øª
//+
void OnTester() {
   // Ú¯Ø²Ø§Ø±Ø´ ÙÙØ§ÛÛ ØªØ³ØªØ±
   PrintReport();
}
//+------------------------------------------------------------------+
