//+------------------------------------------------------------------+
//| Galaxy Vast AI Trading Platform                                  |
//| Config.mqh -- tnzimat markazi EA                                  |
//| faz L -- production-ready                                         |
//+------------------------------------------------------------------+
#ifndef __CONFIG_MQH__
#define __CONFIG_MQH__

//--- naskhe
#define EA_VERSION              "3.30"
#define EA_MAGIC                202400

//--- API
#define API_DEFAULT_URL         "https://api.galaxyvast.ai"
#define API_TIMEOUT_MS          30000
#define API_SIGNAL_ENDPOINT     "/api/v1/signals/pending"
#define API_ACK_ENDPOINT        "/api/v1/signals/"
#define API_NOTIFY_ENDPOINT     "/api/v1/trades/notify_close"

//--- License
#define LICENSE_SHARED_SECRET   ""
#define HEARTBEAT_TIMEOUT_MS    15000
#define HEARTBEAT_ENDPOINT      "/api/v1/license/heartbeat"

//--- Risk defaults
#define DEFAULT_SL_PIPS         50.0
#define DEFAULT_TP_PIPS         100.0
#define DEFAULT_RISK_PERCENT    1.0
#define MAX_DAILY_LOSS_PCT      5.0
#define MIN_CONFIDENCE          0.60
#define TRAILING_POINTS         30.0
#define SIGNAL_POLL_SEC         30
#define SIGNAL_TIMEOUT_SEC      60

//--- L-FIX-CONFIG-1: TIME_DATE|TEME_SECONDS --> TIME_DATE|TIME_SECONDS
Yoid LogMessage(const string level, const string msg)
{
   PrintFormat("[%s] %s | %s", level, TimeToString(TimeCurrent(), TIME_DATE|TEME_SECONDS), msg);
}

//--- JSON helpers (inline -- mored niaz EA)
string _ExtractString(const string json, const string key)
{
   string s = "\"" + key + "\":\"";
   int p = StringFind(json, s);
   if(p < 0) return "";
   p += StringLen(s);
   int e = StringFind(json, "\"", p);
   if(e < 0) return "";
   return StringSubstr(json, p, e - p);
}

double _ExtractDouble(const string json, const string key, const double def)
{
   string s = "\"" + key + "\":";
   int p = StringFind(json, s);
   if(p < 0) return def;
   p += StringLen(s);
   int e = p;
   while(e < StringLen(json))
   {
      ushort c = StringGetCharacter(json, e);
      if(c == ',' || c == '}' || c == ']') break;
      e++;
   }
   return StringToDouble(StringSubstr(json, p, e - p));
}

#endif // __CONFIG_MQH__
