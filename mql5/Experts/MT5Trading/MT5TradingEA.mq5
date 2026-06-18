//+------------------------------------------------------------------+
//|                                             MT5TradingEA.mq5     |
//|                          ⚠️ این فایل منسوخ شده است               |
//|                          از MT5TradingEA_Complete.mq5 استفاده کن |
//+------------------------------------------------------------------+
// این فایل در فاز ۶ به حالت منسوخ (deprecated) تبدیل شد.
// فایل اصلی و معتبر: MT5TradingEA_Complete.mq5
// دلیل: MT5TradingEA_Complete.mq5 دارای OnTimer، OnTradeTransaction،
//        DrawManager کامل و RiskManager یکپارچه است.
//
// برای نصب: فقط MT5TradingEA_Complete.mq5 را Compile و روی چارت بگذارید.
//+------------------------------------------------------------------+
#property copyright "Bot12 Trading System"
#property version   "1.00"
#property description "⚠️ DEPRECATED - Use MT5TradingEA_Complete.mq5"

// این فایل هیچ منطقی ندارد و نباید Compile شود.
// لطفاً MT5TradingEA_Complete.mq5 را به‌جای این فایل استفاده کنید.

void OnInit() {
   Alert("⚠️ این فایل منسوخ است! لطفاً MT5TradingEA_Complete.mq5 را استفاده کنید.");
   ExpertRemove();
}
void OnTick() {}
void OnDeinit(const int reason) {}
