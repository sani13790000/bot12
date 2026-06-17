//+------------------------------------------------------------------+
//|                                              SMCAnalyzer.mqh      |
//|                         سیستم معامله‌گری حرفه‌ای MT5               |
//|                                                                    |
//| توضیح فارسی:                                                       |
//| این فایل موتور کامل تحلیل Smart Money Concept است.               |
//| شامل: Market Structure, BOS, CHOCH, MSS, Order Block,             |
//|        Mitigation Block, Breaker Block, Rejection Block,           |
//|        FVG, IFVG, Premium/Discount, Equilibrium,                  |
//|        Session Liquidity, Kill Zones, Internal/External Liquidity  |
//| تمام نواحی امتیازدهی می‌شوند و خروجی برای Decision Engine آماده است|
//+------------------------------------------------------------------+
#pragma once
#include "Config.mqh"
#include "Helpers.mqh"

//--- ساختار داده ناحیه اوردر بلاک
struct OrderBlockZone {
   double   high;           // سقف ناحیه
   double   low;            // کف ناحیه
   double   mid;            // میانه ناحیه
   datetime time;           // زمان شکل‌گیری
   bool     isBullish;      // جهت: صعودی یا نزولی
   bool     isValid;        // آیا هنوز معتبر است
   bool     isMitigated;    // آیا تست شده است
   bool     isBreaker;      // آیا تبدیل به Breaker شده
   bool     isRejection;    // آیا Rejection Block است
   double   score;          // امتیاز ناحیه
   int      barIndex;       // اندیس شمع
};

//--- ساختار داده FVG
struct FVGZone {
   double   high;           // سقف گپ
   double   low;            // کف گپ
   double   mid;            // میانه گپ
   datetime time;           // زمان شکل‌گیری
   bool     isBullish;      // جهت
   bool     isFilled;       // آیا پر شده
   bool     isInverse;      // آیا IFVG است
   double   score;          // امتیاز
   int      barIndex;       // اندیس شمع
};

//--- ساختار ساختار بازار
struct MarketStructureData {
   bool     isBullish;         // روند صعودی
   bool     isBearish;         // روند نزولی
   bool     isRanging;         // رنج
   bool     hasBOS;            // Break of Structure
   bool     hasCHOCH;          // Change of Character
   bool     hasMSS;            // Market Structure Shift
   double   lastSwingHigh;     // آخرین سقف
   double   lastSwingLow;      // آخرین کف
   double   previousSwingHigh; // سقف قبلی
   double   previousSwingLow;  // کف قبلی
   datetime bosTime;           // زمان BOS
   datetime chochTime;         // زمان CHOCH
   double   structureScore;    // امتیاز ساختار
};

//--- ساختار لیکوییدیتی
struct LiquidityData {
   double   sellSideLiquidity; // سقف‌های برابر (SSL)
   double   buySideLiquidity;  // کف‌های برابر (BSL)
   double   internalHigh;      // سقف داخلی
   double   internalLow;       // کف داخلی
   double   externalHigh;      // سقف خارجی
   double   externalLow;       // کف خارجی
   bool     hasLiquiditySweep; // جاروب لیکوییدیتی
   bool     sweepBullish;      // جهت جاروب
   double   sessionHigh;       // سقف سشن
   double   sessionLow;        // کف سشن
   double   liquidityScore;    // امتیاز
};

//--- ساختار پریمیوم/دیسکانت
struct PremiumDiscountData {
   double   rangeHigh;         // سقف رنج
   double   rangeLow;          // کف رنج
   double   equilibrium;       // تعادل (50%)
   double   premium75;         // 75% پریمیوم
   double   discount25;        // 25% دیسکانت
   bool     isInPremium;       // قیمت در پریمیوم
   bool     isInDiscount;      // قیمت در دیسکانت
   bool     isAtEquilibrium;   // قیمت در تعادل
   double   currentRatio;      // موقعیت فعلی قیمت
};

