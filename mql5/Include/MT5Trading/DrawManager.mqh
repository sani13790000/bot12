//+------------------------------------------------------------------+
//|                                                    DrawManager.mqh |
//|                              MT5 Trading System - Bot12           |
//|  توضیح: مدیریت کامل رسم نمودار شامل:                            |
//|  - رسم Order Block (صعودی/نزولی/Breaker/Rejection/Mitigation)    |
//|  - رسم FVG و IFVG                                                |
//|  - رسم BOS، CHOCH، MSS                                           |
//|  - رسم Liquidity Zones (SSL/BSL/Internal/External)               |
//|  - رسم Premium/Discount و Equilibrium                            |
//|  - رسم Session Range و Kill Zone                                 |
//|  - رسم سیگنال ورود با SL/TP چندگانه                             |
//|  - مدیریت چرخه عمر آبجکت‌ها (انقضا، پاک‌سازی، به‌روزرسانی)      |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"

//+------------------------------------------------------------------+
//| رنگ‌های استاندارد سیستم                                           |
//+------------------------------------------------------------------+
color COLOR_OB_BULL       = C'30,100,255';   // آبی - Order Block صعودی
color COLOR_OB_BEAR       = C'220,50,50';    // قرمز - Order Block نزولی
color COLOR_OB_BREAKER    = C'180,0,180';    // بنفش - Breaker Block
color COLOR_OB_REJECTION  = C'255,140,0';    // نارنجی - Rejection Block
color COLOR_OB_MITIGATION = C'128,128,128';  // خاکستری - Mitigated OB
color COLOR_FVG_BULL      = C'0,200,200';    // فیروزه‌ای - FVG صعودی
color COLOR_FVG_BEAR      = C'200,0,200';    // ارغوانی - FVG نزولی
color COLOR_FVG_INVERSE   = C'255,200,0';    // زرد - IFVG
color COLOR_BOS           = C'255,255,0';    // زرد - Break of Structure
color COLOR_CHOCH         = C'255,165,0';    // نارنجی - Change of Character
color COLOR_MSS           = C'255,0,255';    // صورتی - Market Structure Shift
color COLOR_LIQUIDITY     = C'255,215,0';    // طلایی - Liquidity
color COLOR_LIQ_SWEEP     = C'255,69,0';     // قرمز-نارنجی - Liquidity Sweep
color COLOR_EQUILIBRIUM   = C'150,150,150';  // خاکستری - Equilibrium
color COLOR_PREMIUM       = C'255,80,80';    // قرمز - Premium Zone
color COLOR_DISCOUNT      = C'80,200,80';    // سبز - Discount Zone
color COLOR_SESSION       = C'40,40,80';     // آبی تیره - Session Range
color COLOR_KILL_ZONE     = C'80,60,20';     // قهوه‌ای - Kill Zone
color COLOR_ENTRY_BUY     = C'0,220,0';      // سبز - ورود خرید
color COLOR_ENTRY_SELL    = C'220,0,0';      // قرمز - ورود فروش
color COLOR_SL            = C'200,0,0';      // قرمز - Stop Loss
color COLOR_TP            = C'0,200,0';      // سبز - Take Profit
color COLOR_SWING_HIGH    = C'220,50,50';    // قرمز - Swing High
color COLOR_SWING_LOW     = C'50,200,50';    // سبز - Swing Low

//+------------------------------------------------------------------+
//| ساختار ناحیه رسم                                                 |
//+------------------------------------------------------------------+
struct DrawZone {
   string   name;        // نام آبجکت در چارت
   string   labelName;   // نام برچسب متنی
   string   type;        // نوع ناحیه
   double   high;        // سقف ناحیه
   double   low;         // کف ناحیه
   datetime startTime;   // زمان شروع
   datetime endTime;     // زمان پایان
   color    zoneColor;   // رنگ ناحیه
   bool     isActive;    // آیا فعال است
   double   score;       // امتیاز ناحیه
};

//+------------------------------------------------------------------+
//| کلاس مدیریت رسم حرفه‌ای                                           |
//+------------------------------------------------------------------+
class CDrawManager {
private:
   string      m_symbol;       // نماد فعال
   int         m_nextId;       // شمارنده یکتا
   DrawZone    m_zones[];      // آرایه نواحی رسم‌شده
   int         m_zoneCount;    // تعداد نواحی

