//+------------------------------------------------------------------+
//|                                           DecisionEngine.mqh       |
//|                                    MT5 Trading System             |
//|                                    موتور تصمیم‌گیری               |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"
#include "Helpers.mqh"
#include "SMCAnalyzer.mqh"
#include "PAAnalyzer.mqh"

//+
// کلاس موتور تصمیم‌گیری
//+
class CDecisionEngine {
private:
   string m_symbol;
   ENUM_TIMEFRAME m_timeframe;

   CStructureAnalyzer *m_structureAnalyzer;
   CBlockAnalyzer *m_blockAnalyzer;
   CFVGAnalyzer *m_fvgAnalyzer;
   CCandleAnalyzer *m_candleAnalyzer;
   CPriceStructureAnalyzer *m_priceAnalyzer;

   // امتیازدهی
   int m_smcScore;
   int m_paScore;
   int m_timeScore;
   int m_riskScore;
   int m_momentumScore;

   // محاسبه امتیازات بخش‌ها
   int CalculateSMCScore(SMCData &smc);
   int CalculatePAScore(PAData &pa);
   int CalculateTimeScore();
   int CalculateRiskScore();
   int CalculateMomentumScore();

   // بررسی فیلترها
   bool CheckFilters(string &failedFilter);

public:
   CDecisionEngine(const string symbol, const ENUM_TIMEFRAME tf);
   ~CDecisionEngine();

   // تحلیل کامل
   bool Analyze(TradeSignal &signal);

   // تحلیل‌های تکی
   bool AnalyzeSMC(SMCData &smc);
   bool AnalyzePriceAction(PAData &pa);

   // دریافت امتیاز کل
   int GetTotalScore();

   // بررسی مجاز بودن ورود
   bool IsEntryAllowed(string &reason);
};

//+
// سازنده
//+
CDecisionEngine::CDecisionEngine(const string symbol, const ENUM_TIMEFRAME tf) {
   m_symbol = symbol;
   m_timeframe = tf;

   m_smcScore = 0;
   m_paScore = 0;
   m_timeScore = 0;
   m_riskScore = 0;
   m_momentumScore = 0;

   // ایجاد تحلیل‌گرها
   m_structureAnalyzer = new CStructureAnalyzer(symbol, tf, SwingLookback);
   m_blockAnalyzer = new CBlockAnalyzer(symbol, tf, OBThreshold);
   m_fvgAnalyzer = new CFVGAnalyzer(symbol, tf, FVGMinSize);
   m_candleAnalyzer = new CCandleAnalyzer(symbol, tf);
   m_priceAnalyzer = new CPriceStructureAnalyzer(symbol, tf);
}

//+
// مخرب
//+
CDecisionEngine::~CDecisionEngine() {
   if(m_structureAnalyzer) delete m_structureAnalyzer;
   if(m_blockAnalyzer) delete m_blockAnalyzer;
   if(m_fvgAnalyzer) delete m_fvgAnalyzer;
   if(m_candleAnalyzer) delete m_candleAnalyzer;
   if(m_priceAnalyzer) delete m_priceAnalyzer;
}

//+
// محاسبه امتیاز SMC
//+
int CDecisionEngine::CalculateSMCScore(SMCData &smc) {
   int score = 40;  // امتیاز پایه

   // BOS (20 امتیاز)
   if(smc.hasBOS) {
      score += 20;
      if(RequireBOS) score += 5;  // پاداشنی در صورت نیاز
   }

   // CHOCH (15 امتیاز)
   if(smc.hasCHOCH) {
      score += 15;
      if(RequireCHOCH) score += 5;
   }

   // MSS (10 امتیاز)
   if(smc.hasMSS) {
      score += 10;
   }

   // Order Block (10 امتیاز)
   if(smc.hasOrderBlock) {
      score += 10;
   }

   // FVG (5 امتیاز)
   if(smc.hasFVG) {
      score += 5;
   }

   // روند (5 امتیاز)
   if(smc.trendDirection == "bullish" || smc.trendDirection == "bearish") {
      score += 5;
   }

   // محدود کردن به 100
   return MathMin(score, 100);
}

//+
// محاسبه امتیاز Price Action
//+
int CDecisionEngine::CalculatePAScore(PAData &pa) {
   int score = 30;  // امتیاز پایه

   // Engulfing (20 امتیاز)
   if(pa.hasEngulfing) {
      score += 20;
      if(RequireEngulfing) score += 5;
   }

   // Pin Bar (15 امتیاز)
   if(pa.hasPinBar) {
      score += 15;
      if(RequirePinBar) score += 5;
   }

   // Inside Bar (10 امتیاز)
   if(pa.hasInsideBar) {
      score += 10;
      if(RequireInsideBar) score += 5;
   }

   // Fakey (15 امتیاز)
   if(pa.hasFakey) {
      score += 15;
   }

   // جهت الگو (5 امتیاز)
   if(pa.patternBias != "") {
      score += 5;
   }

   return MathMin(score, 100);
}