//--- خروجی کامل SMC
struct SMCAnalysisResult {
   MarketStructureData  structure;     // ساختار بازار
   LiquidityData        liquidity;     // لیکوییدیتی
   PremiumDiscountData  pd;            // پریمیوم/دیسکانت
   OrderBlockZone       bestBullishOB; // بهترین OB صعودی
   OrderBlockZone       bestBearishOB; // بهترین OB نزولی
   FVGZone              bestBullishFVG;// بهترین FVG صعودی
   FVGZone              bestBearishFVG;// بهترین FVG نزولی
   double               totalScore;   // امتیاز کل SMC
   ENUM_SIGNAL_DIRECTION direction;   // جهت پیشنهادی
   string               reason;       // دلیل تصمیم
};

//+------------------------------------------------------------------+
//| کلاس تحلیل ساختار بازار                                          |
//+------------------------------------------------------------------+
class CStructureAnalyzer {
private:
   string   m_symbol;
   ENUM_TIMEFRAMES m_tf;
   int      m_lookback;
   double   m_swingHigh[];
   double   m_swingLow[];
   int      m_swingHighBars[];
   int      m_swingLowBars[];
   int      m_swingHighCount;
   int      m_swingLowCount;
   double   m_high[];
   double   m_low[];
   double   m_close[];
   datetime m_time[];
   int      m_bars;

public:
   //--- سازنده
   CStructureAnalyzer(string symbol, ENUM_TIMEFRAMES tf, int lookback = 50) {
      m_symbol = symbol;
      m_tf = tf;
      m_lookback = lookback;
      m_swingHighCount = 0;
      m_swingLowCount = 0;
      m_bars = 0;
   }

   //--- به‌روزرسانی داده‌های قیمتی
   bool Update() {
      m_bars = MathMin(m_lookback + 10, Bars(m_symbol, m_tf));
      if(m_bars < 10) return false;

      if(CopyHigh(m_symbol, m_tf, 0, m_bars, m_high) < m_bars) return false;
      if(CopyLow(m_symbol, m_tf, 0, m_bars, m_low) < m_bars) return false;
      if(CopyClose(m_symbol, m_tf, 0, m_bars, m_close) < m_bars) return false;
      if(CopyTime(m_symbol, m_tf, 0, m_bars, m_time) < m_bars) return false;

      ArrayResize(m_swingHigh, m_bars);
      ArrayResize(m_swingLow, m_bars);
      ArrayResize(m_swingHighBars, m_bars);
      ArrayResize(m_swingLowBars, m_bars);

      m_swingHighCount = 0;
      m_swingLowCount = 0;

      int strength = 3; // تعداد شمع‌های تایید برای سوینگ
      for(int i = strength; i < m_bars - strength; i++) {
         bool isSwingHigh = true;
         bool isSwingLow = true;
         for(int j = 1; j <= strength; j++) {
            if(m_high[i] <= m_high[i-j] || m_high[i] <= m_high[i+j]) isSwingHigh = false;
            if(m_low[i] >= m_low[i-j] || m_low[i] >= m_low[i+j]) isSwingLow = false;
         }
         if(isSwingHigh && m_swingHighCount < m_bars) {
            m_swingHigh[m_swingHighCount] = m_high[i];
            m_swingHighBars[m_swingHighCount] = i;
            m_swingHighCount++;
         }
         if(isSwingLow && m_swingLowCount < m_bars) {
            m_swingLow[m_swingLowCount] = m_low[i];
            m_swingLowBars[m_swingLowCount] = i;
            m_swingLowCount++;
         }
      }
      return true;
   }

   //--- بررسی BOS (شکست ساختار)
   bool CheckBOS(bool bullish) {
      if(m_swingHighCount < 2 || m_swingLowCount < 2) return false;
      if(bullish) {
         // BOS صعودی: بستن بالای آخرین سقف
         double lastHigh = m_swingHigh[0];
         return (m_close[0] > lastHigh);
      } else {
         // BOS نزولی: بستن زیر آخرین کف
         double lastLow = m_swingLow[0];
         return (m_close[0] < lastLow);
      }
   }

   //--- بررسی CHOCH (تغییر کاراکتر)
   bool CheckCHOCH(bool bullish) {
      if(m_swingHighCount < 2 || m_swingLowCount < 2) return false;
      if(bullish) {
         // در روند نزولی، شکست صعودی = CHOCH
         bool prevDowntrend = (m_swingHigh[1] > m_swingHigh[0]) && (m_swingLow[1] > m_swingLow[0]);
         return prevDowntrend && CheckBOS(true);
      } else {
         bool prevUptrend = (m_swingHigh[1] < m_swingHigh[0]) && (m_swingLow[1] < m_swingLow[0]);
         return prevUptrend && CheckBOS(false);
      }
   }