   // تولید نام یکتا برای آبجکت
   string GenerateName(const string prefix);

   // بررسی وجود آبجکت
   bool ObjectExists(const string name);

   // ایجاد مستطیل پر با شفافیت
   bool CreateFilledRect(const string name, const datetime t1, const double p1,
                         const datetime t2, const double p2,
                         const color clr, const bool back = true);

   // ایجاد متن برچسب
   bool CreateLabel(const string name, const datetime t, const double p,
                    const string text, const color clr, const int fontSize = 8);

   // ایجاد خط ترند
   bool CreateTrendLine(const string name, const datetime t1, const double p1,
                        const datetime t2, const double p2,
                        const color clr, const ENUM_LINE_STYLE style = STYLE_SOLID,
                        const int width = 2);

   // ثبت ناحیه در آرایه
   void RegisterZone(const string name, const string label, const string type,
                     const double high, const double low,
                     const datetime startTime, const datetime endTime,
                     const color clr, const double score);

public:
   CDrawManager(const string symbol);
   ~CDrawManager();

   // رسم Order Block اصلی
   bool DrawOrderBlock(const double high, const double low,
                       const datetime barTime, const bool isBullish,
                       const double score = 50.0);

   // رسم Breaker Block
   bool DrawBreakerBlock(const double high, const double low,
                         const datetime barTime, const bool isBullish);

   // رسم Rejection Block
   bool DrawRejectionBlock(const double high, const double low,
                           const datetime barTime, const bool isBullish);

   // رسم Mitigation Block
   bool DrawMitigationBlock(const double high, const double low,
                            const datetime barTime, const bool isBullish);

   // رسم Fair Value Gap
   bool DrawFVG(const double high, const double low,
                const datetime barTime, const bool isBullish,
                const bool isInverse = false);

   // رسم BOS
   bool DrawBOS(const double price, const datetime fromTime,
                const datetime toTime, const bool isBullish);

   // رسم CHOCH
   bool DrawCHOCH(const double price, const datetime fromTime,
                  const datetime toTime, const bool isBullish);

   // رسم MSS
   bool DrawMSS(const double price, const datetime fromTime,
                const datetime toTime, const bool isBullish);

   // رسم Swing Point
   bool DrawSwingPoint(const double price, const datetime barTime,
                       const string type);

   // رسم Liquidity Zone
   bool DrawLiquidity(const double price, const datetime barTime,
                      const string type, const bool isSweep = false);

   // رسم Liquidity Sweep
   bool DrawLiquiditySweep(const double price, const datetime sweepTime,
                           const bool isBullish);

   // رسم Premium/Discount/Equilibrium
   bool DrawPremiumDiscount(const double rangeHigh, const double rangeLow,
                            const double equilibrium, const datetime fromTime);

   // رسم Session Range
   bool DrawSessionRange(const string sessionName, const datetime sessionOpen,
                         const double sessionHigh, const double sessionLow);

   // رسم Kill Zone
   bool DrawKillZone(const string kzName, const datetime kzOpen,
                     const datetime kzClose);

   // رسم سیگنال کامل
   bool DrawSignal(const double entry, const double sl,
                   const double tp1, const double tp2,
                   const double tp3, const string direction,
                   const int score);

   // پاک کردن همه
   void ClearAll();

   // پاک کردن بر اساس نوع
   void ClearByType(const string type);

   // به‌روزرسانی نواحی منقضی
   void UpdateZones();

   // رفرش چارت
   void Refresh();

   // تعداد نواحی فعال
   int GetZoneCount() { return m_zoneCount; }
};

//+------------------------------------------------------------------+
CDrawManager::CDrawManager(const string symbol) {
   m_symbol    = symbol;
   m_nextId    = 0;
   m_zoneCount = 0;
   ArrayResize(m_zones, 0);
}
CDrawManager::~CDrawManager() { ClearAll(); }

string CDrawManager::GenerateName(const string prefix) {
   m_nextId++;
   return StringFormat("B12_%s_%d_%d", prefix, m_nextId, (int)TimeCurrent());
}
bool CDrawManager::ObjectExists(const string name) {
   return ObjectFind(0, name) >= 0;
}

