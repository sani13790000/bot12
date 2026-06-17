//+------------------------------------------------------------------+
//|                                              PAAnalyzer.mqh       |
//|                         سیستم معامله‌گری حرفه‌ای MT5               |
//|                                                                    |
//| توضیح فارسی:                                                       |
//| موتور کامل Price Action شامل تشخیص تمام الگوهای شمعی و ساختاری  |
//| الگوها: Pin Bar, Engulfing, Fakey, Inside Bar, Outside Bar,       |
//|          Doji, Morning Star, Evening Star, Three Soldiers,         |
//|          Three Crows, Breakout, Retest, Compression, Expansion     |
//| تمام الگوها امتیازدهی شده و به Decision Engine ارسال می‌شوند      |
//+------------------------------------------------------------------+
#pragma once
#include "Config.mqh"
#include "Helpers.mqh"

//--- ساختار داده شمع
struct CandleData {
   double open, high, low, close;
   double body;         // بدنه
   double upperWick;    // سایه بالا
   double lowerWick;    // سایه پایین
   double range;        // دامنه کامل
   double bodyRatio;    // نسبت بدنه به دامنه
   bool   isBullish;    // صعودی؟
};

//--- نتیجه تشخیص الگو
struct PatternResult {
   string name;         // نام الگو
   bool   detected;     // شناسایی شد؟
   bool   isBullish;    // صعودی یا نزولی؟
   double score;        // امتیاز (0-100)
   int    barIndex;     // شمع مربوطه
   string description;  // توضیح فارسی
};

//--- نتیجه کامل Price Action
struct PAAnalysisResult {
   PatternResult pinBar;
   PatternResult engulfing;
   PatternResult fakey;
   PatternResult insideBar;
   PatternResult outsideBar;
   PatternResult doji;
   PatternResult morningStar;
   PatternResult eveningStar;
   PatternResult threeSoldiers;
   PatternResult threeCrows;
   PatternResult breakout;
   PatternResult retest;
   PatternResult compression;
   PatternResult expansion;
   double        totalScore;        // امتیاز کل
   ENUM_SIGNAL_DIRECTION direction; // جهت پیشنهادی
   int           patternCount;      // تعداد الگوهای شناسایی شده
   string        topPattern;        // قوی‌ترین الگو
};

//+------------------------------------------------------------------+
//| کلاس تشخیص الگوهای شمعی                                         |
//+------------------------------------------------------------------+
class CCandleAnalyzer {
private:
   string          m_symbol;
   ENUM_TIMEFRAMES m_tf;
   double          m_high[];
   double          m_low[];
   double          m_open[];
   double          m_close[];
   int             m_bars;

   //--- دریافت داده یک شمع
   CandleData _GetCandle(int i) {
      CandleData c;
      c.open      = m_open[i];
      c.high      = m_high[i];
      c.low       = m_low[i];
      c.close     = m_close[i];
      c.range     = c.high - c.low;
      c.body      = MathAbs(c.close - c.open);
      c.upperWick = c.high - MathMax(c.open, c.close);
      c.lowerWick = MathMin(c.open, c.close) - c.low;
      c.bodyRatio = (c.range > 0) ? c.body / c.range : 0;
      c.isBullish = (c.close >= c.open);
      return c;
   }

public:
   CCandleAnalyzer(string symbol, ENUM_TIMEFRAMES tf) {
      m_symbol = symbol;
      m_tf     = tf;
      m_bars   = 0;
   }

   bool Update(int lookback = 50) {
      m_bars = MathMin(lookback + 5, Bars(m_symbol, m_tf));
      if(m_bars < 5) return false;
      if(CopyHigh(m_symbol, m_tf, 0, m_bars, m_high)   < m_bars) return false;
      if(CopyLow(m_symbol, m_tf, 0, m_bars, m_low)     < m_bars) return false;
      if(CopyOpen(m_symbol, m_tf, 0, m_bars, m_open)   < m_bars) return false;
      if(CopyClose(m_symbol, m_tf, 0, m_bars, m_close) < m_bars) return false;
      return true;
   }

