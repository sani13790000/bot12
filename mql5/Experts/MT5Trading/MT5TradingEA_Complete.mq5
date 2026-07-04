//+------------------------------------------------------------------+
//| Galaxy Vast AI Trading Platform                                     |
//| MT5TradingEA_Complete.mq5                                            |
//+--------------------------------------------------------------------+
#property copyright   "Galaxy Vast AI"
#property link        "https://galaxyvast.ai"
#property version     "3.30"
#property strict

#include <MT5Trading/Config.mqh>
#include <MT5Trading/LicenseChecker.mqh>

input group "═══ تنظیمات اتصال ═══"
input string  InpApiBaseUrl = "https://api.galaxyvast.ai";
input string  InpLicenseKey = "";
input int     InpHeartbeatSeconds = 300;

input group "═══ تنظیمات معاملات ═══"
input string  InpSymbols = "XAUUSD,EURUSD,GBPUSD";
input double  InpRiskPercent = 1.0;
input double  InpMaxDailyLoss = 5.0;
input int     InpSignalTimeoutSec = 60;
input bool    InpDemoMode = true;

input group "═══ تنظیمات ریسک ═══"
input double  InpDefaultSL = 50.0;
input double  InpDefaultTP = 100.0;
input bool    InpUseTrailingStop = true;
input double  InpTrailingPoints = 30.0;

LicenseChecker  g_license;
bool     g_license_valid = false;
bool     g_emergency_stop = false;
datetime g_last_heartbeat = 0;
datetime g_last_signal_poll = 0;
double   g_daily_start_balance = 0.0;
string   g_device_id = "";
int      g_trades_today = 0;
double   g_profit_today = 0.0;
int      g_signals_received = 0;

int OnInit()
{
   Print("Galaxy Vast AI EA v3.30");
   if(InpLicenseKey == "") { Alert("خطا: کلید لایسنس وارد نشده!"); return INIT_PARAMETERS_INCORRECT; }
   if(InpApiBaseUrl == "") { Alert("خائ: ادرس API وارد نزده!"); return INIT_PARAMETERS_INCORRECT; }
   g_device_id = _GenerateDeviceId();
   if(!g_license.Init(InpLicenseKey, g_device_id, InpApiBaseUrl)) { Alert("خائ: فعال؂سازی لایسنس ناموفق بود!"); return INIT_FAILED; }
   g_license_valid = true;
   g_last_heartbeat = TimeCurrent();
   g_daily_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   EventSetTimer(30);
   if(InpDemoMode) Print("⚠️ Halat Demo faal ast");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   g_license.Revoke();
   PrintFormat("EA matopef shad | maamalat: %d | sod/zarar: %.2f", g_trades_today, g_profit_today);
}

void OnTimer()
{
   if(g_emergency_stop) { _ShowStatus("STOP", clrRed); return; }
   if(TimeCurrent() - g_last_heartbeat >= InpHeartbeatSeconds) {
      if(!g_license.SendHeartbeat()) { g_license_valid = false; g_emergency_stop = true; return; }
      g_last_heartbeat = TimeCurrent(); g_license_valid = true;
   }
   if(_IsDailyLossBreached()) { g_emergency_stop = true; return; }
   if(TimeCurrent() - g_last_signal_poll >= 30) { _PollSignals(); g_last_signal_poll = TimeCurrent(); }
   if(InpUseTrailingStop) _UpdateTrailingStops();
   _ShowStatus(StringFormat("active | sig:%d trades:%d pnl:%.2f", g_signals_received, g_trades_today, g_profit_today), clrLimeGreen);
}

void OnTick()
{
   if(g_emergency_stop || !g_license_valid) return;
   if(InpUseTrailingStop) _UpdateTrailingStops();
}

void OnTradeTransaction(const MqlTradeTransaction& trans,const MqlTradeRequest& req,const MqlTradeResult& res)
{
   if(trans.type == TPADETRANSACTION_DEAL_ADD) {
      double p = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
      g_profit_today += p; g_trades_today++;
      _NotifyTradeClose(trans.deal, p);
   }
}