//+
// محاسبه امتیاز زمانی
//+
int CDecisionEngine::CalculateTimeScore() {
   if(!UseTimeFilter) return 100;

   string kz = GetActiveKillZone();

   if(kz == "لندن" && UseLondonKZ) return 100;
   if(kz == "نیویورک" && UseNYKZ) return 100;
   if(kz == "توکیو" && UseTokyoKZ) return 85;

   return 40;  // خارج از Kill Zone
}

//+
// محاسبه امتیاز ریسک
//+
int CDecisionEngine::CalculateRiskScore() {
   int score = 100;

   // کسر به ازای هر معامله باز
   int openTrades = CountOpenTrades(m_symbol);
   score -= openTrades * 15;

   // کسر به ازای معاملات امروز
   int todayTrades = CountTodayTrades();
   score -= todayTrades * 10;

   // بررسی اسپرد
   int spread = (int)SymbolInfoInteger(m_symbol, SYMBOL_SPREAD);
   if(spread > MaxSpread) {
      score -= 30;
   } else if(spread > MaxSpread * 0.7) {
      score -= 15;
   }

   return MathMax(score, 0);
}

//+
// محاسبه امتیاز مومنتوم
//+
int CDecisionEngine::CalculateMomentumScore() {
   double momentum = m_priceAnalyzer.CalculateMomentum();

   // مومنتوم قوی (مثبت یا منفی)
   if(MathAbs(momentum) > 100) return 100;
   if(MathAbs(momentum) > 70) return 85;
   if(MathAbs(momentum) > 50) return 70;
   if(MathAbs(momentum) > 30) return 55;

   return 40;
}

//+
// بررسی فیلترها
//+
bool CDecisionEngine::CheckFilters(string &failedFilter) {
   // فیلتر زمان
   if(UseTimeFilter && !IsTradingTime()) {
      failedFilter = "خارج از Kill Zone";
      return false;
   }

   // فیلتر اسپرد
   int spread = (int)SymbolInfoInteger(m_symbol, SYMBOL_SPREAD);
   if(spread > MaxSpread) {
      failedFilter = "اسپرد بالا";
      return false;
   }

   // فیلتر تعداد معاملات
   if(CountOpenTrades() >= MaxOpenTrades) {
      failedFilter = "حداکثر معاملات همزمان";
      return false;
   }

   if(CountTodayTrades() >= MaxDailyTrades) {
      failedFilter = "حداکثر معاملات روزانه";
      return false;
   }

   return true;
}

//+
// تحلیل SMC
//+
bool CDecisionEngine::AnalyzeSMC(SMCData &smc) {
   if(!EnableSMC) {
      smc.smcScore = 50;
      return true;
   }

   // به‌روزرسانی داده‌ها
   if(!m_structureAnalyzer.Update()) return false;

   // BOS
   int bosBar;
   smc.hasBOS = m_structureAnalyzer.CheckBOS(bosBar);

   // CHOCH
   int chochBar;
   smc.hasCHOCH = m_structureAnalyzer.CheckCHOCH(chochBar);

   // MSS
   int mssBar;
   smc.hasMSS = m_structureAnalyzer.CheckMSS(mssBar);

   // روند
   smc.trendDirection = m_structureAnalyzer.GetCurrentTrend();

   // Order Block
   if(m_structureAnalyzer.GetCurrentTrend() == "bullish") {
      smc.hasOrderBlock = m_blockAnalyzer.FindBullishOB(smc.obHigh, smc.obLow, bosBar);
   } else {
      smc.hasOrderBlock = m_blockAnalyzer.FindBearishOB(smc.obHigh, smc.obLow, bosBar);
   }
   smc.obType = smc.hasOrderBlock ? (smc.trendDirection == "bullish" ? "bullish" : "bearish") : "none";

   // FVG
   if(smc.trendDirection == "bullish") {
      smc.hasFVG = m_fvgAnalyzer.FindBullishFVG(smc.fvgHigh, smc.fvgLow, bosBar);
   } else {
      smc.hasFVG = m_fvgAnalyzer.FindBearishFVG(smc.fvgHigh, smc.fvgLow, bosBar);
   }

   // محاسبه امتیاز
   smc.smcScore = CalculateSMCScore(smc);

   m_smcScore = smc.smcScore;

   return true;
}