   //--- Pin Bar: سایه بلند، بدنه کوچک
   PatternResult DetectPinBar(int i = 1) {
      PatternResult r;
      r.name = "Pin Bar";
      r.detected = false;
      r.barIndex = i;
      if(i >= m_bars) return r;

      CandleData c = _GetCandle(i);
      if(c.range == 0) return r;

      double wickThreshold = 0.6; // حداقل 60% سایه
      bool bullishPin = (c.lowerWick >= c.range * wickThreshold) && (c.body < c.range * 0.35);
      bool bearishPin = (c.upperWick >= c.range * wickThreshold) && (c.body < c.range * 0.35);

      if(bullishPin || bearishPin) {
         r.detected  = true;
         r.isBullish = bullishPin;
         // امتیازدهی بر اساس کیفیت سایه
         double wickRatio = bullishPin ? c.lowerWick / c.range : c.upperWick / c.range;
         r.score = 50 + (wickRatio - 0.6) / 0.4 * 50;
         r.description = bullishPin ? "پین بار صعودی - سایه پایین بلند" : "پین بار نزولی - سایه بالا بلند";
      }
      return r;
   }

   //--- Engulfing: بلع کامل شمع قبلی
   PatternResult DetectEngulfing(int i = 1) {
      PatternResult r;
      r.name = "Engulfing";
      r.detected = false;
      r.barIndex = i;
      if(i + 1 >= m_bars) return r;

      CandleData curr = _GetCandle(i);
      CandleData prev = _GetCandle(i + 1);
      if(prev.range == 0 || curr.range == 0) return r;

      bool bullEngulf = (!curr.isBullish ? false : true) && curr.isBullish && !prev.isBullish
                     && curr.close > prev.open && curr.open < prev.close;
      bool bearEngulf = !curr.isBullish && prev.isBullish
                     && curr.close < prev.open && curr.open > prev.close;

      if(bullEngulf || bearEngulf) {
         r.detected  = true;
         r.isBullish = bullEngulf;
         double engulfRatio = curr.body / (prev.body + 0.0001);
         r.score = MathMin(50 + engulfRatio * 25, 100);
         r.description = bullEngulf ? "انگالفینگ صعودی - بلع کامل شمع قبلی" : "انگالفینگ نزولی";
      }
      return r;
   }

   //--- Fakey: شکست جعلی Inside Bar
   PatternResult DetectFakey(int i = 1) {
      PatternResult r;
      r.name = "Fakey";
      r.detected = false;
      r.barIndex = i;
      if(i + 2 >= m_bars) return r;

      CandleData curr   = _GetCandle(i);
      CandleData inside = _GetCandle(i + 1);
      CandleData mother = _GetCandle(i + 2);

      // Inside Bar: شمع داخل بازه مادر
      bool isInsideBar = inside.high <= mother.high && inside.low >= mother.low;
      if(!isInsideBar) return r;

      // Fakey: شمع فعلی ابتدا شکسته و برگشته
      bool bullFakey = curr.low < inside.low && curr.close > inside.low && curr.close < mother.high;
      bool bearFakey = curr.high > inside.high && curr.close < inside.high && curr.close > mother.low;

      if(bullFakey || bearFakey) {
         r.detected  = true;
         r.isBullish = bullFakey;
         r.score     = 70;
         r.description = bullFakey ? "فیکی صعودی - شکست جعلی به پایین" : "فیکی نزولی - شکست جعلی به بالا";
      }
      return r;
   }

   //--- Inside Bar: شمع داخل بازه شمع قبلی
   PatternResult DetectInsideBar(int i = 1) {
      PatternResult r;
      r.name = "Inside Bar";
      r.detected = false;
      r.barIndex = i;
      if(i + 1 >= m_bars) return r;

      CandleData curr = _GetCandle(i);
      CandleData prev = _GetCandle(i + 1);

      if(curr.high <= prev.high && curr.low >= prev.low) {
         r.detected  = true;
         r.isBullish = prev.isBullish; // جهت مادر
         // Inside Bar کوچک‌تر = فشردگی بیشتر = امتیاز بیشتر
         double ratio = curr.range / (prev.range + 0.0001);
         r.score = MathMax(40, 80 - ratio * 40);
         r.description = "اینساید بار - فشردگی در بازه شمع قبلی";
      }
      return r;
   }

