//+------------------------------------------------------------------+
//|                                               SMCAnalyzer.mqh      |
//|                                    MT5 Trading System             |
//|                                    موتور تحلیل SMC                |
//+------------------------------------------------------------------+
#property strict

//+
// کلاس تحلیل‌گر ساختار بازار
//+
class CStructureAnalyzer {
private:
   string m_symbol;
   ENUM_TIMEFRAME m_timeframe;
   int m_lookback;

   // آرایه‌های داده
   double m_high[];
   double m_low[];
   double m_close[];

   // سطوح سویینگ
   double m_swingHighs[];
   double m_swingLows[];
   int m_swingHighBars[];
   int m_swingLowBars[];

public:
   CStructureAnalyzer(const string symbol, const ENUM_TIMEFRAME tf, const int lookback = 50);
   ~CStructureAnalyzer();

   bool Update();
   bool CheckBOS(int &bosBar);
   bool CheckCHOCH(int &chochBar);
   bool CheckMSS(int &mssBar);
   string GetCurrentTrend();
   double GetLastSwingHigh();
   double GetLastSwingLow();
};

//+
// سازنده
//+
CStructureAnalyzer::CStructureAnalyzer(
   const string symbol,
   const ENUM_TIMEFRAME tf,
   const int lookback
) {
   m_symbol = symbol;
   m_timeframe = tf;
   m_lookback = lookback;

   ArraySetAsSeries(m_high, true);
   ArraySetAsSeries(m_low, true);
   ArraySetAsSeries(m_close, true);
   ArraySetAsSeries(m_swingHighs, true);
   ArraySetAsSeries(m_swingLows, true);
}

//+
// مخرب
//+
CStructureAnalyzer::~CStructureAnalyzer() {
   // پاکسازی آرایه‌ها
   ArrayFree(m_high);
   ArrayFree(m_low);
   ArrayFree(m_close);
   ArrayFree(m_swingHighs);
   ArrayFree(m_swingLows);
}

//+
// به‌روزرسانی داده‌ها
//+
bool CStructureAnalyzer::Update() {
   // کپی داده‌های قیمتی
   if(CopyHigh(m_symbol, m_timeframe, 1, m_lookback, m_high) < m_lookback) return false;
   if(CopyLow(m_symbol, m_timeframe, 1, m_lookback, m_low) < m_lookback) return false;
   if(CopyClose(m_symbol, m_timeframe, 1, m_lookback, m_close) < m_lookback) return false;

   // یافتن نقاط سویینگ
   int swingCount = 0;
   int maxSwings = 20;

   ArrayResize(m_swingHighs, maxSwings);
   ArrayResize(m_swingLows, maxSwings);
   ArrayResize(m_swingHighBars, maxSwings);
   ArrayResize(m_swingLowBars, maxSwings);

   for(int i = 2; i < m_lookback - 2 && swingCount < maxSwings; i++) {
      // سویینگ های
      if(m_high[i] > m_high[i-1] && m_high[i] > m_high[i-2] &&
         m_high[i] > m_high[i+1] && m_high[i] > m_high[i+2]) {
         m_swingHighs[swingCount] = m_high[i];
         m_swingHighBars[swingCount] = i;
      }

      // سویینگ لو
      if(m_low[i] < m_low[i-1] && m_low[i] < m_low[i-2] &&
         m_low[i] < m_low[i+1] && m_low[i] < m_low[i+2]) {
         m_swingLows[swingCount] = m_low[i];
         m_swingLowBars[swingCount] = i;
         swingCount++;
      }
   }

   return true;
}

//+
// تشخیص BOS (Break of Structure)
//+
bool CStructureAnalyzer::CheckBOS(int &bosBar) {
   if(ArraySize(m_swingHighs) < 2 || ArraySize(m_swingLows) < 2) return false;

   // BOS صعودی: شکست سویینگ های قبلی
   if(m_close[0] > m_swingHighs[0]) {
      bosBar = m_swingHighBars[0];
      return true;
   }

   // BOS نزولی: شکست سویینگ لو قبلی
   if(m_close[0] < m_swingLows[0]) {
      bosBar = m_swingLowBars[0];
      return true;
   }

   return false;
}

