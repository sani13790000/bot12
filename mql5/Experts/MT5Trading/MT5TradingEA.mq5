//+------------------------------------------------------------------+
//|                                                MT5TradingEA.mq5   |
//|                                    MT5 Trading System             |
//|                                    اکسپرت ادوایزر اصلی            |
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
// متغیرهای گلوبال
//+

// مدیریت
CRiskManager *g_riskManager = NULL;
CTradeManager *g_tradeManager = NULL;
CPositionManager *g_positionManager = NULL;
CDecisionConnector *g_decisionConnector = NULL;
CLicenseChecker *g_licenseChecker = NULL;

// تحلیلگرها
CSMCAnalyzer *g_smcAnalyzer = NULL;
CPAAnalyzer *g_paAnalyzer = NULL;

// وضعیت
datetime g_lastAnalysisTime = 0;
int g_analysisInterval = 60;
datetime g_lastLicenseCheck = 0;
int g_licenseCheckInterval = 3600;

bool g_tradeEnabled = true;
bool g_licenseValid = false;
bool g_emergencyStopActive = false;

// آمار
int g_dailyTrades = 0;
double g_dailyPnL = 0;
datetime g_dayStart = 0;

//+
// تابع initialization
//+
int OnInit() {
   // بررسی نماد
   if(Symbol() == "") {
      Print("خطا: نماد تعیین نشده");
      return INIT_PARAMETERS_INCORRECT;
   }

   // ایجاد مدیریت ریسک
   g_riskManager = new CRiskManager(Symbol());

   if(g_riskManager == NULL) {
      Print("خطا: ایجاد مدیر ریسک ناموفق");
      return INIT_FAILED;
   }

   // ایجاد مدیر معاملات
   g_tradeManager = new CTradeManager(Symbol(), g_riskManager);

   if(g_tradeManager == NULL) {
      Print("خطا: ایجاد مدیر معاملات ناموفق");
      CleanupOnInit();
      return INIT_FAILED;
   }

   // ایجاد مدیر پوزیشن
   g_positionManager = new CPositionManager(Symbol());

   if(g_positionManager == NULL) {
      Print("خطا: ایجاد مدیر پوزیشن ناموفق");
      CleanupOnInit();
      return INIT_FAILED;
   }

   // ایجاد اتصال به Decision Engine
   g_decisionConnector = new CDecisionConnector();

   if(g_decisionConnector == NULL) {
      Print("خطا: ایجاد Decision Connector ناموفق");
      CleanupOnInit();
      return INIT_FAILED;
   }

   g_decisionConnector.SetApiUrl(ApiBaseUrl);
   g_decisionConnector.SetTimeout(ApiTimeout);

   // ایجاد بررسی لایسنس
   g_licenseChecker = new CLicenseChecker();

   if(g_licenseChecker == NULL) {
      Print("خطا: ایجاد بررسی لایسنس ناموفق");
      CleanupOnInit();
      return INIT_FAILED;
   }

   // ایجاد تحلیلگرها
   g_smcAnalyzer = new CSMCAnalyzer(Symbol(), PERIOD_CURRENT);

   if(g_smcAnalyzer == NULL) {
      Print("خطا: ایجاد تحلیلگر SMC ناموفق");
      CleanupOnInit();
      return INIT_FAILED;
   }

   g_paAnalyzer = new CPAAnalyzer(Symbol(), PERIOD_CURRENT);

   if(g_paAnalyzer == NULL) {
      Print("خطا: ایجاد تحلیلگر PA ناموفق");
      CleanupOnInit();
      return INIT_FAILED;
   }

   // بررسی اولیه لایسنس
   if(!CheckLicense()) {
      Print("هشدار: لایسنس معتبر نیست");
   }

   // راه‌اندازی متغیرها
   g_dayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   g_lastLicenseCheck = TimeCurrent();

   // لاگ راه‌اندازی
   LogMessage(StringFormat("اکسپرت راه‌اندازی شد | نماد: %s | تایم‌فریم: %s | نسخه: %s",
      Symbol(), EnumToString(Period()), VERSION));

   PrintStatus();

   return INIT_SUCCEEDED;
}

//+
// پاکسازی در OnInit
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
// تابع deinitialization
//+
void OnDeinit(const int reason) {
   // حذف آبجکت‌ها
   if(g_riskManager) delete g_riskManager;
   if(g_tradeManager) delete g_tradeManager;
   if(g_positionManager) delete g_positionManager;
   if(g_decisionConnector) delete g_decisionConnector;
   if(g_licenseChecker) delete g_licenseChecker;
   if(g_smcAnalyzer) delete g_smcAnalyzer;
   if(g_paAnalyzer) delete g_paAnalyzer;

   LogMessage("اکسپرت متوقف شد | دلیل: " + GetDeinitReason(reason));
}