   //--- Outside Bar: بلع کامل بازه شمع قبلی
   PatternResult DetectOutsideBar(int i = 1) {
      PatternResult r;
      r.name = "Outside Bar";
      r.detected = false;
      r.barIndex = i;
      if(i + 1 >= m_bars) return r;

      CandleData curr = _GetCandle(i);
      CandleData prev = _GetCandle(i + 1);

      if(curr.high > prev.high && curr.low < prev.low) {
         r.detected  = true;
         r.isBullish = curr.isBullish;
         r.score     = 60;
         r.description = "اوتساید بار - گسترش فراتر از شمع قبلی";
      }
      return r;
   }

   //--- Doji: بدنه بسیار کوچک
   PatternResult DetectDoji(int i = 1) {
      PatternResult r;
      r.name = "Doji";
      r.detected = false;
      r.barIndex = i;
      if(i >= m_bars) return r;

      CandleData c = _GetCandle(i);
      if(c.range == 0) return r;

      if(c.bodyRatio < 0.1) {
         r.detected  = true;
         r.isBullish = c.isBullish;
         r.score     = 50;
         // Dragonfly Doji
         if(c.lowerWick > c.range * 0.6 && c.upperWick < c.range * 0.1) {
            r.isBullish = true; r.score = 70;
            r.description = "Dragonfly Doji - سایه پایین بلند";
         }
         // Gravestone Doji
         else if(c.upperWick > c.range * 0.6 && c.lowerWick < c.range * 0.1) {
            r.isBullish = false; r.score = 70;
            r.description = "Gravestone Doji - سایه بالا بلند";
         } else {
            r.description = "دوجی - بلاتکلیفی بازار";
         }
      }
      return r;
   }

   //--- Morning Star: برگشت صعودی ۳ شمعی
   PatternResult DetectMorningStar(int i = 1) {
      PatternResult r;
      r.name = "Morning Star";
      r.detected = false;
      r.barIndex = i;
      if(i + 2 >= m_bars) return r;

      CandleData c1 = _GetCandle(i + 2); // نزولی بزرگ
      CandleData c2 = _GetCandle(i + 1); // کوچک (ستاره)
      CandleData c3 = _GetCandle(i);     // صعودی بزرگ

      bool isValid = !c1.isBullish                          // اول نزولی
                  && c2.body < c1.body * 0.4               // دوم کوچک
                  && c3.isBullish                           // سوم صعودی
                  && c3.close > (c1.open + c1.close) / 2.0 // بسته‌شدن بالای میانه اول
                  && c3.body > c1.body * 0.5;              // بدنه سوم قوی

      if(isValid) {
         r.detected  = true;
         r.isBullish = true;
         r.score     = 80;
         r.description = "Morning Star - برگشت صعودی سه‌شمعی";
      }
      return r;
   }

   //--- Evening Star: برگشت نزولی ۳ شمعی
   PatternResult DetectEveningStar(int i = 1) {
      PatternResult r;
      r.name = "Evening Star";
      r.detected = false;
      r.barIndex = i;
      if(i + 2 >= m_bars) return r;

      CandleData c1 = _GetCandle(i + 2);
      CandleData c2 = _GetCandle(i + 1);
      CandleData c3 = _GetCandle(i);

      bool isValid = c1.isBullish
                  && c2.body < c1.body * 0.4
                  && !c3.isBullish
                  && c3.close < (c1.open + c1.close) / 2.0
                  && c3.body > c1.body * 0.5;

      if(isValid) {
         r.detected  = true;
         r.isBullish = false;
         r.score     = 80;
         r.description = "Evening Star - برگشت نزولی سه‌شمعی";
      }
      return r;
   }

