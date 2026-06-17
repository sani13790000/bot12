//+------------------------------------------------------------------+
//|                                          DecisionEngine.mqh       |
//|                         سیستم معامله‌گری حرفه‌ای MT5               |
//|                                                                    |
//| توضیح فارسی:                                                       |
//| موتور تصمیم‌گیری ۶ مرحله‌ای کامل برای ورود به معامله              |
//| ورودی: SMC + Price Action + Liquidity + MTF + Sessions + Risk     |
//| خروجی: No Trade / Buy / Sell با امتیاز کیفیت                     |
//| تصمیم چندمرحله‌ای: هر مرحله می‌تواند فرآیند را متوقف کند         |
//| سیستم امتیازدهی وزن‌دار: SMC 35% + MTF 25% + PA 20% + Risk 10%  |
//+------------------------------------------------------------------+
#pragma once
#include "Config.mqh"
#include "Helpers.mqh"
#include "SMCAnalyzer.mqh"
#include "PAAnalyzer.mqh"
#include "RiskManager.mqh"

//--- ساختار سیگنال نهایی
struct TradeSignal {
   ENUM_SIGNAL_DIRECTION direction;    // Buy / Sell / None
   double               entryPrice;   // قیمت ورود
   double               stopLoss;     // حد ضرر
   double               takeProfit;   // حد سود
   double               lotSize;      // حجم معامله
   double               qualityScore; // امتیاز کیفیت (0-100)
   double               smcScore;     // امتیاز SMC
   double               paScore;      // امتیاز PA
   double               mtfScore;     // امتیاز MTF
   double               riskScore;    // امتیاز ریسک
   double               sessionScore; // امتیاز سشن
   string               reason;       // دلیل ورود
   string               rejectionReason; // دلیل رد (اگر No Trade)
   bool                 isValid;      // معتبر است؟
   datetime             signalTime;   // زمان سیگنال
};

//--- وضعیت هر مرحله تصمیم
struct DecisionStageResult {
   string stageName;   // نام مرحله
   bool   passed;      // قبول شد؟
   double score;       // امتیاز
   string reason;      // دلیل
};

//+------------------------------------------------------------------+
//| موتور تصمیم‌گیری ۶ مرحله‌ای                                       |
//+------------------------------------------------------------------+
class CDecisionEngine {
private:
   string          m_symbol;
   CConfig*        m_config;
   CRiskManager*   m_risk;

   // تحلیلگرهای چند تایم‌فریمی
   CSMCAnalyzer*   m_smcHTF;   // Higher Time Frame
   CSMCAnalyzer*   m_smcMTF;   // Medium Time Frame
   CSMCAnalyzer*   m_smcLTF;   // Lower Time Frame (Entry)
   CPAAnalyzer*    m_paLTF;    // Price Action در LTF
   CPAAnalyzer*    m_paMTF;    // Price Action در MTF
   bool            m_enabled;

   // نتایج مراحل
   DecisionStageResult m_stages[6];

public:
   //--- سازنده
   CDecisionEngine(string symbol, CConfig* config, CRiskManager* risk) {
      m_symbol  = symbol;
      m_config  = config;
      m_risk    = risk;
      m_enabled = true;

      // تایم‌فریم‌های HTF/MTF/LTF
      ENUM_TIMEFRAMES htf = config.GetHTF();
      ENUM_TIMEFRAMES mtf = config.GetMTF();
      ENUM_TIMEFRAMES ltf = config.GetLTF();

      m_smcHTF = new CSMCAnalyzer(symbol, htf);
      m_smcMTF = new CSMCAnalyzer(symbol, mtf);
      m_smcLTF = new CSMCAnalyzer(symbol, ltf);
      m_paLTF  = new CPAAnalyzer(symbol, ltf);
      m_paMTF  = new CPAAnalyzer(symbol, mtf);
   }

   //--- مخرب
   ~CDecisionEngine() {
      if(m_smcHTF != NULL) { delete m_smcHTF; m_smcHTF = NULL; }
      if(m_smcMTF != NULL) { delete m_smcMTF; m_smcMTF = NULL; }
      if(m_smcLTF != NULL) { delete m_smcLTF; m_smcLTF = NULL; }
      if(m_paLTF  != NULL) { delete m_paLTF;  m_paLTF  = NULL; }
      if(m_paMTF  != NULL) { delete m_paMTF;  m_paMTF  = NULL; }
   }

