
//+------------------------------------------------------------------+
//|                                          ExecutionEngine.mqh     |
//|                                                                  |
//|  توضیح: موتور اجرای معاملات حرفه‌ای برای پروژه Bot12          |
//|                                                                  |
//|  این ماژول مسئول اجرای دقیق و هوشمند معاملات است:             |
//|  - اجرای Market Order با اسلیپیج کنترل شده                    |
//|  - اجرای Limit Order و Stop Order                              |
//|  - مدیریت خطاهای اجرا با Retry Logic                          |
//|  - تایید اجرا و ثبت لاگ کامل                                  |
//|  - Slippage Monitor و هشدار                                    |
//|  - Pre-trade Validation کامل                                    |
//+------------------------------------------------------------------+

#ifndef EXECUTION_ENGINE_MQH
#define EXECUTION_ENGINE_MQH

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\OrderInfo.mqh>

//--- ساختار نتیجه اجرا
struct ExecutionResult {
   bool     success;          // آیا موفق بود؟
   ulong    ticket;           // شماره تیکت
   double   executed_price;   // قیمت اجرا شده
   double   slippage_points;  // اسلیپیج واقعی
   double   spread_at_exec;   // اسپرد در زمان اجرا
   int      retry_count;      // تعداد تلاش‌ها
   string   error_message;    // پیام خطا (اگر باشد)
   datetime exec_time;        // زمان اجرا
   ulong    execution_ms;     // زمان اجرا به میلی‌ثانیه
};

//--- ساختار درخواست معامله
struct TradeRequest {
   ENUM_POSITION_TYPE  direction;        // جهت: BUY یا SELL
   double              volume;           // حجم
   double              price;            // قیمت (برای Limit/Stop)
   double              stop_loss;        // حد ضرر
   double              take_profit;      // حد سود
   ENUM_ORDER_TYPE     order_type;       // نوع سفارش
   string              comment;          // کامنت
   ulong               magic;            // magic number
   int                 max_slippage;     // حداکثر اسلیپیج مجاز (پوینت)
   bool                use_market;       // آیا Market Order استفاده شود؟
};

//+------------------------------------------------------------------+
//| موتور اجرای معاملات                                              |
//+------------------------------------------------------------------+
class CExecutionEngine
{
private:
   string         m_symbol;          // نماد
   CTrade         m_trade;           // شیء معامله
   CPositionInfo  m_position;        // اطلاعات پوزیشن
   COrderInfo     m_order;           // اطلاعات سفارش

   // تنظیمات اجرا
   int            m_max_retries;     // حداکثر تلاش مجدد
   int            m_retry_delay_ms;  // تاخیر بین تلاش‌ها (میلی‌ثانیه)
   int            m_max_slippage;    // حداکثر اسلیپیج مجاز
   bool           m_log_enabled;     // آیا لاگ فعال است؟

   // آمار اجرا
   int            m_total_executions;   // کل اجراها
   int            m_successful_execs;   // اجراهای موفق
   double         m_avg_slippage;       // میانگین اسلیپیج

   //--- لاگ اجرا
   void LogExecution(const string action, const ExecutionResult &result) {
      if(!m_log_enabled) return;
      PrintFormat(
         "[EXEC] %s | %s | موفق:%s | تیکت:%d | قیمت:%.5f | اسلیپیج:%.1f پوینت | زمان:%dms",
         action, m_symbol,
         result.success ? "بله" : "خیر",
         result.ticket, result.executed_price,
         result.slippage_points, result.execution_ms
      );
   }