   //--- Three White Soldiers: سه شمع صعودی پیاپی
   PatternResult DetectThreeSoldiers(int i = 1) {
      PatternResult r;
      r.name = "Three Soldiers";
      r.detected = false;
      r.barIndex = i;
      if(i + 2 >= m_bars) return r;

      CandleData c1 = _GetCandle(i + 2);
      CandleData c2 = _GetCandle(i + 1);
      CandleData c3 = _GetCandle(i);

      bool isValid = c1.isBullish && c2.isBullish && c3.isBullish
                  && c2.open > c1.open && c2.close > c1.close
                  && c3.open > c2.open && c3.close > c2.close
                  && c1.bodyRatio > 0.5 && c2.bodyRatio > 0.5 && c3.bodyRatio > 0.5
                  && c1.upperWick < c1.body * 0.3
                  && c2.upperWick < c2.body * 0.3
                  && c3.upperWick < c3.body * 0.3;

      if(isValid) {
         r.detected  = true;
         r.isBullish = true;
         r.score     = 85;
         r.description = "Three White Soldiers - سه سرباز سفید صعودی";
      }
      return r;
   }

   //--- Three Black Crows: سه شمع نزولی پیاپی
   PatternResult DetectThreeCrows(int i = 1) {
      PatternResult r;
      r.name = "Three Crows";
      r.detected = false;
      r.barIndex = i;
      if(i + 2 >= m_bars) return r;

      CandleData c1 = _GetCandle(i + 2);
      CandleData c2 = _GetCandle(i + 1);
      CandleData c3 = _GetCandle(i);

      bool isValid = !c1.isBullish && !c2.isBullish && !c3.isBullish
                  && c2.open < c1.open && c2.close < c1.close
                  && c3.open < c2.open && c3.close < c2.close
                  && c1.bodyRatio > 0.5 && c2.bodyRatio > 0.5 && c3.bodyRatio > 0.5
                  && c1.lowerWick < c1.body * 0.3
                  && c2.lowerWick < c2.body * 0.3
                  && c3.lowerWick < c3.body * 0.3;

      if(isValid) {
         r.detected  = true;
         r.isBullish = false;
         r.score     = 85;
         r.description = "Three Black Crows - سه کلاغ سیاه نزولی";
      }
      return r;
   }
};

//+------------------------------------------------------------------+
//| کلاس تحلیل ساختار قیمت                                          |
//+------------------------------------------------------------------+
class CPriceStructureAnalyzer {
private:
   string          m_symbol;
   ENUM_TIMEFRAMES m_tf;
   double          m_high[];
   double          m_low[];
   double          m_close[];
   double          m_open[];
   int             m_bars;
   int             m_atrHandle;
   double          m_atr[];

public:
   CPriceStructureAnalyzer(string symbol, ENUM_TIMEFRAMES tf) {
      m_symbol    = symbol;
      m_tf        = tf;
      m_bars      = 0;
      m_atrHandle = iATR(symbol, tf, 14);
   }

   ~CPriceStructureAnalyzer() {
      if(m_atrHandle != INVALID_HANDLE) IndicatorRelease(m_atrHandle);
   }

   bool Update(int lookback = 50) {
      m_bars = MathMin(lookback + 5, Bars(m_symbol, m_tf));
      if(m_bars < 10) return false;
      if(CopyHigh(m_symbol, m_tf, 0, m_bars, m_high)   < m_bars) return false;
      if(CopyLow(m_symbol, m_tf, 0, m_bars, m_low)     < m_bars) return false;
      if(CopyClose(m_symbol, m_tf, 0, m_bars, m_close) < m_bars) return false;
      if(CopyOpen(m_symbol, m_tf, 0, m_bars, m_open)   < m_bars) return false;
      if(m_atrHandle != INVALID_HANDLE)
         CopyBuffer(m_atrHandle, 0, 0, m_bars, m_atr);
      return true;
   }

