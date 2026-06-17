//+------------------------------------------------------------------+
//|                                               PAAnalyzer.mqh      |
//|                                    MT5 Trading System             |
//|                                    موتور تحلیل Price Action       |
//+------------------------------------------------------------------+
#property strict

//+
// ساختار کندل
//+
struct CandleData {
   double open;
   double high;
   double low;
   double close;
   double body;
   double upperWick;
   double lowerWick;
   double range;
   bool isBullish;
   double bodyRatio;  // نسبت بدنه به رنج
};

//+
// کلاس تحلیل‌گر کندل
//+
class CCandleAnalyzer {
private:
   string m_symbol;
   ENUM_TIMEFRAME m_timeframe;

   CandleData GetCandleData(const int shift);
   bool IsPinBar(const CandleData &candle, const double bodyRatio = 0.3);
   bool IsEngulfing(const CandleData &candle1, const CandleData &candle2);
   bool IsDoji(const CandleData &candle, const double threshold = 0.1);
   bool IsInsideBar(const CandleData &candle1, const CandleData &candle2);

public:
   CCandleAnalyzer(const string symbol, const ENUM_TIMEFRAME tf);
   bool DetectPinBar(int &barShift, string &bias);
   bool DetectEngulfing(int &barShift, string &bias);
   bool DetectDoji(int &barShift);
   bool DetectInsideBar(int &barShift);
   bool DetectFakey(int &barShift, string &bias);
   bool DetectMorningStar(int &barShift);
   bool DetectEveningStar(int &barShift);
};

//+
// سازنده
//+
CCandleAnalyzer::CCandleAnalyzer(const string symbol, const ENUM_TIMEFRAME tf) {
   m_symbol = symbol;
   m_timeframe = tf;
}

