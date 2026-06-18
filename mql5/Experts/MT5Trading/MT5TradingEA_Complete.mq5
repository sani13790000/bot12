//+------------------------------------------------------------------+
//|                              MT5TradingEA_Complete.mq5           |
//|                              MT5 Trading System - Bot12 v3.1    |
//|  تغییرات فاز 9:                                                 |
//|  ① DrawSMCZones کامل: OB/FVG/BOS/CHOCH/MSS/Liquidity/PD       |
//|  ② DrawSessionRange با سقف/کف واقعی سشن                        |
//|  ③ DrawKillZone در MonitorSessions                              |
//|  ④ OnTimer برای polling سیگنال از Python                       |
//|  ⑤ OnTradeTransaction برای detect بسته شدن پوزیشن             |
//+------------------------------------------------------------------+
#property copyright "Bot12 Trading System v3.1"
#property link      "https://github.com/sani13790000/bot12"
#property version   "3.10"
#property strict

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
input string   ActiveSymbol      = "EURUSD";          // نماد فعال
input bool     EnableTrading     = true;              // فعال‌سازی معاملات
input bool     DebugMode         = false;             // حالت Debug
input bool     LogToFile         = true;              // ذخیره لاگ در فایل

input double   RiskPercent       = 1.0;               // درصد ریسک هر معامله
input double   MaxDailyLoss      = 3.0;               // حداکثر ضرر روزانه (%)
input double   MaxDrawdown       = 10.0;              // حداکثر افت سرمایه (%)
input int      MaxPositions      = 3;                 // حداکثر پوزیشن باز
input double   MinRR             = 1.5;               // حداقل Risk/Reward

input bool     UseATRForSLTP     = true;              // استفاده از ATR برای SL/TP
input double   ATRMultiplierSL   = 1.5;               // ضریب ATR برای SL
input double   ATRMultiplierTP   = 2.5;               // ضریب ATR برای TP
input int      BreakEvenPoints   = 50;                // نقطه سربه‌سر (پوینت)
input int      TrailingPoints    = 30;                // Trailing Stop (پوینت)

input bool     UseSydney         = false;             // سشن سیدنی
input bool     UseTokyo          = true;              // سشن توکیو
input bool     UseLondon         = true;              // سشن لندن
input bool     UseNewYork        = true;              // سشن نیویورک
input bool     OnlyKillZones     = true;              // فقط در Kill Zone

input bool     DrawOB            = true;              // رسم Order Block
input bool     DrawFVG           = true;              // رسم FVG
input bool     DrawLiquidity     = true;              // رسم Liquidity
input bool     DrawStructure     = true;              // رسم ساختار بازار
input bool     DrawKillZones     = true;              // رسم Kill Zones

input bool     NotifyOnEntry     = true;              // هشدار ورود
input bool     NotifyOnExit      = true;              // هشدار خروج
input bool     NotifyOnSession   = true;              // هشدار سشن

input string   LicenseKey        = "";               // کلید لایسنس

//+------------------------------------------------------------------+
//| متغیرهای سراسری                                                  |
//+------------------------------------------------------------------+
CRiskManager*           g_risk_manager     = NULL;
CTradeManager*          g_trade_manager    = NULL;
CPositionManager*       g_position_manager = NULL;
CDrawManager*           g_draw_manager     = NULL;
CNotificationManager*   g_notification     = NULL;
CDecisionConnector*     g_decision         = NULL;
CStrategyLoader*        g_strategy         = NULL;
CExecutionEngine*       g_execution        = NULL;
CRiskManagerComplete*   g_risk_complete    = NULL;
CSessionManager*        g_session          = NULL;