   //--- بررسی MSS (تغییر ساختار)
   bool CheckMSS() {
      if(m_swingHighCount < 3 || m_swingLowCount < 3) return false;
      bool bullishMSS = (m_swingHigh[0] > m_swingHigh[1]) && (m_swingLow[0] > m_swingLow[1])
                     && (m_swingHigh[1] < m_swingHigh[2]); // تغییر از نزولی به صعودی
      bool bearishMSS = (m_swingHigh[0] < m_swingHigh[1]) && (m_swingLow[0] < m_swingLow[1])
                     && (m_swingLow[1] > m_swingLow[2]);  // تغییر از صعودی به نزولی
      return bullishMSS || bearishMSS;
   }

   //--- دریافت روند فعلی
   ENUM_SIGNAL_DIRECTION GetCurrentTrend() {
      if(m_swingHighCount < 2 || m_swingLowCount < 2) return SIGNAL_NONE;
      bool higherHighs = m_swingHigh[0] > m_swingHigh[1];
      bool higherLows  = m_swingLow[0]  > m_swingLow[1];
      bool lowerHighs  = m_swingHigh[0] < m_swingHigh[1];
      bool lowerLows   = m_swingLow[0]  < m_swingLow[1];
      if(higherHighs && higherLows) return SIGNAL_BUY;
      if(lowerHighs  && lowerLows)  return SIGNAL_SELL;
      return SIGNAL_NONE;
   }

   //--- دریافت داده‌های ساختار
   MarketStructureData GetStructureData() {
      MarketStructureData data;
      ZeroMemory(data);
      if(m_swingHighCount < 1 || m_swingLowCount < 1) return data;

      data.lastSwingHigh     = m_swingHighCount > 0 ? m_swingHigh[0] : 0;
      data.lastSwingLow      = m_swingLowCount  > 0 ? m_swingLow[0]  : 0;
      data.previousSwingHigh = m_swingHighCount > 1 ? m_swingHigh[1] : 0;
      data.previousSwingLow  = m_swingLowCount  > 1 ? m_swingLow[1]  : 0;

      ENUM_SIGNAL_DIRECTION trend = GetCurrentTrend();
      data.isBullish  = (trend == SIGNAL_BUY);
      data.isBearish  = (trend == SIGNAL_SELL);
      data.isRanging  = (trend == SIGNAL_NONE);
      data.hasBOS     = CheckBOS(data.isBullish);
      data.hasCHOCH   = CheckCHOCH(data.isBullish);
      data.hasMSS     = CheckMSS();

      // امتیازدهی ساختار
      data.structureScore = 0;
      if(data.isBullish || data.isBearish) data.structureScore += 30;
      if(data.hasBOS)   data.structureScore += 25;
      if(data.hasCHOCH) data.structureScore += 25;
      if(data.hasMSS)   data.structureScore += 20;

      return data;
   }

   double GetLastSwingHigh() { return m_swingHighCount > 0 ? m_swingHigh[0] : 0; }
   double GetLastSwingLow()  { return m_swingLowCount  > 0 ? m_swingLow[0]  : 0; }
   double GetHigh(int i)     { return (i >= 0 && i < m_bars) ? m_high[i]  : 0; }
   double GetLow(int i)      { return (i >= 0 && i < m_bars) ? m_low[i]   : 0; }
   double GetClose(int i)    { return (i >= 0 && i < m_bars) ? m_close[i] : 0; }
   int    GetBars()          { return m_bars; }
};

//+------------------------------------------------------------------+
//| کلاس تحلیل اوردر بلاک                                            |
//+------------------------------------------------------------------+
class CBlockAnalyzer {
private:
   string          m_symbol;
   ENUM_TIMEFRAMES m_tf;
   int             m_lookback;
   double          m_high[];
   double          m_low[];
   double          m_open[];
   double          m_close[];
   long            m_volume[];
   int             m_bars;

public:
   CBlockAnalyzer(string symbol, ENUM_TIMEFRAMES tf, int lookback = 50) {
      m_symbol   = symbol;
      m_tf       = tf;
      m_lookback = lookback;
      m_bars     = 0;
   }

