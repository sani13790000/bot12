
//+------------------------------------------------------------------+
//|                                        RiskManager_Complete.mqh  |
//|                                                                  |
//|  توضیح: تکمیل ماژول مدیریت ریسک برای پروژه Bot12              |
//|                                                                  |
//|  این فایل شامل توابع تکمیلی RiskManager است که در فایل اصلی   |
//|  موجود نبودند:                                                   |
//|  - محاسبه TakeProfit بر اساس روش‌های مختلف                     |
//|  - سیستم Partial Close حرفه‌ای                                  |
//|  - سیستم Scale In/Out                                          |
//|  - مدیریت پوزیشن‌های متعدد                                     |
//|  - سیستم هشدار ریسک پیشرفته                                   |
//+------------------------------------------------------------------+

#ifndef RISK_MANAGER_COMPLETE_MQH
#define RISK_MANAGER_COMPLETE_MQH

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Arrays\ArrayDouble.mqh>

//--- ساختار نتیجه TakeProfit
struct TakeProfitResult {
   double   tp1;              // هدف اول (۱:۱)
   double   tp2;              // هدف دوم (۱:۲)
   double   tp3;              // هدف سوم (۱:۳)
   double   tp_structure;     // هدف بر اساس ساختار بازار
   double   tp_fib_618;       // هدف فیبوناچی ۶۱.۸
   double   tp_fib_100;       // هدف فیبوناچی ۱۰۰
   double   tp_fib_161;       // هدف فیبوناچی ۱۶۱.۸
   double   recommended_tp;   // هدف پیشنهادی
   double   risk_reward;      // نسبت ریسک به ریوارد
   bool     is_valid;         // آیا محاسبه معتبر است؟
   string   reason;           // دلیل انتخاب
};

//--- ساختار نتیجه Partial Close
struct PartialCloseResult {
   bool     executed;         // آیا اجرا شد؟
   double   closed_volume;    // حجم بسته شده
   double   remaining_volume; // حجم باقی‌مانده
   double   realized_pnl;     // سود/زیان تحقق یافته
   string   message;          // پیام نتیجه
};

//--- ساختار سطح Scale Out
struct ScaleOutLevel {
   double   price;            // قیمت هدف
   double   percent;          // درصد حجم برای بستن
   bool     move_sl_to_entry; // آیا SL به نقطه ورود منتقل شود؟
   bool     executed;         // آیا اجرا شده؟
};

//+------------------------------------------------------------------+
//| کلاس تکمیلی مدیریت ریسک                                         |
//+------------------------------------------------------------------+
class CRiskManagerComplete
{
private:
   string            m_symbol;          // نماد معاملاتی
   CTrade            m_trade;           // شیء معامله
   CPositionInfo     m_position;        // اطلاعات پوزیشن

   // پارامترهای TP
   double            m_atr_value;       // مقدار ATR جاری
   double            m_pip_size;        // اندازه پیپ

   // سطوح Scale Out
   ScaleOutLevel     m_scale_levels[5]; // حداکثر ۵ سطح
   int               m_scale_count;     // تعداد سطوح فعال

public:
   //--- سازنده
   void CRiskManagerComplete(const string symbol) {
      m_symbol = symbol;
      m_pip_size = SymbolInfoDouble(symbol, SYMBOL_POINT) * 10;
      if(SymbolInfoInteger(symbol, SYMBOL_DIGITS) == 3 || 
         SymbolInfoInteger(symbol, SYMBOL_DIGITS) == 5)
         m_pip_size = SymbolInfoDouble(symbol, SYMBOL_POINT) * 10;
      else
         m_pip_size = SymbolInfoDouble(symbol, SYMBOL_POINT);
      m_scale_count = 0;
      m_trade.SetExpertMagicNumber(12345);
      m_trade.SetDeviationInPoints(10);
      m_trade.SetTypeFilling(ORDER_FILLING_FOK);
   }

   //+----------------------------------------------------------------+
   //| به‌روزرسانی مقدار ATR                                          |
   //+----------------------------------------------------------------+
   void UpdateATR(const double atr_value) {
      // به‌روزرسانی مقدار ATR برای محاسبات
      m_atr_value = atr_value;
   }

