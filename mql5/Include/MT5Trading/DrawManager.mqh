//+------------------------------------------------------------------+
//|                                                    DrawManager.mqh |
//|                                    MT5 Trading System             |
//|                                    مدیریت رسم نمودار               |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"

//+
// ثابت‌های رسم
//+
#define DRAW_NONE 0
#define DRAW_LINE 1
#define DRAW_HISTOGRAM 2
#define DRAW_ARROW 3
#define DRAW_SECTION 4

// رنگ‌های پیش‌فرض
color COLOR_BULLISH = clrLime;
color COLOR_BEARISH = clrRed;
color COLOR_NEUTRAL = clrGray;
color COLOR_OB_BULL = clrDodgerBlue;
color COLOR_OB_BEAR = clrCrimson;
color COLOR_FVG_BULL = clrAqua;
color COLOR_FVG_BEAR = clrMagenta;
color COLOR_LIQUIDITY = clrGold;
color COLOR_BOS = clrYellow;
color COLOR_CHOCH = clrOrange;

//+
// ساختارهای داده رسم
//+

// ساختار ناحیه رسم
struct DrawZone {
   string name;
   string type;
   double high;
   double low;
   datetime startTime;
   datetime endTime;
   color zoneColor;
   int width;
   bool filled;
   string label;
   bool isActive;
};

// ساختار خط رسم
struct DrawLine {
   string name;
   string type;
   double price;
   color lineColor;
   int style;
   int width;
   string label;
   bool showArrow;
};

// ساختار برچسب رسم
struct DrawLabel {
   string name;
   double price;
   int bar;
   string text;
   color textColor;
   int fontSize;
   string fontName;
   int corner;
   int xOffset;
   int yOffset;
};

//+
// کلاس مدیریت رسم
//+
class CDrawManager {
private:
   string m_symbol;
   int m_nextId;

   // آرایه‌های نگهداری
   DrawZone m_zones[];
   DrawLine m_lines[];
   DrawLabel m_labels[];

   // توابع کمکی
   string GenerateName(const string prefix);
   bool ObjectExists(const string name);
   void RemoveExpiredObjects();

public:
   CDrawManager(const string symbol);
   ~CDrawManager();

   // رسم نواحی
   bool DrawOrderBlock(const double high, const double low, const int bar, const string type);
   bool DrawFVG(const double high, const double low, const int bar, const bool isBullish);
   bool DrawLiquidityZone(const double price, const int bar, const string type);
   bool DrawSwingPoint(const double price, const int bar, const string type);

   // رسم خطوط
   bool DrawBOS(const double price, const int bar);
   bool DrawCHOCH(const double price, const int bar);
   bool DrawMSS(const double price, const int bar);
   bool DrawEquilibrium(const double price, const int bar);
   bool DrawSupport(const double price);
   bool DrawResistance(const double price);

   // رسم سیگنال
   bool DrawSignal(
      const double entry,
      const double sl,
      const double tp,
      const string direction,
      const int score
   );

   // مدیریت
   void ClearAll();
   void ClearZones();
   void ClearLines();
   void ClearLabels();
   void UpdateZones();
   void Refresh();

   // گرفتن اطلاعات
   int GetZoneCount();
   int GetLineCount();
};

//+
// سازنده
//+
CDrawManager::CDrawManager(const string symbol) {
   m_symbol = symbol;
   m_nextId = 0;

   ArraySetAsSeries(m_zones, false);
   ArraySetAsSeries(m_lines, false);
   ArraySetAsSeries(m_labels, false);
}

//+
// مخرب
//+
CDrawManager::~CDrawManager() {
   ClearAll();
}

//+
// تولید نام یکتا
//+
string CDrawManager::GenerateName(const string prefix) {
   m_nextId++;
   return StringFormat("MT5_%s_%d_%d", prefix, m_nextId, TimeCurrent());
}

//+
// بررسی وجود آبجکت
//+
bool CDrawManager::ObjectExists(const string name) {
   return ObjectFind(0, name) >= 0;
}

