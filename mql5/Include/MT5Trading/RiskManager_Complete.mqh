//+------------------------------------------------------------------+
//|                                    RiskManager_Complete.mqh      |
//|          مدیریت ریسک تکمیلی - ScaleOut و Take Profit چندگانه    |
//|          توضیح: این کلاس متدهای خروج تدریجی و TP چندگانه را    |
//|          فراهم می‌کند و توسط MT5TradingEA_Complete استفاده می‌شود|
//+------------------------------------------------------------------+
#pragma once
#ifndef RISK_MANAGER_COMPLETE_MQH
#define RISK_MANAGER_COMPLETE_MQH

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

// ساختار نتیجه Take Profit چندگانه
struct TakeProfitResult {
   double   tp1;              // هدف اول (1:1)
   double   tp2;              // هدف دوم (1:2)
   double   tp3;              // هدف سوم (1:3)
   double   tp_structure;     // هدف بر اساس ساختار بازار
   bool     valid;            // اعتبار محاسبه
};

//+------------------------------------------------------------------+
//| کلاس مدیریت ریسک تکمیلی - ScaleOut و TP چندگانه                 |
//| توضیح: این کلاس متدهای اضافی برای خروج تدریجی و                 |
//|         محاسبه Take Profit چندگانه را فراهم می‌کند.             |
//+------------------------------------------------------------------+
class CRiskManagerComplete {
private:
   string         m_symbol;
   CTrade         m_trade;
   CPositionInfo  m_position;
   double         m_scale_out_tp1;
   double         m_scale_out_tp2;
   double         m_scale_out_tp3;
   double         m_scale_out_percent;
   bool           m_scale_out_active;
   ENUM_POSITION_TYPE m_scale_direction;

   // محاسبه حجم خروج جزئی
   double CalculateScaleVolume(const double close_percent) {
      if(!m_position.Select(m_symbol)) return 0;
      double current_volume = m_position.Volume();
      double close_volume = NormalizeDouble(current_volume * (close_percent / 100.0), 2);
      double min_lot  = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
      double step_lot = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      close_volume = MathMax(min_lot, NormalizeDouble(MathFloor(close_volume / step_lot) * step_lot, 2));
      if(close_volume >= current_volume) return 0;
      return close_volume;
   }

public:
   // سازنده
   CRiskManagerComplete(const string symbol) {
      m_symbol            = symbol;
      m_scale_out_tp1     = 0;
      m_scale_out_tp2     = 0;
      m_scale_out_tp3     = 0;
      m_scale_out_percent = 30.0;
      m_scale_out_active  = false;
   }

   // تنظیم سطوح ScaleOut
   void SetScaleOutLevels(
      const ENUM_POSITION_TYPE direction,
      const double entry_price,
      const double stop_loss,
      const double take_profit
   ) {
      double sl_dist = MathAbs(entry_price - stop_loss);
      if(sl_dist <= 0) return;
      m_scale_direction = direction;
      int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
      if(direction == POSITION_TYPE_BUY) {
         m_scale_out_tp1 = NormalizeDouble(entry_price + sl_dist * 1.0, digits);
         m_scale_out_tp2 = NormalizeDouble(entry_price + sl_dist * 2.0, digits);
         m_scale_out_tp3 = NormalizeDouble(entry_price + sl_dist * 3.0, digits);
      } else {
         m_scale_out_tp1 = NormalizeDouble(entry_price - sl_dist * 1.0, digits);
         m_scale_out_tp2 = NormalizeDouble(entry_price - sl_dist * 2.0, digits);
         m_scale_out_tp3 = NormalizeDouble(entry_price - sl_dist * 3.0, digits);
      }
      m_scale_out_active = true;
   }

   // محاسبه Take Profit چندگانه بر اساس SL Distance و ساختار بازار
   TakeProfitResult CalculateTakeProfits(
      const ENUM_POSITION_TYPE direction,
      const double entry_price,
      const double stop_loss,
      const double structure_target = 0
   ) {
      TakeProfitResult result;
      result.valid = false;
      double sl_dist = MathAbs(entry_price - stop_loss);
      if(sl_dist <= 0) return result;
      int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
      if(direction == POSITION_TYPE_BUY) {
         result.tp1 = NormalizeDouble(entry_price + sl_dist * 1.0, digits);
         result.tp2 = NormalizeDouble(entry_price + sl_dist * 2.0, digits);
         result.tp3 = NormalizeDouble(entry_price + sl_dist * 3.0, digits);
         result.tp_structure = (structure_target > entry_price) ? structure_target : result.tp2;
      } else {
         result.tp1 = NormalizeDouble(entry_price - sl_dist * 1.0, digits);
         result.tp2 = NormalizeDouble(entry_price - sl_dist * 2.0, digits);
         result.tp3 = NormalizeDouble(entry_price - sl_dist * 3.0, digits);
         result.tp_structure = (structure_target > 0 && structure_target < entry_price) ? structure_target : result.tp2;
      }
      result.valid = true;
      return result;
   }

