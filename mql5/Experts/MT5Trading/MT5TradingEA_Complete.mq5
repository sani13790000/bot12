//+------------------------------------------------------------------+
//| Galaxy Vast AI Trading Platform                                    |
//| MT5TradingEA_Complete.mq5                                         |
//|                                                                    |
//| Expert Advisor اصلی — نسخه کامل                                  |
//|                                                                    |
//| وظایف:                                                             |
//|   - اتصال به backend API از طریق WebRequest                       |
//|   - دریافت سیگنال و اجرای معامله روی MT5                         |
//|   - مدیریت لایسنس و heartbeat هر ۵ دقیقه                         |
//|   - مدیریت ریسک: حد ضرر، حد سود، trailing stop                  |
//|   - پشتیبانی از حالت Demo و Live                                  |
//+------------------------------------------------------------------+
#property copyright   "Galaxy Vast AI"
#property link        "https://galaxyvast.ai"
#property version     "3.20"
#property strict

#include <MT5Trading/Config.mqh>
#include <MT5Trading/SMCAnalyzer.mqh>
#include <MT5Trading/ExecutionEngine.mqh>
#include <MT5Trading/LicenseChecker.mqh>

//+------------------------------------------------------------------+
//| پارامترهای ورودی EA                                               |
//+------------------------------------------------------------------+
input group "═══ تنظیمات اتصال ═══"
input string  InpApiBaseUrl       = "https://api.galaxyvast.ai"; // آدرس API Backend
input string  InpLicenseKey       = "";                           // کلید لایسنس
input int     InpHeartbeatSeconds = 300;                          // فاصله heartbeat (ثانیه)

input group "═══ تنظیمات معامله ═══"
input string  InpSymbols          = "XAUUSD,EURUSD,GBPUSD";     // نمادها (با کاما جدا کنید)
input double  InpRiskPercent      = 1.0;                          // ریسک هر معامله (درصد)
input double  InpMaxDailyLoss     = 5.0;                          // حداکثر ضرر روزانه (درصد)
input int     InpSignalTimeoutSec = 60;                           // حداکثر عمر سیگنال (ثانیه)
input bool    InpDemoMode         = true;                         // حالت Demo (بدون اجرای واقعی)

input group "═══ تنظیمات ریسک ═══"
input double  InpDefaultSL        = 50.0;                         // حد ضرر پیش‌فرض (پیپ)
input double  InpDefaultTP        = 100.0;                        // حد سود پیش‌فرض (پیپ)
input bool    InpUseTrailingStop  = true;                         // فعال‌سازی Trailing Stop
input double  InpTrailingPoints   = 30.0;                         // فاصله Trailing Stop (پیپ)

//+------------------------------------------------------------------+
//| متغیرهای سراسری                                                  |
//+------------------------------------------------------------------+
LicenseChecker  g_license;
ExecutionEngine g_executor;

bool     g_license_valid    = false;
bool     g_emergency_stop   = false;
datetime g_last_heartbeat   = 0;
datetime g_last_signal_poll = 0;
double   g_daily_start_balance = 0.0;
string   g_device_id        = "";

int    g_trades_today     = 0;
double g_profit_today     = 0.0;
int    g_signals_received = 0;

//+------------------------------------------------------------------+
//| تابع راه‌اندازی EA                                               |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
   Print("Galaxy Vast AI EA v3.20 — در حال راه‌اندازی");
   Print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

   if(InpLicenseKey == "") { Alert("خطا: کلید لایسنس وارد نشده است!"); return INIT_PARAMETERS_INCORRECT; }
   if(InpApiBaseUrl == "") { Alert("خطا: آدرس API وارد نشده است!"); return INIT_PARAMETERS_INCORRECT; }

   g_device_id = _GenerateDeviceId();
   Print("شناسه دستگاه: ", g_device_id);

   if(!g_license.Init(InpLicenseKey, g_device_id, InpApiBaseUrl)) {
      Alert("خطا: فعال‌سازی لایسنس ناموفق بود!");
      return INIT_FAILED;
   }
   g_license_valid  = true;
   g_last_heartbeat = TimeCurrent();
   Print("لایسنس فعال شد | پلن: ", g_license.GetPlan());

   g_daily_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   g_executor.Init(InpApiBaseUrl, g_device_id, InpDemoMode);
   EventSetTimer(30);

   if(InpDemoMode) Print("⚠️  حالت Demo فعال است — هیچ معامله واقعی اجرا نمی‌شود");
   Print("EA با موفقیت راه‌اندازی شد ✓");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| تابع خاموش شدن EA                                              |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   g_license.Revoke();
   PrintFormat("EA متوقف شد | معاملات امروز: %d | سود/ضرر: %.2f", g_trades_today, g_profit_today);
}