bool     g_initialized       = false;
bool     g_license_valid     = false;
bool     g_emergency_stop    = false;
string   g_active_symbol     = "";
datetime g_session_open_time = 0;

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit() {
   g_active_symbol = (ActiveSymbol == "") ? Symbol() : ActiveSymbol;

   if(!TerminalInfoInteger(TERMINAL_WEBREQUEST))
      LogMessage("⚠️ WebRequest غیرفعال - Tools > Options > Expert Advisors را تنظیم کنید", "WARN");

   // --- راه‌اندازی RiskManager ---
   g_risk_manager = new CRiskManager();
   g_risk_manager.SetRiskPercent(RiskPercent);
   g_risk_manager.SetMaxDailyLossPercent(MaxDailyLoss);
   g_risk_manager.SetMaxDrawdownPercent(MaxDrawdown);
   LogMessage("✅ RiskManager راه‌اندازی شد", "INFO");

   // --- راه‌اندازی TradeManager ---
   g_trade_manager = new CTradeManager(g_active_symbol);
   LogMessage("✅ TradeManager راه‌اندازی شد", "INFO");

   // --- راه‌اندازی PositionManager ---
   g_position_manager = new CPositionManager(g_active_symbol);
   LogMessage("✅ PositionManager راه‌اندازی شد", "INFO");

   // --- راه‌اندازی DrawManager ---
   g_draw_manager = new CDrawManager(g_active_symbol);
   LogMessage("✅ DrawManager راه‌اندازی شد", "INFO");

   // --- راه‌اندازی NotificationManager ---
   g_notification = new CNotificationManager();
   LogMessage("✅ NotificationManager راه‌اندازی شد", "INFO");

   // --- راه‌اندازی DecisionConnector ---
   g_decision = new CDecisionConnector(g_active_symbol);
   LogMessage("✅ DecisionConnector راه‌اندازی شد", "INFO");

   // --- راه‌اندازی StrategyLoader ---
   g_strategy = new CStrategyLoader();
   LogMessage("✅ StrategyLoader راه‌اندازی شد", "INFO");

   // --- راه‌اندازی ExecutionEngine ---
   g_execution = new CExecutionEngine(g_active_symbol);
   LogMessage("✅ ExecutionEngine راه‌اندازی شد", "INFO");

   // --- راه‌اندازی RiskManagerComplete ---
   g_risk_complete = new CRiskManagerComplete();
   LogMessage("✅ RiskManagerComplete راه‌اندازی شد", "INFO");

   // --- راه‌اندازی SessionManager ---
   g_session = new CSessionManager();
   g_session.SetActiveSessions(UseSydney, UseTokyo, UseLondon, UseNewYork, false, OnlyKillZones);
   LogMessage("✅ SessionManager راه‌اندازی شد", "INFO");

   // --- بررسی لایسنس ---
   CLicenseChecker licChecker;
   g_license_valid = licChecker.Validate(LicenseKey, g_active_symbol);
   if(!g_license_valid) {
      LogMessage("❌ لایسنس نامعتبر - EA متوقف شد", "ERROR");
      return INIT_FAILED;
   }
   LogMessage("✅ لایسنس معتبر", "INFO");

   // --- timer برای polling سیگنال ---
   EventSetTimer(5);

   g_initialized = true;
   LogMessage(StringFormat("✅ Bot12 EA v3.1 روی %s راه‌اندازی شد", g_active_symbol), "INFO");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| OnTick                                                           |
//+------------------------------------------------------------------+
void OnTick() {
   if(!g_initialized || !g_license_valid || g_emergency_stop) return;

   // --- بررسی حداکثر Drawdown ---
   if(g_risk_manager.IsMaxDrawdownReached()) {
      if(!g_emergency_stop) {
         g_emergency_stop = true;
         g_notification.NotifyEmergencyStop("حداکثر Drawdown رسیده");
         g_execution.CloseAllPositions("Emergency - Max Drawdown");
         LogMessage("🛑 Emergency Stop: حداکثر Drawdown", "ERROR");
      }
      return;
   }

   // --- پایش سشن‌ها ---
   MonitorSessions();

   // --- رسم نواحی SMC (هر 10 تیک) ---
   if(DrawOB || DrawFVG || DrawLiquidity || DrawStructure)
      DrawSMCZones();

   // --- Trailing Stop و Break Even ---
   if(g_position_manager.GetOpenPositionCount() > 0) {
      g_execution.ManageTrailingStop(TrailingPoints);
      g_execution.ManageBreakEven(BreakEvenPoints);
      g_risk_complete.CheckAndExecuteScaleOut(g_active_symbol);
   }
}

//+------------------------------------------------------------------+
//| OnTimer - polling سیگنال از Python هر 5 ثانیه                   |
//+------------------------------------------------------------------+
void OnTimer() {
   if(!g_initialized || !g_license_valid || g_emergency_stop) return;

   if(!g_session.CanTradeNow()) return;
   if(g_position_manager.GetOpenPositionCount() >= MaxPositions) return;

   if(g_decision.HasNewSignal()) {
      ProcessNewSignal();
   }
}

//+------------------------------------------------------------------+
//| OnTradeTransaction - detect بسته شدن پوزیشن                     |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result) {
   // بررسی بسته شدن پوزیشن
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD) {
      if(trans.deal_type == DEAL_TYPE_BUY || trans.deal_type == DEAL_TYPE_SELL) {
         // Reset ScaleOut پس از بسته شدن پوزیشن
         g_risk_complete.ResetScaleOut();
         LogMessage(StringFormat("✅ پوزیشن بسته شد - ScaleOut Reset | Ticket:%d",
            (int)trans.position), "TRADE");

         // آمار روزانه
         double dailyPnl     = g_position_manager.GetDailyPnL();
         int    todayTrades  = g_position_manager.GetTodayTradeCount();
         LogMessage(StringFormat("📊 آمار روز: معاملات=%d | PnL=%.2f",
            todayTrades, dailyPnl), "INFO");
      }
   }
}