   // بررسی و اجرای خروج تدریجی در سطوح TP1 و TP2
   bool CheckAndExecuteScaleOut(const ulong ticket) {
      if(!m_scale_out_active || ticket == 0) return false;
      if(!m_position.SelectByTicket(ticket)) return false;
      double current_price = (m_scale_direction == POSITION_TYPE_BUY) ?
                              SymbolInfoDouble(m_symbol, SYMBOL_BID) :
                              SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      double buffer = SymbolInfoDouble(m_symbol, SYMBOL_POINT) * 5;
      // خروج در TP1 - بستن ۳۰٪ حجم
      if(m_scale_out_tp1 > 0) {
         bool tp1_hit = (m_scale_direction == POSITION_TYPE_BUY) ?
                        (current_price >= m_scale_out_tp1 - buffer) :
                        (current_price <= m_scale_out_tp1 + buffer);
         if(tp1_hit) {
            double vol = CalculateScaleVolume(30.0);
            if(vol > 0) {
               m_trade.PositionClosePartial(ticket, vol);
               m_scale_out_tp1 = 0;
               return true;
            }
         }
      }
      // خروج در TP2 - بستن ۳۰٪ دیگر
      if(m_scale_out_tp2 > 0) {
         bool tp2_hit = (m_scale_direction == POSITION_TYPE_BUY) ?
                        (current_price >= m_scale_out_tp2 - buffer) :
                        (current_price <= m_scale_out_tp2 + buffer);
         if(tp2_hit) {
            double vol = CalculateScaleVolume(30.0);
            if(vol > 0) {
               m_trade.PositionClosePartial(ticket, vol);
               m_scale_out_tp2 = 0;
               return true;
            }
         }
      }
      return false;
   }

   // محاسبه ریسک/پاداش واقعی معامله
   double CalculateRealRiskReward(
      const double entry,
      const double sl,
      const double tp
   ) {
      double risk   = MathAbs(entry - sl);
      double reward = MathAbs(tp - entry);
      if(risk <= 0) return 0;
      return NormalizeDouble(reward / risk, 2);
   }

   // محاسبه درصد ریسک کل پورتفولیو
   double GetPortfolioRiskPercent() {
      double account_equity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(account_equity <= 0) return 0;
      double total_risk = 0;
      int pos_count = PositionsTotal();
      CPositionInfo pos;
      for(int i = 0; i < pos_count; i++) {
         if(pos.SelectByIndex(i)) {
            double entry_p = pos.PriceOpen();
            double sl_p    = pos.StopLoss();
            double vol     = pos.Volume();
            if(sl_p <= 0) continue;
            double sl_dist  = MathAbs(entry_p - sl_p);
            double tick_val = SymbolInfoDouble(pos.Symbol(), SYMBOL_TRADE_TICK_VALUE);
            double tick_sz  = SymbolInfoDouble(pos.Symbol(), SYMBOL_TRADE_TICK_SIZE);
            double point    = SymbolInfoDouble(pos.Symbol(), SYMBOL_POINT);
            if(tick_sz <= 0 || point <= 0) continue;
            double risk_money = (sl_dist / point) * tick_val * vol;
            total_risk += risk_money;
         }
      }
      return NormalizeDouble((total_risk / account_equity) * 100.0, 2);
   }

   // بررسی تجاوز از حد Drawdown کل پورتفولیو
   bool IsPortfolioDrawdownExceeded(const double max_percent) {
      double equity   = AccountInfoDouble(ACCOUNT_EQUITY);
      double balance  = AccountInfoDouble(ACCOUNT_BALANCE);
      double drawdown = (balance > 0) ? ((balance - equity) / balance * 100.0) : 0;
      double port_risk = GetPortfolioRiskPercent();
      return (drawdown >= max_percent || port_risk >= max_percent * 1.5);
   }

   // آیا ScaleOut فعال است
   bool IsScaleOutActive() const { return m_scale_out_active; }

   // بازنشانی ScaleOut بعد از بسته شدن پوزیشن
   void ResetScaleOut() {
      m_scale_out_tp1    = 0;
      m_scale_out_tp2    = 0;
      m_scale_out_tp3    = 0;
      m_scale_out_active = false;
   }
};

#endif // RISK_MANAGER_COMPLETE_MQH