bool CDrawManager::CreateFilledRect(const string name,
                                     const datetime t1, const double p1,
                                     const datetime t2, const double p2,
                                     const color clr, const bool back) {
   if(ObjectExists(name)) ObjectDelete(0, name);
   if(!ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2)) return false;
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_FILL,       true);
   ObjectSetInteger(0, name, OBJPROP_BACK,       back);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN,     true);
   ObjectSetInteger(0, name, OBJPROP_WIDTH,      1);
   return true;
}

bool CDrawManager::CreateLabel(const string name, const datetime t,
                                const double p, const string text,
                                const color clr, const int fontSize) {
   if(ObjectExists(name)) ObjectDelete(0, name);
   if(!ObjectCreate(0, name, OBJ_TEXT, 0, t, p)) return false;
   ObjectSetString(0, name,  OBJPROP_TEXT,       text);
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,   fontSize);
   ObjectSetString(0, name,  OBJPROP_FONT,       "Arial Bold");
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN,     true);
   return true;
}

bool CDrawManager::CreateTrendLine(const string name,
                                    const datetime t1, const double p1,
                                    const datetime t2, const double p2,
                                    const color clr,
                                    const ENUM_LINE_STYLE style,
                                    const int width) {
   if(ObjectExists(name)) ObjectDelete(0, name);
   if(!ObjectCreate(0, name, OBJ_TREND, 0, t1, p1, t2, p2)) return false;
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE,      style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH,      width);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT,  false);
   ObjectSetInteger(0, name, OBJPROP_BACK,       false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN,     true);
   return true;
}

void CDrawManager::RegisterZone(const string name, const string label,
                                  const string type,
                                  const double high, const double low,
                                  const datetime startTime, const datetime endTime,
                                  const color clr, const double score) {
   int size = ArraySize(m_zones);
   ArrayResize(m_zones, size + 1);
   m_zones[size].name      = name;
   m_zones[size].labelName = label;
   m_zones[size].type      = type;
   m_zones[size].high      = high;
   m_zones[size].low       = low;
   m_zones[size].startTime = startTime;
   m_zones[size].endTime   = endTime;
   m_zones[size].zoneColor = clr;
   m_zones[size].isActive  = true;
   m_zones[size].score     = score;
   m_zoneCount++;
}