   //--- تحلیل کامل و بازگرداندن سیگنال
   TradeSignal Analyze() {
      TradeSignal signal;
      ZeroMemory(signal);
      signal.isValid    = false;
      signal.direction  = SIGNAL_NONE;
      signal.signalTime = TimeCurrent();

      if(!m_enabled) {
         signal.rejectionReason = "سیستم غیرفعال است";
         return signal;
      }

      // ===== مرحله ۱: بررسی پیش‌شرط‌های اولیه =====
      if(!_Stage1_Prerequisites(signal)) return signal;

      // ===== مرحله ۲: تحلیل HTF (روند کلان) =====
      SMCAnalysisResult htfResult;
      if(!_Stage2_HTFAnalysis(signal, htfResult)) return signal;

      // ===== مرحله ۳: تحلیل MTF (ساختار میانی) =====
      SMCAnalysisResult mtfResult;
      if(!_Stage3_MTFAnalysis(signal, htfResult, mtfResult)) return signal;

      // ===== مرحله ۴: تحلیل LTF (نقطه ورود) =====
      SMCAnalysisResult ltfResult;
      PAAnalysisResult  paResult;
      if(!_Stage4_LTFEntryAnalysis(signal, ltfResult, paResult)) return signal;

      // ===== مرحله ۵: امتیازدهی نهایی =====
      if(!_Stage5_FinalScoring(signal, htfResult, mtfResult, ltfResult, paResult)) return signal;

      // ===== مرحله ۶: محاسبه ورود/خروج =====
      if(!_Stage6_CalculateEntry(signal, ltfResult)) return signal;

      signal.isValid = true;
      _LogSignal(signal);
      return signal;
   }

   void Enable()    { m_enabled = true;  }
   void Disable()   { m_enabled = false; }
   bool IsEnabled() { return m_enabled;  }
   DecisionStageResult* GetStages() { return m_stages; }

private:
   //--- مرحله ۱: پیش‌شرط‌های اولیه
   bool _Stage1_Prerequisites(TradeSignal &signal) {
      m_stages[0].stageName = "پیش‌شرط‌های اولیه";
      m_stages[0].score     = 0;

      // بررسی اتصال و داده‌ها
      if(!TerminalInfoInteger(TERMINAL_CONNECTED)) {
         signal.rejectionReason = "مرحله ۱: اتصال اینترنت نیست";
         m_stages[0].passed = false; m_stages[0].reason = signal.rejectionReason;
         return false;
      }

      // بررسی اسپرد
      double spread = SymbolInfoInteger(m_symbol, SYMBOL_SPREAD) * SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      double maxSpread = m_config.GetMaxSpreadPoints() * SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      if(spread > maxSpread) {
         signal.rejectionReason = StringFormat("مرحله ۱: اسپرد %.0f بیشتر از حداکثر %.0f است",
            spread / SymbolInfoDouble(m_symbol, SYMBOL_POINT),
            m_config.GetMaxSpreadPoints());
         m_stages[0].passed = false; m_stages[0].reason = signal.rejectionReason;
         return false;
      }

      // بررسی حداکثر پوزیشن‌های باز
      if(m_risk->IsMaxPositionsReached(m_symbol)) {
         signal.rejectionReason = "مرحله ۱: حداکثر پوزیشن‌های مجاز پر شده";
         m_stages[0].passed = false; m_stages[0].reason = signal.rejectionReason;
         return false;
      }

      // بررسی محدودیت ضرر روزانه
      if(m_risk->IsDailyLossLimitReached()) {
         signal.rejectionReason = "مرحله ۱: محدودیت ضرر روزانه";
         m_stages[0].passed = false; m_stages[0].reason = signal.rejectionReason;
         return false;
      }

      // بررسی توقف اضطراری
      if(m_risk->IsEmergencyStop()) {
         signal.rejectionReason = "مرحله ۱: توقف اضطراری فعال است";
         m_stages[0].passed = false; m_stages[0].reason = signal.rejectionReason;
         return false;
      }

      m_stages[0].passed = true;
      m_stages[0].score  = 100;
      m_stages[0].reason = "همه پیش‌شرط‌ها تایید شدند";
      return true;
   }