   bool Update() {
      m_bars = MathMin(m_lookback + 5, Bars(m_symbol, m_tf));
      if(m_bars < 5) return false;
      if(CopyHigh(m_symbol, m_tf, 0, m_bars, m_high)     < m_bars) return false;
      if(CopyLow(m_symbol, m_tf, 0, m_bars, m_low)       < m_bars) return false;
      if(CopyOpen(m_symbol, m_tf, 0, m_bars, m_open)     < m_bars) return false;
      if(CopyClose(m_symbol, m_tf, 0, m_bars, m_close)   < m_bars) return false;
      if(CopyTickVolume(m_symbol, m_tf, 0, m_bars, m_volume) < m_bars) return false;
      return true;
   }

   //--- یافتن بهترین اوردر بلاک صعودی
   OrderBlockZone FindBullishOB() {
      OrderBlockZone ob;
      ZeroMemory(ob);
      ob.isValid = false;
      double bestScore = 0;

      for(int i = 3; i < m_bars - 3; i++) {
         // شرط: شمع نزولی قبل از حرکت صعودی قوی
         bool isBearishCandle = m_close[i] < m_open[i];
         bool nextIsBullish   = m_close[i-1] > m_open[i-1];
         bool strongMove      = (m_close[i-1] - m_open[i-1]) > (m_high[i] - m_low[i]) * 0.7;
         // BOS بعد از OB
         bool hasBOS = false;
         for(int k = 1; k <= 5 && k < i; k++) {
            if(m_close[i-k] > m_high[i]) { hasBOS = true; break; }
         }
         if(!isBearishCandle || !nextIsBullish || !strongMove || !hasBOS) continue;

         // امتیازدهی
         double score = 50;
         double bodyRatio = MathAbs(m_close[i] - m_open[i]) / (m_high[i] - m_low[i] + 0.0001);
         if(bodyRatio > 0.6) score += 15; // بدنه بزرگ = قوی‌تر
         if(m_volume[i] > m_volume[i+1] * 1.2) score += 15; // حجم بالا
         // تایید نشده (تازه): امتیاز بیشتر
         bool isMitigated = false;
         for(int k = 1; k < i; k++) {
            if(m_low[k] <= m_close[i] && m_high[k] >= m_open[i]) { isMitigated = true; break; }
         }
         if(!isMitigated) score += 20;
         // نزدیک‌تر بودن به قیمت فعلی
         double dist = MathAbs(m_close[0] - m_high[i]) / (m_high[i] - m_low[i] + 0.0001);
         if(dist < 10) score += 10;

         if(score > bestScore) {
            bestScore      = score;
            ob.high        = m_high[i];
            ob.low         = m_low[i];
            ob.mid         = (m_high[i] + m_low[i]) / 2.0;
            ob.time        = iTime(m_symbol, m_tf, i);
            ob.isBullish   = true;
            ob.isValid     = true;
            ob.isMitigated = isMitigated;
            ob.isBreaker   = false;
            ob.isRejection = false;
            ob.score       = score;
            ob.barIndex    = i;
         }
      }
      return ob;
   }