   //+----------------------------------------------------------------+
   //| محاسبه TakeProfit بر اساس روش‌های مختلف                       |
   //| این تابع چندین روش مختلف محاسبه TP را پیاده‌سازی می‌کند      |
   //+----------------------------------------------------------------+
   TakeProfitResult CalculateTakeProfits(
      const ENUM_POSITION_TYPE direction,
      const double entry_price,
      const double stop_loss,
      const double swing_high = 0,
      const double swing_low = 0,
      const double structure_target = 0
   ) {
      TakeProfitResult result;
      result.is_valid = false;

      // اعتبارسنجی ورودی‌ها
      if(entry_price <= 0 || stop_loss <= 0) {
         result.reason = "ورودی‌های نامعتبر";
         return result;
      }

      double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      double sl_distance = 0;

      // محاسبه فاصله SL
      if(direction == POSITION_TYPE_BUY) {
         if(stop_loss >= entry_price) {
            result.reason = "SL باید زیر قیمت ورود باشد";
            return result;
         }
         sl_distance = (entry_price - stop_loss);
      } else {
         if(stop_loss <= entry_price) {
            result.reason = "SL باید بالای قیمت ورود باشد";
            return result;
         }
         sl_distance = (stop_loss - entry_price);
      }

      if(sl_distance <= 0) {
         result.reason = "فاصله SL صفر است";
         return result;
      }

      // --- محاسبه اهداف RR ---
      if(direction == POSITION_TYPE_BUY) {
         result.tp1 = NormalizeDouble(entry_price + sl_distance * 1.0, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
         result.tp2 = NormalizeDouble(entry_price + sl_distance * 2.0, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
         result.tp3 = NormalizeDouble(entry_price + sl_distance * 3.0, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
      } else {
         result.tp1 = NormalizeDouble(entry_price - sl_distance * 1.0, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
         result.tp2 = NormalizeDouble(entry_price - sl_distance * 2.0, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
         result.tp3 = NormalizeDouble(entry_price - sl_distance * 3.0, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
      }

      // --- محاسبه اهداف فیبوناچی (بر اساس Swing) ---
      if(swing_high > 0 && swing_low > 0 && swing_high > swing_low) {
         double swing_range = swing_high - swing_low;
         if(direction == POSITION_TYPE_BUY) {
            result.tp_fib_618 = NormalizeDouble(swing_low + swing_range * 0.618, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
            result.tp_fib_100 = NormalizeDouble(swing_high, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
            result.tp_fib_161 = NormalizeDouble(swing_low + swing_range * 1.618, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
         } else {
            result.tp_fib_618 = NormalizeDouble(swing_high - swing_range * 0.618, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
            result.tp_fib_100 = NormalizeDouble(swing_low, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
            result.tp_fib_161 = NormalizeDouble(swing_high - swing_range * 1.618, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
         }
      }

      // --- هدف بر اساس ساختار بازار ---
      if(structure_target > 0) {
         result.tp_structure = structure_target;
      }

      // --- انتخاب بهترین TP پیشنهادی ---
      // اولویت: ساختار > فیبو > RR 2:1
      if(result.tp_structure > 0) {
         // بررسی اینکه آیا هدف ساختار معقول است
         double struct_distance = MathAbs(result.tp_structure - entry_price);
         double struct_rr = struct_distance / sl_distance;

         if(struct_rr >= 1.5 && struct_rr <= 5.0) {
            result.recommended_tp = result.tp_structure;
            result.reason = "هدف بر اساس ساختار بازار";
            result.risk_reward = struct_rr;
         } else if(result.tp_fib_618 > 0) {
            result.recommended_tp = result.tp_fib_618;
            result.reason = "هدف فیبوناچی ۶۱.۸%";
            result.risk_reward = MathAbs(result.tp_fib_618 - entry_price) / sl_distance;
         } else {
            result.recommended_tp = result.tp2;
            result.reason = "هدف RR 2:1";
            result.risk_reward = 2.0;
         }
      } else if(result.tp_fib_618 > 0) {
         result.recommended_tp = result.tp_fib_618;
         result.reason = "هدف فیبوناچی ۶۱.۸%";
         result.risk_reward = MathAbs(result.tp_fib_618 - entry_price) / sl_distance;
      } else {
         result.recommended_tp = result.tp2;
         result.reason = "هدف RR 2:1 (پیش‌فرض)";
         result.risk_reward = 2.0;
      }

      result.is_valid = true;
      return result;
   }

   //+----------------------------------------------------------------+
   //| بستن بخشی از پوزیشن (Partial Close)                          |
   //| این تابع مکانیزم حرفه‌ای Partial Close را پیاده‌سازی می‌کند  |
   //+----------------------------------------------------------------+
   PartialCloseResult PartialClose(
      const ulong ticket,
      const double close_percent,
      const bool move_sl_to_entry = false
   ) {
      PartialCloseResult result;
      result.executed = false;

      // اعتبارسنجی ورودی
      if(close_percent <= 0 || close_percent > 100) {
         result.message = "درصد بستن نامعتبر است";
         return result;
      }

      // انتخاب پوزیشن
      if(!m_position.SelectByTicket(ticket)) {
         result.message = "پوزیشن یافت نشد: " + IntegerToString(ticket);
         return result;
      }

      double current_volume = m_position.Volume();
      double entry_price    = m_position.PriceOpen();
      double current_sl     = m_position.StopLoss();
      double current_tp     = m_position.TakeProfit();
      string symbol         = m_position.Symbol();

      // محاسبه حجم برای بستن
      double close_volume = NormalizeDouble(current_volume * (close_percent / 100.0), 2);

      // اطمینان از حداقل لات
      double min_lot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
      double step_lot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

      close_volume = MathFloor(close_volume / step_lot) * step_lot;

      if(close_volume < min_lot) {
         result.message = "حجم برای Partial Close کمتر از حداقل مجاز است";
         return result;
      }

      // بستن بخشی از پوزیشن
      bool closed = false;
      if(m_position.PositionType() == POSITION_TYPE_BUY) {
         double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
         closed = m_trade.Sell(close_volume, symbol, bid, 0, 0, "Partial Close");
      } else {
         double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
         closed = m_trade.Buy(close_volume, symbol, ask, 0, 0, "Partial Close");
      }

      if(closed) {
         result.executed = true;
         result.closed_volume = close_volume;
         result.remaining_volume = current_volume - close_volume;

         // محاسبه سود تحقق یافته
         double price_diff = 0;
         if(m_position.PositionType() == POSITION_TYPE_BUY)
            price_diff = SymbolInfoDouble(symbol, SYMBOL_BID) - entry_price;
         else
            price_diff = entry_price - SymbolInfoDouble(symbol, SYMBOL_ASK);

         double tick_value = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
         double tick_size  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
         result.realized_pnl = (price_diff / tick_size) * tick_value * close_volume;

         // انتقال SL به نقطه ورود (Break Even)
         if(move_sl_to_entry && result.remaining_volume > 0) {
            double new_sl = entry_price;
            // اضافه کردن چند پوینت برای اطمینان
            double buffer = SymbolInfoDouble(symbol, SYMBOL_POINT) * 5;
            if(m_position.PositionType() == POSITION_TYPE_BUY)
               new_sl = entry_price + buffer;
            else
               new_sl = entry_price - buffer;

            m_trade.PositionModify(ticket, new_sl, current_tp);
         }

         result.message = StringFormat(
            "Partial Close موفق | بسته: %.2f | باقی: %.2f | P&L: %.2f",
            close_volume, result.remaining_volume, result.realized_pnl
         );
      } else {
         result.message = "خطا در Partial Close: " + m_trade.ResultComment();
      }

      return result;
   }

   //+----------------------------------------------------------------+
   //| تنظیم سطوح Scale Out خودکار                                   |
   //| این تابع سطوح خروج تدریجی را تعریف می‌کند                    |
   //+----------------------------------------------------------------+
   void SetScaleOutLevels(
      const ENUM_POSITION_TYPE direction,
      const double entry_price,
      const double stop_loss,
      const double final_tp
   ) {
      // پاک کردن سطوح قبلی
      m_scale_count = 0;
      ArrayInitialize(m_scale_levels, 0);

      double sl_dist = MathAbs(entry_price - stop_loss);
      int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

      // سطح ۱: بستن ۳۰% در RR 1:1
      m_scale_levels[0].price = direction == POSITION_TYPE_BUY ?
         NormalizeDouble(entry_price + sl_dist * 1.0, digits) :
         NormalizeDouble(entry_price - sl_dist * 1.0, digits);
      m_scale_levels[0].percent = 30.0;
      m_scale_levels[0].move_sl_to_entry = true;
      m_scale_levels[0].executed = false;

      // سطح ۲: بستن ۳۰% در RR 1:2
      m_scale_levels[1].price = direction == POSITION_TYPE_BUY ?
         NormalizeDouble(entry_price + sl_dist * 2.0, digits) :
         NormalizeDouble(entry_price - sl_dist * 2.0, digits);
      m_scale_levels[1].percent = 30.0;
      m_scale_levels[1].move_sl_to_entry = false;
      m_scale_levels[1].executed = false;

      // سطح ۳: بستن ۴۰% باقیمانده در TP نهایی
      m_scale_levels[2].price = final_tp;
      m_scale_levels[2].percent = 100.0;
      m_scale_levels[2].move_sl_to_entry = false;
      m_scale_levels[2].executed = false;

      m_scale_count = 3;
   }

   //+----------------------------------------------------------------+
   //| بررسی و اجرای Scale Out در هر تیک                            |
   //| این تابع باید در OnTick فراخوانی شود                         |
   //+----------------------------------------------------------------+
   void CheckAndExecuteScaleOut(const ulong ticket) {
      if(m_scale_count == 0) return;

      if(!m_position.SelectByTicket(ticket)) return;

      ENUM_POSITION_TYPE pos_type = m_position.PositionType();
      double current_price = (pos_type == POSITION_TYPE_BUY) ?
         SymbolInfoDouble(m_symbol, SYMBOL_BID) :
         SymbolInfoDouble(m_symbol, SYMBOL_ASK);

      for(int i = 0; i < m_scale_count; i++) {
         if(m_scale_levels[i].executed) continue;

         bool level_hit = false;
         if(pos_type == POSITION_TYPE_BUY && current_price >= m_scale_levels[i].price)
            level_hit = true;
         else if(pos_type == POSITION_TYPE_SELL && current_price <= m_scale_levels[i].price)
            level_hit = true;

         if(level_hit) {
            PartialCloseResult pcr = PartialClose(
               ticket,
               m_scale_levels[i].percent,
               m_scale_levels[i].move_sl_to_entry
            );

            if(pcr.executed) {
               m_scale_levels[i].executed = true;
               Print("✅ Scale Out سطح ", i+1, " اجرا شد | ", pcr.message);
            }
         }
      }
   }

   //+----------------------------------------------------------------+
   //| محاسبه نسبت ریسک به ریوارد واقعی                             |
   //+----------------------------------------------------------------+
   double CalculateRealRiskReward(
      const ENUM_POSITION_TYPE direction,
      const double entry,
      const double sl,
      const double tp
   ) {
      if(entry <= 0 || sl <= 0 || tp <= 0) return 0;

      double risk   = MathAbs(entry - sl);
      double reward = MathAbs(tp - entry);

      if(risk <= 0) return 0;
      return NormalizeDouble(reward / risk, 2);
   }

   //+----------------------------------------------------------------+
   //| بررسی ریسک کل سبد پوزیشن‌ها                                  |
   //+----------------------------------------------------------------+
   double GetPortfolioRiskPercent() {
      double total_risk = 0;
      double account_equity = AccountInfoDouble(ACCOUNT_EQUITY);

      if(account_equity <= 0) return 0;

      for(int i = PositionsTotal() - 1; i >= 0; i--) {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;
         if(!m_position.SelectByTicket(ticket)) continue;
         if(m_position.Symbol() != m_symbol) continue;

         double entry_p = m_position.PriceOpen();
         double sl_p    = m_position.StopLoss();
         double vol     = m_position.Volume();

         if(sl_p <= 0) continue;

         double sl_dist  = MathAbs(entry_p - sl_p);
         double tick_val = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
         double tick_sz  = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
         double point    = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

         double risk_money = (sl_dist / point) * tick_val * vol;
         total_risk += risk_money;
      }

      return NormalizeDouble((total_risk / account_equity) * 100.0, 2);
   }

   //+----------------------------------------------------------------+
   //| گزارش وضعیت ریسک جاری                                        |
   //+----------------------------------------------------------------+
   string GetRiskStatusReport() {
      double equity      = AccountInfoDouble(ACCOUNT_EQUITY);
      double balance     = AccountInfoDouble(ACCOUNT_BALANCE);
      double drawdown    = (balance > 0) ? ((balance - equity) / balance * 100.0) : 0;
      double port_risk   = GetPortfolioRiskPercent();
      int    pos_count   = PositionsTotal();

      string report = StringFormat(
         "📊 وضعیت ریسک:\n"
         "  موجودی: %.2f\n"
         "  اکوئیتی: %.2f\n"
         "  افت سرمایه: %.2f%%\n"
         "  ریسک سبد: %.2f%%\n"
         "  پوزیشن‌های باز: %d",
         balance, equity, drawdown, port_risk, pos_count
      );

      return report;
   }
};

#endif // RISK_MANAGER_COMPLETE_MQH