//+------------------------------------------------------------------+
//| رسم Order Block اصلی                                             |
//+------------------------------------------------------------------+
bool CDrawManager::DrawOrderBlock(const double high, const double low,
                                   const datetime barTime,
                                   const bool isBullish,
                                   const double score) {
   color  clr     = isBullish ? COLOR_OB_BULL : COLOR_OB_BEAR;
   string typeStr = isBullish ? "OB↑" : "OB↓";
   datetime endTime = barTime + PeriodSeconds(PERIOD_CURRENT) * 200;
   string name  = GenerateName("OB");
   string label = name + "_L";
   if(!CreateFilledRect(name, barTime, high, endTime, low, clr)) return false;
   CreateLabel(label, barTime, high, StringFormat("%s %.0f", typeStr, score), clr, 8);
   RegisterZone(name, label, "OB", high, low, barTime, endTime, clr, score);
   LogMessage(StringFormat("OB رسم: %s | %.5f-%.5f | امتیاز:%.0f", typeStr, low, high, score), "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| رسم Breaker Block                                                |
//+------------------------------------------------------------------+
bool CDrawManager::DrawBreakerBlock(const double high, const double low,
                                     const datetime barTime, const bool isBullish) {
   datetime endTime = barTime + PeriodSeconds(PERIOD_CURRENT) * 150;
   string name  = GenerateName("BB");
   string label = name + "_L";
   string typeStr = isBullish ? "BB↑" : "BB↓";
   if(!CreateFilledRect(name, barTime, high, endTime, low, COLOR_OB_BREAKER)) return false;
   CreateLabel(label, barTime, high, typeStr, COLOR_OB_BREAKER, 8);
   RegisterZone(name, label, "BB", high, low, barTime, endTime, COLOR_OB_BREAKER, 60.0);
   LogMessage(StringFormat("Breaker Block: %s | %.5f-%.5f", typeStr, low, high), "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| رسم Rejection Block                                              |
//+------------------------------------------------------------------+
bool CDrawManager::DrawRejectionBlock(const double high, const double low,
                                       const datetime barTime, const bool isBullish) {
   datetime endTime = barTime + PeriodSeconds(PERIOD_CURRENT) * 100;
   string name  = GenerateName("RB");
   string label = name + "_L";
   if(!CreateFilledRect(name, barTime, high, endTime, low, COLOR_OB_REJECTION)) return false;
   CreateLabel(label, barTime, high, isBullish ? "RB↑" : "RB↓", COLOR_OB_REJECTION, 8);
   RegisterZone(name, label, "RB", high, low, barTime, endTime, COLOR_OB_REJECTION, 45.0);
   return true;
}

//+------------------------------------------------------------------+
//| رسم Mitigation Block                                             |
//+------------------------------------------------------------------+
bool CDrawManager::DrawMitigationBlock(const double high, const double low,
                                        const datetime barTime, const bool isBullish) {
   datetime endTime = barTime + PeriodSeconds(PERIOD_CURRENT) * 50;
   string name  = GenerateName("MB");
   string label = name + "_L";
   if(!CreateFilledRect(name, barTime, high, endTime, low, COLOR_OB_MITIGATION)) return false;
   CreateLabel(label, barTime, high, isBullish ? "MB↑" : "MB↓", COLOR_OB_MITIGATION, 7);
   RegisterZone(name, label, "MB", high, low, barTime, endTime, COLOR_OB_MITIGATION, 30.0);
   return true;
}

//+------------------------------------------------------------------+
//| رسم Fair Value Gap                                               |
//+------------------------------------------------------------------+
bool CDrawManager::DrawFVG(const double high, const double low,
                            const datetime barTime, const bool isBullish,
                            const bool isInverse) {
   color  clr;
   string typeStr;
   if(isInverse) {
      clr     = COLOR_FVG_INVERSE;
      typeStr = isBullish ? "IFVG↑" : "IFVG↓";
   } else {
      clr     = isBullish ? COLOR_FVG_BULL : COLOR_FVG_BEAR;
      typeStr = isBullish ? "FVG↑" : "FVG↓";
   }
   datetime endTime = barTime + PeriodSeconds(PERIOD_CURRENT) * 150;
   string name  = GenerateName(isInverse ? "IFVG" : "FVG");
   string label = name + "_L";
   if(!CreateFilledRect(name, barTime, high, endTime, low, clr)) return false;
   CreateLabel(label, barTime, isBullish ? high : low, typeStr, clr, 8);
   RegisterZone(name, label, isInverse ? "IFVG" : "FVG", high, low, barTime, endTime, clr, 55.0);
   LogMessage(StringFormat("%s رسم: %.5f-%.5f", typeStr, low, high), "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| رسم Break of Structure                                           |
//+------------------------------------------------------------------+
bool CDrawManager::DrawBOS(const double price, const datetime fromTime,
                            const datetime toTime, const bool isBullish) {
   string name  = GenerateName("BOS");
   string label = name + "_L";
   string text  = isBullish ? "BOS ↑" : "BOS ↓";
   if(!CreateTrendLine(name, fromTime, price, toTime, price, COLOR_BOS, STYLE_SOLID, 2)) return false;
   datetime labelTime = fromTime + (toTime - fromTime) / 2;
   CreateLabel(label, labelTime, price, text, COLOR_BOS, 9);
   string arrowName = name + "_A";
   if(!ObjectExists(arrowName)) {
      ObjectCreate(0, arrowName, OBJ_ARROW, 0, toTime, price);
      ObjectSetInteger(0, arrowName, OBJPROP_ARROWTYPE, isBullish ? ARROW_UP : ARROW_DOWN);
      ObjectSetInteger(0, arrowName, OBJPROP_COLOR, COLOR_BOS);
      ObjectSetInteger(0, arrowName, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, arrowName, OBJPROP_SELECTABLE, false);
   }
   LogMessage(StringFormat("BOS رسم: %s | سطح: %.5f", text, price), "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| رسم Change of Character                                          |
//+------------------------------------------------------------------+
bool CDrawManager::DrawCHOCH(const double price, const datetime fromTime,
                              const datetime toTime, const bool isBullish) {
   string name  = GenerateName("CHOCH");
   string label = name + "_L";
   string text  = isBullish ? "CHoCH ↑" : "CHoCH ↓";
   if(!CreateTrendLine(name, fromTime, price, toTime, price, COLOR_CHOCH, STYLE_DASH, 2)) return false;
   datetime labelTime = fromTime + (toTime - fromTime) / 3;
   CreateLabel(label, labelTime, price, text, COLOR_CHOCH, 9);
   string arrowName = name + "_A";
   if(!ObjectExists(arrowName)) {
      ObjectCreate(0, arrowName, OBJ_ARROW, 0, toTime, price);
      ObjectSetInteger(0, arrowName, OBJPROP_ARROWTYPE, isBullish ? ARROW_UP : ARROW_DOWN);
      ObjectSetInteger(0, arrowName, OBJPROP_COLOR, COLOR_CHOCH);
      ObjectSetInteger(0, arrowName, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, arrowName, OBJPROP_SELECTABLE, false);
   }
   LogMessage(StringFormat("CHOCH رسم: %s | سطح: %.5f", text, price), "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| رسم Market Structure Shift                                       |
//+------------------------------------------------------------------+
bool CDrawManager::DrawMSS(const double price, const datetime fromTime,
                            const datetime toTime, const bool isBullish) {
   string name  = GenerateName("MSS");
   string label = name + "_L";
   string text  = isBullish ? "MSS ↑" : "MSS ↓";
   if(!CreateTrendLine(name, fromTime, price, toTime, price, COLOR_MSS, STYLE_DOT, 2)) return false;
   datetime labelTime = fromTime + (toTime - fromTime) / 4;
   CreateLabel(label, labelTime, price, text, COLOR_MSS, 9);
   LogMessage(StringFormat("MSS رسم: %s | سطح: %.5f", text, price), "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| رسم Swing Point                                                   |
//+------------------------------------------------------------------+
bool CDrawManager::DrawSwingPoint(const double price, const datetime barTime,
                                   const string type) {
   bool   isHigh = (type == "High");
   string name   = GenerateName("SW");
   if(!ObjectExists(name)) {
      if(!ObjectCreate(0, name, OBJ_ARROW, 0, barTime, price)) return false;
      ObjectSetInteger(0, name, OBJPROP_ARROWTYPE, isHigh ? ARROW_DOWN : ARROW_UP);
      ObjectSetInteger(0, name, OBJPROP_COLOR,     isHigh ? COLOR_SWING_HIGH : COLOR_SWING_LOW);
      ObjectSetInteger(0, name, OBJPROP_WIDTH,     2);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR,    isHigh ? ANCHOR_LOWER : ANCHOR_UPPER);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE,false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN,    true);
   }
   string label = name + "_L";
   CreateLabel(label, barTime, price, isHigh ? "HH" : "LL",
               isHigh ? COLOR_SWING_HIGH : COLOR_SWING_LOW, 7);
   return true;
}

//+------------------------------------------------------------------+
//| رسم Liquidity Zone                                               |
//+------------------------------------------------------------------+
bool CDrawManager::DrawLiquidity(const double price, const datetime barTime,
                                  const string type, const bool isSweep) {
   string name  = GenerateName("LQ");
   string label = name + "_L";
   color  clr   = isSweep ? COLOR_LIQ_SWEEP : COLOR_LIQUIDITY;
   if(ObjectExists(name)) ObjectDelete(0, name);
   if(!ObjectCreate(0, name, OBJ_HLINE, 0, 0, price)) return false;
   ObjectSetInteger(0, name, OBJPROP_COLOR,      clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE,      isSweep ? STYLE_SOLID : STYLE_DASH);
   ObjectSetInteger(0, name, OBJPROP_WIDTH,      isSweep ? 2 : 1);
   ObjectSetInteger(0, name, OBJPROP_BACK,       true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   CreateLabel(label, barTime, price, isSweep ? "⚡" + type + " SWEPT" : type, clr, 8);
   return true;
}

//+------------------------------------------------------------------+
//| رسم Liquidity Sweep                                              |
//+------------------------------------------------------------------+
bool CDrawManager::DrawLiquiditySweep(const double price,
                                       const datetime sweepTime,
                                       const bool isBullish) {
   string name = GenerateName("LSW");
   if(!ObjectExists(name)) {
      if(!ObjectCreate(0, name, OBJ_ARROW, 0, sweepTime, price)) return false;
      ObjectSetInteger(0, name, OBJPROP_ARROWTYPE, isBullish ? ARROW_UP : ARROW_DOWN);
      ObjectSetInteger(0, name, OBJPROP_COLOR,     COLOR_LIQ_SWEEP);
      ObjectSetInteger(0, name, OBJPROP_WIDTH,     3);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE,false);
   }
   string label = name + "_L";
   CreateLabel(label, sweepTime, price, isBullish ? "⚡LSW↑" : "⚡LSW↓", COLOR_LIQ_SWEEP, 9);
   LogMessage(StringFormat("Liquidity Sweep: %.5f", price), "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| رسم Premium / Discount / Equilibrium                             |
//+------------------------------------------------------------------+
bool CDrawManager::DrawPremiumDiscount(const double rangeHigh,
                                        const double rangeLow,
                                        const double equilibrium,
                                        const datetime fromTime) {
   datetime toTime = TimeCurrent() + PeriodSeconds(PERIOD_CURRENT) * 100;
   double   mid    = (rangeHigh + rangeLow) / 2.0;
   double   p75    = rangeLow + (rangeHigh - rangeLow) * 0.75;
   double   p25    = rangeLow + (rangeHigh - rangeLow) * 0.25;
   string premName  = GenerateName("PREM");
   string premLabel = premName + "_L";
   CreateFilledRect(premName, fromTime, rangeHigh, toTime, mid, COLOR_PREMIUM, true);
   CreateLabel(premLabel, fromTime, p75, "PREMIUM", COLOR_PREMIUM, 8);
   string discName  = GenerateName("DISC");
   string discLabel = discName + "_L";
   CreateFilledRect(discName, fromTime, mid, toTime, rangeLow, COLOR_DISCOUNT, true);
   CreateLabel(discLabel, fromTime, p25, "DISCOUNT", COLOR_DISCOUNT, 8);
   string eqName = GenerateName("EQ");
   if(ObjectExists(eqName)) ObjectDelete(0, eqName);
   ObjectCreate(0, eqName, OBJ_HLINE, 0, 0, equilibrium);
   ObjectSetInteger(0, eqName, OBJPROP_COLOR,      COLOR_EQUILIBRIUM);
   ObjectSetInteger(0, eqName, OBJPROP_STYLE,      STYLE_DASHDOTDOT);
   ObjectSetInteger(0, eqName, OBJPROP_WIDTH,      1);
   ObjectSetInteger(0, eqName, OBJPROP_BACK,       true);
   ObjectSetInteger(0, eqName, OBJPROP_SELECTABLE, false);
   string eqLabel = eqName + "_L";
   CreateLabel(eqLabel, fromTime, equilibrium,
      StringFormat("EQ %.5f", equilibrium), COLOR_EQUILIBRIUM, 8);
   RegisterZone(premName, premLabel, "PREMIUM", rangeHigh, mid, fromTime, toTime, COLOR_PREMIUM, 0);
   RegisterZone(discName, discLabel, "DISCOUNT", mid, rangeLow, fromTime, toTime, COLOR_DISCOUNT, 0);
   LogMessage(StringFormat("PD رسم: H=%.5f EQ=%.5f L=%.5f", rangeHigh, equilibrium, rangeLow), "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| رسم Session Range                                                |
//+------------------------------------------------------------------+
bool CDrawManager::DrawSessionRange(const string sessionName,
                                     const datetime sessionOpen,
                                     const double sessionHigh,
                                     const double sessionLow) {
   datetime sessionClose = sessionOpen + 8 * 3600;
   string name  = GenerateName("SESS");
   string label = name + "_L";
   if(!CreateFilledRect(name, sessionOpen, sessionHigh,
                        sessionClose, sessionLow, COLOR_SESSION, true)) return false;
   CreateLabel(label, sessionOpen, sessionHigh, "🕐 " + sessionName, COLOR_SESSION, 8);
   string highLineName = name + "_H";
   string lowLineName  = name + "_L2";
   if(ObjectExists(highLineName)) ObjectDelete(0, highLineName);
   ObjectCreate(0, highLineName, OBJ_TREND, 0, sessionOpen, sessionHigh, sessionClose, sessionHigh);
   ObjectSetInteger(0, highLineName, OBJPROP_COLOR,      COLOR_LIQUIDITY);
   ObjectSetInteger(0, highLineName, OBJPROP_STYLE,      STYLE_DASH);
   ObjectSetInteger(0, highLineName, OBJPROP_WIDTH,      1);
   ObjectSetInteger(0, highLineName, OBJPROP_SELECTABLE, false);
   if(ObjectExists(lowLineName)) ObjectDelete(0, lowLineName);
   ObjectCreate(0, lowLineName, OBJ_TREND, 0, sessionOpen, sessionLow, sessionClose, sessionLow);
   ObjectSetInteger(0, lowLineName, OBJPROP_COLOR,      COLOR_LIQUIDITY);
   ObjectSetInteger(0, lowLineName, OBJPROP_STYLE,      STYLE_DASH);
   ObjectSetInteger(0, lowLineName, OBJPROP_WIDTH,      1);
   ObjectSetInteger(0, lowLineName, OBJPROP_SELECTABLE, false);
   RegisterZone(name, label, "SESSION", sessionHigh, sessionLow,
                sessionOpen, sessionClose, COLOR_SESSION, 0);
   LogMessage(StringFormat("Session رسم: %s | %.5f-%.5f", sessionName, sessionLow, sessionHigh), "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| رسم Kill Zone                                                     |
//+------------------------------------------------------------------+
bool CDrawManager::DrawKillZone(const string kzName,
                                 const datetime kzOpen,
                                 const datetime kzClose) {
   double high = iHigh(m_symbol, PERIOD_CURRENT, 0) * 1.001;
   double low  = iLow(m_symbol,  PERIOD_CURRENT, 0) * 0.999;
   string name  = GenerateName("KZ");
   string label = name + "_L";
   if(!CreateFilledRect(name, kzOpen, high, kzClose, low, COLOR_KILL_ZONE, true)) return false;
   double mid = (high + low) / 2.0;
   CreateLabel(label, kzOpen, high, "🎯 " + kzName, clrGold, 9);
   RegisterZone(name, label, "KZ", high, low, kzOpen, kzClose, COLOR_KILL_ZONE, 0);
   LogMessage("Kill Zone رسم: " + kzName, "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| رسم سیگنال کامل با SL/TP چندگانه                                 |
//+------------------------------------------------------------------+
bool CDrawManager::DrawSignal(const double entry, const double sl,
                               const double tp1, const double tp2,
                               const double tp3, const string direction,
                               const int score) {
   bool   isBuy     = (direction == "buy");
   color  entryClr  = isBuy ? COLOR_ENTRY_BUY : COLOR_ENTRY_SELL;
   datetime now     = TimeCurrent();
   string entryName = GenerateName("ENT");
   if(ObjectExists(entryName)) ObjectDelete(0, entryName);
   ObjectCreate(0, entryName, OBJ_HLINE, 0, 0, entry);
   ObjectSetInteger(0, entryName, OBJPROP_COLOR, entryClr);
   ObjectSetInteger(0, entryName, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, entryName, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, entryName, OBJPROP_SELECTABLE, false);
   string entryLabel = entryName + "_L";
   CreateLabel(entryLabel, now, entry,
      StringFormat("%s ENTRY %.5f [%d/100]", isBuy ? "▲ BUY" : "▼ SELL", entry, score),
      entryClr, 10);
   string slName = GenerateName("SL");
   if(ObjectExists(slName)) ObjectDelete(0, slName);
   ObjectCreate(0, slName, OBJ_HLINE, 0, 0, sl);
   ObjectSetInteger(0, slName, OBJPROP_COLOR, COLOR_SL);
   ObjectSetInteger(0, slName, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, slName, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, slName, OBJPROP_SELECTABLE, false);
   CreateLabel(slName + "_L", now, sl, StringFormat("SL %.5f", sl), COLOR_SL, 9);
   if(tp1 > 0) {
      string tp1n = GenerateName("TP1");
      ObjectCreate(0, tp1n, OBJ_HLINE, 0, 0, tp1);
      ObjectSetInteger(0, tp1n, OBJPROP_COLOR, COLOR_TP);
      ObjectSetInteger(0, tp1n, OBJPROP_STYLE, STYLE_DASH);
      ObjectSetInteger(0, tp1n, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, tp1n, OBJPROP_SELECTABLE, false);
      CreateLabel(tp1n + "_L", now, tp1, StringFormat("TP1 %.5f", tp1), COLOR_TP, 9);
   }
   if(tp2 > 0) {
      string tp2n = GenerateName("TP2");
      ObjectCreate(0, tp2n, OBJ_HLINE, 0, 0, tp2);
      ObjectSetInteger(0, tp2n, OBJPROP_COLOR, clrGreenYellow);
      ObjectSetInteger(0, tp2n, OBJPROP_STYLE, STYLE_DASHDOT);
      ObjectSetInteger(0, tp2n, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, tp2n, OBJPROP_SELECTABLE, false);
      CreateLabel(tp2n + "_L", now, tp2, StringFormat("TP2 %.5f", tp2), clrGreenYellow, 9);
   }
   if(tp3 > 0) {
      string tp3n = GenerateName("TP3");
      ObjectCreate(0, tp3n, OBJ_HLINE, 0, 0, tp3);
      ObjectSetInteger(0, tp3n, OBJPROP_COLOR, clrLimeGreen);
      ObjectSetInteger(0, tp3n, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetInteger(0, tp3n, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, tp3n, OBJPROP_SELECTABLE, false);
      CreateLabel(tp3n + "_L", now, tp3, StringFormat("TP3 %.5f", tp3), clrLimeGreen, 9);
   }
   LogMessage(StringFormat("سیگنال رسم: %s | Entry:%.5f SL:%.5f TP1:%.5f Score:%d",
      direction, entry, sl, tp1, score), "DRAW");
   return true;
}

//+------------------------------------------------------------------+
//| پاک کردن همه آبجکت‌ها                                            |
//+------------------------------------------------------------------+
void CDrawManager::ClearAll() {
   for(int i = ObjectsTotal(0, 0, -1) - 1; i >= 0; i--) {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, "B12_") == 0)
         ObjectDelete(0, name);
   }
   ArrayResize(m_zones, 0);
   m_zoneCount = 0;
   ChartRedraw(0);
   LogMessage("تمام رسم‌ها پاک شدند", "DRAW");
}

//+------------------------------------------------------------------+
//| پاک کردن بر اساس نوع                                             |
//+------------------------------------------------------------------+
void CDrawManager::ClearByType(const string type) {
   for(int i = ArraySize(m_zones) - 1; i >= 0; i--) {
      if(m_zones[i].type == type) {
         ObjectDelete(0, m_zones[i].name);
         ObjectDelete(0, m_zones[i].labelName);
         for(int j = i; j < ArraySize(m_zones) - 1; j++)
            m_zones[j] = m_zones[j + 1];
         ArrayResize(m_zones, ArraySize(m_zones) - 1);
         m_zoneCount--;
      }
   }
}

//+------------------------------------------------------------------+
//| به‌روزرسانی نواحی منقضی                                          |
//+------------------------------------------------------------------+
void CDrawManager::UpdateZones() {
   datetime now = TimeCurrent();
   for(int i = ArraySize(m_zones) - 1; i >= 0; i--) {
      if(m_zones[i].endTime > 0 && m_zones[i].endTime < now) {
         ObjectDelete(0, m_zones[i].name);
         ObjectDelete(0, m_zones[i].labelName);
         for(int j = i; j < ArraySize(m_zones) - 1; j++)
            m_zones[j] = m_zones[j + 1];
         ArrayResize(m_zones, ArraySize(m_zones) - 1);
         m_zoneCount--;
      }
   }
}

//+------------------------------------------------------------------+
//| رفرش چارت                                                        |
//+------------------------------------------------------------------+
void CDrawManager::Refresh() {
   UpdateZones();
   ChartRedraw(0);
}
//+------------------------------------------------------------------+