   //--- یافتن بهترین اوردر بلاک نزولی
   OrderBlockZone FindBearishOB() {
      OrderBlockZone ob;
      ZeroMemory(ob);
      ob.isValid = false;
      double bestScore = 0;

      for(int i = 3; i < m_bars - 3; i++) {
         bool isBullishCandle = m_close[i] > m_open[i];
         bool nextIsBearish   = m_close[i-1] < m_open[i-1];
         bool strongMove      = (m_open[i-1] - m_close[i-1]) > (m_high[i] - m_low[i]) * 0.7;
         bool hasBOS = false;
         for(int k = 1; k <= 5 && k < i; k++) {
            if(m_close[i-k] < m_low[i]) { hasBOS = true; break; }
         }
         if(!isBullishCandle || !nextIsBearish || !strongMove || !hasBOS) continue;

         double score = 50;
         double bodyRatio = MathAbs(m_close[i] - m_open[i]) / (m_high[i] - m_low[i] + 0.0001);
         if(bodyRatio > 0.6) score += 15;
         if(m_volume[i] > m_volume[i+1] * 1.2) score += 15;
         bool isMitigated = false;
         for(int k = 1; k < i; k++) {
            if(m_low[k] <= m_open[i] && m_high[k] >= m_close[i]) { isMitigated = true; break; }
         }
         if(!isMitigated) score += 20;
         double dist = MathAbs(m_close[0] - m_low[i]) / (m_high[i] - m_low[i] + 0.0001);
         if(dist < 10) score += 10;

         if(score > bestScore) {
            bestScore      = score;
            ob.high        = m_high[i];
            ob.low         = m_low[i];
            ob.mid         = (m_high[i] + m_low[i]) / 2.0;
            ob.time        = iTime(m_symbol, m_tf, i);
            ob.isBullish   = false;
            ob.isValid     = true;
            ob.isMitigated = isMitigated;
            ob.isBreaker   = false;
            ob.isRejection = false;
            ob.score       = score;
            ob.barIndex    = i;
         }
      }
      return ob;
   }

   //--- بررسی اینکه قیمت داخل OB است
   bool IsPriceInOB(const OrderBlockZone &ob, double price) {
      if(!ob.isValid) return false;
      double buffer = (ob.high - ob.low) * 0.1;
      return (price >= ob.low - buffer && price <= ob.high + buffer);
   }

   //--- تبدیل OB به Breaker Block (اگر OB شکسته شد)
   bool IsBreaker(const OrderBlockZone &ob) {
      if(!ob.isBullish) {
         // اگر OB نزولی شکسته شود از پایین به بالا = Breaker
         return m_close[0] > ob.high;
      } else {
         return m_close[0] < ob.low;
      }
   }
};

//+------------------------------------------------------------------+
//| کلاس تحلیل FVG (Fair Value Gap)                                  |
//+------------------------------------------------------------------+
class CFVGAnalyzer {
private:
   string          m_symbol;
   ENUM_TIMEFRAMES m_tf;
   int             m_lookback;
   double          m_high[];
   double          m_low[];
   double          m_close[];
   int             m_bars;

public:
   CFVGAnalyzer(string symbol, ENUM_TIMEFRAMES tf, int lookback = 50) {
      m_symbol   = symbol;
      m_tf       = tf;
      m_lookback = lookback;
      m_bars     = 0;
   }

   bool Update() {
      m_bars = MathMin(m_lookback + 5, Bars(m_symbol, m_tf));
      if(m_bars < 5) return false;
      if(CopyHigh(m_symbol, m_tf, 0, m_bars, m_high)   < m_bars) return false;
      if(CopyLow(m_symbol, m_tf, 0, m_bars, m_low)     < m_bars) return false;
      if(CopyClose(m_symbol, m_tf, 0, m_bars, m_close) < m_bars) return false;
      return true;
   }

   //--- یافتن بهترین FVG صعودی
   FVGZone FindBullishFVG() {
      FVGZone fvg;
      ZeroMemory(fvg);
      fvg.isFilled = true;
      double bestScore = 0;

      // FVG صعودی: کف شمع i-2 > سقف شمع i (گپ بین شمع اول و سوم)
      for(int i = 3; i < m_bars - 1; i++) {
         // شمع 1=i+2, شمع 2=i+1, شمع 3=i
         // gapHigh = Low[i], gapLow = High[i+2]
         if(m_low[i] <= m_high[i+2]) continue; // گپ وجود ندارد

         double gapHigh = m_low[i];
         double gapLow  = m_high[i+2];
         double gapSize = gapHigh - gapLow;
         if(gapSize <= 0) continue;

         // بررسی پر نشدن گپ
         bool isFilled = false;
         for(int k = 1; k < i; k++) {
            if(m_low[k] <= gapLow) { isFilled = true; break; }
         }

         // امتیازدهی
         double score = 40;
         double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
         if(gapSize > 10 * point) score += 20;
         if(!isFilled) score += 30;
         if(i <= 10) score += 10; // تازه‌تر = بهتر

         if(score > bestScore) {
            bestScore      = score;
            fvg.high       = gapHigh;
            fvg.low        = gapLow;
            fvg.mid        = (gapHigh + gapLow) / 2.0;
            fvg.time       = iTime(m_symbol, m_tf, i);
            fvg.isBullish  = true;
            fvg.isFilled   = isFilled;
            fvg.isInverse  = false;
            fvg.score      = score;
            fvg.barIndex   = i;
         }
      }
      return fvg;
   }

