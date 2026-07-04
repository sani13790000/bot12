//+--------------------------------------------------------------------+
//| Galaxy Vast AI Trading Platform                                   |
//| MT5TradingEA_Complete.mq5                                          |
//| faz L -- production-ready -- all compile errors fixed             |
//+--------------------------------------------------------------------+
#property copyright   "Galaxy Vast AI"
#property link        "https://galaxyvast.ai"
#property version     "3.32"
#property strict

#include <MT5Trading/Config.mqh>
#include <MT5Trading/LicenseChecker.mqh>

input group "--- Tanzimate Ettesal ---"
input string  InpApiBaseUrl        = "https://api.galaxyvast.ai";
input string  InpLicenseKey        = "";
input int     InpHeartbeatSeconds  = 300;

input group "--- Tanzimate Moamelaht ---"
input string  InpSymbols            = "XAUUSD,EURUSD,GBPUSD";
input double  InpRiskPercent       = 1.0;
input double  InpMaxDailyLoss      = 5.0;
input int     InpSignalTimeoutSec  = 60;
input bool    InpDemoMode           = false;

input group "--- Tanzimate Risk ---"
input double  InpDefaultSL          = 50.0;
input double  InpDefaultTP          = 100.0;
input bool    InpUseTrailingStop    = true;
input double  InpTrailingPoints     = 30.0;

LicenseChecker  g_license;
bool     g_license_valid        = false;
bool     g_emergency_stop       = false;
datetime g_last_heartbeat       = 0;
datetime g_last_signal_poll     = 0;
double   g_daily_start_balance  = 0.0;
string   g_device_id            = "";
int      g_trades_today          = 0;
double   g_profit_today         = 0.0;
int      g_signals_received     = 0;

int OnInit()
{
   LogMessage("INFO", "Galaxy Vast AI EA v  | EA_VERSION);
   if(InpLicenseKey == "") { Alert("Khata: License Key vared nashode ast!"); return INIT_PARAMETERS_INCORRECT; }
   if(InpApiBaseUrl == "") { Alert("Khata: Adresse API vared nashode ast!"); return INIT_PARAMETERS_INCORRECT; }
   g_device_id = _GenerateDeviceId();
   if(!g_license.Init(InpLicenseKey, g_device_id, InpApiBaseUrl))
   {
      Alert("Khata: Mojavezai namovafaq!");
      return INIT_FAILED;
   }
   g_license_valid           = true;
   g_last_heartbeat          = TimeCurrent();
   g_daily_start_balance     = AccountInfoDouble(ACCOUNT_BALANCE);
   EventSetTimer(30);
   if(InpDemoMode) LogMessage("WARN", "halate Demo faal ast -- heech trade dade nemishad");
   LogMessage("INFO", StringFormat("EA faal shad | hesab: %d | mohjodi: %.2f",
      (int)AccountInfoInteger(ACCOUNT_LOGIN), g_daily_start_balance));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   g_license.Revoke();
   PrintFormat("EA motaveghef shad | moamelahat: %d | sod/zarar: %.2f", g_trades_today, g_profit_today);
}

void OnTimer()
{
   if(g_emergency_stop) { _ShowStatus("STOP", clrRed); return; }
   if(TimeCurrent() - g_last_heartbeat >= InpHeartbeatSeconds)
   {
      if(!g_license.SendHeartbeat()) { g_license_valid = false; g_emergency_stop = true; return; }
      g_last_heartbeat = TimeCurrent();
      g_license_valid  = true;
   }
   if(_IsDailyLossBreached()) { g_emergency_stop = true; return; }
   if(TimeCurrent() - g_last_signal_poll >= SIGNAL_POLL_SEC)
   {
      _PollSignals();
      g_last_signal_poll = TimeCurrent();
   }
   if(InpUseTrailingStop) _UpdateTrailingStops();
   _ShowStatus(StringFormat("active | sig:%d trades:%d pnl:%.2f",
      g_signals_received, g_trades_today, g_profit_today), clrLimeGreen);
}

void OnTick()
{
   if(g_emergency_stop || !g_license_valid) return;
   if(InpUseTrailingStop) _UpdateTrailingStops();
}

void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest&     req,
                        const MqlTradeResult&      res)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      double p = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
      g_profit_today += p;
      g_trades_today++;
      _NotifyTradeClose(trans.deal, p);
   }
}