void _PollSignals()
{
   string url = InpApiBaseUrl + "/api/v1/signals/pending";
   string hdrs = StringFormat("Authorization: Bearer %s\r\nX-Device-ID: %s\r\n", InpLicenseKey, g_device_id);
   char post[], resp[]; string rhdrs;
   int code = WebRequest("GET", url, hdrs, InpSignalTimeoutSec*1000, post, resp, rhdrs);
   if(code != 200) { if(code == 401) g_license_valid=false; return; }
   string json = CharArrayToString(resp, 0, WHOLE_ARRAY, CP_UTF8);
   if(json == "" || json == "[]") return;
   g_signals_received++;
   _ProcessSignalJson(json);
}

void _ProcessSignalJson(const string json)
{
   string symbol = _ExtractString(json,"symbol");
   string dir    = _ExtractString(json,"direction");
   string sid    = _ExtractString(json,"signal_id");
   double sl     = _ExtractDouble(json,"sl_pips",InpDefaultSL);
   double tp     = _ExtractDouble(json,tp_pips",InpDefaultTP);
   double conf   = _ExtractDouble(json,"confidence",0.0);
   if(symbol==""||dir==""||sid=="") return;
   if(StringFind(InpSymbols,symbol)<0) return;
   if(conf < 0.60) { _RejectSignal(sid,"low_confidence"); return; }
   double lot = _CalculateLotSize(symbol,sl);
   if(lot<=0.0) return;
   if(InpDemoMode) { _AcknowledgeSignal(sid,0,true); return; }
   long ticket = _PlaceOrder(symbol,dir,lot,sl,tp,sid);
   if(ticket>0) _AcknowledgeSignal(sid,ticket,false);
   else _RejectSignal(sid,"execution_failed");
}

long _PlaceOrder(const string sym,const string dir,const double lot,const double sl_pips,const double tp_pips,const string sid)
{
   MqlTradeRequest req={}; MqlTradeResult res={};
   double pt=SymbolInfoDouble(sym,SYMBOL_POINT);
   double ask=SymbolInfoDouble(sym,SYMBOL_ASK);
   double bid=SymbolInfoDouble(sym,SYMBOL_BID);
   if(dir=="buy") { req.type=ORDER_TYPE_BUY; req.price=ask; req.sl=ask-sl_pips*pt*10; req.tp=ask+tp_pips*pt*10; }
   else { req.type=ORDER_TYPE_SELL; req.price=bid; req.sl=bid+sl_pips*pt*10; req.tp=bid-tp_pips*pt*10; }
   req.action=TRADE_ACTION_DEAL; req.symbol=sym; req.volume=lot;
   req.deviation=20; req.magic=202400; req.comment="GV_"+sid;
   req.type_filling=ORDER_FILLING_IOC;
   if(!OrderSend(req,res)) { PrintFormat("OrderSend failed: %d",res.retcode); return -1; }
   return (long)res.order;
}

void _AcknowledgeSignal(const string sid,const long ticket,const bool demo)
{
   string url=InpApiBaseUrl+"/api/v1/signals/"+sid+"/acknowledge";
   string body=StringFormat("{\"ticket\":%lld,\"demo\":%s}",ticket,demo?"true":"false");
   string hdrs=StringFormat("Content-Type: application/json\r\nAuthorization: Bearer %s\r\n",InpLicenseKey);
   char p[],r[]; string rh; StringToCharArray(body,p,0,WHOLE_ARRAY,CP_UTF8);
   WebRequest("POST",url,hdrs,10000,p,r,rh);
}

void _RejectSignal(const string sid,const string reason)
{
   string url=InpApiBaseUrl+"/api/v1/signals/"+sid+"/reject";
   string body=StringFormat("{\"reason\":\"%s\"}",reason);
   string hdrs=StringFormat("Content-Type: application/json\r\nAuthorization: Bearer %s\r\n",InpLicenseKey);
   char p[],r[]; string rh; StringToCharArray(body,p,0,WHOLE_ARRAY,CP_UTF8);
   WebRequest("POST",url,hdrs,10000,p,r,rh);
}

void _NotifyTradeClose(const long deal,const double profit)
{
   string url=InpApiBaseUrl+"/api/v1/trades/notify_close";
   string body=StringFormat("{\"deal\":%lld,\"profit\":%.2f}",deal,profit);
   string hdrs=StringFormat("Content-Type: application/json\r\nAuthorization: Bearer %s\r\n",InpLicenseKey);
   char p[],r[]; string rh; StringToCharArray(body,p,0,HS�HLE_ARRAY,CP_UTF8);
   WebRequest("POST",url,hdrs,10000,p,r,rh);
}

void _UpdateTrailingStops()
{
   double trail=InpTrailingPoints*_Point*10;
   for(int i=PositionsTotal()-1;i>=0;i--) {
      ulong t=PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      string s=PositionGetString(POSITION_SYMBOL);
      int ptype=(int)PositionGetInteger(POSITION_TYPE);
      double sl=PositionGetDouble(POSITION_SL);
      double open=PositionGetDouble(POSITION_PRICE_OPEN);
      double bid=SymbolInfoDouble(s,SYMBOL_BID);
      double ask=SymbolInfoDouble(s,SYMBOL_ASK);
      double ns;
      if(ptype==POSITION_TYPE_BUY) { ns=bid-trail; if(ns<=sl||ns<=open) continue; }
      else { ns=ask-trail; if(ns>=sl||ns>=open) continue; }
      MqlTradeRequest req={}; MqlTradeResult res={};
      req.action=TRADE_ACTION_SLTP; req.position=t; req.symbol=s; req.sl=ns;
      req.tp=PositionGetDouble(POSITION_TP);
      OrderSend(req,res);
   }
}

bool _IsDailyLossBreached()
{
   if(g_daily_start_balance<=0) return false;
   double pct=(g_daily_start_balance-AccountInfoDouble(ACCOUNT_BALANCE))/g_daily_start_balance*100.0;
   return pct>=InpMaxDailyLoss;
}

double _CalculateLotSize(const string sym,const double sl_pips)
{
   if(sl_pips<=0) return 0.0;
   double bal=AccountInfoDouble(ACCOUNT_BALANCE);
   double risk=bal*InpRiskPercent/100.0;
   double tv=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_VALUE);
   double ts=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   double pt=SymbolInfoDouble(sym,SYMBOL_POINT);
   if(tv<=0||ts<=0||pt<=0) return 0.0;
   double sval=(sl_pips*pt/ts)*tv;
   if(sval<=0) return 0.0;
   double lot=risk/sval;
   double mn=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double mx=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
   double st=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   lot=MathMax(mn,MathMin(mx,lot));
   if(st>0) lot=MathFloor(lot/st)*st;
   return NormalizeDouble(lot,2);
}