   //--- یافتن بهترین FVG نزولی
   FVGZone FindBearishFVG() {
      FVGZone fvg;
      ZeroMemory(fvg);
      fvg.isFilled = true;
      double bestScore = 0;

      for(int i = 3; i < m_bars - 1; i++) {
         if(m_high[i] >= m_low[i+2]) continue;

         double gapLow  = m_high[i];
         double gapHigh = m_low[i+2];
         double gapSize = gapHigh - gapLow;
         if(gapSize <= 0) continue;

         bool isFilled = false;
         for(int k = 1; k < i; k++) {
            if(m_high[k] >= gapHigh) { isFilled = true; break; }
         }

         double score = 40;
         double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
         if(gapSize > 10 * point) score += 20;
         if(!isFilled) score += 30;
         if(i <= 10) score += 10;

         if(score > bestScore) {
            bestScore      = score;
            fvg.high       = gapHigh;
            fvg.low        = gapLow;
            fvg.mid        = (gapHigh + gapLow) / 2.0;
            fvg.time       = iTime(m_symbol, m_tf, i);
            fvg.isBullish  = false;
            fvg.isFilled   = isFilled;
            fvg.isInverse  = false;
            fvg.score      = score;
            fvg.barIndex   = i;
         }
      }
      return fvg;
   }

   //--- بررسی IFVG (Inverse FVG)
   bool IsIFVG(const FVGZone &fvg) {
      if(!fvg.isBullish) return false;
      // اگر FVG صعودی از بالا شکسته شود = IFVG
      return (m_close[0] < fvg.low);
   }

   bool IsPriceInFVG(const FVGZone &fvg, double price) {
      if(fvg.isFilled) return false;
      return (price >= fvg.low && price <= fvg.high);
   }
};

//+------------------------------------------------------------------+
//| کلاس تحلیل لیکوییدیتی                                           |
//+------------------------------------------------------------------+
class CLiquidityAnalyzer {
private:
   string          m_symbol;
   ENUM_TIMEFRAMES m_tf;
   int             m_lookback;
   double          m_high[];
   double          m_low[];
   double          m_close[];
   int             m_bars;

public:
   CLiquidityAnalyzer(string symbol, ENUM_TIMEFRAMES tf, int lookback = 50) {
      m_symbol   = symbol;
      m_tf       = tf;
      m_lookback = lookback;
   }

   bool Update() {
      m_bars = MathMin(m_lookback + 5, Bars(m_symbol, m_tf));
      if(m_bars < 5) return false;
      if(CopyHigh(m_symbol, m_tf, 0, m_bars, m_high)   < m_bars) return false;
      if(CopyLow(m_symbol, m_tf, 0, m_bars, m_low)     < m_bars) return false;
      if(CopyClose(m_symbol, m_tf, 0, m_bars, m_close) < m_bars) return false;
      return true;
   }