//+
// تحلیل Price Action
//+
bool CDecisionEngine::AnalyzePriceAction(PAData &pa) {
   if(!EnablePA) {
      pa.paScore = 50;
      return true;
   }

   string bias;

   // Engulfing
   int engBar;
   pa.hasEngulfing = m_candleAnalyzer.DetectEngulfing(engBar, bias);

   // Pin Bar
   int pinBar;
   pa.hasPinBar = m_candleAnalyzer.DetectPinBar(pinBar, bias);

   // Inside Bar
   int insideBar;
   pa.hasInsideBar = m_candleAnalyzer.DetectInsideBar(insideBar);

   // Fakey
   int fakeyBar;
   pa.hasFakey = m_candleAnalyzer.DetectFakey(fakeyBar, bias);

   // تنظیم جهت الگو
   if(pa.hasEngulfing || pa.hasFakey) {
      pa.patternBias = bias;
   } else if(pa.hasPinBar) {
      pa.patternBias = bias;
   }

   // محاسبه امتیاز
   pa.paScore = CalculatePAScore(pa);

   m_paScore = pa.paScore;

   return true;
}

//+
// دریافت امتیاز کل
//+
int CDecisionEngine::GetTotalScore() {
   // وزن‌دهی
   double weightedScore = 0;

   weightedScore += m_smcScore * 0.35;      // 35% SMC
   weightedScore += m_paScore * 0.30;       // 30% Price Action
   weightedScore += m_timeScore * 0.15;     // 15% زمان
   weightedScore += m_riskScore * 0.10;     // 10% ریسک
   weightedScore += m_momentumScore * 0.10; // 10% مومنتوم

   return (int)MathRound(weightedScore);
}

//+
// بررسی مجاز بودن ورود
//+
bool CDecisionEngine::IsEntryAllowed(string &reason) {
   string failedFilter;

   // بررسی فیلترها
   if(!CheckFilters(failedFilter)) {
      reason = "فیلتر: " + failedFilter;
      return false;
   }

   // بررسی امتیاز
   int total = GetTotalScore();
   if(total < MinEntryScore) {
      reason = StringFormat("امتیاز کم: %d < %d", total, MinEntryScore);
      return false;
   }

   // بررسی الزامات SMC
   if(EnableSMC && RequireBOS && m_smcScore < 60) {
      reason = "نیاز به BOS";
      return false;
   }

   // بررسی الزامات PA
   if(EnablePA && RequireEngulfing && m_paScore < 50) {
      reason = "نیاز به Engulfing";
      return false;
   }

   reason = "سیگنال معتبر";
   return true;
}

//+
// تحلیل کامل
//+
bool CDecisionEngine::Analyze(TradeSignal &signal) {
   // تحلیل SMC
   SMCData smc;
   if(!AnalyzeSMC(smc)) {
      LogMessage("تحلیل SMC ناموفق", "ERROR");
      return false;
   }

   // تحلیل Price Action
   PAData pa;
   if(!AnalyzePriceAction(pa)) {
      LogMessage("تحلیل Price Action ناموفق", "ERROR");
      return false;
   }

   // محاسبه امتیازات کمکی
   m_timeScore = CalculateTimeScore();
   m_riskScore = CalculateRiskScore();
   m_momentumScore = CalculateMomentumScore();

   // تنظیم اطلاعات سیگنال
   signal.symbol = m_symbol;
   signal.totalScore = GetTotalScore();
   signal.entryAllowed = IsEntryAllowed(signal.reason);

   // تعیین جهت
   if(smc.trendDirection == "bullish" && pa.patternBias == "bullish") {
      signal.direction = "buy";
   } else if(smc.trendDirection == "bearish" && pa.patternBias == "bearish") {
      signal.direction = "sell";
   } else if(smc.trendDirection == "bullish") {
      signal.direction = "buy";
   } else if(smc.trendDirection == "bearish") {
      signal.direction = "sell";
   } else {
      signal.direction = "neutral";
   }

   // محاسبه سطوح
   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

   if(signal.direction == "buy") {
      signal.entryPrice = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      if(smc.hasOrderBlock) {
         signal.stopLoss = smc.obLow - (50 * point);
      } else {
         signal.stopLoss = m_structureAnalyzer.GetLastSwingLow() - (10 * point);
      }
      signal.takeProfit = CalculateTPByRR(signal.entryPrice, signal.stopLoss, ORDER_TYPE_BUY, 2.0);
   } else if(signal.direction == "sell") {
      signal.entryPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      if(smc.hasOrderBlock) {
         signal.stopLoss = smc.obHigh + (50 * point);
      } else {
         signal.stopLoss = m_structureAnalyzer.GetLastSwingHigh() + (10 * point);
      }
      signal.takeProfit = CalculateTPByRR(signal.entryPrice, signal.stopLoss, ORDER_TYPE_SELL, 2.0);
   }

   // زمان اعتبار
   signal.validUntil = TimeCurrent() + 3600;  // 1 ساعت

   return true;
}
//+------------------------------------------------------------------+