//+
// رسم Order Block
//+
bool CDrawManager::DrawOrderBlock(
   const double high,
   const double low,
   const int bar,
   const string type
) {
   string name = GenerateName("OB");
   datetime time1 = iTime(m_symbol, PERIOD_CURRENT, bar);
   datetime time2 = TimeCurrent() + PeriodSeconds() * 500;  // 500 کندل جلوتر

   color obColor = (type == "bullish") ? COLOR_OB_BULL : COLOR_OB_BEAR;

   // ایجاد مستطیل
   if(!ObjectCreate(0, name, OBJ_RECTANGLE, 0, time1, high, time2, low)) {
      LogMessage("خطا در رسم Order Block: " + IntegerToString(GetLastError()), "ERROR");
      return false;
   }

   // تنظیمات ظاهری
   ObjectSetInteger(0, name, OBJPROP_COLOR, obColor);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);

   // تنظیم شفافیت
   ObjectSetInteger(0, name, OBJPROP_COLOR, clrNONE);
   long clrValue = ObjectGetInteger(0, name, OBJPROP_COLOR);
   // استفاده از颜色 با شفافیت
   ObjectSetInteger(0, name, OBJPROP_COLOR, obColor);

   // برچسب
   string labelName = name + "_Label";
   ObjectCreate(0, labelName, OBJ_TEXT, 0, time1, high);
   ObjectSetString(0, labelName, OBJPROP_TEXT, type == "bullish" ? "OB ↑" : "OB ↓");
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, obColor);
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 8);
   ObjectSetString(0, labelName, OBJPROP_FONT, "Arial");

   // ذخیره
   DrawZone zone;
   zone.name = name;
   zone.type = "OrderBlock";
   zone.high = high;
   zone.low = low;
   zone.startTime = time1;
   zone.endTime = time2;
   zone.zoneColor = obColor;
   zone.isActive = true;

   int size = ArraySize(m_zones);
   ArrayResize(m_zones, size + 1);
   m_zones[size] = zone;

   LogMessage(StringFormat("OB رسم شد: %s | %.5f - %.5f", type, low, high), "DRAW");

   return true;
}

//+
// رسم FVG
//+
bool CDrawManager::DrawFVG(
   const double high,
   const double low,
   const int bar,
   const bool isBullish
) {
   string name = GenerateName("FVG");
   datetime time1 = iTime(m_symbol, PERIOD_CURRENT, bar);
   datetime time2 = TimeCurrent() + PeriodSeconds() * 300;

   color fvgColor = isBullish ? COLOR_FVG_BULL : COLOR_FVG_BEAR;

   // ایجاد مستطیل
   if(!ObjectCreate(0, name, OBJ_RECTANGLE, 0, time1, high, time2, low)) {
      return false;
   }

   ObjectSetInteger(0, name, OBJPROP_COLOR, fvgColor);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);

   // برچسب
   string labelName = name + "_Label";
   ObjectCreate(0, labelName, OBJ_TEXT, 0, time1, isBullish ? high : low);
   ObjectSetString(0, labelName, OBJPROP_TEXT, isBullish ? "FVG ↑" : "FVG ↓");
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, fvgColor);
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 8);

   // ذخیره
   DrawZone zone;
   zone.name = name;
   zone.type = "FVG";
   zone.high = high;
   zone.low = low;
   zone.startTime = time1;
   zone.zoneColor = fvgColor;
   zone.isActive = true;

   int size = ArraySize(m_zones);
   ArrayResize(m_zones, size + 1);
   m_zones[size] = zone;

   LogMessage(StringFormat("FVG رسم شد: %s | %.5f - %.5f",
      isBullish ? "Bullish" : "Bearish", low, high), "DRAW");

   return true;
}

//+
// رسم ناحیه لیکوییدیتی
//+
bool CDrawManager::DrawLiquidityZone(
   const double price,
   const int bar,
   const string type
) {
   string name = GenerateName("LIQ");
   datetime time = iTime(m_symbol, PERIOD_CURRENT, bar);

   // ایجاد خط
   if(!ObjectCreate(0, name, OBJ_HLINE, 0, 0, price)) {
      return false;
   }

   ObjectSetInteger(0, name, OBJPROP_COLOR, COLOR_LIQUIDITY);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);

   // برچسب
   string labelName = name + "_Label";
   ObjectCreate(0, labelName, OBJ_TEXT, 0, time, price);
   ObjectSetString(0, labelName, OBJPROP_TEXT, "LQ " + type);
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, COLOR_LIQUIDITY);
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 8);

   return true;
}

//+
// رسم نقطه سویینگ
//+
bool CDrawManager::DrawSwingPoint(
   const double price,
   const int bar,
   const string type
) {
   string name = GenerateName("SWING");
   datetime time = iTime(m_symbol, PERIOD_CURRENT, bar);

   // تعیین فلش
   ENUM_ARROW_TYPE arrowType = (type == "high") ? ARROW_DOWN : ARROW_UP;
   color arrowColor = (type == "high") ? COLOR_BEARISH : COLOR_BULLISH;

   // ایجاد فلش
   if(!ObjectCreate(0, name, OBJ_ARROW, 0, time, price)) {
      return false;
   }

   ObjectSetInteger(0, name, OBJPROP_ARROWTYPE, arrowType);
   ObjectSetInteger(0, name, OBJPROP_COLOR, arrowColor);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR,
      type == "high" ? ANCHOR_LOWER : ANCHOR_UPPER);

   return true;
}

