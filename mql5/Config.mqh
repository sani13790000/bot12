//+------------------------------------------------------------------+
//| Config.mqh — Galaxy Vast AI Trading Bot Configuration            |
//| All server-side settings in one place                            |
//+------------------------------------------------------------------+
#pragma once

//--- Server configuration
// Change API_BASE_URL to your production server before deploying
input string API_BASE_URL    = "http://localhost:8000";  // API Base URL
input string API_TOKEN       = "";                       // JWT Bearer token (from /auth/login)
input int    API_TIMEOUT_MS  = 10000;                    // HTTP timeout in milliseconds

//--- Trading configuration  
input string TRADING_SYMBOL  = "XAUUSD";                 // Default symbol
input double RISK_PCT        = 1.0;                      // Risk per trade (%)
input double INITIAL_BALANCE = 10000.0;                  // Initial balance
input bool   SEMI_AUTO_MODE  = false;                    // Semi-auto mode

//--- License
input string LICENSE_KEY     = "";                       // License key
