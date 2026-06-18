//+------------------------------------------------------------------+
//|                                  MT5TradingEA_Complete.mq5       |
//|               سیستم معاملاتی حرفه‌ای Bot12 - نسخه کامل          |
//|               تمام ماژول‌ها یکپارچه و Production Ready           |
//+------------------------------------------------------------------+
// ویژگی‌های این فایل:
//  ① همه Print() به LogMessage() با سطح‌بندی INFO/TRADE/ERROR/WARN تبدیل شده‌اند
//  ② DrawSMCZones() در OnTick فراخوانی می‌شود (هر 10 تیک)
//  ③ OnTimer() برای polling سیگنال از Python
//  ④ OnTradeTransaction() برای detect بسته شدن پوزیشن
//  ⑤ RiskManagerComplete برای ScaleOut و TP چندگانه
//+------------------------------------------------------------------+
#property copyright "Bot12 Trading System v3.0"
#property link      "https://github.com/sani13790000/bot12"
#property version   "3.00"
#property strict

// --- Include تمام ماژول‌های اصلی ---
#include <MT5Trading\Config.mqh>
#include <MT5Trading\LicenseChecker.mqh>
#include <MT5Trading\RiskManager.mqh>
#include <MT5Trading\TradeManager.mqh>
#include <MT5Trading\PositionManager.mqh>
#include <MT5Trading\DrawManager.mqh>
#include <MT5Trading\NotificationManager.mqh>
#include <MT5Trading\DecisionConnector.mqh>
#include <MT5Trading\StrategyLoader.mqh>
#include <MT5Trading\ExecutionEngine.mqh>
#include <MT5Trading\RiskManager_Complete.mqh>
#include <MT5Trading\SessionManager.mqh>
#include <MT5Trading\Helpers.mqh>

//+------------------------------------------------------------------+
//| پارامترهای ورودی کاربر                                           |
//+------------------------------------------------------------------+
// --- تنظیمات اصلی ---
input string   ActiveSymbol      = "EURUSD";          // نماد فعال
input bool     EnableTrading     = true;              // فعال‌سازی معاملات
input bool     DebugMode         = false;             // حالت Debug (لاگ کامل)
input bool     LogToFile         = true;              // ذخیره لاگ در فایل

// --- تنظیمات ریسک ---
input double   RiskPercent       = 1.0;               // درصد ریسک هر معامله
input double   MaxDailyLoss      = 3.0;               // حداکثر ضرر روزانه (%)
input double   MaxDrawdown       = 10.0;              // حداکثر افت سرمایه (%)
input int      MaxPositions      = 3;                 // حداکثر پوزیشن باز
input double   MinRR             = 1.5;               // حداقل Risk/Reward

// --- تنظیمات SL/TP ---
input bool     UseATRForSLTP     = true;              // استفاده از ATR برای SL/TP
input double   ATRMultiplierSL   = 1.5;               // ضریب ATR برای SL
input double   ATRMultiplierTP   = 2.5;               // ضریب ATR برای TP
input int      BreakEvenPoints   = 50;                // نقطه سربه‌سر (پوینت)
input int      TrailingPoints    = 30;                // Trailing Stop (پوینت)

// --- تنظیمات سشن ---
input bool     UseSydney         = false;             // سشن سیدنی
input bool     UseTokyo          = true;              // سشن توکیو
input bool     UseLondon         = true;              // سشن لندن
input bool     UseNewYork        = true;              // سشن نیویورک
input bool     OnlyKillZones     = true;              // فقط در Kill Zone معامله

// --- تنظیمات رسم ---
input bool     DrawOB            = true;              // رسم Order Block
input bool     DrawFVG           = true;              // رسم FVG
input bool     DrawLiquidity     = true;              // رسم Liquidity
input bool     DrawStructure     = true;              // رسم ساختار بازار
input bool     DrawKillZones     = true;              // رسم Kill Zones

// --- تنظیمات اعلان ---
input bool     NotifyOnEntry     = true;              // هشدار ورود
input bool     NotifyOnExit      = true;              // هشدار خروج
input bool     NotifyOnSession   = true;              // هشدار سشن

// --- تنظیمات لایسنس ---
input string   LicenseKey        = "";               // کلید لایسنس

