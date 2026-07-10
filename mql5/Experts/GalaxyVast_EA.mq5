//+------------------------------------------------------------------+
//| GalaxyVast_EA.mq5                                                 |
//| Expert Advisor for MetaTrader 5                                  |
//| Galaxy Vast AI Trading Platform v1.0                            |
//| Connects to Python backend for AI signal generation              |
//+------------------------------------------------------------------+

#property copyright "Galaxy Vast Trading"
#property link      "https://github.com/sani13790000/bot12"
#property version   "1.0"
#property description "AI trading EA: SMC + Price Action + Decision Engine"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

// Input parameters
input double   LotSize = 0.1;
input int      StopLossPoints = 100;
input int      TakeProfitPoints = 200;
input string   BackendURL = "http://localhost:8000";
input string   APIToken = "";
input bool     EnableTrading = true;
input bool     DemoMode = true;
input int      CheckInterval = 5;

// Global variables
CTrade         trade;
CPositionInfo  positionInfo;
int            lastCheckTime = 0;
int            tradesThisPeriod = 0;
double         dailyLoss = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                  |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("╔════════════════════════════════════════════════════════════╗");
    Print("║         Galaxy Vast Expert Advisor v1.0 - INITIALIZED     ║");
    Print("╚════════════════════════════════════════════════════════════╝");
    
    trade.SetExpertMagicNumber(20260710);
    
    if (LotSize <= 0 || LotSize > 100)
    {
        Print("ERROR: Invalid LotSize");
        return INIT_FAILED;
    }
    
    if (!VerifyBackendConnection())
    {
        Print("WARNING: Backend not available. Will retry on tick");
    }
    
    Print("✓ Symbol: ", Symbol());
    Print("✓ LotSize: ", LotSize);
    Print("✓ Demo Mode: ", DemoMode);
    
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    Print("╔════════════════════════════════════════════════════════════╗");
    Print("║              Expert Advisor Shutting Down                 ║");
    Print("╚════════════════════════════════════════════════════════════╝");
    Print("Total trades in session: ", tradesThisPeriod);
    Print("Daily loss: ", dailyLoss);
}

//+------------------------------------------------------------------+
//| Expert tick function                                            |
//+------------------------------------------------------------------+
void OnTick()
{
    if ((int)TimeCurrent() - lastCheckTime < CheckInterval)
        return;
    
    lastCheckTime = (int)TimeCurrent();
    
    if (!CheckDailyLimits())
        return;
    
    string signal = GetSignalFromBackend();
    if (signal == "")
        return;
    
    ProcessSignal(signal);
    UpdateBackendStats();
}

//+------------------------------------------------------------------+
//| Verify backend connection                                       |
//+------------------------------------------------------------------+
bool VerifyBackendConnection()
{
    string url = BackendURL + "/api/health";
    string headers = "User-Agent: GalaxyVast-EA/1.0\r\nContent-Type: application/json\r\n";
    string response = "";
    
    int result = WebRequest("GET", url, headers, NULL, 5000, response);
    return (result == 200);
}

//+------------------------------------------------------------------+
//| Get signal from backend API                                     |
//+------------------------------------------------------------------+
string GetSignalFromBackend()
{
    if (APIToken == "")
        return "";
    
    string url = BackendURL + "/api/trading/signal/" + Symbol();
    string headers = "User-Agent: GalaxyVast-EA/1.0\r\n"
                    "Content-Type: application/json\r\n"
                    "Authorization: Bearer " + APIToken + "\r\n";
    
    string response = "";
    int result = WebRequest("GET", url, headers, NULL, 5000, response);
    
    if (result != 200)
        return "";
    
    // Parse JSON: {"signal":"BUY","confidence":0.85}
    if (StringFind(response, "\"signal\":\"BUY\"") >= 0)
        return "BUY";
    if (StringFind(response, "\"signal\":\"SELL\"") >= 0)
        return "SELL";
    
    return "";
}