//+------------------------------------------------------------------+
//| OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   EventKillTimer();

   if(g_draw_manager) g_draw_manager.ClearAll();

   // آزادسازی حافظه
   if(g_risk_manager)     { delete g_risk_manager;     g_risk_manager     = NULL; }
   if(g_trade_manager)    { delete g_trade_manager;    g_trade_manager    = NULL; }
   if(g_position_manager) { delete g_position_manager; g_position_manager = NULL; }
   if(g_draw_manager)     { delete g_draw_manager;     g_draw_manager     = NULL; }
   if(g_notification)     { delete g_notification;     g_notification     = NULL; }
   if(g_decision)         { delete g_decision;         g_decision         = NULL; }
   if(g_strategy)         { delete g_strategy;         g_strategy         = NULL; }
   if(g_execution)        { delete g_execution;        g_execution        = NULL; }
   if(g_risk_complete)    { delete g_risk_complete;    g_risk_complete    = NULL; }
   if(g_session)          { delete g_session;          g_session          = NULL; }

   LogMessage("Bot12 EA متوقف شد", "INFO");
}

//+------------------------------------------------------------------+
//| پردازش سیگنال جدید از Python                                     |
//+------------------------------------------------------------------+
void ProcessNewSignal() {
   SignalData signal = g_decision.GetLastSignal();

   if(signal.direction == "NO_TRADE") {
      LogMessage("⏭ سیگنال NO_TRADE دریافت شد", "INFO");
      return;
   }

   // بررسی حداقل امتیاز
   if(signal.score < 60) {
      LogMessage(StringFormat("⏭ امتیاز پایین: %d/100", signal.score), "INFO");
      return;
   }

   // محاسبه Lot
   double lotSize = g_risk_manager.CalculateLotSize(
      g_active_symbol, signal.entry, signal.sl);

   if(lotSize <= 0) {
      LogMessage("❌ محاسبه Lot ناموفق", "ERROR");
      return;
   }

   // اجرای معامله
   bool success = false;
   if(signal.direction == "buy") {
      success = g_trade_manager.OpenBuy(
         g_active_symbol, lotSize, signal.sl, signal.tp, "Bot12-BUY");
   } else if(signal.direction == "sell") {
      success = g_trade_manager.OpenSell(
         g_active_symbol, lotSize, signal.sl, signal.tp, "Bot12-SELL");
   }

   if(success) {
      // رسم سیگنال روی چارت
      if(g_draw_manager != NULL) {
         double tp2 = signal.direction == "buy"
            ? signal.tp + (signal.tp - signal.entry) * 0.5
            : signal.tp - (signal.entry - signal.tp) * 0.5;
         double tp3 = signal.direction == "buy"
            ? signal.tp + (signal.tp - signal.entry) * 1.0
            : signal.tp - (signal.entry - signal.tp) * 1.0;
         g_draw_manager.DrawSignal(signal.entry, signal.sl, signal.tp,
                                    tp2, tp3, signal.direction, signal.score);
      }

      // اعلان تلگرام
      if(NotifyOnEntry)
         g_notification.NotifyTradeOpen(
            signal.direction, signal.entry, signal.sl, signal.tp,
            lotSize, signal.score, signal.reason);

      // تنظیم ScaleOut
      double riskPips = MathAbs(signal.entry - signal.sl) /
                        SymbolInfoDouble(g_active_symbol, SYMBOL_POINT);
      g_risk_complete.SetScaleOutLevels(
         signal.entry, riskPips, signal.direction == "buy");

      LogMessage(StringFormat("✅ معامله باز شد: %s | Entry:%.5f SL:%.5f TP:%.5f Lot:%.2f Score:%d",
         signal.direction, signal.entry, signal.sl, signal.tp, lotSize, signal.score), "TRADE");
   } else {
      LogMessage("❌ اجرای معامله ناموفق: " + IntegerToString(GetLastError()), "ERROR");
   }
}