   //--- مرحله ۲: تحلیل HTF
   bool _Stage2_HTFAnalysis(TradeSignal &signal, SMCAnalysisResult &htfResult) {
      m_stages[1].stageName = "تحلیل تایم‌فریم بالا (HTF)";
      m_stages[1].score     = 0;

      htfResult = m_smcHTF->Analyze();

      // در HTF باید روند مشخص باشد
      if(htfResult.structure.isRanging && htfResult.totalScore < 40) {
         signal.rejectionReason = "مرحله ۲: HTF رنج است و روند مشخصی ندارد";
         m_stages[1].passed = false; m_stages[1].reason = signal.rejectionReason;
         return false;
      }

      m_stages[1].passed = true;
      m_stages[1].score  = htfResult.totalScore;
      m_stages[1].reason = StringFormat("HTF روند: %s امتیاز: %.0f",
         htfResult.structure.isBullish ? "صعودی" : "نزولی",
         htfResult.totalScore);
      return true;
   }

   //--- مرحله ۳: تحلیل MTF
   bool _Stage3_MTFAnalysis(TradeSignal &signal, const SMCAnalysisResult &htfResult, SMCAnalysisResult &mtfResult) {
      m_stages[2].stageName = "تحلیل تایم‌فریم میانی (MTF)";
      m_stages[2].score     = 0;

      mtfResult = m_smcMTF->Analyze();

      // همسویی HTF و MTF
      bool aligned = (htfResult.direction == mtfResult.direction)
                  || (htfResult.direction == SIGNAL_NONE);

      if(!aligned && mtfResult.totalScore < 50) {
         signal.rejectionReason = "مرحله ۳: MTF با HTF همسو نیست";
         m_stages[2].passed = false; m_stages[2].reason = signal.rejectionReason;
         return false;
      }

      double alignmentBonus = aligned ? 20 : -10;
      m_stages[2].passed = true;
      m_stages[2].score  = MathMin(mtfResult.totalScore + alignmentBonus, 100);
      m_stages[2].reason = StringFormat("MTF روند: %s همسویی: %s امتیاز: %.0f",
         mtfResult.structure.isBullish ? "صعودی" : "نزولی",
         aligned ? "بله" : "خیر",
         m_stages[2].score);
      return true;
   }

   //--- مرحله ۴: تحلیل LTF (نقطه ورود)
   bool _Stage4_LTFEntryAnalysis(TradeSignal &signal, SMCAnalysisResult &ltfResult, PAAnalysisResult &paResult) {
      m_stages[3].stageName = "تحلیل نقطه ورود (LTF)";
      m_stages[3].score     = 0;

      ltfResult = m_smcLTF->Analyze();
      paResult  = m_paLTF->Analyze();

      // باید حداقل یک الگوی PA یا OB در LTF وجود داشته باشد
      bool hasTrigger = (ltfResult.bestBullishOB.isValid || ltfResult.bestBearishOB.isValid)
                     || (!ltfResult.bestBullishFVG.isFilled || !ltfResult.bestBearishFVG.isFilled)
                     || (paResult.patternCount > 0);

      if(!hasTrigger) {
         signal.rejectionReason = "مرحله ۴: هیچ تریگر ورودی در LTF وجود ندارد";
         m_stages[3].passed = false; m_stages[3].reason = signal.rejectionReason;
         return false;
      }

      // BOS یا CHOCH در LTF اجباری است (اگر در config فعال باشد)
      if(m_config.IsRequireBOS() && !ltfResult.structure.hasBOS && !ltfResult.structure.hasCHOCH) {
         signal.rejectionReason = "مرحله ۴: BOS یا CHOCH در LTF وجود ندارد";
         m_stages[3].passed = false; m_stages[3].reason = signal.rejectionReason;
         return false;
      }

      double combinedScore = (ltfResult.totalScore * 0.6) + (paResult.totalScore * 0.4);
      m_stages[3].passed = true;
      m_stages[3].score  = combinedScore;
      m_stages[3].reason = StringFormat("LTF SMC: %.0f PA: %.0f الگو: %s",
         ltfResult.totalScore, paResult.totalScore, paResult.topPattern);
      return true;
   }