//+
// دریافت اطلاعات کندل
//+
CandleData CCandleAnalyzer::GetCandleData(const int shift) {
   CandleData candle;

   double open[], high[], low[], close[];
   ArraySetAsSeries(open, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(close, true);

   CopyOpen(m_symbol, m_timeframe, shift, 1, open);
   CopyHigh(m_symbol, m_timeframe, shift, 1, high);
   CopyLow(m_symbol, m_timeframe, shift, 1, low);
   CopyClose(m_symbol, m_timeframe, shift, 1, close);

   candle.open = open[0];
   candle.high = high[0];
   candle.low = low[0];
   candle.close = close[0];
   candle.range = candle.high - candle.low;
   candle.body = MathAbs(candle.close - candle.open);
   candle.isBullish = candle.close > candle.open;
   candle.upperWick = candle.high - MathMax(candle.open, candle.close);
   candle.lowerWick = MathMin(candle.open, candle.close) - candle.low;
   candle.bodyRatio = (candle.range > 0) ? candle.body / candle.range : 0;

   return candle;
}

//+
// تشخیص Pin Bar
//+
bool CCandleAnalyzer::DetectPinBar(int &barShift, string &bias) {
   CandleData candle = GetCandleData(1);

   // Pin Bar: سایه بزرگ از یک طرف + بدنه کوچک
   bool isPinBar = false;

   if(candle.lowerWick > candle.body * 2 && candle.lowerWick > candle.upperWick * 2) {
      // Pin Bar صعودی (فتیله پایین)
      bias = "bullish";
      isPinBar = true;
   } else if(candle.upperWick > candle.body * 2 && candle.upperWick > candle.lowerWick * 2) {
      // Pin Bar نزولی (فتیله بالا)
      bias = "bearish";
      isPinBar = true;
   }

   if(isPinBar) {
      barShift = 1;
      return true;
   }

   return false;
}

//+
// تشخیص Engulfing
//+
bool CCandleAnalyzer::DetectEngulfing(int &barShift, string &bias) {
   CandleData candle1 = GetCandleData(1);  // کندل اخیر
   CandleData candle2 = GetCandleData(2);  // کندل قبلی

   // Engulfing صعودی
   if(!candle2.isBullish && candle1.isBullish) {
      if(candle1.close > candle2.open && candle1.open < candle2.close) {
         bias = "bullish";
         barShift = 1;
         return true;
      }
   }

   // Engulfing نزولی
   if(candle2.isBullish && !candle1.isBullish) {
      if(candle1.close < candle2.open && candle1.open > candle2.close) {
         bias = "bearish";
         barShift = 1;
         return true;
      }
   }

   return false;
}

//+
// تشخیص Inside Bar
//+
bool CCandleAnalyzer::DetectInsideBar(int &barShift) {
   CandleData candle1 = GetCandleData(1);  // کندل داخل
   CandleData candle2 = GetCandleData(2);  // کندل مادر

   // Inside Bar: کندل داخل محدوده کندل قبلی
   if(candle1.high <= candle2.high && candle1.low >= candle2.low) {
      barShift = 1;
      return true;
   }

   return false;
}

//+
// تشخیص Doji
//+
bool CCandleAnalyzer::DetectDoji(int &barShift) {
   CandleData candle = GetCandleData(1);

   // Doji: بدنه بسیار کوچک
   if(candle.bodyRatio < 0.1) {
      barShift = 1;
      return true;
   }

   return false;
}

//+
// تشخیص Fakey
//+
bool CCandleAnalyzer::DetectFakey(int &barShift, string &bias) {
   // Fakey = Inside Bar + شکست دروغین
   int insideBarShift;
   if(!DetectInsideBar(insideBarShift)) return false;

   CandleData candle0 = GetCandleData(0);  // کندل فعلی
   CandleData candle1 = GetCandleData(1);  // Inside Bar
   CandleData candle2 = GetCandleData(2);  // Mother Bar

   // Fakey صعودی: شکست پایین و بستن داخل Mother Bar
   if(candle0.low < candle2.low && candle0.close > candle2.low) {
      bias = "bullish";
      barShift = 0;
      return true;
   }

   // Fakey نزولی: شکست بالا و بستن داخل Mother Bar
   if(candle0.high > candle2.high && candle0.close < candle2.high) {
      bias = "bearish";
      barShift = 0;
      return true;
   }

   return false;
}

//+
// تشخیص Morning Star
//+
bool CCandleAnalyzer::DetectMorningStar(int &barShift) {
   CandleData candle1 = GetCandleData(1);  // کندل اخیر (صعودی)
   CandleData candle2 = GetCandleData(2);  // کندل میانی (کوچک)
   CandleData candle3 = GetCandleData(3);  // کندل اول (نزولی)

   // Morning Star: نزولی + کوچک + صعودی
   if(!candle3.isBullish && candle2.bodyRatio < 0.3 && candle1.isBullish) {
      if(candle1.close > (candle3.open + candle3.close) / 2) {
         barShift = 1;
         return true;
      }
   }

   return false;
}

//+
// تشخیص Evening Star
//+
bool CCandleAnalyzer::DetectEveningStar(int &barShift) {
   CandleData candle1 = GetCandleData(1);  // کندل اخیر (نزولی)
   CandleData candle2 = GetCandleData(2);  // کندل میانی (کوچک)
   CandleData candle3 = GetCandleData(3);  // کندل اول (صعودی)

   // Evening Star: صعودی + کوچک + نزولی
   if(candle3.isBullish && candle2.bodyRatio < 0.3 && !candle1.isBullish) {
      if(candle1.close < (candle3.open + candle3.close) / 2) {
         barShift = 1;
         return true;
      }
   }

   return false;
}


//+
// کلاس تحلیل‌گر ساختار قیمت
//+
class CPriceStructureAnalyzer {
private:
   string m_symbol;
   ENUM_TIMEFRAME m_timeframe;

public:
   CPriceStructureAnalyzer(const string symbol, const ENUM_TIMEFRAME tf);
   bool IsBreakout(const int lookback = 20);
   bool IsCompression();
   bool IsExpansion();
   bool HasMomentum(const int threshold = 50);
   double CalculateMomentum();
};

//+
// سازنده
//+
CPriceStructureAnalyzer::CPriceStructureAnalyzer(
   const string symbol,
   const ENUM_TIMEFRAME tf
) {
   m_symbol = symbol;
   m_timeframe = tf;
}

//+
// تشخیص شکست
//+
bool CPriceStructureAnalyzer::IsBreakout(const int lookback) {
   double high[], low[], close[];
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(close, true);

   if(CopyHigh(m_symbol, m_timeframe, 1, lookback + 1, high) < lookback + 1) return false;
   if(CopyLow(m_symbol, m_timeframe, 1, lookback + 1, low) < lookback + 1) return false;
   if(CopyClose(m_symbol, m_timeframe, 1, lookback + 1, close) < lookback + 1) return false;

   // یافتن سقف و کف
   double rangeHigh = high[ArrayMaximum(high, 1, lookback)];
   double rangeLow = low[ArrayMinimum(low, 1, lookback)];

   // شکست
   if(close[0] > rangeHigh || close[0] < rangeLow) {
      return true;
   }

   return false;
}

//+
// تشخیص فشرده‌سازی
//+
bool CPriceStructureAnalyzer::IsCompression() {
   // دریافت هندل ATR
   int atrHandle = iATR(m_symbol, m_timeframe, 14);
   if(atrHandle == INVALID_HANDLE) return false;

   double atrValue[];
   ArraySetAsSeries(atrValue, true);

   // کپی مقادیر ATR
   if(CopyBuffer(atrHandle, 0, 0, 20, atrValue) < 20) {
      IndicatorRelease(atrHandle);
      return false;
   }

   // مقایسه ATR فعلی با میانگین
   double avgATR = 0;
   for(int i = 1; i < 20; i++) {
      avgATR += atrValue[i];
   }
   avgATR /= 19;

   // آزادسازی هندل
   IndicatorRelease(atrHandle);

   // ATR کمتر از 70% میانگین = فشرده‌سازی
   if(atrValue[0] < avgATR * 0.7) {
      return true;
   }

   return false;
}

//+
// تشخیص انبساط
//+
bool CPriceStructureAnalyzer::IsExpansion() {
   // دریافت هندل ATR
   int atrHandle = iATR(m_symbol, m_timeframe, 14);
   if(atrHandle == INVALID_HANDLE) return false;

   double atrValue[];
   ArraySetAsSeries(atrValue, true);

   // کپی مقادیر ATR
   if(CopyBuffer(atrHandle, 0, 0, 20, atrValue) < 20) {
      IndicatorRelease(atrHandle);
      return false;
   }

   // محاسبه میانگین
   double avgATR = 0;
   for(int i = 1; i < 20; i++) {
      avgATR += atrValue[i];
   }
   avgATR /= 19;

   // آزادسازی هندل
   IndicatorRelease(atrHandle);

   // ATR بیشتر از 130% میانگین = انبساط
   if(atrValue[0] > avgATR * 1.3) {
      return true;
   }

   return false;
}

//+
// محاسبه مومنتوم
//+
double CPriceStructureAnalyzer::CalculateMomentum() {
   double close[];
   ArraySetAsSeries(close, true);
   CopyClose(m_symbol, m_timeframe, 1, 14, close);

   if(ArraySize(close) < 14) return 0;

   // محاسبه ROC
   double momentum = ((close[0] - close[13]) / close[13]) * 100;
   return momentum;
}

//+
// بررسی مومنتوم
//+
bool CPriceStructureAnalyzer::HasMomentum(const int threshold) {
   double momentum = CalculateMomentum();
   return MathAbs(momentum) > threshold;
}
//+------------------------------------------------------------------+