//+------------------------------------------------------------------+
//| Process trading signal                                          |
//+------------------------------------------------------------------+
void ProcessSignal(const string signal)
{
    if (PositionSelect(Symbol()))
    {
        Print("Position exists, skipping");
        return;
    }
    
    if (!EnableTrading || !VerifyTradingAllowed())
        return;
    
    double bid = SymbolInfoDouble(Symbol(), SYMBOL_BID);
    double ask = SymbolInfoDouble(Symbol(), SYMBOL_ASK);
    double sl = 0, tp = 0;
    
    if (signal == "BUY")
    {
        sl = bid - StopLossPoints * _Point;
        tp = ask + TakeProfitPoints * _Point;
        Print("BUY Signal - Entry: ", ask, " SL: ", sl, " TP: ", tp);
        trade.Buy(LotSize, Symbol(), ask, sl, tp, "Galaxy Vast BUY");
    }
    else if (signal == "SELL")
    {
        sl = ask + StopLossPoints * _Point;
        tp = bid - TakeProfitPoints * _Point;
        Print("SELL Signal - Entry: ", bid, " SL: ", sl, " TP: ", tp);
        trade.Sell(LotSize, Symbol(), bid, sl, tp, "Galaxy Vast SELL");
    }
    
    if (trade.ResultRetcode() == TRADE_RETCODE_DONE)
    {
        Print("✓ Trade executed. Ticket: ", trade.ResultOrder());
        tradesThisPeriod++;
        SendTradeNotification(trade.ResultOrder(), signal);
    }
    else
    {
        Print("✗ Trade failed: ", trade.ResultRetcodeDescription());
    }
}

//+------------------------------------------------------------------+
//| Send trade notification to backend                              |
//+------------------------------------------------------------------+
void SendTradeNotification(ulong ticket, const string signal)
{
    if (APIToken == "")
        return;
    
    string url = BackendURL + "/api/trading/notify";
    string headers = "User-Agent: GalaxyVast-EA/1.0\r\n"
                    "Content-Type: application/json\r\n"
                    "Authorization: Bearer " + APIToken + "\r\n";
    
    string payload = "{\"ticket\":" + IntegerToString(ticket) + ",\"symbol\":\"" + Symbol() + "\",\"signal\":\"" + signal + "\"}";
    string response = "";
    
    WebRequest("POST", url, headers, payload, 5000, response);
}

//+------------------------------------------------------------------+
//| Check daily loss limits                                         |
//+------------------------------------------------------------------+
bool CheckDailyLimits()
{
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    dailyLoss = balance - equity;
    
    if (dailyLoss > balance * 0.05)  // 5% daily limit
    {
        Print("Daily loss limit exceeded");
        return false;
    }
    
    return true;
}

//+------------------------------------------------------------------+
//| Verify trading is allowed                                       |
//+------------------------------------------------------------------+
bool VerifyTradingAllowed()
{
    if (!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
        return false;
    if (!MQL5InfoInteger(MQL5_TRADE_ALLOWED))
        return false;
    if (SymbolInfoInteger(Symbol(), SYMBOL_SPREAD) > 50)
        return false;
    
    return true;
}

//+------------------------------------------------------------------+
//| Update backend with account stats                               |
//+------------------------------------------------------------------+
void UpdateBackendStats()
{
    static int updateCounter = 0;
    if (++updateCounter % 60 != 0)
        return;
    
    if (APIToken == "")
        return;
    
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    
    string url = BackendURL + "/api/trading/stats";
    string headers = "User-Agent: GalaxyVast-EA/1.0\r\n"
                    "Content-Type: application/json\r\n"
                    "Authorization: Bearer " + APIToken + "\r\n";
    
    string payload = "{\"equity\":" + DoubleToString(equity, 2) + ",\"balance\":" + DoubleToString(balance, 2) + "}";
    string response = "";
    
    WebRequest("POST", url, headers, payload, 5000, response);
}

//+------------------------------------------------------------------+