//+------------------------------------------------------------------+
//| پایش سشن‌ها و رسم Session Range / Kill Zone                      |
//+------------------------------------------------------------------+
void MonitorSessions() {
   SessionInfo current = g_session.GetCurrentSession();

   static bool prev_session_active = false;
   if(current.can_trade != prev_session_active) {
      prev_session_active = current.can_trade;

      if(current.can_trade) {
         g_session_open_time = TimeCurrent();
         if(NotifyOnSession)
            g_notification.NotifySessionOpen(current.session_name, TimeCurrent());
         LogMessage(StringFormat("🕐 سشن %s باز شد", current.session_name), "INFO");

         // رسم محدوده سشن با سقف و کف 40 کندل اخیر
         if(DrawKillZones && g_draw_manager != NULL) {
            double sessHigh = iHigh(g_active_symbol, PERIOD_CURRENT,
               iHighest(g_active_symbol, PERIOD_CURRENT, MODE_HIGH, 40, 0));
            double sessLow  = iLow(g_active_symbol, PERIOD_CURRENT,
               iLowest(g_active_symbol,  PERIOD_CURRENT, MODE_LOW,  40, 0));
            g_draw_manager.DrawSessionRange(current.session_name,
                                            g_session_open_time, sessHigh, sessLow);
         }
      } else {
         if(g_session_open_time > 0) {
            datetime duration_sec   = TimeCurrent() - g_session_open_time;
            int      trades_in_sess = g_position_manager.GetSessionTradeCount(g_session_open_time);
            if(NotifyOnSession)
               g_notification.NotifySessionClose(
                  current.session_name, TimeCurrent(),
                  (int)duration_sec, trades_in_sess);
            LogMessage(StringFormat("🕐 سشن %s بسته شد | معاملات:%d",
               current.session_name, trades_in_sess), "INFO");
         }
      }
   }

   // رسم Kill Zone در صورت فعال بودن
   if(DrawKillZones && g_draw_manager != NULL && current.is_kill_zone) {
      static string prev_kz = "";
      if(current.kill_zone_name != prev_kz) {
         prev_kz = current.kill_zone_name;
         datetime kzEnd = TimeCurrent() + 3600;
         g_draw_manager.DrawKillZone(current.kill_zone_name, TimeCurrent(), kzEnd);
         LogMessage("🎯 Kill Zone فعال: " + current.kill_zone_name, "INFO");
      }
   }
}