void _ShowStatus(const string txt,const color clr)
{
   string n="GV_Status";
   if(ObjectFind(0,n)<0) ObjectCreate(0,n,OBJ_LABEL,0,0,0);
   ObjectSetInteger(0,n,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,n,OBJPROP_XDISTANCE,10);
   ObjectSetInteger(0,n,OBJPROP_YDISTANCE,20);
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,10);
   ObjectSetInteger(0,n,OBJPROP_COLOR,clr);
   ObjectSetString(0,n,OBJPROP_TEXT,"GV: "+txt);
   ChartRedraw(0);
}

string _GenerateDeviceId()
{
   return StringFormat("MT5_%d_%s",(int)AccountInfoInteger(ACCOUNT_LOGIN),StringSubstr(AccountInfoString(ACCOUNT_SERVER),0,8));
}

string _ExtractString(const string json,const string key)
{
   string s="\""+key+"\":\"";
   int p=StringFind(json,s); if(p<0) return "";
   p+=StringLen(s);
   int e=StringFind(json,\"\"",p); if(e<0) return "";
   return StringSubstr(json,p,e-p);
}

double _ExtractDouble(const string json,const string key,const double def)
{
   string s="\""+key+"\":";
   int p=StringFind(json,s); if(p<0) return def;
   p+=StringLen(s);
   int e=p;
   while(e<StringLen(json)) { ushort c=StringGetCharacter(json,e); if(c==','||c=='}'||c==']') break; e++; }
   return StringToDouble(StringSubstr(json,p,e-p));
}