//+
// رسم BOS
//+
bool CDrawManager::DrawBOS(const double price, const int bar) {
   string name = GenerateName("BOS");
   datetime time = iTime(m_symbol, PERIOD_CURRENT, bar);

   // ایجاد خط
   if(!ObjectCreate(0, name, OBJ_TREND, 0, time, price, TimeCurrent(), price)) {
      return false;
   }

   ObjectSetInteger(0, name, OBJPROP_COLOR, COLOR_BOS);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);

   // برچسب
   string labelName = name + "_Label";
   ObjectCreate(0, labelName, OBJ_TEXT, 0, time, price);
   ObjectSetString(0, labelName, OBJPROP_TEXT, "BOS");
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, COLOR_BOS);
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 10);
   ObjectSetString(0, labelName, OBJPROP_FONT, "Arial Bold");

   LogMessage("BOS رسم شد: " + DoubleToString(price, 5), "DRAW");

   return true;
}

//+
// رسم CHOCH
//+
bool CDrawManager::DrawCHOCH(const double price, const int bar) {
   string name = GenerateName("CHOCH");
   datetime time = iTime(m_symbol, PERIOD_CURRENT, bar);

   // ایجاد خط
   if(!ObjectCreate(0, name, OBJ_TREND, 0, time, price, TimeCurrent(), price)) {
      return false;
   }

   ObjectSetInteger(0, name, OBJPROP_COLOR, COLOR_CHOCH);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);

   // برچسب
   string labelName = name + "_Label";
   ObjectCreate(0, labelName, OBJ_TEXT, 0, time, price);
   ObjectSetString(0, labelName, OBJPROP_TEXT, "CHOCH");
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, COLOR_CHOCH);
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 10);
   ObjectSetString(0, labelName, OBJPROP_FONT, "Arial Bold");

   LogMessage("CHOCH رسم شد: " + DoubleToString(price, 5), "DRAW");

   return true;
}

//+
// رسم MSS
//+
bool CDrawManager::DrawMSS(const double price, const int bar) {
   string name = GenerateName("MSS");
   datetime time = iTime(m_symbol, PERIOD_CURRENT, bar);

   if(!ObjectCreate(0, name, OBJ_TREND, 0, time, price, TimeCurrent(), price)) {
      return false;
   }

   ObjectSetInteger(0, name, OBJPROP_COLOR, clrMagenta);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DOT);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);

   // برچسب
   string labelName = name + "_Label";
   ObjectCreate(0, labelName, OBJ_TEXT, 0, time, price);
   ObjectSetString(0, labelName, OBJPROP_TEXT, "MSS");
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, clrMagenta);
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 10);

   return true;
}

//+
// رسم Equilibrium
//+
bool CDrawManager::DrawEquilibrium(const double price, const int bar) {
   string name = GenerateName("EQ");
   datetime time = iTime(m_symbol, PERIOD_CURRENT, bar);

   if(!ObjectCreate(0, name, OBJ_HLINE, 0, 0, price)) {
      return false;
   }

   ObjectSetInteger(0, name, OBJPROP_COLOR, clrGray);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASHDOTDOT);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);

   // برچسب
   string labelName = name + "_Label";
   ObjectCreate(0, labelName, OBJ_TEXT, 0, time, price);
   ObjectSetString(0, labelName, OBJPROP_TEXT, "EQ");
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, clrGray);
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 8);

   return true;
}

//+
// رسم حمایت
//+
bool CDrawManager::DrawSupport(const double price) {
   string name = GenerateName("SUP");

   if(!ObjectCreate(0, name, OBJ_HLINE, 0, 0, price)) {
      return false;
   }

   ObjectSetInteger(0, name, OBJPROP_COLOR, clrGreen);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);

   return true;
}

//+
// رسم مقاومت
//+
bool CDrawManager::DrawResistance(const double price) {
   string name = GenerateName("RES");

   if(!ObjectCreate(0, name, OBJ_HLINE, 0, 0, price)) {
      return false;
   }

   ObjectSetInteger(0, name, OBJPROP_COLOR, clrRed);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);

   return true;
}