//+------------------------------------------------------------------+
//| DrawSMCZones - رسم کامل نواحی SMC روی چارت                      |
//| هر 10 تیک اجرا می‌شود                                           |
//+------------------------------------------------------------------+
void DrawSMCZones() {
   if(g_draw_manager == NULL) return;

   // کنترل فرکانس: هر 10 تیک
   static int  draw_counter  = 0;
   static bool zones_drawn_ob = false;
   static bool zones_drawn_pd = false;
   draw_counter++;
   if(draw_counter < 10) return;
   draw_counter = 0;

   // به‌روزرسانی نواحی منقضی
   g_draw_manager.UpdateZones();

   // داده‌های کندل اخیر
   int    bars = 50;
   double high[]; CopyHigh(g_active_symbol, PERIOD_CURRENT, 0, bars, high);
   double low[];  CopyLow(g_active_symbol,  PERIOD_CURRENT, 0, bars, low);
   double close[];CopyClose(g_active_symbol,PERIOD_CURRENT, 0, bars, close);
   double open[]; CopyOpen(g_active_symbol, PERIOD_CURRENT, 0, bars, open);
   datetime times[]; CopyTime(g_active_symbol, PERIOD_CURRENT, 0, bars, times);
   ArraySetAsSeries(high, true); ArraySetAsSeries(low,  true);
   ArraySetAsSeries(close,true); ArraySetAsSeries(open, true);
   ArraySetAsSeries(times,true);

   // ================================================================
   // ① ساختار بازار: BOS / CHOCH / MSS / Swing Points
   // ================================================================
   if(DrawStructure) {
      // Swing Points با روش 3-کندل
      for(int i = 2; i < bars - 2; i++) {
         bool isSH = high[i] > high[i-1] && high[i] > high[i+1] &&
                     high[i] > high[i-2] && high[i] > high[i+2];
         bool isSL = low[i]  < low[i-1]  && low[i]  < low[i+1]  &&
                     low[i]  < low[i-2]  && low[i]  < low[i+2];
         if(isSH) g_draw_manager.DrawSwingPoint(high[i], times[i], "High");
         if(isSL) g_draw_manager.DrawSwingPoint(low[i],  times[i], "Low");
      }

      // یافتن آخرین Swing High/Low برای BOS/CHOCH
      double lastSH = 0, lastSL = 999999;
      datetime lastSHTime = 0, lastSLTime = 0;
      for(int i = bars - 1; i >= 2; i--) {
         if(high[i] > high[i-1] && high[i] > high[i+1] && high[i] > lastSH) {
            lastSH = high[i]; lastSHTime = times[i];
         }
         if(low[i] < low[i-1] && low[i] < low[i+1] && low[i] < lastSL) {
            lastSL = low[i]; lastSLTime = times[i];
         }
      }

      // BOS صعودی: بسته شدن بالای آخرین Swing High
      if(lastSH > 0 && close[0] > lastSH && lastSHTime > 0)
         g_draw_manager.DrawBOS(lastSH, lastSHTime, times[0], true);

      // BOS نزولی: بسته شدن پایین آخرین Swing Low
      if(lastSL < 999999 && close[0] < lastSL && lastSLTime > 0)
         g_draw_manager.DrawBOS(lastSL, lastSLTime, times[0], false);

      // CHOCH: برگشت ناگهانی ساختار
      bool isBullTrend = close[0] > close[bars - 1];
      if(isBullTrend && lastSL < 999999 && close[1] < lastSL && close[0] > lastSL)
         g_draw_manager.DrawCHOCH(lastSL, lastSLTime, times[0], false);
      if(!isBullTrend && lastSH > 0 && close[1] > lastSH && close[0] < lastSH)
         g_draw_manager.DrawCHOCH(lastSH, lastSHTime, times[0], true);
   }

   // ================================================================
   // ② Order Blocks (یکبار رسم می‌شوند)
   // ================================================================
   if(DrawOB && !zones_drawn_ob) {
      for(int i = 3; i < MathMin(bars - 1, 30); i++) {
         double bodySize = MathAbs(close[i] - open[i]);
         if(bodySize < SymbolInfoDouble(g_active_symbol, SYMBOL_POINT) * 3) continue;

         // OB صعودی: کندل نزولی قبل از پامپ قوی
         if(close[i] < open[i] && close[i-1] > open[i-1]) {
            double nextBody = MathAbs(close[i-1] - open[i-1]);
            if(nextBody > bodySize * 1.5)
               g_draw_manager.DrawOrderBlock(high[i], low[i], times[i], true, 65.0);
         }
         // OB نزولی: کندل صعودی قبل از دامپ قوی
         if(close[i] > open[i] && close[i-1] < open[i-1]) {
            double nextBody = MathAbs(close[i-1] - open[i-1]);
            if(nextBody > bodySize * 1.5)
               g_draw_manager.DrawOrderBlock(high[i], low[i], times[i], false, 65.0);
         }
      }
      zones_drawn_ob = true;
   }

   // ================================================================
   // ③ Fair Value Gap
   // ================================================================
   if(DrawFVG) {
      double minGap = SymbolInfoDouble(g_active_symbol, SYMBOL_POINT) * 5;
      for(int i = 2; i < MathMin(bars - 1, 25); i++) {
         // FVG صعودی
         if(low[i-1] > high[i+1] && low[i-1] - high[i+1] > minGap)
            g_draw_manager.DrawFVG(low[i-1], high[i+1], times[i], true, false);
         // FVG نزولی
         if(high[i-1] < low[i+1] && low[i+1] - high[i-1] > minGap)
            g_draw_manager.DrawFVG(low[i+1], high[i-1], times[i], false, false);
      }
   }

   // ================================================================
   // ④ Liquidity Zones (SSL/BSL) و Sweep
   // ================================================================
   if(DrawLiquidity) {
      double tol = SymbolInfoDouble(g_active_symbol, SYMBOL_POINT) * 10;
      for(int i = 3; i < MathMin(bars - 1, 30); i++) {
         // Equal Lows = SSL
         bool isEqLow  = MathAbs(low[i] - low[i+2])  < tol &&
                         low[i]  < low[i-1]  && low[i+2]  < low[i+1];
         // Equal Highs = BSL
         bool isEqHigh = MathAbs(high[i] - high[i+2]) < tol &&
                         high[i] > high[i-1] && high[i+2] > high[i+1];

         if(isEqLow)  g_draw_manager.DrawLiquidity(low[i],  times[i], "SSL", false);
         if(isEqHigh) g_draw_manager.DrawLiquidity(high[i], times[i], "BSL", false);

         // تشخیص Sweep
         if(isEqLow  && low[1]  < low[i]  - tol && close[0] > low[i])
            g_draw_manager.DrawLiquiditySweep(low[i],  times[1], true);
         if(isEqHigh && high[1] > high[i] + tol && close[0] < high[i])
            g_draw_manager.DrawLiquiditySweep(high[i], times[1], false);
      }
   }

   // ================================================================
   // ⑤ Premium / Discount (یکبار)
   // ================================================================
   if(!zones_drawn_pd) {
      double rHigh = high[ArrayMaximum(high, 0, 20)];
      double rLow  = low[ArrayMinimum(low,  0, 20)];
      double eq    = (rHigh + rLow) / 2.0;
      double minRange = SymbolInfoDouble(g_active_symbol, SYMBOL_POINT) * 50;
      if(rHigh - rLow > minRange)
         g_draw_manager.DrawPremiumDiscount(rHigh, rLow, eq, times[19]);
      zones_drawn_pd = true;
   }

   // رفرش چارت
   g_draw_manager.Refresh();
}

//+------------------------------------------------------------------+
//| آمار روزانه                                                      |
//+------------------------------------------------------------------+
void LogDailyStats() {
   double balance     = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity      = AccountInfoDouble(ACCOUNT_EQUITY);
   double daily_pnl   = g_position_manager.GetDailyPnL();
   double daily_pct   = balance > 0 ? daily_pnl / balance * 100.0 : 0;
   int    today_trades= g_position_manager.GetTodayTradeCount();
   double drawdown    = g_risk_manager.GetCurrentDrawdown();

   LogMessage(StringFormat(
      "📊 آمار روزانه | Balance:%.2f | Equity:%.2f | PnL:%.2f (%.1f%%) | معاملات:%d | DD:%.1f%%",
      balance, equity, daily_pnl, daily_pct, today_trades, drawdown), "INFO");
}
//+------------------------------------------------------------------+