//+
// دریافت دلیل توقف
//+
string GetDeinitReason(const int reason) {
   switch(reason) {
      case REASON_PROGRAM:     return "برنامه";
      case REASON_REMOVE:      return "حذف";
      case REASON_RECOMPILE:   return "کامپایل مجدد";
      case REASON_CHARTCHANGE: return "تغییر چارت";
      case REASON_CHARTCLOSE:  return "بستن چارت";
      case REASON_PARAMETERS:  return "تغییر پارامتر";
      case REASON_ACCOUNT:     return "تغییر حساب";
      default: return IntegerToString(reason);
   }
}

//+
// بررسی لایسنس
//+
bool CheckLicense() {
   if(g_licenseChecker == NULL) return false;

   // بررسی دوره‌ای
   if(TimeCurrent() - g_lastLicenseCheck > g_licenseCheckInterval) {
      g_lastLicenseCheck = TimeCurrent();

      if(!g_licenseChecker.Verify()) {
         g_licenseValid = false;
         LogMessage("لایسنس نامعتبر", "ERROR");
         return false;
      }
   }

   g_licenseValid = g_licenseChecker.IsValid();
   return g_licenseValid;
}

//+
// تابع اصلی تیک
//+
void OnTick() {
   // بررسی روز جدید
   CheckNewDay();

   // بررسی اتصال
   if(!TerminalInfoInteger(TERMINAL_CONNECTED)) {
      LogMessage("عدم اتصال به سرور", "WARNING");
      return;
   }

   // بررسی لایسنس
   if(!g_licenseValid && !CheckLicense()) {
      // ادامه بدون معامله
      ManageExistingPositions();
      return;
   }

   // بررسی توقف اضطراری
   if(g_emergencyStopActive || g_riskManager.IsEmergencyStop()) {
      g_tradeEnabled = false;
      ManageExistingPositions();
      return;
   }

   // به‌روزرسانی پوزیشن‌ها
   g_positionManager.UpdatePositions();

   // بررسی محدودیت‌های ریسک روزانه
   if(g_riskManager.IsDailyLossLimitReached()) {
      LogMessage("حد ضرر روزانه رسید", "WARNING");
      g_tradeEnabled = false;
   }

   // مدیریت پوزیشن‌های موجود
   ManageExistingPositions();

   // تحلیل و معامله (در کندل جدید)
   if(g_tradeEnabled && IsNewBar()) {
      AnalyzeAndTrade();
   }

   // به‌روزرسانی آمار
   UpdateDailyStats();
}

//+
// بررسی روز جدید
//+
void CheckNewDay() {
   datetime todayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));

   if(todayStart != g_dayStart) {
      g_dayStart = todayStart;
      g_dailyTrades = 0;
      g_dailyPnL = 0;

      // بازنشانی آمار ریسک
      g_riskManager.ResetDailyStats();

      // بازنشانی لایسنس چک
      g_licenseCheckInterval = 3600;

      LogMessage("روز جدید شروع شد", "INFO");

      // فعال‌سازی مجدد
      if(!g_riskManager.IsEmergencyStop()) {
         g_tradeEnabled = true;
      }
   }
}

//+
// به‌روزرسانی آمار روزانه
//+
void UpdateDailyStats() {
   g_dailyPnL = g_riskManager.GetDailyPnL();
   g_dailyTrades = g_riskManager.GetTodayTradesCount();
}

//+
// بررسی کندل جدید
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
// تحلیل و معامله
//+
void AnalyzeAndTrade() {
   if(g_tradeManager == NULL || g_riskManager == NULL) {
      return;
   }

   // بررسی فیلتر زمانی
   if(UseTimeFilter && !IsTradingTime()) {
      LogMessage("خارج از زمان معاملاتی", "INFO");
      return;
   }

   // تحلیل SMC
   SMCData smcData;
   ZeroMemory(smcData);

   if(EnableSMC && g_smcAnalyzer != NULL) {
      if(!g_smcAnalyzer.Analyze(smcData)) {
         LogMessage("تحلیل SMC ناموفق", "WARNING");
      }
   }

   // تحلیل Price Action
   PAData paData;
   ZeroMemory(paData);

   if(EnablePA && g_paAnalyzer != NULL) {
      if(!g_paAnalyzer.Analyze(paData)) {
         LogMessage("تحلیل PA ناموفق", "WARNING");
      }
   }

   // دریافت تصمیم از API
   DecisionResponse decision = GetDecisionFromAPI(smcData, paData);

   // اعتبارسنجی تصمیم
   if(!g_decisionConnector.ValidateDecision(decision)) {
      return;
   }

   // ساخت سیگنال
   TradeSignal signal;
   BuildSignalFromDecision(decision, signal);

   // لاگ تحلیل
   LogMessage(StringFormat("تصمیم: %s | امتیاز: %d | جهت: %s",
      decision.decision, decision.confidenceScore, decision.direction));

   // بررسی و اجرا
   if(decision.allowed && decision.decision != "NO_TRADE") {
      ExecuteTrade(signal);
   }
}