   //--- Breakout: شکست یک سطح مهم با بدنه قوی
   PatternResult DetectBreakout() {
      PatternResult r;
      r.name = "Breakout";
      r.detected = false;
      r.barIndex = 1;
      if(m_bars < 20) return r;

      // پیدا کردن بالاترین/پایین‌ترین در 20 شمع گذشته
      double highest = m_high[2], lowest = m_low[2];
      for(int i = 3; i <= 20 && i < m_bars; i++) {
         if(m_high[i] > highest) highest = m_high[i];
         if(m_low[i]  < lowest)  lowest  = m_low[i];
      }

      double currClose = m_close[1];
      double currBody  = MathAbs(m_close[1] - m_open[1]);
      double range     = m_high[1] - m_low[1];
      double bodyRatio = (range > 0) ? currBody / range : 0;

      bool bullBreak = currClose > highest && bodyRatio > 0.6;
      bool bearBreak = currClose < lowest  && bodyRatio > 0.6;

      if(bullBreak || bearBreak) {
         r.detected  = true;
         r.isBullish = bullBreak;
         r.score     = 60 + bodyRatio * 30;
         r.description = bullBreak ? "شکست صعودی سطح مقاومت" : "شکست نزولی سطح حمایت";
      }
      return r;
   }

   //--- Retest: برگشت قیمت برای تست سطح شکسته شده
   PatternResult DetectRetest() {
      PatternResult r;
      r.name = "Retest";
      r.detected = false;
      r.barIndex = 1;
      if(m_bars < 20) return r;

      double highest = m_high[10], lowest = m_low[10];
      for(int i = 5; i <= 20 && i < m_bars; i++) {
         if(m_high[i] > highest) highest = m_high[i];
         if(m_low[i]  < lowest)  lowest  = m_low[i];
      }

      double point    = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      double atrVal   = (ArraySize(m_atr) > 2) ? m_atr[2] : 0;
      double tolerance = MathMax(atrVal * 0.3, 10 * point);

      double currLow  = m_low[1];
      double currHigh = m_high[1];

      // Bullish Retest: قیمت پس از شکست بالا، به سطح مقاومت باز می‌گردد
      bool bullRetest = (m_close[5] > highest) && (MathAbs(currLow - highest) < tolerance);
      bool bearRetest = (m_close[5] < lowest)  && (MathAbs(currHigh - lowest) < tolerance);

      if(bullRetest || bearRetest) {
         r.detected  = true;
         r.isBullish = bullRetest;
         r.score     = 75;
         r.description = bullRetest ? "ریتست صعودی سطح شکسته شده" : "ریتست نزولی سطح شکسته شده";
      }
      return r;
   }

   //--- Compression: کاهش نوسانات (ATR کم می‌شود)
   PatternResult DetectCompression() {
      PatternResult r;
      r.name = "Compression";
      r.detected = false;
      r.barIndex = 1;
      if(m_bars < 20 || ArraySize(m_atr) < 20) return r;

      double recentATR = 0, pastATR = 0;
      int count = 0;
      for(int i = 1; i <= 5 && i < ArraySize(m_atr); i++) {
         recentATR += m_atr[i]; count++;
      }
      recentATR = (count > 0) ? recentATR / count : 0;

      count = 0;
      for(int i = 10; i <= 20 && i < ArraySize(m_atr); i++) {
         pastATR += m_atr[i]; count++;
      }
      pastATR = (count > 0) ? pastATR / count : 0;

      if(pastATR > 0 && recentATR < pastATR * 0.6) {
         r.detected  = true;
         r.isBullish = false; // خنثی، جهت نداره
         double compressionRatio = 1.0 - (recentATR / pastATR);
         r.score     = 50 + compressionRatio * 50;
         r.description = StringFormat("فشردگی قیمت - ATR کاهش %.0f%%", compressionRatio * 100);
      }
      return r;
   }

   //--- Expansion: افزایش نوسانات (ATR زیاد می‌شود)
   PatternResult DetectExpansion() {
      PatternResult r;
      r.name = "Expansion";
      r.detected = false;
      r.barIndex = 1;
      if(m_bars < 20 || ArraySize(m_atr) < 20) return r;

      double recentATR = 0, pastATR = 0;
      int count = 0;
      for(int i = 1; i <= 3 && i < ArraySize(m_atr); i++) {
         recentATR += m_atr[i]; count++;
      }
      recentATR = (count > 0) ? recentATR / count : 0;

      count = 0;
      for(int i = 10; i <= 20 && i < ArraySize(m_atr); i++) {
         pastATR += m_atr[i]; count++;
      }
      pastATR = (count > 0) ? pastATR / count : 0;

      if(pastATR > 0 && recentATR > pastATR * 1.5) {
         r.detected  = true;
         r.isBullish = m_close[1] > m_open[1]; // جهت بر اساس شمع فعلی
         double expansionRatio = (recentATR / pastATR) - 1.0;
         r.score     = MathMin(50 + expansionRatio * 30, 100);
         r.description = StringFormat("انبساط قیمت - ATR افزایش %.0f%%", expansionRatio * 100);
      }
      return r;
   }
};

