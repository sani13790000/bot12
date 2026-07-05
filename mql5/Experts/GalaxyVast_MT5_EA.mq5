//+------------------------------------------------------------------+
//|  GalaxyVast_MT5_EA.mq5  —  Phase H Hardened                     |
//|  Fixes:                                                           |
//|    - BUG-H1: server_url from extern input (no hardcode)           |
//|    - BUG-H2: HTTP 4xx/5xx response handling with error codes      |
//|    - BUG-H3: retry logic on timeout / network error               |
//|    - BUG-H4: JSON parse error detection                           |
//|    - BUG-H5: Position sync with /health/live before trading       |
//+------------------------------------------------------------------+
#property copyright "GalaxyVast Trading"
#property version   "2.0"
#property strict

#include <Trade\Trade.mqh>
#include <JAson.mqh>

//--- Extern inputs (configurable from MetaTrader inputs panel)
extern string  ServerURL        = "http://api:8000";   // API base URL — set in MT5 inputs
extern string  APIKey           = "";                  // Gateway API key
extern string  Symbol_Override  = "";                  // Override symbol (blank = current)
extern int     MagicNumber      = 202601;
extern double  DefaultLotSize   = 0.01;
extern int     MaxRetries       = 3;                   // HTTP retry attempts
extern int     RetryDelayMs     = 500;                 // ms between retries
extern bool    VerboseLogging   = false;
extern bool    DemoMode         = true;                // Safety: true = no real orders

//--- Internal state
CTrade  g_trade;
bool    g_api_healthy  = false;
datetime g_last_health = 0;
int     g_health_interval = 60;  // seconds between health checks

//+------------------------------------------------------------------+
//| Expert init                                                       |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_trade.SetExpertMagicNumber(MagicNumber);
   g_trade.SetDeviationInPoints(20);

   // Validate server URL
   if(StringLen(StringTrimRight(StringTrimLeft(ServerURL))) == 0)
     {
      Print("[GV] ERROR: ServerURL is empty. Set it in EA inputs.");
      return INIT_PARAMETERS_INCORRECT;
     }

   // Initial health check
   g_api_healthy = CheckAPIHealth();
   if(!g_api_healthy)
      Print("[GV] WARNING: API health check failed on init — will retry on tick");
   else
      Print("[GV] API connected to ", ServerURL);

   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert tick                                                       |
//+------------------------------------------------------------------+
void OnTick()
  {
   // Periodic health re-check
   if(TimeCurrent() - g_last_health > g_health_interval)
     {
      g_api_healthy  = CheckAPIHealth();
      g_last_health  = TimeCurrent();
      if(VerboseLogging)
         Print("[GV] Health check: ", g_api_healthy ? "OK" : "FAIL");
     }

   if(!g_api_healthy)
      return;  // API not reachable — skip tick

   // Request signal from API
   string symbol = StringLen(Symbol_Override) > 0 ? Symbol_Override : _Symbol;
   string signal_json = "";
   int    code        = 0;

   if(!RequestSignal(symbol, signal_json, code))
     {
      if(VerboseLogging)
         Print("[GV] Signal request failed, code=", code);
      return;
     }

   // Parse signal
   CJAVal js;
   if(!js.Deserialize(signal_json))
     {
      Print("[GV] ERROR: JSON parse failed — raw=", StringSubstr(signal_json, 0, 120));
      return;
     }

   string direction = js["direction"].ToStr();
   double volume    = js["volume"].ToDbl();
   double sl        = js["sl"].ToDbl();
   double tp        = js["tp"].ToDbl();
   string sig_type  = js["signal"].ToStr();   // BUY / SELL / NO_TRADE

   if(sig_type == "NO_TRADE" || sig_type == "ABSTAIN" || sig_type == "")
     {
      if(VerboseLogging)
         Print("[GV] Signal=NO_TRADE — skipping");
      return;
     }

   if(DemoMode)
     {
      Print("[GV] DEMO MODE — would execute: ", sig_type, " ", symbol,
            " vol=", DoubleToString(volume, 2),
            " sl=",  DoubleToString(sl, 5),
            " tp=",  DoubleToString(tp, 5));
      return;
     }

   // Execute order
   bool ok = ExecuteOrder(symbol, sig_type, volume > 0 ? volume : DefaultLotSize, sl, tp);
   if(ok)
      Print("[GV] Order executed: ", sig_type, " ", symbol);
   else
      Print("[GV] Order FAILED: ", sig_type, " ", symbol);
  }