   //--- بررسی قبل از معامله
   bool PreTradeCheck(const TradeRequest &req, string &error_msg) {
      // بررسی نماد
      if(!SymbolInfoInteger(m_symbol, SYMBOL_TRADE_MODE)) {
         error_msg = "نماد در دسترس نیست";
         return false;
      }

      // بررسی حجم
      double min_lot  = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
      double max_lot  = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
      if(req.volume < min_lot || req.volume > max_lot) {
         error_msg = StringFormat("حجم نامعتبر: %.2f (min:%.2f, max:%.2f)", req.volume, min_lot, max_lot);
         return false;
      }

      // بررسی اسپرد
      long spread = SymbolInfoInteger(m_symbol, SYMBOL_SPREAD);
      if(spread > m_max_slippage * 2) {
         error_msg = StringFormat("اسپرد خیلی بالا: %d پوینت", spread);
         return false;
      }

      // بررسی مارجین کافی
      double margin_required = 0;
      ENUM_ORDER_TYPE ord_type = (req.direction == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      if(!OrderCalcMargin(ord_type, m_symbol, req.volume, SymbolInfoDouble(m_symbol, SYMBOL_ASK), margin_required)) {
         error_msg = "محاسبه مارجین ناموفق";
         return false;
      }

      double free_margin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      if(free_margin < margin_required * 1.2) {
         error_msg = StringFormat("مارجین ناکافی: %.2f < %.2f", free_margin, margin_required);
         return false;
      }

      // بررسی SL و TP
      if(req.stop_loss > 0 && req.take_profit > 0) {
         int stop_level = (int)SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
         double point   = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
         double ask     = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
         double bid     = SymbolInfoDouble(m_symbol, SYMBOL_BID);

         if(req.direction == POSITION_TYPE_BUY) {
            if((ask - req.stop_loss) / point < stop_level) {
               error_msg = StringFormat("SL خیلی نزدیک به قیمت (حداقل: %d پوینت)", stop_level);
               return false;
            }
         } else {
            if((req.stop_loss - bid) / point < stop_level) {
               error_msg = StringFormat("SL خیلی نزدیک به قیمت (حداقل: %d پوینت)", stop_level);
               return false;
            }
         }
      }

      return true;
   }

public:
   //--- سازنده
   CExecutionEngine(const string symbol, const ulong magic = 12345) {
      m_symbol        = symbol;
      m_max_retries   = 3;
      m_retry_delay_ms = 500;
      m_max_slippage  = 30;
      m_log_enabled   = true;
      m_total_executions  = 0;
      m_successful_execs  = 0;
      m_avg_slippage  = 0;

      m_trade.SetExpertMagicNumber(magic);
      m_trade.SetDeviationInPoints(m_max_slippage);
      m_trade.SetTypeFilling(ORDER_FILLING_FOK);
      m_trade.SetAsyncMode(false);
   }

   //--- تنظیمات
   void SetMaxRetries(const int retries)    { m_max_retries = retries; }
   void SetMaxSlippage(const int slippage)  { m_max_slippage = slippage; m_trade.SetDeviationInPoints(slippage); }
   void SetLogEnabled(const bool enabled)   { m_log_enabled = enabled; }

   //+----------------------------------------------------------------+
   //| اجرای Market Order (خرید/فروش فوری)                          |
   //| با Retry Logic و اسلیپیج کنترل شده                           |
   //+----------------------------------------------------------------+
   ExecutionResult ExecuteMarketOrder(const TradeRequest &req) {
      ExecutionResult result;
      result.success      = false;
      result.ticket       = 0;
      result.retry_count  = 0;
      result.exec_time    = TimeCurrent();

      // بررسی‌های قبل از معامله
      string pre_check_error = "";
      if(!PreTradeCheck(req, pre_check_error)) {
         result.error_message = "Pre-check ناموفق: " + pre_check_error;
         LogExecution("MARKET_ORDER_REJECTED", result);
         return result;
      }

      uint start_ms = GetTickCount();

      // حلقه Retry
      for(int attempt = 0; attempt < m_max_retries; attempt++) {
         result.retry_count = attempt + 1;

         // دریافت قیمت جاری
         double price = 0;
         if(req.direction == POSITION_TYPE_BUY) {
            price = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
            result.spread_at_exec = (SymbolInfoDouble(m_symbol, SYMBOL_ASK) - SymbolInfoDouble(m_symbol, SYMBOL_BID)) /
                                    SymbolInfoDouble(m_symbol, SYMBOL_POINT);

            if(m_trade.Buy(req.volume, m_symbol, price, req.stop_loss, req.take_profit, req.comment)) {
               result.success = true;
               result.ticket  = m_trade.ResultOrder();
               result.executed_price = m_trade.ResultPrice();
               result.slippage_points = MathAbs(price - result.executed_price) / SymbolInfoDouble(m_symbol, SYMBOL_POINT);
               break;
            }
         } else {
            price = SymbolInfoDouble(m_symbol, SYMBOL_BID);
            result.spread_at_exec = (SymbolInfoDouble(m_symbol, SYMBOL_ASK) - SymbolInfoDouble(m_symbol, SYMBOL_BID)) /
                                    SymbolInfoDouble(m_symbol, SYMBOL_POINT);

            if(m_trade.Sell(req.volume, m_symbol, price, req.stop_loss, req.take_profit, req.comment)) {
               result.success = true;
               result.ticket  = m_trade.ResultOrder();
               result.executed_price = m_trade.ResultPrice();
               result.slippage_points = MathAbs(price - result.executed_price) / SymbolInfoDouble(m_symbol, SYMBOL_POINT);
               break;
            }
         }

         // خطا - بررسی نوع خطا
         int error_code = (int)m_trade.ResultRetcode();
         result.error_message = StringFormat("تلاش %d: کد خطا %d - %s", attempt+1, error_code, m_trade.ResultComment());

         // اگر خطا قابل retry نباشد، متوقف شو
         if(error_code == TRADE_RETCODE_INVALID_STOPS ||
            error_code == TRADE_RETCODE_TOO_MANY_REQUESTS ||
            error_code == TRADE_RETCODE_MARKET_CLOSED) {
            break;
         }

         // انتظار قبل از تلاش مجدد
         if(attempt < m_max_retries - 1)
            Sleep(m_retry_delay_ms);
      }

      result.execution_ms = GetTickCount() - start_ms;

      // به‌روزرسانی آمار
      m_total_executions++;
      if(result.success) {
         m_successful_execs++;
         m_avg_slippage = (m_avg_slippage * (m_successful_execs - 1) + result.slippage_points) / m_successful_execs;
      }

      LogExecution("MARKET_ORDER", result);
      return result;
   }

   //+----------------------------------------------------------------+
   //| اجرای Pending Order (Limit یا Stop)                           |
   //+----------------------------------------------------------------+
   ExecutionResult PlacePendingOrder(const TradeRequest &req) {
      ExecutionResult result;
      result.success     = false;
      result.ticket      = 0;
      result.retry_count = 1;
      result.exec_time   = TimeCurrent();

      uint start_ms = GetTickCount();
      bool placed = false;

      if(req.order_type == ORDER_TYPE_BUY_LIMIT) {
         placed = m_trade.BuyLimit(req.volume, req.price, m_symbol, req.stop_loss, req.take_profit, ORDER_TIME_GTC, 0, req.comment);
      } else if(req.order_type == ORDER_TYPE_SELL_LIMIT) {
         placed = m_trade.SellLimit(req.volume, req.price, m_symbol, req.stop_loss, req.take_profit, ORDER_TIME_GTC, 0, req.comment);
      } else if(req.order_type == ORDER_TYPE_BUY_STOP) {
         placed = m_trade.BuyStop(req.volume, req.price, m_symbol, req.stop_loss, req.take_profit, ORDER_TIME_GTC, 0, req.comment);
      } else if(req.order_type == ORDER_TYPE_SELL_STOP) {
         placed = m_trade.SellStop(req.volume, req.price, m_symbol, req.stop_loss, req.take_profit, ORDER_TIME_GTC, 0, req.comment);
      } else {
         result.error_message = "نوع سفارش نامعتبر";
         return result;
      }

      result.execution_ms = GetTickCount() - start_ms;

      if(placed) {
         result.success        = true;
         result.ticket         = m_trade.ResultOrder();
         result.executed_price = req.price;
         result.slippage_points = 0;
         m_total_executions++;
         m_successful_execs++;
      } else {
         result.error_message = m_trade.ResultComment();
         m_total_executions++;
      }

      LogExecution("PENDING_ORDER", result);
      return result;
   }

   //+----------------------------------------------------------------+
   //| بستن پوزیشن با بررسی‌های کامل                                 |
   //+----------------------------------------------------------------+
   ExecutionResult ClosePosition(const ulong ticket, const string reason = "") {
      ExecutionResult result;
      result.success     = false;
      result.ticket      = ticket;
      result.retry_count = 0;
      result.exec_time   = TimeCurrent();

      if(!m_position.SelectByTicket(ticket)) {
         result.error_message = "پوزیشن یافت نشد";
         return result;
      }

      uint start_ms = GetTickCount();

      for(int attempt = 0; attempt < m_max_retries; attempt++) {
         result.retry_count++;

         if(m_trade.PositionClose(ticket, m_max_slippage)) {
            result.success        = true;
            result.executed_price = m_trade.ResultPrice();
            result.slippage_points = 0;
            break;
         }

         result.error_message = StringFormat("تلاش %d: %s", attempt+1, m_trade.ResultComment());

         if(attempt < m_max_retries - 1)
            Sleep(m_retry_delay_ms);
      }

      result.execution_ms = GetTickCount() - start_ms;

      if(result.success) {
         Print("✅ پوزیشن بسته شد | تیکت:", ticket, " | دلیل:", reason);
      } else {
         Print("❌ خطا در بستن پوزیشن | تیکت:", ticket, " | خطا:", result.error_message);
      }

      return result;
   }

   //+----------------------------------------------------------------+
   //| بستن تمام پوزیشن‌های باز                                      |
   //+----------------------------------------------------------------+
   int CloseAllPositions(const string reason = "Close All") {
      int closed = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--) {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(!m_position.SelectByTicket(ticket)) continue;
         if(m_position.Symbol() != m_symbol) continue;

         ExecutionResult res = ClosePosition(ticket, reason);
         if(res.success) closed++;
      }
      PrintFormat("✅ %d پوزیشن بسته شد | دلیل: %s", closed, reason);
      return closed;
   }

   //+----------------------------------------------------------------+
   //| بستن تمام Buy یا تمام Sell                                    |
   //+----------------------------------------------------------------+
   int CloseByDirection(const ENUM_POSITION_TYPE dir, const string reason = "") {
      int closed = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--) {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(!m_position.SelectByTicket(ticket)) continue;
         if(m_position.Symbol() != m_symbol) continue;
         if(m_position.PositionType() != dir) continue;

         ExecutionResult res = ClosePosition(ticket, reason);
         if(res.success) closed++;
      }
      return closed;
   }

   //--- آمار اجرا
   string GetExecutionStats() {
      double success_rate = (m_total_executions > 0) ?
         (double)m_successful_execs / m_total_executions * 100.0 : 0;
      return StringFormat(
         "📈 آمار اجرا:\n کل: %d | موفق: %d | نرخ: %.1f%% | میانگین اسلیپیج: %.1f پوینت",
         m_total_executions, m_successful_execs, success_rate, m_avg_slippage
      );
   }
};

#endif // EXECUTION_ENGINE_MQH