//+------------------------------------------------------------------+
//| تایمر — هر ۳۰ ثانیه                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(g_emergency_stop) { _ShowStatus("🛑 EMERGENCY STOP", clrRed); return; }

   if(TimeCurrent() - g_last_heartbeat >= InpHeartbeatSeconds) {
      if(!g_license.SendHeartbeat()) {
         g_license_valid = false;
         g_emergency_stop = true;
         _ShowStatus("🛑 لایسنس نامعتبر — EA متوقف شد", clrRed);
         return;
      }
      g_last_heartbeat = TimeCurrent();
      g_license_valid  = true;
   }

   if(_IsDailyLossBreached()) {
      g_emergency_stop = true;
      _ShowStatus("🛑 حد ضرر روزانه فعال", clrRed);
      return;
   }

   if(TimeCurrent() - g_last_signal_poll >= 30) {
      _PollSignals();
      g_last_signal_poll = TimeCurrent();
   }

   if(InpUseTrailingStop) _UpdateTrailingStops();

   _ShowStatus(
      StringFormat("✅ فعال | سیگنال: %d | معاملات: %d | PnL: %.2f",
                   g_signals_received, g_trades_today, g_profit_today),
      clrLimeGreen
   );
}

//+------------------------------------------------------------------+
//| رویداد تیک                                                        |
//+------------------------------------------------------------------+
void OnTick()
{
   if(g_emergency_stop || !g_license_valid) return;
   if(InpUseTrailingStop) _UpdateTrailingStops();
}

//+------------------------------------------------------------------+
//| رویداد بسته شدن معامله                                           |
//+------------------------------------------------------------------+
void OnTradeTransaction(
   const MqlTradeTransaction& trans,
   const MqlTradeRequest&     request,
   const MqlTradeResult&      result
)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD) {
      double deal_profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
      g_profit_today += deal_profit;
      g_trades_today++;
      PrintFormat("معامله بسته شد | ticket=%lld profit=%.2f | مجموع: %.2f",
                  trans.deal, deal_profit, g_profit_today);
      g_executor.NotifyTradeClosed(trans.deal, deal_profit);
   }
}

//+------------------------------------------------------------------+
//| دریافت سیگنال از backend API                                     |
//+------------------------------------------------------------------+
void _PollSignals()
{
   string url     = InpApiBaseUrl + "/api/v1/signals/pending";
   string headers = StringFormat("Authorization: Bearer %s\r\nX-Device-ID: %s\r\n",
                                 InpLicenseKey, g_device_id);
   char post[], response[];
   string resp_headers;
   int http_code = WebRequest("GET", url, headers, InpSignalTimeoutSec * 1000,
                              post, response, resp_headers);
   if(http_code != 200) {
      if(http_code == 401)  { Print("❌ خطای احراز هویت"); g_license_valid = false; }
      else if(http_code == -1) Print("⚠️ سرور در دسترس نیست");
      else PrintFormat("⚠️ HTTP %d", http_code);
      return;
   }
   string json = CharArrayToString(response, 0, WHOLE_ARRAY, CP_UTF8);
   if(json == "" || json == "[]") return;
   g_signals_received++;
   _ProcessSignalJson(json);
}

//+------------------------------------------------------------------+
//| پردازش سیگنال و اجرای معامله                                   |
//+------------------------------------------------------------------+
void _ProcessSignalJson(const string json)
{
   string symbol     = _ExtractString(json, "symbol");
   string direction  = _ExtractString(json, "direction");
   string signal_id  = _ExtractString(json, "signal_id");
   double sl_pips    = _ExtractDouble(json, "sl_pips",    InpDefaultSL);
   double tp_pips    = _ExtractDouble(json, "tp_pips",    InpDefaultTP);
   double confidence = _ExtractDouble(json, "confidence", 0.0);

   if(symbol == "" || direction == "" || signal_id == "") {
      Print("⚠️ سیگنال ناقص — نادیده گرفته شد"); return;
   }
   if(StringFind(InpSymbols, symbol) < 0) {
      PrintFormat("⚠️ نماد %s مجاز نیست", symbol); return;
   }

   double lot = _CalculateLotSize(symbol, sl_pips);
   if(lot <= 0.0) { Print("⚠️ محاسبه حجم ناموفق"); return; }

   PrintFormat("📡 سیگنال | %s %s sl=%.1f tp=%.1f conf=%.0f%%",
               symbol, direction, sl_pips, tp_pips, confidence * 100);

   long ticket = g_executor.PlaceOrder(symbol, direction, lot, sl_pips, tp_pips, signal_id);
   if(ticket > 0) {
      PrintFormat("✅ سفارش اجرا شد | ticket=%d lot=%.2f", ticket, lot);
      g_executor.AcknowledgeSignal(signal_id, ticket);
   } else {
      PrintFormat("❌ اجرای سفارش ناموفق | signal=%s", signal_id);
      g_executor.RejectSignal(signal_id, "execution_failed");
   }
}