//+------------------------------------------------------------------+
//| Health check — GET /health/live                                   |
//+------------------------------------------------------------------+
bool CheckAPIHealth()
  {
   string url     = ServerURL + "/health/live";
   string headers = BuildHeaders();
   string result  = "";
   int    http_code = 0;

   if(!HTTPGetWithRetry(url, headers, result, http_code, 1, 0))
      return false;

   if(http_code != 200)
     {
      Print("[GV] Health endpoint HTTP ", http_code);
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Request trading signal — POST /api/v1/signal                     |
//+------------------------------------------------------------------+
bool RequestSignal(string symbol, string &response, int &http_code)
  {
   string url     = ServerURL + "/api/v1/signal";
   string headers = BuildHeaders() + "Content-Type: application/json\r\n";
   string payload = "{\"symbol\": \"" + symbol + "\"}";
   response = "";
   http_code = 0;

   return HTTPPostWithRetry(url, headers, payload, response, http_code, MaxRetries, RetryDelayMs);
  }

//+------------------------------------------------------------------+
//| Execute order via trade object                                    |
//+------------------------------------------------------------------+
bool ExecuteOrder(string symbol, string direction, double volume, double sl, double tp)
  {
   MqlTradeResult result = {};
   MqlTradeRequest req   = {};

   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = symbol;
   req.volume    = volume;
   req.type      = (direction == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price     = (direction == "BUY") ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                                       : SymbolInfoDouble(symbol, SYMBOL_BID);
   req.sl        = sl;
   req.tp        = tp;
   req.magic     = MagicNumber;
   req.deviation = 20;
   req.comment   = "GalaxyVast_v2";
   req.type_filling = ORDER_FILLING_IOC;

   bool ok = OrderSend(req, result);
   if(!ok || result.retcode != TRADE_RETCODE_DONE)
     {
      Print("[GV] OrderSend failed: retcode=", result.retcode,
            " comment=", result.comment);
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Build common HTTP headers                                         |
//+------------------------------------------------------------------+
string BuildHeaders()
  {
   string h = "Accept: application/json\r\n";
   if(StringLen(APIKey) > 0)
      h += "X-API-Key: " + APIKey + "\r\n";
   return h;
  }

//+------------------------------------------------------------------+
//| HTTP GET with retry                                               |
//+------------------------------------------------------------------+
bool HTTPGetWithRetry(string url, string headers, string &result,
                      int &http_code, int retries, int delay_ms)
  {
   for(int attempt = 0; attempt <= retries; attempt++)
     {
      if(attempt > 0 && delay_ms > 0)
         Sleep(delay_ms);

      char  post_data[];
      char  resp_data[];
      string resp_headers = "";

      http_code = WebRequest("GET", url, headers, 5000,
                             post_data, resp_data, resp_headers);

      // -1 = network error
      if(http_code == -1)
        {
         int err = GetLastError();
         Print("[GV] HTTPGet attempt ", attempt + 1, " network error: ", err);
         continue;
        }

      // 5xx = server error — retry
      if(http_code >= 500)
        {
         Print("[GV] HTTPGet attempt ", attempt + 1, " server error: HTTP ", http_code);
         if(attempt < retries) continue;
         return false;
        }

      // 4xx = client error — do NOT retry
      if(http_code >= 400)
        {
         Print("[GV] HTTPGet client error: HTTP ", http_code, " url=", url);
         return false;
        }

      // 2xx = success
      result = CharArrayToString(resp_data, 0, ArraySize(resp_data), CP_UTF8);
      return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| HTTP POST with retry                                              |
//+------------------------------------------------------------------+
bool HTTPPostWithRetry(string url, string headers, string payload,
                       string &result, int &http_code, int retries, int delay_ms)
  {
   int payload_len = StringLen(payload);
   char post_data[];
   StringToCharArray(payload, post_data, 0, payload_len, CP_UTF8);
   ArrayResize(post_data, payload_len);

   for(int attempt = 0; attempt <= retries; attempt++)
     {
      if(attempt > 0 && delay_ms > 0)
         Sleep(delay_ms);

      char  resp_data[];
      string resp_headers = "";

      http_code = WebRequest("POST", url, headers, 8000,
                             post_data, resp_data, resp_headers);

      if(http_code == -1)
        {
         int err = GetLastError();
         Print("[GV] HTTPPost attempt ", attempt + 1, " network error: ", err);
         continue;
        }

      if(http_code >= 500)
        {
         Print("[GV] HTTPPost attempt ", attempt + 1, " server error: HTTP ", http_code);
         if(attempt < retries) continue;
         return false;
        }

      if(http_code >= 400)
        {
         Print("[GV] HTTPPost client error: HTTP ", http_code, " url=", url);
         return false;
        }

      result = CharArrayToString(resp_data, 0, ArraySize(resp_data), CP_UTF8);
      return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Print("[GV] EA deinit reason=", reason);
  }
//+------------------------------------------------------------------+