//+
// تشخیص CHOCH (Change of Character)
//+
bool CStructureAnalyzer::CheckCHOCH(int &chochBar) {
   if(ArraySize(m_swingHighs) < 3 || ArraySize(m_swingLows) < 3) return false;

   string currentTrend = GetCurrentTrend();

   // تغییر روند صعودی به نزولی
   if(currentTrend == "bullish") {
      if(m_close[0] < m_swingLows[1]) {
         chochBar = m_swingLowBars[1];
         return true;
      }
   }

   // تغییر روند نزولی به صعودی
   if(currentTrend == "bearish") {
      if(m_close[0] > m_swingHighs[1]) {
         chochBar = m_swingHighBars[1];
         return true;
      }
   }

   return false;
}

//+
// تشخیص MSS (Market Structure Shift)
//+
bool CStructureAnalyzer::CheckMSS(int &mssBar) {
   if(ArraySize(m_swingHighs) < 3 || ArraySize(m_swingLows) < 3) return false;

   string currentTrend = GetCurrentTrend();

   // MSS صعودی در روند نزولی
   if(currentTrend == "bearish") {
      bool newHigh = m_high[0] > m_swingHighs[1];
      bool newLow = m_low[0] > m_swingLows[0];
      if(newHigh && newLow) {
         mssBar = 1;
         return true;
      }
   }

   // MSS نزولی در روند صعودی
   if(currentTrend == "bullish") {
      bool newHigh = m_high[0] < m_swingHighs[0];
      bool newLow = m_low[0] < m_swingLows[1];
      if(newHigh && newLow) {
         mssBar = 1;
         return true;
      }
   }

   return false;
}

//+
// دریافت روند فعلی
//+
string CStructureAnalyzer::GetCurrentTrend() {
   if(ArraySize(m_swingHighs) < 2 || ArraySize(m_swingLows) < 2)
      return "neutral";

   // روند صعودی: های بالاتر و لوهای بالاتر
   bool higherHighs = m_swingHighs[0] > m_swingHighs[1];
   bool higherLows = m_swingLows[0] > m_swingLows[1];

   if(higherHighs && higherLows) return "bullish";

   // روند نزولی: های پایین‌تر و لوهای پایین‌تر
   bool lowerHighs = m_swingHighs[0] < m_swingHighs[1];
   bool lowerLows = m_swingLows[0] < m_swingLows[1];

   if(lowerHighs && lowerLows) return "bearish";

   return "ranging";
}

//+
// دریافت آخرین سویینگ های
//+
double CStructureAnalyzer::GetLastSwingHigh() {
   if(ArraySize(m_swingHighs) > 0)
      return m_swingHighs[0];
   return 0;
}

//+
// دریافت آخرین سویینگ لو
//+
double CStructureAnalyzer::GetLastSwingLow() {
   if(ArraySize(m_swingLows) > 0)
      return m_swingLows[0];
   return 0;
}


//+
// کلاس تحلیل‌گر Order Block
//+
class CBlockAnalyzer {
private:
   string m_symbol;
   ENUM_TIMEFRAME m_timeframe;
   double m_threshold;

public:
   CBlockAnalyzer(const string symbol, const ENUM_TIMEFRAME tf, const double threshold = 0.1);
   bool FindBullishOB(double &obHigh, double &obLow, int &obBar);
   bool FindBearishOB(double &obHigh, double &obLow, int &obBar);
   bool IsPriceInOB(const double price, const double obHigh, const double obLow);
};

//+
// سازنده
//+
CBlockAnalyzer::CBlockAnalyzer(
   const string symbol,
   const ENUM_TIMEFRAME tf,
   const double threshold
) {
   m_symbol = symbol;
   m_timeframe = tf;
   m_threshold = threshold;
}

//+
// یافتن Order Block صعودی
//+
bool CBlockAnalyzer::FindBullishOB(double &obHigh, double &obLow, int &obBar) {
   double open[], close[], high[], low[];
   ArraySetAsSeries(open, true);
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);

   if(CopyOpen(m_symbol, m_timeframe, 1, 50, open) < 50) return false;
   if(CopyClose(m_symbol, m_timeframe, 1, 50, close) < 50) return false;
   if(CopyHigh(m_symbol, m_timeframe, 1, 50, high) < 50) return false;
   if(CopyLow(m_symbol, m_timeframe, 1, 50, low) < 50) return false;

   // جستجوی کندل نزولی قوی قبل از حرکت صعودی
   for(int i = 2; i < 40; i++) {
      double body = MathAbs(close[i] - open[i]);
      double range = high[i] - low[i];

      // کندل نزولی با بدنه بزرگ
      bool isBearish = close[i] < open[i];
      bool hasBigBody = body > (range * m_threshold);

      // حرکت صعودی بعدی
      bool hasImpulse = high[i-1] > high[i] && close[i-1] > high[i];

      if(isBearish && hasBigBody && hasImpulse) {
         obHigh = high[i];
         obLow = low[i];
         obBar = i;
         return true;
      }
   }

   return false;
}