//+
// دریافت تصمیم از API
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
// ساخت سیگنال از تصمیم
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
// جلسه فعلی
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
// اجرای معامله
//+
void ExecuteTrade(TradeSignal &signal) {
   if(g_tradeManager == NULL) return;

   // بررسی محدودیت ریسک
   RiskCheckResult riskCheck = g_riskManager.CheckRiskBeforeTrade(
      signal.direction == "buy" ? POSITION_TYPE_BUY : POSITION_TYPE_SELL);

   if(!riskCheck.allowed) {
      LogMessage("تصمیم رد شد: " + riskCheck.reason, "WARNING");
      return;
   }

   OrderResult result = g_tradeManager.OpenTradeEx(signal);

   if(result.success) {
      g_dailyTrades++;

      LogMessage(StringFormat("معامله باز شد: #%I64u | %.2f @ %.5f",
         result.positionTicket, result.executedVolume, result.executedPrice), "TRADE");

      // ارسال اعلان
      if(EnableTelegram) {
         SendTelegramNotification(signal, result);
      }
   } else {
      LogMessage("خطا در معامله: " + result.errorMessage, "ERROR");
   }
}

//+
// مدیریت پوزیشن‌های موجود
//+
void ManageExistingPositions() {
   if(g_positionManager == NULL) return;

   // به‌روزرسانی پوزیشن‌ها
   g_positionManager.UpdatePositions();

   // تریلینگ استاپ
   if(TrailingStop > 0) {
      g_positionManager.ProcessTrailingStops(TrailingStop, TrailingStep);
   }

   // انتقال به BE
   if(BreakEvenTrigger > 0) {
      g_positionManager.ProcessBreakeven(BreakEvenTrigger);
   }

   // بستن جزئی
   if(PartialCloseRR > 0 && PartialClosePercent > 0) {
      g_positionManager.ProcessPartialClose(PartialCloseRR, PartialClosePercent);
   }

   // به‌روزرسانی peak balance
   g_riskManager.UpdatePeakBalance();
}

//+
// ارسال اعلان تلگرام
//+
void SendTelegramNotification(TradeSignal &signal, OrderResult &result) {
   string directionStr = signal.direction == "buy" ? "خرید" : "فروش";
   string directionEmoji = signal.direction == "buy" ? "🟢" : "🔴";

   string message = StringFormat(
      "🔔 معامله جدید\n\n" +
      "📈 نماد: %s\n" +
      "🎯 جهت: %s %s\n" +
      "📊 امتیاز: %d\n\n" +
      "📍 ورود: %.5f\n" +
      "🛡 حد ضرر: %.5f\n" +
      "🎯 حد سود: %.5f\n\n" +
      "📝 Ticket: #%I64u\n" +
      "⏰ %s",
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
// ارسال درخواست API
//+
void SendApiRequest(const string endpoint, const string method, const string body) {
   string url = ApiBaseUrl + endpoint;

   char data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";

   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);

   int res = WebRequest(method, url, headers, ApiTimeout / 1000, data, result, headers);

   if(res == -1) {
      LogMessage("خطا در ارسال درخواست API: " + IntegerToString(GetLastError()), "ERROR");
   }
}

//+
// چاپ وضعیت
//+
void PrintStatus() {
   Print("═══════════════════════════════════");
   Print("    MT5 Trading System v" + VERSION);
   Print("═══════════════════════════════════");
   Print("نماد: " + Symbol());
   Print("تایم‌فریم: " + EnumToString(Period()));
   Print("Magic: " + MagicNumber);
   Print("═══════════════════════════════════");
}

//+
// دستورات دکمه‌ای
//+
void OnChartEvent(
   const int id,
   const long &lparam,
   const double &dparam,
   const string &sparam
) {
   if(id == CHARTEVENT_CUSTOM + 1) {
      // دستور بستن همه
      g_tradeManager.CloseAllTrades();
   }

   if(id == CHARTEVENT_CUSTOM + 2) {
      // دستور توقف اضطراری
      g_riskManager.TriggerEmergencyStop();
      g_tradeEnabled = false;
   }

   if(id == CHARTEVENT_CUSTOM + 3) {
      // گزارش
      PrintReport();
   }
}

//+
// چاپ گزارش
//+
void PrintReport() {
   Print(g_riskManager.GetRiskReport());
   Print(g_tradeManager.GetTradeReport());
   Print(g_positionManager.GetPositionReport());
   Print(g_decisionConnector.GetConnectorReport());
}

//+
// تابع تست
//+
void OnTester() {
   // گزارش نهایی تستر
   PrintReport();
}
//+------------------------------------------------------------------+