   //--- مرحله ۵: امتیازدهی نهایی
   bool _Stage5_FinalScoring(TradeSignal &signal, 
                              const SMCAnalysisResult &htf,
                              const SMCAnalysisResult &mtf,
                              const SMCAnalysisResult &ltf,
                              const PAAnalysisResult  &pa) {
      m_stages[4].stageName = "امتیازدهی نهایی";

      // وزن‌دهی حرفه‌ای
      double smcScore     = (htf.totalScore * 0.4 + mtf.totalScore * 0.35 + ltf.totalScore * 0.25);
      double mtfAlignment = _CalculateMTFAlignment(htf, mtf, ltf);
      double paScore      = pa.totalScore;
      double sessionScore = _CalculateSessionScore();
      double riskScore    = _CalculateRiskScore();

      // ترکیب وزن‌دار
      double totalScore = smcScore     * 0.35
                        + mtfAlignment * 0.25
                        + paScore      * 0.20
                        + riskScore    * 0.10
                        + sessionScore * 0.10;

      signal.smcScore     = smcScore;
      signal.mtfScore     = mtfAlignment;
      signal.paScore      = paScore;
      signal.riskScore    = riskScore;
      signal.sessionScore = sessionScore;
      signal.qualityScore = totalScore;

      // حداقل امتیاز برای ورود
      double minScore = m_config.GetMinEntryScore();
      if(totalScore < minScore) {
         signal.rejectionReason = StringFormat(
            "مرحله ۵: امتیاز %.1f کمتر از حداقل %.1f است (SMC:%.0f MTF:%.0f PA:%.0f)",
            totalScore, minScore, smcScore, mtfAlignment, paScore);
         m_stages[4].passed = false; m_stages[4].reason = signal.rejectionReason;
         return false;
      }

      // تعیین جهت نهایی
      ENUM_SIGNAL_DIRECTION dir = _DetermineDirection(htf, mtf, ltf, pa);
      if(dir == SIGNAL_NONE) {
         signal.rejectionReason = "مرحله ۵: جهت معامله مشخص نیست (سیگنال متضاد)";
         m_stages[4].passed = false; m_stages[4].reason = signal.rejectionReason;
         return false;
      }

      signal.direction = dir;
      m_stages[4].passed = true;
      m_stages[4].score  = totalScore;
      m_stages[4].reason = StringFormat(
         "امتیاز %.1f/%0.f جهت:%s SMC:%.0f MTF:%.0f PA:%.0f Risk:%.0f Session:%.0f",
         totalScore, minScore,
         dir == SIGNAL_BUY ? "BUY" : "SELL",
         smcScore, mtfAlignment, paScore, riskScore, sessionScore);
      return true;
   }

   //--- مرحله ۶: محاسبه ورود
   bool _Stage6_CalculateEntry(TradeSignal &signal, const SMCAnalysisResult &ltf) {
      m_stages[5].stageName = "محاسبه نقطه ورود";

      double point    = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      double ask      = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      double bid      = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      double spread   = ask - bid;

      if(signal.direction == SIGNAL_BUY) {
         signal.entryPrice = ask;
         // SL: زیر OB یا آخرین کف
         double obLow = ltf.bestBullishOB.isValid ? ltf.bestBullishOB.low : ltf.structure.lastSwingLow;
         signal.stopLoss = obLow - spread - 5 * point;
      } else {
         signal.entryPrice = bid;
         double obHigh = ltf.bestBearishOB.isValid ? ltf.bestBearishOB.high : ltf.structure.lastSwingHigh;
         signal.stopLoss = obHigh + spread + 5 * point;
      }

      double slDistance = MathAbs(signal.entryPrice - signal.stopLoss);
      if(slDistance < 10 * point) {
         signal.rejectionReason = "مرحله ۶: فاصله SL خیلی کم است";
         m_stages[5].passed = false; m_stages[5].reason = signal.rejectionReason;
         return false;
      }

      // TP: نسبت RR از Config
      double rrRatio = m_config.GetRiskRewardRatio();
      if(signal.direction == SIGNAL_BUY)
         signal.takeProfit = signal.entryPrice + slDistance * rrRatio;
      else
         signal.takeProfit = signal.entryPrice - slDistance * rrRatio;

      // محاسبه لات
      RiskCheckResult riskCheck = m_risk->CheckRiskBeforeTrade(
         m_symbol, signal.direction == SIGNAL_BUY ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,
         signal.entryPrice, signal.stopLoss);

      if(!riskCheck.canTrade) {
         signal.rejectionReason = "مرحله ۶: ریسک اجازه ورود نمی‌دهد - " + riskCheck.reason;
         m_stages[5].passed = false; m_stages[5].reason = signal.rejectionReason;
         return false;
      }

      signal.lotSize = riskCheck.recommendedLot;
      signal.reason  = StringFormat(
         "Entry:%.5f SL:%.5f TP:%.5f Lot:%.2f RR:%.1f Quality:%.1f",
         signal.entryPrice, signal.stopLoss, signal.takeProfit,
         signal.lotSize, rrRatio, signal.qualityScore);

      m_stages[5].passed = true;
      m_stages[5].score  = 100;
      m_stages[5].reason = signal.reason;
      return true;
   }