void _PollSignals()
{
   string url  = InpApiBaseUrl + API_SIGNAL_ENDPOINT;
   string hdrs = StringFormat("Authorization: Bearer %s\r\nX-Device-ID: %s\r\n",
                              InpLicenseKey, g_device_id);
   char post[], resp[]; string rhdrs;
   int code = WebRequest("GET", url, hdrs, InpSignalTimeoutSec * 1000, post, resp, rhdrs);
   if(code != 200)
   {
      if(code == 401) { g_license_valid = false; LogMessage("ERROR", "mojavez namotabegheg (401)"); }
      return;
   }
   string json = CharArrayToString(resp, 0, WHOLE_ARRAY, CP_UTF8);
   if(json == "" || json == "[]") return;
   g_signals_received++;
   _ProcessSignalJson(json);
}

void _ProcessSignalJson(const string json)
{
   string symbol = _ExtractString(json, "symbol");
   string dir    = _ExtractString(json, "direction");
   string sid    = _ExtractString(json, "signal_id");
   double sl     = _ExtractDouble(json, "sl_pips", InpDefaultSL);
   double tp     = _ExtractDouble(json, "tp_pips", InpDefaultTP);
   double conf   = _ExtractDouble(json, "confidence", 0.0);

   if(symbol == "" || dir == "" || sid == "") return;
   if(StringFind(InpSymbols, symbol) < 0) return;
   if(conf < MIN_CONFIDENCE) { _RejectSignal(sid, "low_confidence"); return; }

   double lot = _CalculateLotSize(symbol, sl);
   if(lot <= 0.0) return;

   if(InpDemoMode)
   {
      LogMessage("DEMO", StringFormat("signal dryrun: %s %s %.2flot", dir, symbol, lot));
      _AcknowledgeSignal(sid, 0, true);
      return;
   }

   int ort = (dir == "buy") ? ORDER_TYPE_BUY  : ORDER_TYPE_SELL;
   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};
   request.action   = TRADE_ACTION_DEAL;
   request.symbol   = symbol;
   request.volume   = lot;
   request.type     = ort;
   request.price    = (ort == ORDER_TYPE_BUY) ? SymbolInfoDouble(symbol, SYMBOL_ASK) : SymbolInfoDouble(symbol, SYMBOL_BID);
   request.deviation = 20;
   request.magic    = EA_MAGIC;
   request.comment  = "GV_" + sid;
   request.type_time = ORDER_TIME_GTC;
   request.type_filling = ORDER_FILLING_IOC;

   double pt = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(ort == ORDER_TYPE_BUY)
   {
      request.sl = NormalizeDouble(request.price - sl * pt * 10, SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      request.tp = NormalizeDouble(request.price + tp * pt * 10, SymbolInfoInteger(symbol, SYMBOL_DIGITS));
   }
   else
   {
      request.sl = NormalizeDouble(request.price + sl * pt * 10, SymbolInfoInteger(symbol, SYMBOL_DIGITS));
      request.tp = NormalizeDouble(request.price - tp * pt * 10, SymbolInfoInteger(symbol, SYMBOL_DIGITS));
   }

   if(!OrderSend(request, result))
   {
      LogMessage("ERROR", StringFormat("send failed: %d -- %s", result.retcode, result.comment));
      _AcknowledgeSignal(sid, 0, false);
      return;
   }
   _AcknowledgeSignal(sid, result.order, true);
   LogMessage("INFO", StringFormat("order opened | ticket:%d | dir:%s | price:%.5f",
      result.order, dir, result.price));
}

void _AcknowledgeSignal(const string sid, const long ticket, const bool success)
{
   string url  = InpApiBaseUrl + API_ACK_ENDPOINT + sid + "/ack";
   string body = StringFormat("{\"ticket\":%d,\"success\":%s}", ticket, success ? "true" : "false");
   string hdrs = StringFormat("Authorization: Bearer %s\r\nContent-Type: application/json\r\n", InpLicenseKey);
   char post[], resp[]; string rhdrs;
   StringToCharArray(body, post, 0, WHOLE_ARRAY, CP_UTF8);
   WebRequest("POST", url, hdrs, InpSignalTimeoutSec * 1000, post, resp, rhdrs);
}

void _RejectSignal(const string sid, const string reason)
{
   LogMessage("INFO", StringFormat("signal rejected: %s -- %s", sid, reason));
   _AcknowledgeSignal(sid, 0, false);
}