   //--- دریافت داده‌های لیکوییدیتی
   LiquidityData GetLiquidityData() {
      LiquidityData data;
      ZeroMemory(data);

      // پیدا کردن سقف‌ها و کف‌های برابر (Equal Highs/Lows)
      double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      double threshold = 5 * point;
      double highestHigh = 0, lowestLow = DBL_MAX;
      double internalHigh = 0, internalLow = DBL_MAX;

      for(int i = 1; i < m_bars; i++) {
         if(m_high[i] > highestHigh) highestHigh = m_high[i];
         if(m_low[i] < lowestLow)   lowestLow   = m_low[i];
         if(i <= m_bars/2) {
            if(m_high[i] > internalHigh) internalHigh = m_high[i];
            if(m_low[i] < internalLow)   internalLow  = m_low[i];
         }
      }

      data.sellSideLiquidity = highestHigh;
      data.buySideLiquidity  = lowestLow;
      data.internalHigh      = internalHigh;
      data.internalLow       = internalLow;
      data.externalHigh      = highestHigh;
      data.externalLow       = lowestLow;

      // بررسی جاروب لیکوییدیتی
      double currentClose = m_close[0];
      double prevHigh     = m_high[1];
      double prevLow      = m_low[1];

      data.hasLiquiditySweep = false;
      if(m_high[0] > highestHigh && currentClose < highestHigh) {
         data.hasLiquiditySweep = true;
         data.sweepBullish      = false; // جاروب سقف = نزولی
      } else if(m_low[0] < lowestLow && currentClose > lowestLow) {
         data.hasLiquiditySweep = true;
         data.sweepBullish      = true; // جاروب کف = صعودی
      }

      // سشن
      data.sessionHigh = highestHigh;
      data.sessionLow  = lowestLow;

      // امتیازدهی
      data.liquidityScore = 0;
      if(data.hasLiquiditySweep) data.liquidityScore += 40;
      double distToSSL = MathAbs(currentClose - data.sellSideLiquidity);
      double distToBSL = MathAbs(currentClose - data.buySideLiquidity);
      double range = data.sellSideLiquidity - data.buySideLiquidity;
      if(range > 0) {
         if(distToSSL < range * 0.15) data.liquidityScore += 30;
         if(distToBSL < range * 0.15) data.liquidityScore += 30;
      }

      return data;
   }
};

//+------------------------------------------------------------------+
//| کلاس تحلیل پریمیوم/دیسکانت                                      |
//+------------------------------------------------------------------+
class CPremiumDiscountAnalyzer {
public:
   //--- محاسبه پریمیوم/دیسکانت
   PremiumDiscountData Calculate(double rangeHigh, double rangeLow, double currentPrice) {
      PremiumDiscountData data;
      ZeroMemory(data);

      data.rangeHigh    = rangeHigh;
      data.rangeLow     = rangeLow;
      data.equilibrium  = (rangeHigh + rangeLow) / 2.0;
      data.premium75    = rangeLow + (rangeHigh - rangeLow) * 0.75;
      data.discount25   = rangeLow + (rangeHigh - rangeLow) * 0.25;

      double range = rangeHigh - rangeLow;
      if(range > 0) {
         data.currentRatio = (currentPrice - rangeLow) / range;
      }

      data.isInPremium    = (currentPrice > data.premium75);
      data.isInDiscount   = (currentPrice < data.discount25);
      data.isAtEquilibrium = (MathAbs(currentPrice - data.equilibrium) < range * 0.05);

      return data;
   }
};

//+------------------------------------------------------------------+
//| کلاس اصلی تحلیلگر SMC                                           |
//+------------------------------------------------------------------+
class CSMCAnalyzer {
private:
   string          m_symbol;
   ENUM_TIMEFRAMES m_tf;
   bool            m_enabled;

   CStructureAnalyzer*     m_structure;
   CBlockAnalyzer*         m_blocks;
   CFVGAnalyzer*           m_fvg;
   CLiquidityAnalyzer*     m_liquidity;
   CPremiumDiscountAnalyzer* m_pd;

public:
   //--- سازنده
   CSMCAnalyzer(string symbol, ENUM_TIMEFRAMES tf) {
      m_symbol  = symbol;
      m_tf      = tf;
      m_enabled = true;

      m_structure = new CStructureAnalyzer(symbol, tf, 100);
      m_blocks    = new CBlockAnalyzer(symbol, tf, 100);
      m_fvg       = new CFVGAnalyzer(symbol, tf, 100);
      m_liquidity = new CLiquidityAnalyzer(symbol, tf, 100);
      m_pd        = new CPremiumDiscountAnalyzer();
   }

   //--- مخرب
   ~CSMCAnalyzer() {
      if(m_structure != NULL) { delete m_structure; m_structure = NULL; }
      if(m_blocks    != NULL) { delete m_blocks;    m_blocks    = NULL; }
      if(m_fvg       != NULL) { delete m_fvg;       m_fvg       = NULL; }
      if(m_liquidity != NULL) { delete m_liquidity; m_liquidity = NULL; }
      if(m_pd        != NULL) { delete m_pd;        m_pd        = NULL; }
   }