   //--- محاسبه همسویی MTF
   double _CalculateMTFAlignment(const SMCAnalysisResult &htf,
                                  const SMCAnalysisResult &mtf,
                                  const SMCAnalysisResult &ltf) {
      double score = 0;
      int alignedCount = 0;
      ENUM_SIGNAL_DIRECTION baseDir = htf.direction;
      if(baseDir == SIGNAL_NONE) baseDir = mtf.direction;

      if(htf.direction == baseDir && baseDir != SIGNAL_NONE) { score += 40; alignedCount++; }
      if(mtf.direction == baseDir && baseDir != SIGNAL_NONE) { score += 35; alignedCount++; }
      if(ltf.direction == baseDir && baseDir != SIGNAL_NONE) { score += 25; alignedCount++; }

      if(alignedCount == 3) score = MathMin(score + 10, 100); // بونوس هم‌راستایی کامل
      return score;
   }

   //--- محاسبه امتیاز سشن
   double _CalculateSessionScore() {
      MqlDateTime dt;
      TimeToStruct(TimeGMT(), dt);
      int hour = dt.hour;

      // London: 7-16 UTC، New York: 13-22 UTC، Kill Zones پریمیوم
      if((hour >= 7 && hour < 9) || (hour >= 13 && hour < 15)) return 100; // Kill Zones
      if(hour >= 7  && hour < 16) return 70;  // London Session
      if(hour >= 13 && hour < 22) return 70;  // New York Session
      if(hour >= 22 || hour < 7)  return 20;  // Asian Session
      return 50;
   }

   //--- محاسبه امتیاز ریسک
   double _CalculateRiskScore() {
      double score = 100;
      double drawdown = m_risk->GetCurrentDrawdown();
      if(drawdown > 10) score -= 40;
      else if(drawdown > 5) score -= 20;
      else if(drawdown > 2) score -= 10;

      double dailyPnL = m_risk->GetDailyPnL();
      double balance  = m_risk->GetAccountBalance();
      if(balance > 0) {
         double pnlPct = dailyPnL / balance * 100;
         if(pnlPct < -3)  score -= 30;
         else if(pnlPct > 2) score += 10;
      }
      return MathMax(score, 0);
   }

   //--- تعیین جهت نهایی
   ENUM_SIGNAL_DIRECTION _DetermineDirection(
      const SMCAnalysisResult &htf, const SMCAnalysisResult &mtf,
      const SMCAnalysisResult &ltf, const PAAnalysisResult  &pa) {

      int bullVotes = 0, bearVotes = 0;
      double bullWeight = 0, bearWeight = 0;

      auto _Vote = [&](ENUM_SIGNAL_DIRECTION dir, double weight) {
         if(dir == SIGNAL_BUY)  { bullVotes++; bullWeight += weight; }
         if(dir == SIGNAL_SELL) { bearVotes++; bearWeight += weight; }
      };

      _Vote(htf.direction, 3.0);
      _Vote(mtf.direction, 2.5);
      _Vote(ltf.direction, 2.0);
      _Vote(pa.direction,  1.5);

      if(bullWeight > bearWeight * 1.3) return SIGNAL_BUY;
      if(bearWeight > bullWeight * 1.3) return SIGNAL_SELL;
      return SIGNAL_NONE;
   }

   //--- لاگ سیگنال
   void _LogSignal(const TradeSignal &signal) {
      LogInfo(StringFormat(
         "===== سیگنال جدید =====\n"
         "جهت: %s | کیفیت: %.1f%%\n"
         "ورود: %.5f | SL: %.5f | TP: %.5f | Lot: %.2f\n"
         "SMC: %.0f | MTF: %.0f | PA: %.0f | Risk: %.0f | Session: %.0f\n"
         "دلیل: %s",
         signal.direction == SIGNAL_BUY ? "BUY" : "SELL",
         signal.qualityScore,
         signal.entryPrice, signal.stopLoss, signal.takeProfit, signal.lotSize,
         signal.smcScore, signal.mtfScore, signal.paScore, signal.riskScore, signal.sessionScore,
         signal.reason
      ));
   }
};