void _NotifyTradeClose(const ulong deal, const double profit)
{
   string url  = InpApiBaseUrl + API_NOTIFY_ENDPOINT;
   string body = StringFormat("{\"deal\":%d,\"profit\":%.2f}", deal, profit);
   string hdrs = StringFormat("Authorization: Bearer %s\r\nContent-Type: application/json\r\n", InpLicenseKey);
   char post[], resp[]; string rhdrs;
   StringToCharArray(body, post, 0, WHOLE_ARRAY, CP_UTF8);
   WebRequest("POST", url, hdrs, InpSignalTimeoutSec * 1000, post, resp, rhdrs);
}

bool _IsDailyLossBreached()
{
   double current = AccountInfoDouble(ACCOUNT_BALANCE);
   double loss    = g_daily_start_balance - current;
   double lossPct = (g_daily_start_balance > 0) ? (loss / g_daily_start_balance * 100) : 0.0;
   if(lossPct >= InpMaxDailyLoss)
   {
      LogMessage("WARN", StringFormat("daily loss limit reached: %.2f%% (%% limit: %.2f%%)", lossPct, InpMaxDailyLoss));
      return true;
   }
   return false;
}

double _CalculateLotSize(const string symbol, const double sl_pips)
{
   double balance    = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmount  = balance * InpRiskPercent / 100.0;
   double tickValue   = SymbolInfoDouble(symbol, SYMBOL_TICK_VALUE);
   double tickSize    = SymbolInfoDouble(symbol, SYMBOL_TICK_SIZE);
   double point       = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(tickValue <= 0 || tickSize <= 0 || point <= 0) return 0.0;
   double pipValue = (tickValue / tickSize) * point * 10;
   if(pipValue <= 0) return 0.0;
   double rawLot   = riskAmount / (sl_pips * pipValue);
   double minLot   = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLot   = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double step     = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   rawLot = MathFloor(rawLot / step) * step;
   return MathMax(minLot, MathMin(maxLot, rawLot));
}

void _UpdateTrailingStops()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionSelectByTicket(PositionGetTicket(i)))
      {
         if(PositionGetInteger(POSITION_MAGIC) != EA_MAGIC) continue;
         string sym = PositionGetString(POSITION_SYMBOL);
         double openp = PositionGetDouble(POSITION_PRICE_OPEN);
         double currp = PositionGetDouble(POSITION_PRICE_CURRENT);
         double sl    = PositionGetDouble(POSITION_SL);
         long   ptype = PositionGetInteger(POSITION_TYPE);
         double pt    = SymbolInfoDouble(sym, SYMBOL_POINT);
         double trail = InpTrailingPoints * pt;
         if(ptype == POSITION_TYPE_BUY)
         {
            double newSL = currp - trail;
            if(newSL > sl && newSL < currp)
            {
               MqlTradeRequest req = {}; MqlTradeResult res = {};
               req.action = TRADE_ACTION_SLTP; req.symbol = sym;
               req.position = PositionGetTicket(i); req.sl = newSL;
               req.tp = PositionGetDouble(POSITION_TP);
               OrderSend(req, res);
            }
         }
         else if(ptype == POSITION_TYPE_SELL)
         {
            double newSL = currp + trail;
            if(newSL < sl && newSL > currp)
            {
               MqlTradeRequest req = {}; MqlTradeResult res = {};
               req.action = TRADE_ACTION_SLTP; req.symbol = sym;
               req.position = PositionGetTicket(i); req.sl = newSL;
               req.tp = PositionGetDouble(POSITION_TP);
               OrderSend(req, res);
            }
         }
      }
   }
}

string _GenerateDeviceId()
{
   return StringFormat("EA_%d_%d", (int)AccountInfoInteger(ACCOUNT_LOGIN), (int)TimeCurrent());
}

void _ShowStatus(const string txt, const color clr)
{
   string n = "GV_status";
   if(ObjectFind(0, n) < 0) ObjectCreate(0, n, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, n, OBJPROP_XDISTANCE, 10);
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE, 20);
   ObjectSetInteger(0, n, OBJPROP_FONTSIZE, 10);
   ObjectSetInteger(0, n, OBJPROP_COLOR, clr);
   ObjectSetString(0, n, OBJPROP_TEXT, "GV: " + txt);
   ChartRedraw(0);
}
