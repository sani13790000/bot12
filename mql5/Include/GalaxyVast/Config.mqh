//+------------------------------------------------------------------+
//| Config.mqh - Galaxy Vast EA Configuration                        |
//| Security: API token from input, not hardcoded                    |
//+------------------------------------------------------------------+
#ifndef GALAXY_VAST_CONFIG_MQH
#define GALAXY_VAST_CONFIG_MQH

//--- Server configuration
input group "=== Server Configuration ==="
input string InpAPIBaseURL    = "http://localhost:8000";  // API Base URL
input string InpAPIToken      = "";                       // API Bearer Token (required)
input int    InpAPITimeoutMs  = 10000;                    // API Timeout (ms)
input int    InpAPIRetries    = 3;                        // API retry count

//--- Trading configuration  
input group "=== Trading Configuration ==="
input string InpSymbol        = "XAUUSD";                 // Symbol
input string InpTimeframe     = "H1";                     // Timeframe
input double InpRiskPercent   = 1.0;                      // Risk % per trade
input double InpMaxLots       = 5.0;                      // Maximum lot size
input bool   InpEnableTrading = false;                    // Enable auto-trading

//--- Allowed symbols (whitelist)
const string ALLOWED_SYMBOLS[] = {
   "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
   "AUDUSD", "USDCAD", "NZDUSD", "GBPJPY", "EURJPY",
   "EURGBP", "XAGUSD", "BTCUSD", "ETHUSD"
};

//--- Validate symbol against whitelist
bool IsAllowedSymbol(string symbol) {
   int count = ArraySize(ALLOWED_SYMBOLS);
   for(int i = 0; i < count; i++) {
      if(ALLOWED_SYMBOLS[i] == symbol) return true;
   }
   return false;
}

//--- Validate configuration at startup
bool ValidateConfig() {
   if(InpAPIToken == "") {
      Print("[GalaxyVast] ERROR: API Token not set. Please configure InpAPIToken.");
      return false;
   }
   if(StringLen(InpAPIToken) < 20) {
      Print("[GalaxyVast] ERROR: API Token too short. Please check your token.");
      return false;
   }
   if(!IsAllowedSymbol(InpSymbol)) {
      Print("[GalaxyVast] ERROR: Symbol '", InpSymbol, "' not supported.");
      return false;
   }
   if(InpRiskPercent <= 0 || InpRiskPercent > 10) {
      Print("[GalaxyVast] ERROR: RiskPercent must be between 0 and 10.");
      return false;
   }
   return true;
}

#endif // GALAXY_VAST_CONFIG_MQH