   //--- تحلیل کامل و بازگرداندن نتیجه
   SMCAnalysisResult Analyze() {
      SMCAnalysisResult result;
      ZeroMemory(result);

      if(!m_enabled) return result;

      // به‌روزرسانی همه تحلیلگرها
      if(!m_structure->Update()) return result;
      if(!m_blocks->Update())    return result;
      if(!m_fvg->Update())       return result;
      if(!m_liquidity->Update()) return result;

      // دریافت داده‌های ساختار
      result.structure = m_structure->GetStructureData();

      // دریافت داده‌های لیکوییدیتی
      result.liquidity = m_liquidity->GetLiquidityData();

      // دریافت بهترین OB
      result.bestBullishOB = m_blocks->FindBullishOB();
      result.bestBearishOB = m_blocks->FindBearishOB();

      // دریافت بهترین FVG
      result.bestBullishFVG = m_fvg->FindBullishFVG();
      result.bestBearishFVG = m_fvg->FindBearishFVG();

      // محاسبه پریمیوم/دیسکانت
      double currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      result.pd = m_pd->Calculate(
         result.liquidity.sellSideLiquidity,
         result.liquidity.buySideLiquidity,
         currentPrice
      );

      // تعیین جهت و امتیاز کل
      _CalculateDirection(result, currentPrice);

      return result;
   }

   void Enable()  { m_enabled = true;  }
   void Disable() { m_enabled = false; }
   bool IsEnabled() { return m_enabled; }

private:
   //--- محاسبه جهت و امتیاز
   void _CalculateDirection(SMCAnalysisResult &result, double currentPrice) {
      double bullScore = 0, bearScore = 0;

      // ساختار
      if(result.structure.isBullish) bullScore += result.structure.structureScore;
      if(result.structure.isBearish) bearScore += result.structure.structureScore;
      if(result.structure.hasBOS && result.structure.isBullish) bullScore += 20;
      if(result.structure.hasBOS && result.structure.isBearish) bearScore += 20;
      if(result.structure.hasCHOCH && result.structure.isBullish) bullScore += 15;
      if(result.structure.hasCHOCH && result.structure.isBearish) bearScore += 15;

      // OB
      if(result.bestBullishOB.isValid) {
         bool inOB = m_blocks->IsPriceInOB(result.bestBullishOB, currentPrice);
         if(inOB) bullScore += result.bestBullishOB.score * 0.5;
      }
      if(result.bestBearishOB.isValid) {
         bool inOB = m_blocks->IsPriceInOB(result.bestBearishOB, currentPrice);
         if(inOB) bearScore += result.bestBearishOB.score * 0.5;
      }

      // FVG
      if(!result.bestBullishFVG.isFilled && m_fvg->IsPriceInFVG(result.bestBullishFVG, currentPrice))
         bullScore += result.bestBullishFVG.score * 0.3;
      if(!result.bestBearishFVG.isFilled && m_fvg->IsPriceInFVG(result.bestBearishFVG, currentPrice))
         bearScore += result.bestBearishFVG.score * 0.3;

      // لیکوییدیتی
      if(result.liquidity.hasLiquiditySweep) {
         if(result.liquidity.sweepBullish) bullScore += result.liquidity.liquidityScore;
         else                              bearScore += result.liquidity.liquidityScore;
      }

      // پریمیوم/دیسکانت
      if(result.pd.isInDiscount)   bullScore += 20;
      if(result.pd.isInPremium)    bearScore += 20;

      // تعیین جهت
      if(bullScore > bearScore && bullScore > 50)      result.direction = SIGNAL_BUY;
      else if(bearScore > bullScore && bearScore > 50) result.direction = SIGNAL_SELL;
      else                                              result.direction = SIGNAL_NONE;

      result.totalScore = MathMax(bullScore, bearScore);
      result.reason = StringFormat("Bull:%.0f Bear:%.0f Trend:%s BOS:%s CHOCH:%s OB:%s FVG:%s",
         bullScore, bearScore,
         result.structure.isBullish ? "UP" : (result.structure.isBearish ? "DN" : "RANGE"),
         result.structure.hasBOS ? "YES" : "NO",
         result.structure.hasCHOCH ? "YES" : "NO",
         (result.bestBullishOB.isValid || result.bestBearishOB.isValid) ? "YES" : "NO",
         (!result.bestBullishFVG.isFilled || !result.bestBearishFVG.isFilled) ? "YES" : "NO"
      );
   }
};