//+------------------------------------------------------------------+
//| متغیرهای سراسری                                                  |
//+------------------------------------------------------------------+
CRiskManager*           g_risk_manager    = NULL;
CTradeManager*          g_trade_manager   = NULL;
CPositionManager*       g_position_manager = NULL;
CDrawManager*           g_draw_manager    = NULL;
CNotificationManager*   g_notification    = NULL;
CDecisionConnector*     g_decision        = NULL;
CStrategyLoader*        g_strategy        = NULL;
CExecutionEngine*       g_execution       = NULL;
CRiskManagerComplete*   g_risk_complete   = NULL;
CSessionManager*        g_session         = NULL;

// --- وضعیت سیستم ---
bool     g_initialized       = false;
bool     g_license_valid     = false;
bool     g_emergency_stop    = false;
string   g_active_symbol     = "";
datetime g_session_open_time = 0;

//+------------------------------------------------------------------+
//| رویداد شروع EA                                                   |
//+------------------------------------------------------------------+
int OnInit() {
   // تنظیم نماد فعال
   g_active_symbol = (ActiveSymbol == "") ? Symbol() : ActiveSymbol;

   // بررسی WebRequest
   if(!TerminalInfoInteger(TERMINAL_WEBREQUEST)) {
      LogMessage("⚠️ WebRequest غیرفعال → Tools > Options > Expert Advisors > Allow WebRequest را فعال کنید", "WARN");
   }

   // نمایش بنر شروع
   LogMessage("══════════════════════════════════════════", "INFO");
   LogMessage("  Bot12 Trading System v3.0 - شروع موداردهی", "INFO");
   LogMessage("══════════════════════════════════════════", "INFO");

   // بررسی لایسنس
   CLicenseChecker license_checker;
   if(!license_checker.ValidateLicense(LicenseKey, g_active_symbol)) {
      LogMessage("❌ خطا: مجوز نامعتبر", "ERROR");
      return INIT_FAILED;
   }
   g_license_valid = true;
   LogMessage("✅ مجوز معتبر", "INFO");

   // راه‌اندازی ماژول‌ها
   g_risk_manager = new CRiskManager(g_active_symbol);
   g_risk_manager.SetMaxDailyLossPercent(MaxDailyLoss);
   g_risk_manager.SetMaxDrawdownPercent(MaxDrawdown);
   g_risk_manager.SetATRMultipliers(ATRMultiplierSL, ATRMultiplierTP);
   g_risk_manager.InitializeATR(14, PERIOD_CURRENT);
   LogMessage("✅ RiskManager راه‌اندازی شد", "INFO");

   g_trade_manager = new CTradeManager(g_active_symbol);
   LogMessage("✅ TradeManager راه‌اندازی شد", "INFO");

   g_position_manager = new CPositionManager(g_active_symbol);
   LogMessage("✅ PositionManager راه‌اندازی شد", "INFO");

   g_draw_manager = new CDrawManager(g_active_symbol);
   LogMessage("✅ DrawManager راه‌اندازی شد", "INFO");

   g_decision = new CDecisionConnector(g_active_symbol);
   LogMessage("✅ DecisionConnector راه‌اندازی شد", "INFO");

   g_strategy = new CStrategyLoader(g_active_symbol);
   LogMessage("✅ StrategyLoader راه‌اندازی شد", "INFO");

   g_execution = new CExecutionEngine(g_active_symbol);
   LogMessage("✅ ExecutionEngine راه‌اندازی شد", "INFO");

   g_risk_complete = new CRiskManagerComplete(g_active_symbol);
   LogMessage("✅ RiskManagerComplete راه‌اندازی شد", "INFO");

   g_session = new CSessionManager();
   g_session.SetActiveSessions(UseSydney, UseTokyo, UseLondon, UseNewYork, false, OnlyKillZones);
   LogMessage("✅ SessionManager راه‌اندازی شد", "INFO");

   // راه‌اندازی NotificationManager
   g_notification = new CNotificationManager();
   if(g_notification.Initialize()) {
      LogMessage("✅ تلگرام متصل شد", "INFO");
   }

   // تنظیم Timer برای polling سیگنال از Python (هر 5 ثانیه)
   EventSetTimer(5);

   g_initialized = true;
   LogMessage("✅ موداردهی کامل شد", "INFO");
   LogMessage("══════════════════════════════════════════", "INFO");

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| رویداد هر تیک                                                    |
//+------------------------------------------------------------------+
void OnTick() {
   if(!g_initialized || !g_license_valid) return;

   // --- بررسی Emergency Stop ---
   if(g_emergency_stop) {
      static datetime last_es_warn = 0;
      if(TimeCurrent() - last_es_warn > 60) {
         LogMessage("⚠️ Emergency Stop فعال - معامله‌ای انجام نمی‌شود", "WARN");
         last_es_warn = TimeCurrent();
      }
      return;
   }

   // --- بررسی محدودیت‌های ریسک ---
   if(g_risk_manager.IsDailyLossLimitReached()) {
      static datetime last_dl_warn = 0;
      if(TimeCurrent() - last_dl_warn > 300) {
         string warn = StringFormat("⚠️ محدودیت ضرر روزانه رسیده! معامله‌ای انجام نمی‌شود.");
         g_notification.NotifyRiskWarning(warn, g_risk_manager.GetDailyPnL());
         last_dl_warn = TimeCurrent();
      }
      return;
   }

   if(g_risk_manager.IsMaxDrawdownReached()) {
      if(!g_emergency_stop) {
         g_emergency_stop = true;
         g_notification.NotifyEmergencyStop("حداکثر Drawdown رسیده");
         g_execution.CloseAllPositions("Emergency - Max Drawdown");
      }
      return;
   }

   // --- پایش سشن ---
   MonitorSessions();

   // --- رسم نواحی SMC روی چارت ---
   if(DrawOB || DrawFVG || DrawLiquidity || DrawStructure)
      DrawSMCZones();

   // --- به‌روزرسانی پوزیشن‌های باز ---
   UpdateOpenPositions();

   // --- بررسی گزارش روزانه ---
   CheckDailyReport();
}

//+------------------------------------------------------------------+
//| رویداد Timer - polling سیگنال از Python Backend هر 5 ثانیه      |
//+------------------------------------------------------------------+
void OnTimer() {
   if(!g_initialized || !g_license_valid || g_emergency_stop) return;

   // --- بررسی سیگنال جدید از Python ---
   if(!g_session.CanTradeNow()) return;

   // بررسی وجود پوزیشن‌های باز بیش از حد
   if(g_position_manager.GetOpenPositionCount() >= MaxPositions) return;

   // خواندن سیگنال
   if(g_decision.HasNewSignal()) {
      ProcessNewSignal();
   }
}

//+------------------------------------------------------------------+
//| پردازش سیگنال جدید از Python Backend                            |
//+------------------------------------------------------------------+
void ProcessNewSignal() {
   // دریافت تصمیم از Decision Connector
   string signal_type = g_decision.GetSignalType();

   if(signal_type == "NO_TRADE") return;

   double entry      = g_decision.GetEntryPrice();
   double sl         = g_decision.GetStopLoss();
   double tp         = g_decision.GetTakeProfit();
   double score      = g_decision.GetScore();

   // اعتبارسنجی قیمت‌ها
   if(entry <= 0 || sl <= 0) {
      LogMessage("⚠️ سیگنال نامعتبر - قیمت ورود یا SL صفر است", "WARN");
      return;
   }

   // محاسبه Lot Size
   ENUM_POSITION_TYPE direction = (signal_type == "BUY") ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
   double sl_points = MathAbs(entry - sl) / SymbolInfoDouble(g_active_symbol, SYMBOL_POINT);
   LotCalculationResult lot_result = g_risk_manager.CalculateLot(RiskPercent, sl_points, direction);

   if(!lot_result.valid) {
      LogMessage("⚠️ محاسبه Lot ناموفق", "WARN");
      return;
   }

   // بررسی حداقل RR
   double rr = MathAbs(tp - entry) / MathAbs(entry - sl);
   if(rr < MinRR) {
      LogMessage(StringFormat("⚠️ RR کافی نیست: %.2f < %.2f", rr, MinRR), "WARN");
      return;
   }

   // اجرای معامله
   TradeRequest req;
   req.symbol    = g_active_symbol;
   req.direction = direction;
   req.lot       = lot_result.lot;
   req.sl        = sl;
   req.tp        = tp;
   req.comment   = StringFormat("Bot12|Score:%.0f", score);

   ExecutionResult exec = g_execution.ExecuteTrade(req);

   if(exec.success) {
      // محاسبه TP چندگانه برای ScaleOut
      TakeProfitResult tp_result = g_risk_complete.CalculateTakeProfits(
         direction, exec.executed_price, sl, tp
      );

      // تنظیم سطوح ScaleOut
      if(tp_result.valid) {
         double final_tp = tp_result.tp_structure;
         g_risk_complete.SetScaleOutLevels(direction, exec.executed_price, sl, final_tp);
      }

      // اعلان ورود
      if(NotifyOnEntry) {
         g_notification.NotifyTradeOpen(
            exec.ticket, direction, g_active_symbol,
            exec.executed_price, sl, tp, lot_result.lot, score
         );
      }
      LogMessage(StringFormat("✅ معامله باز شد | Ticket:%d | %s | Score:%.0f",
                 exec.ticket, signal_type, score), "TRADE");
   } else {
      LogMessage(StringFormat("❌ باز کردن معامله ناموفق: %s", exec.error_description), "ERROR");
   }
}

//+------------------------------------------------------------------+
//| به‌روزرسانی پوزیشن‌های باز - BreakEven و Trailing و ScaleOut    |
//+------------------------------------------------------------------+
void UpdateOpenPositions() {
   int total = g_position_manager.GetOpenPositionCount();
   if(total == 0) return;

   for(int i = 0; i < total; i++) {
      ulong ticket = g_position_manager.GetTicketByIndex(i);
      if(ticket == 0) continue;

      // BreakEven
      if(BreakEvenPoints > 0)
         g_risk_manager.UpdateBreakEven(ticket, BreakEvenPoints, 2.0);

      // Trailing Stop
      if(TrailingPoints > 0)
         g_risk_manager.UpdateTrailingStop(ticket, TrailingPoints, 5.0);

      // ScaleOut در سطوح TP
      if(g_risk_complete.IsScaleOutActive())
         g_risk_complete.CheckAndExecuteScaleOut(ticket);
   }
}

//+------------------------------------------------------------------+
//| پایش سشن‌های معاملاتی و ارسال هشدار                             |
//+------------------------------------------------------------------+
void MonitorSessions() {
   SessionInfo current = g_session.GetCurrentSession();

   // بررسی تغییر وضعیت سشن
   static bool prev_session_active = false;
   if(current.can_trade != prev_session_active) {
      prev_session_active = current.can_trade;

      if(current.can_trade) {
         g_session_open_time = TimeCurrent();
         if(NotifyOnSession)
            g_notification.NotifySessionOpen(current.session_name, TimeCurrent());
         LogMessage(StringFormat("🕐 سشن %s باز شد", current.session_name), "INFO");
      } else {
         if(g_session_open_time > 0) {
            datetime duration_sec = TimeCurrent() - g_session_open_time;
            int trades_in_session = g_position_manager.GetSessionTradeCount(g_session_open_time);
            if(NotifyOnSession)
               g_notification.NotifySessionClose(
                  current.session_name, TimeCurrent(),
                  (int)duration_sec, trades_in_session
               );
            LogMessage(StringFormat("🕐 سشن %s بسته شد | معاملات:%d",
                       current.session_name, trades_in_session), "INFO");
         }
      }
   }

   // رسم Kill Zone اگر فعال باشد
   if(DrawKillZones && g_draw_manager != NULL) {
      g_draw_manager.DrawSessionRange(current.session_name, TimeCurrent());
   }
}

//+------------------------------------------------------------------+
//| رسم نواحی SMC روی چارت - هر 10 تیک یکبار                       |
//| توضیح: این تابع نواحی DrawManager را به‌روزرسانی می‌کند.         |
//+------------------------------------------------------------------+
void DrawSMCZones() {
   if(g_draw_manager == NULL) return;

   // کنترل فرکانس رسم - هر 10 تیک یکبار
   static int draw_counter = 0;
   draw_counter++;
   if(draw_counter < 10) return;
   draw_counter = 0;

   // به‌روزرسانی نواحی موجود
   g_draw_manager.UpdateZones();

   // رسم نقاط swing از ساختار بازار
   if(DrawStructure) {
      int high_idx = iHighest(g_active_symbol, PERIOD_CURRENT, MODE_HIGH, 20, 1);
      int low_idx  = iLowest(g_active_symbol,  PERIOD_CURRENT, MODE_LOW,  20, 1);
      if(high_idx >= 0)
         g_draw_manager.DrawSwingPoint(iHigh(g_active_symbol, PERIOD_CURRENT, high_idx), high_idx, "High");
      if(low_idx >= 0)
         g_draw_manager.DrawSwingPoint(iLow(g_active_symbol, PERIOD_CURRENT, low_idx), low_idx, "Low");
   }
}

//+------------------------------------------------------------------+
//| بررسی گزارش روزانه و ارسال به تلگرام                            |
//+------------------------------------------------------------------+
void CheckDailyReport() {
   static datetime last_report = 0;
   datetime now = TimeCurrent();

   // یکبار در روز در ساعت 23:55
   MqlDateTime dt;
   TimeToStruct(now, dt);
   if(dt.hour == 23 && dt.min >= 55) {
      if(now - last_report > 3600) {
         last_report = now;
         double daily_pnl     = g_risk_manager.GetDailyPnL();
         double daily_pnl_pct = g_risk_manager.GetDailyPnLPercent();
         int    today_trades  = g_risk_manager.GetTodayTradesCount();
         double drawdown      = g_risk_manager.GetCurrentDrawdown();

         g_notification.NotifyDailyReport(
            today_trades,
            daily_pnl,
            daily_pnl_pct,
            drawdown
         );
         LogMessage(StringFormat("📊 گزارش روزانه | معاملات:%d | PnL:%.2f (%.1f%%) | DD:%.1f%%",
                    today_trades, daily_pnl, daily_pnl_pct, drawdown), "INFO");
      }
   }
}

//+------------------------------------------------------------------+
//| رویداد معامله - تشخیص بسته شدن پوزیشن از طرف broker           |
//+------------------------------------------------------------------+
void OnTradeTransaction(
   const MqlTradeTransaction& trans,
   const MqlTradeRequest& request,
   const MqlTradeResult& result
) {
   if(!g_initialized) return;

   // بررسی بسته شدن پوزیشن
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD) {
      if(trans.deal_type == DEAL_TYPE_BUY || trans.deal_type == DEAL_TYPE_SELL) {
         // پوزیشن بسته شد - ارسال هشدار
         if(NotifyOnExit && trans.symbol == g_active_symbol) {
            string close_reason = "بسته شده";
            if(trans.deal_entry == DEAL_ENTRY_OUT) {
               double profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
               close_reason = (profit < 0) ? "حد ضرر" : "حد سود";
            }

            g_notification.NotifyTradeClose(
               trans.deal,
               (trans.deal_type == DEAL_TYPE_BUY ? POSITION_TYPE_BUY : POSITION_TYPE_SELL),
               trans.symbol,
               trans.price, 0,
               HistoryDealGetDouble(trans.deal, DEAL_PROFIT),
               close_reason
            );
         }

         // بازنشانی ScaleOut برای این پوزیشن
         if(g_risk_complete != NULL)
            g_risk_complete.ResetScaleOut();

         LogMessage(StringFormat("📌 معامله بسته شد | Deal:%d | %s | Profit:%.2f",
                    trans.deal, close_reason,
                    HistoryDealGetDouble(trans.deal, DEAL_PROFIT)), "TRADE");
      }
   }
}

//+------------------------------------------------------------------+
//| رویداد پایان EA                                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   // توقف Timer
   EventKillTimer();

   // پاک‌سازی DrawManager
   if(g_draw_manager) g_draw_manager.ClearAll();

   // آزاد کردن همه اشاره‌گرها
   if(g_risk_manager)    { delete g_risk_manager;     g_risk_manager = NULL; }
   if(g_trade_manager)   { delete g_trade_manager;    g_trade_manager = NULL; }
   if(g_position_manager){ delete g_position_manager; g_position_manager = NULL; }
   if(g_draw_manager)    { delete g_draw_manager;     g_draw_manager = NULL; }
   if(g_notification)    { delete g_notification;     g_notification = NULL; }
   if(g_decision)        { delete g_decision;         g_decision = NULL; }
   if(g_strategy)        { delete g_strategy;         g_strategy = NULL; }
   if(g_execution)       { delete g_execution;        g_execution = NULL; }
   if(g_risk_complete)   { delete g_risk_complete;    g_risk_complete = NULL; }
   if(g_session)         { delete g_session;          g_session = NULL; }

   LogMessage("🔴 تمام منابع آزاد شدند | Bot12 متوقف شد", "INFO");
}