//+------------------------------------------------------------------+
//| کلاس اصلی تحلیلگر Price Action                                   |
//+------------------------------------------------------------------+
class CPAAnalyzer {
private:
   string                   m_symbol;
   ENUM_TIMEFRAMES          m_tf;
   bool                     m_enabled;
   CCandleAnalyzer*         m_candles;
   CPriceStructureAnalyzer* m_structure;
   int                      m_lookback;

public:
   CPAAnalyzer(string symbol, ENUM_TIMEFRAMES tf, int lookback = 50) {
      m_symbol   = symbol;
      m_tf       = tf;
      m_enabled  = true;
      m_lookback = lookback;
      m_candles  = new CCandleAnalyzer(symbol, tf);
      m_structure = new CPriceStructureAnalyzer(symbol, tf);
   }

   ~CPAAnalyzer() {
      if(m_candles   != NULL) { delete m_candles;   m_candles   = NULL; }
      if(m_structure != NULL) { delete m_structure; m_structure = NULL; }
   }

   //--- تحلیل کامل Price Action
   PAAnalysisResult Analyze() {
      PAAnalysisResult result;
      ZeroMemory(result);

      if(!m_enabled) return result;
      if(!m_candles->Update(m_lookback)) return result;
      if(!m_structure->Update(m_lookback)) return result;

      // تشخیص تمام الگوها
      result.pinBar       = m_candles->DetectPinBar(1);
      result.engulfing    = m_candles->DetectEngulfing(1);
      result.fakey        = m_candles->DetectFakey(1);
      result.insideBar    = m_candles->DetectInsideBar(1);
      result.outsideBar   = m_candles->DetectOutsideBar(1);
      result.doji         = m_candles->DetectDoji(1);
      result.morningStar  = m_candles->DetectMorningStar(1);
      result.eveningStar  = m_candles->DetectEveningStar(1);
      result.threeSoldiers = m_candles->DetectThreeSoldiers(1);
      result.threeCrows   = m_candles->DetectThreeCrows(1);
      result.breakout     = m_structure->DetectBreakout();
      result.retest       = m_structure->DetectRetest();
      result.compression  = m_structure->DetectCompression();
      result.expansion    = m_structure->DetectExpansion();

      // محاسبه امتیاز کل و جهت
      double bullScore = 0, bearScore = 0;
      result.patternCount = 0;
      double topScore = 0;

      PatternResult* patterns[] = {
         &result.pinBar, &result.engulfing, &result.fakey,
         &result.insideBar, &result.outsideBar, &result.doji,
         &result.morningStar, &result.eveningStar,
         &result.threeSoldiers, &result.threeCrows,
         &result.breakout, &result.retest, &result.compression, &result.expansion
      };

      for(int i = 0; i < ArraySize(patterns); i++) {
         if(patterns[i].detected) {
            result.patternCount++;
            if(patterns[i].isBullish) bullScore += patterns[i].score;
            else                      bearScore += patterns[i].score;
            if(patterns[i].score > topScore) {
               topScore = patterns[i].score;
               result.topPattern = patterns[i].name;
            }
         }
      }

      result.totalScore = MathMax(bullScore, bearScore);
      if(bullScore > bearScore && bullScore > 40)       result.direction = SIGNAL_BUY;
      else if(bearScore > bullScore && bearScore > 40)  result.direction = SIGNAL_SELL;
      else                                               result.direction = SIGNAL_NONE;

      return result;
   }

   void Enable()    { m_enabled = true;  }
   void Disable()   { m_enabled = false; }
   bool IsEnabled() { return m_enabled;  }
};