//+
// یافتن Order Block نزولی
//+
bool CBlockAnalyzer::FindBearishOB(double &obHigh, double &obLow, int &obBar) {
   double open[], close[], high[], low[];
   ArraySetAsSeries(open, true);
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);

   if(CopyOpen(m_symbol, m_timeframe, 1, 50, open) < 50) return false;
   if(CopyClose(m_symbol, m_timeframe, 1, 50, close) < 50) return false;
   if(CopyHigh(m_symbol, m_timeframe, 1, 50, high) < 50) return false;
   if(CopyLow(m_symbol, m_timeframe, 1, 50, low) < 50) return false;

   // جستجوی کندل صعودی قوی قبل از حرکت نزولی
   for(int i = 2; i < 40; i++) {
      double body = MathAbs(close[i] - open[i]);
      double range = high[i] - low[i];

      // کندل صعودی با بدنه بزرگ
      bool isBullish = close[i] > open[i];
      bool hasBigBody = body > (range * m_threshold);

      // حرکت نزولی بعدی
      bool hasImpulse = low[i-1] < low[i] && close[i-1] < low[i];

      if(isBullish && hasBigBody && hasImpulse) {
         obHigh = high[i];
         obLow = low[i];
         obBar = i;
         return true;
      }
   }

   return false;
}

//+
// بررسی وجود قیمت در OB
//+
bool CBlockAnalyzer::IsPriceInOB(const double price, const double obHigh, const double obLow) {
   return (price >= obLow && price <= obHigh);
}


//+
// کلاس تحلیل‌گر FVG
//+
class CFVGAnalyzer {
private:
   string m_symbol;
   ENUM_TIMEFRAME m_timeframe;
   int m_minSize;

public:
   CFVGAnalyzer(const string symbol, const ENUM_TIMEFRAME tf, const int minSize = 10);
   bool FindBullishFVG(double &fvgHigh, double &fvgLow, int &fvgBar);
   bool FindBearishFVG(double &fvgHigh, double &fvgLow, int &fvgBar);
};

//+
// سازنده
//+
CFVGAnalyzer::CFVGAnalyzer(
   const string symbol,
   const ENUM_TIMEFRAME tf,
   const int minSize
) {
   m_symbol = symbol;
   m_timeframe = tf;
   m_minSize = minSize;
}

//+
// یافتن FVG صعودی
//+
bool CFVGAnalyzer::FindBullishFVG(double &fvgHigh, double &fvgLow, int &fvgBar) {
   double high[], low[];
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);

   if(CopyHigh(m_symbol, m_timeframe, 1, 50, high) < 50) return false;
   if(CopyLow(m_symbol, m_timeframe, 1, 50, low) < 50) return false;

   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

   // FVG صعودی: Low کندل 1 بالاتر از High کندل 3
   for(int i = 2; i < 40; i++) {
      if(low[i] > high[i+2]) {
         double gapSize = (low[i] - high[i+2]) / point;
         if(gapSize >= m_minSize) {
            fvgHigh = low[i];
            fvgLow = high[i+2];
            fvgBar = i + 1;  // کندل میانی
            return true;
         }
      }
   }

   return false;
}

//+
// یافتن FVG نزولی
//+
bool CFVGAnalyzer::FindBearishFVG(double &fvgHigh, double &fvgLow, int &fvgBar) {
   double high[], low[];
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);

   if(CopyHigh(m_symbol, m_timeframe, 1, 50, high) < 50) return false;
   if(CopyLow(m_symbol, m_timeframe, 1, 50, low) < 50) return false;

   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

   // FVG نزولی: High کندل 1 پایین‌تر از Low کندل 3
   for(int i = 2; i < 40; i++) {
      if(high[i] < low[i+2]) {
         double gapSize = (low[i+2] - high[i]) / point;
         if(gapSize >= m_minSize) {
            fvgHigh = low[i+2];
            fvgLow = high[i];
            fvgBar = i + 1;  // کندل میانی
            return true;
         }
      }
   }

   return false;
}
//+------------------------------------------------------------------+