//+
// رسم سیگنال
//+
bool CDrawManager::DrawSignal(
   const double entry,
   const double sl,
   const double tp,
   const string direction,
   const int score
) {
   // رنگ بر اساس جهت
   color signalColor = (direction == "buy") ? clrLime : clrRed;

   // خط ورود
   string entryName = GenerateName("ENTRY");
   ObjectCreate(0, entryName, OBJ_HLINE, 0, 0, entry);
   ObjectSetInteger(0, entryName, OBJPROP_COLOR, signalColor);
   ObjectSetInteger(0, entryName, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, entryName, OBJPROP_WIDTH, 2);

   // برچسب ورود
   string entryLabel = entryName + "_Label";
   ObjectCreate(0, entryLabel, OBJ_TEXT, 0, TimeCurrent(), entry);
   ObjectSetString(0, entryLabel, OBJPROP_TEXT,
      StringFormat("ENTRY %s (%d/100)", direction == "buy" ? "BUY" : "SELL", score));
   ObjectSetInteger(0, entryLabel, OBJPROP_COLOR, signalColor);
   ObjectSetInteger(0, entryLabel, OBJPROP_FONTSIZE, 10);

   // خط حد ضرر
   string slName = GenerateName("SL");
   ObjectCreate(0, slName, OBJ_HLINE, 0, 0, sl);
   ObjectSetInteger(0, slName, OBJPROP_COLOR, clrRed);
   ObjectSetInteger(0, slName, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, slName, OBJPROP_WIDTH, 1);

   string slLabel = slName + "_Label";
   ObjectCreate(0, slLabel, OBJ_TEXT, 0, TimeCurrent(), sl);
   ObjectSetString(0, slLabel, OBJPROP_TEXT, "SL");
   ObjectSetInteger(0, slLabel, OBJPROP_COLOR, clrRed);
   ObjectSetInteger(0, slLabel, OBJPROP_FONTSIZE, 10);

   // خط حد سود
   string tpName = GenerateName("TP");
   ObjectCreate(0, tpName, OBJ_HLINE, 0, 0, tp);
   ObjectSetInteger(0, tpName, OBJPROP_COLOR, clrLime);
   ObjectSetInteger(0, tpName, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, tpName, OBJPROP_WIDTH, 1);

   string tpLabel = tpName + "_Label";
   ObjectCreate(0, tpLabel, OBJ_TEXT, 0, TimeCurrent(), tp);
   ObjectSetString(0, tpLabel, OBJPROP_TEXT, "TP");
   ObjectSetInteger(0, tpLabel, OBJPROP_COLOR, clrLime);
   ObjectSetInteger(0, tpLabel, OBJPROP_FONTSIZE, 10);

   LogMessage(StringFormat("سیگنال رسم شد: %s | Entry: %.5f | SL: %.5f | TP: %.5f | Score: %d",
      direction, entry, sl, tp, score), "DRAW");

   return true;
}

//+
// پاک کردن همه
//+
void CDrawManager::ClearAll() {
   ClearZones();
   ClearLines();
   ClearLabels();

   // حذف تمام آبجکت‌های MT5
   for(int i = ObjectsTotal(0, 0, -1) - 1; i >= 0; i--) {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, "MT5_") == 0) {
         ObjectDelete(0, name);
      }
   }

   LogMessage("همه رسم‌ها پاک شدند", "DRAW");
}

//+
// پاک کردن نواحی
//+
void CDrawManager::ClearZones() {
   for(int i = 0; i < ArraySize(m_zones); i++) {
      ObjectDelete(0, m_zones[i].name);
      ObjectDelete(0, m_zones[i].name + "_Label");
   }
   ArrayResize(m_zones, 0);
}

//+
// پاک کردن خطوط
//+
void CDrawManager::ClearLines() {
   for(int i = 0; i < ArraySize(m_lines); i++) {
      ObjectDelete(0, m_lines[i].name);
      ObjectDelete(0, m_lines[i].name + "_Label");
   }
   ArrayResize(m_lines, 0);
}

//+
// پاک کردن برچسب‌ها
//+
void CDrawManager::ClearLabels() {
   for(int i = 0; i < ArraySize(m_labels); i++) {
      ObjectDelete(0, m_labels[i].name);
   }
   ArrayResize(m_labels, 0);
}

//+
// به‌روزرسانی نواحی
//+
void CDrawManager::UpdateZones() {
   datetime currentTime = TimeCurrent();

   for(int i = ArraySize(m_zones) - 1; i >= 0; i--) {
      // بررسی انقضا
      if(m_zones[i].endTime < currentTime) {
         ObjectDelete(0, m_zones[i].name);
         ObjectDelete(0, m_zones[i].name + "_Label");

         // حذف از آرایه
         for(int j = i; j < ArraySize(m_zones) - 1; j++) {
            m_zones[j] = m_zones[j + 1];
         }
         ArrayResize(m_zones, ArraySize(m_zones) - 1);
      }
   }
}

//+
// رفرش
//+
void CDrawManager::Refresh() {
   UpdateZones();
   ChartRedraw(0);
}

//+
// دریافت تعداد نواحی
//+
int CDrawManager::GetZoneCount() {
   return ArraySize(m_zones);
}

//+
// دریافت تعداد خطوط
//+
int CDrawManager::GetLineCount() {
   return ArraySize(m_lines);
}
//+------------------------------------------------------------------+