//+------------------------------------------------------------------+
//| به‌روزرسانی Trailing Stop                                          |
//+------------------------------------------------------------------+
void _UpdateTrailingStops()
{
   double trail = InpTrailingPoints * _Point * 10;
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      string sym   = PositionGetString(POSITION_SYMBOL);
      int    ptype = (int)PositionGetInteger(POSITION_TYPE);
      double sl    = PositionGetDouble(POSITION_SL);
      double open  = PositionGetDouble(POSITION_PRICE_OPEN);
      double bid   = SymbolInfoDouble(sym, SYMBOL_BID);
      double ask   = SymbolInfoDouble(sym, SYMBOL_ASK);
      double new_sl;
      if(ptype == POSITION_TYPE_BUY) {
         new_sl = bid - trail;
         if(new_sl <= sl || new_sl <= open) continue;
      } else {
         new_sl = ask + trail;
         if(new_sl >= sl || new_sl >= open) continue;
      }
      MqlTradeRequest req = {}; MqlTradeResult res = {};
      req.action   = TRADE_ACTION_SLTP;
      req.position = ticket;
      req.symbol   = sym;
      req.sl       = new_sl;
      req.tp       = PositionGetDouble(POSITION_TP);
      if(!OrderSend(req, res))
         PrintFormat("⚠️ SL به‌روزنشد | ticket=%lld err=%d", ticket, res.retcode);
   }
}

//+------------------------------------------------------------------+
//| بررسی حد ضرر روزانه                                              |
//+------------------------------------------------------------------+
bool _IsDailyLossBreached()
{
   if(g_daily_start_balance <= 0) return false;
   double loss_pct = (g_daily_start_balance - AccountInfoDouble(ACCOUNT_BALANCE))
                     / g_daily_start_balance * 100.0;
   return loss_pct >= InpMaxDailyLoss;
}

//+------------------------------------------------------------------+
//| محاسبه حجم معامله بر اساس درصد ریسک                             |
//+------------------------------------------------------------------+
double _CalculateLotSize(const string symbol, const double sl_pips)
{
   if(sl_pips <= 0) return 0.0;
   double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
   double risk_amt = balance * InpRiskPercent / 100.0;
   double tv       = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts       = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double pt       = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(tv <= 0 || ts <= 0 || pt <= 0) return 0.0;
   double sl_val   = (sl_pips * pt / ts) * tv;
   if(sl_val <= 0) return 0.0;
   double lot      = risk_amt / sl_val;
   double mn = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double mx = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double st = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   lot = MathMax(mn, MathMin(mx, lot));
   if(st > 0) lot = MathFloor(lot / st) * st;
   return NormalizeDouble(lot, 2);
}

//+------------------------------------------------------------------+
//| نمایش وضعیت روی نمودار                                          |
//+------------------------------------------------------------------+
void _ShowStatus(const string text, const color clr)
{
   string n = "GalaxyVast_Status";
   if(ObjectFind(0, n) < 0) ObjectCreate(0, n, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, n, OBJPROP_CORNER,    CORNER_LEFT_UPPER);
   ObjectSetInteger(0, n, OBJPROP_XDISTANCE, 10);
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE, 20);
   ObjectSetInteger(0, n, OBJPROP_FONTSIZE,  10);
   ObjectSetInteger(0, n, OBJPROP_COLOR,     clr);
   ObjectSetString (0, n, OBJPROP_TEXT,      "GalaxyVast: " + text);
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| تولید شناسه یکتای دستگاه                                        |
//+------------------------------------------------------------------+
string _GenerateDeviceId()
{
   long   account = AccountInfoInteger(ACCOUNT_LOGIN);
   string server  = AccountInfoString(ACCOUNT_SERVER);
   return StringFormat("MT5_%d_%s", account, StringSubstr(server, 0, 8));
}

//+------------------------------------------------------------------+
//| استخراج رشته از JSON ساده                                        |
//+------------------------------------------------------------------+
string _ExtractString(const string json, const string key)
{
   string s = "\"" + key + "\":\"";
   int p = StringFind(json, s); if(p < 0) return "";
   p += StringLen(s);
   int e = StringFind(json, "\"", p); if(e < 0) return "";
   return StringSubstr(json, p, e - p);
}

//+------------------------------------------------------------------+
//| استخراج عدد از JSON ساده                                          |
//+------------------------------------------------------------------+
double _ExtractDouble(const string json, const string key, const double def)
{
   string s = "\"" + key + "\":";
   int p = StringFind(json, s); if(p < 0) return def;
   p += StringLen(s);
   int e = p;
   while(e < StringLen(json)) {
      ushort c = StringGetCharacter(json, e);
      if(c == ',' || c == '}' || c == ']') break;
      e++;
   }
   return StringToDouble(StringSubstr(json, p, e - p));
}
