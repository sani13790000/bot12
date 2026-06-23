//+------------------------------------------------------------------+
//| mql5/Include/MT5Trading/RiskManager_Patch.mqh                    |
//| Phase R MQL5 Fixes:                                              |
//|  MQ-1: OrderSend() result not checked                            |
//|  MQ-2: StopLoss=0.0 blocked                                      |
//|  MQ-3: Magic number from account (not hardcoded)                 |
//|  MQ-4: Retry on REQUOTE/PRICE_CHANGED                            |
//|  MQ-5: Position close magic-number guard                         |
//+------------------------------------------------------------------+
#ifndef RISK_MANAGER_PATCH_MQH
#define RISK_MANAGER_PATCH_MQH
#include <Trade\Trade.mqh>

#ifndef EA_MAGIC_NUMBER
  #define EA_MAGIC_NUMBER GetMagicNumber()
#endif

bool IsRetryableError(uint retcode) {
   return (retcode == TRADE_RETCODE_REQUOTE      ||
           retcode == TRADE_RETCODE_PRICE_CHANGED ||
           retcode == TRADE_RETCODE_OFF_QUOTES    ||
           retcode == TRADE_RETCODE_CONNECTION    ||
           retcode == TRADE_RETCODE_TIMEOUT);
}

int GetMagicNumber() {
   long account = AccountInfoInteger(ACCOUNT_LOGIN);
   return (int)((account % 89999) + 10000);  // MQ-3: unique per account
}

bool SafeOrderSend(MqlTradeRequest &request, MqlTradeResult &result, int maxRetries=3, int retryDelayMs=500) {
   if(request.sl == 0.0 && request.type != ORDER_TYPE_CLOSE_BY) {  // MQ-2
      Print("SafeOrderSend: BLOCKED SL=0.0");
      result.retcode = TRADE_RETCODE_INVALID_STOPS;
      return false;
   }
   request.magic = EA_MAGIC_NUMBER;  // MQ-3
   for(int attempt=1; attempt<=maxRetries; attempt++) {
      ZeroMemory(result);
      bool sent = OrderSend(request, result);  // MQ-1: check result
      if(sent && result.retcode == TRADE_RETCODE_DONE) {
         PrintFormat("SafeOrderSend OK ticket=%d attempt=%d", result.order, attempt);
         return true;
      }
      PrintFormat("SafeOrderSend attempt=%d retcode=%d", attempt, result.retcode);
      if(!IsRetryableError(result.retcode) || attempt==maxRetries) break;  // MQ-4
      Sleep(retryDelayMs * attempt);
   }
   return false;
}

bool SafeClosePosition(ulong ticket, bool requireConfirm=true, int maxRetries=3) {
   if(!PositionSelectByTicket(ticket)) return false;
   string symbol = PositionGetString(POSITION_SYMBOL);
   double volume = PositionGetDouble(POSITION_VOLUME);
   long posType  = PositionGetInteger(POSITION_TYPE);
   ulong magic   = PositionGetInteger(POSITION_MAGIC);
   if(magic != (ulong)EA_MAGIC_NUMBER) {  // MQ-5: only close our positions
      PrintFormat("SafeClosePosition BLOCKED ticket=%d magic=%d ours=%d", ticket, magic, EA_MAGIC_NUMBER);
      return false;
   }
   ENUM_ORDER_TYPE closeType = (posType==POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   MqlTradeRequest req = {};
   MqlTradeResult  res = {};
   req.action   = TRADE_ACTION_DEAL;
   req.symbol   = symbol;
   req.volume   = volume;
   req.type     = closeType;
   req.position = ticket;
   req.price    = (closeType==ORDER_TYPE_SELL) ? SymbolInfoDouble(symbol,SYMBOL_BID) : SymbolInfoDouble(symbol,SYMBOL_ASK);
   req.deviation = 20;
   req.magic    = EA_MAGIC_NUMBER;
   req.comment  = "SafeClose";
   for(int i=1; i<=maxRetries; i++) {
      ZeroMemory(res);
      if(OrderSend(req,res) && res.retcode==TRADE_RETCODE_DONE) return true;
      if(!IsRetryableError(res.retcode) || i==maxRetries) break;
      Sleep(500*i);
   }
   return false;
}

#endif
