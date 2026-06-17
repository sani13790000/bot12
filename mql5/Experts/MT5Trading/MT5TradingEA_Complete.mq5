
//+------------------------------------------------------------------+
//|                                    MT5TradingEA_Complete.mq5    |
//|                                                                  |
//|  توضیح: اکسپرت ادوایزر اصلی پروژه Bot12 - نسخه کامل          |
//|                                                                  |
//|  این EA مغز متفکر سیستم معاملاتی است و تمام ماژول‌ها را      |
//|  به هم متصل می‌کند. وظایف اصلی:                              |
//|  ۱- دریافت سیگنال از Python Backend از طریق فایل               |
//|  ۲- اجرای معاملات از طریق ExecutionEngine                      |
//|  ۳- مدیریت ریسک از طریق RiskManager                           |
//|  ۴- رسم نواحی SMC روی چارت                                     |
//|  ۵- ارسال هشدار از طریق NotificationManager                    |
//|  ۶- بررسی لایسنس و مجوز فعالیت                               |
//|  ۷- مدیریت Scale Out خودکار                                    |
//|  ۸- پایش سشن‌ها و Kill Zones                                   |
//+------------------------------------------------------------------+

#property copyright   "Bot12 Trading System"
#property version     "3.00"
#property description "سیستم معاملاتی حرفه‌ای Bot12 - نسخه کامل"
#property strict

//--- ماژول‌های اصلی
#include <MT5Trading\Config.mqh>
#include <MT5Trading\LicenseChecker.mqh>
#include <MT5Trading\RiskManager.mqh>
#include <MT5Trading\TradeManager.mqh>
#include <MT5Trading\PositionManager.mqh>
#include <MT5Trading\DrawManager.mqh>
#include <MT5Trading\NotificationManager.mqh>
#include <MT5Trading\DecisionConnector.mqh>
#include <MT5Trading\StrategyLoader.mqh>

//--- ماژول‌های جدید
#include <MT5Trading\ExecutionEngine.mqh>
#include <MT5Trading\RiskManager_Complete.mqh>
#include <MT5Trading\SessionManager.mqh>

//--- ==============================================================
//--- پارامترهای ورودی - گروه‌بندی حرفه‌ای
//--- ==============================================================

//--- [لایسنس]
input group "═══ لایسنس ═══"
input string   LicenseKey       = "";             // کلید لایسنس
input string   ServerURL        = "https://bot12.ir/api"; // آدرس سرور

//--- [نماد و تایم‌فریم]
input group "═══ تنظیمات نماد ═══"
input string   TradingSymbol    = "";             // نماد معاملاتی (خالی = نماد جاری)
input bool     MultiTimeframe   = true;           // تحلیل چند تایم‌فریم

//--- [مدیریت ریسک]
input group "═══ مدیریت ریسک ═══"
input double   RiskPercent      = 1.0;            // درصد ریسک هر معامله
input double   MaxDailyLoss     = 3.0;            // حداکثر ضرر روزانه (%)
input double   MaxDrawdown      = 10.0;           // حداکثر افت سرمایه (%)
input int      MaxPositions     = 3;              // حداکثر پوزیشن همزمان
input int      MaxSpread        = 25;             // حداکثر اسپرد مجاز (پوینت)
input bool     UseBreakEven     = true;           // استفاده از Break Even
input double   BreakEvenPoints  = 30.0;           // نقاط برای فعال شدن BE
input bool     UseTrailing      = true;           // Trailing Stop
input double   TrailingPoints   = 20.0;           // نقاط Trailing

//--- [Scale Out]
input group "═══ Scale Out ═══"
input bool     UseScaleOut      = true;           // استفاده از Scale Out
input double   ScaleOut1Percent = 30.0;           // درصد بستن در TP1 (%)
input double   ScaleOut2Percent = 30.0;           // درصد بستن در TP2 (%)

//--- [سشن‌ها]
input group "═══ سشن‌های معاملاتی ═══"
input bool     UseSydney        = false;          // سشن Sydney
input bool     UseTokyo         = true;           // سشن Tokyo
input bool     UseLondon        = true;           // سشن London
input bool     UseNewYork       = true;           // سشن New York
input bool     OnlyKillZones    = false;          // فقط در Kill Zones معامله شود

//--- [اعلان‌ها]
input group "═══ اعلان‌ها ═══"
input string   TelegramToken    = "";             // توکن ربات تلگرام
input string   TelegramChatID   = "";             // شناسه چت تلگرام
input bool     NotifyOnEntry    = true;           // هشدار ورود
input bool     NotifyOnExit     = true;           // هشدار خروج
input bool     NotifyOnSession  = true;           // هشدار سشن
input bool     SendDailyReport  = true;           // گزارش روزانه

//--- [رسم]
input group "═══ رسم روی چارت ═══"
input bool     DrawOB           = true;           // رسم Order Block
input bool     DrawFVG          = true;           // رسم FVG
input bool     DrawLiquidity    = true;           // رسم نقدینگی
input bool     DrawStructure    = true;           // رسم ساختار بازار
input bool     DrawKillZones    = true;           // رسم Kill Zones

//--- [فایل سیگنال]
input group "═══ اتصال Python ═══"
input string   SignalFile       = "bot12_signal.json"; // فایل سیگنال
input int      SignalCheckMs    = 1000;           // فرکانس بررسی سیگنال (ms)

//--- ==============================================================

//--- [اتصال به Python API — فاز ۱]
input group "═══ Python API Connection ═══"
input bool     EnableAPI         = true;            // اتصال به Python Backend
input string   APIBaseURL        = "http://localhost:8000";  // آدرس API
input int      APITimeoutMs      = 5000;            // تایم‌اوت (ms)

//--- [محدودیت‌های پیشرفته — فاز ۱]
input group "═══ محدودیت‌های معاملاتی ═══"
input int      MaxDailyTrades    = 5;               // حداکثر معاملات روزانه
input int      MaxOpenPositions  = 3;               // حداکثر پوزیشن همزمان

//--- متغیرهای سراسری
//--- ==============================================================

// ماژول‌های اصلی
CRiskManager*           g_risk_manager    = NULL;
CTradeManager*          g_trade_manager   = NULL;
CPositionManager*       g_position_manager = NULL;
CDrawManager*           g_draw_manager    = NULL;
CNotificationManager*   g_notification    = NULL;
CDecisionConnector*     g_decision        = NULL;
CLicenseChecker*        g_license         = NULL;
CStrategyLoader*        g_strategy_loader = NULL;

// ماژول‌های جدید
CExecutionEngine*       g_execution       = NULL;
CRiskManagerComplete*   g_risk_complete   = NULL;
CSessionManager*        g_session         = NULL;

// وضعیت سیستم
bool     g_initialized       = false;   // آیا مقداردهی شده؟
bool     g_license_valid      = false;   // آیا لایسنس معتبر است؟
bool     g_trading_allowed    = false;   // آیا معامله مجاز است؟
bool     g_emergency_stop     = false;   // آیا Emergency Stop فعال است؟
string   g_active_symbol      = "";      // نماد فعال

// مدیریت زمان
datetime g_last_signal_check   = 0;     // آخرین بررسی سیگنال
datetime g_last_daily_report   = 0;     // آخرین گزارش روزانه
datetime g_last_session_notify = 0;     // آخرین اعلان سشن
datetime g_session_open_time   = 0;     // زمان باز شدن سشن

// وضعیت سشن قبلی
bool     g_prev_session_active = false; // آیا سشن قبلی فعال بود؟
bool     g_prev_kz_active      = false; // آیا Kill Zone قبلی فعال بود؟

//+------------------------------------------------------------------+
//| مقداردهی اولیه اکسپرت                                           |
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| ارتباط با Python API از طریق WebRequest — فاز ۱                 |
//+------------------------------------------------------------------+

struct APISignalResponse {
   string signal_type;      // BUY / SELL / NO_TRADE
   double entry_price;
   double stop_loss;
   double take_profit;
   double score;
   bool   valid;
};

APISignalResponse FetchSignalFromAPI(string symbol) {
   APISignalResponse resp;
   resp.valid = false;
   resp.signal_type = "NO_TRADE";

   if(!EnableAPI) return resp;

   string url     = APIBaseURL + "/api/v1/signal";
   string headers = "Content-Type: application/json\r\n";
   string body    = StringFormat(
      "{\"symbol\":\"%s\",\"time\":%d}",
      symbol, (int)TimeCurrent()
   );

   char post_data[], result_data[];
   string result_headers;
   StringToCharArray(body, post_data, 0, StringLen(body));

   int res = WebRequest("POST", url, headers, APITimeoutMs, post_data, result_data, result_headers);

   if(res == -1) {
      int err = GetLastError();
      if(err == 4014)
         Print("⚠️ WebRequest غیرفعال — Tools > Options > Expert Advisors > Allow WebRequest را فعال کنید");
      else
         PrintFormat("⚠️ خطای WebRequest: %d", err);
      return resp;
   }

   if(res != 200) {
      PrintFormat("⚠️ API HTTP %d", res);
      return resp;
   }

   string r = CharArrayToString(result_data);

   int p = StringFind(r, "\"signal\":\"");
   if(p >= 0) {
      int s = p + 10, e = StringFind(r, "\"", s);
      resp.signal_type = StringSubstr(r, s, e - s);
   }

   p = StringFind(r, "\"score\":"); if(p >= 0) resp.score       = StringToDouble(StringSubstr(r, p+9,  8));
   p = StringFind(r, "\"entry\":"); if(p >= 0) resp.entry_price = StringToDouble(StringSubstr(r, p+9, 12));
   p = StringFind(r, "\"sl\":");    if(p >= 0) resp.stop_loss   = StringToDouble(StringSubstr(r, p+6, 12));
   p = StringFind(r, "\"tp\":");    if(p >= 0) resp.take_profit = StringToDouble(StringSubstr(r, p+6, 12));

   resp.valid = (resp.signal_type == "BUY" || resp.signal_type == "SELL");
   return resp;
}

void SendEAStatusToAPI(string status) {
   if(!EnableAPI) return;
   string url = APIBaseURL + "/api/v1/ea/heartbeat";
   string headers = "Content-Type: application/json\r\n";
   string body = StringFormat(
      "{\"status\":\"%s\",\"symbol\":\"%s\",\"equity\":%.2f,\"time\":%d}",
      status, g_active_symbol,
      AccountInfoDouble(ACCOUNT_EQUITY),
      (int)TimeCurrent()
   );
   char p[], r[]; string rh;
   StringToCharArray(body, p, 0, StringLen(body));
   WebRequest("POST", url, headers, 3000, p, r, rh);
}

//+------------------------------------------------------------------+
//| اعتبارسنجی قبل از معامله — فاز ۱                                |
//+------------------------------------------------------------------+

struct PreTradeCheck {
   bool   ok;
   string reason;
};

bool IsWeekend() {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   return (dt.day_of_week == 0 || dt.day_of_week == 6);
}

bool IsNearWeekendClose() {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   return (dt.day_of_week == 5 && dt.hour >= 21);
}

int CountTodayTrades() {
   int count = 0;
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d 00:00",
      TimeYear(TimeCurrent()), TimeMonth(TimeCurrent()), TimeDay(TimeCurrent())));
   HistorySelect(today, TimeCurrent());
   for(int i = 0; i < HistoryDealsTotal(); i++) {
      ulong tk = HistoryDealGetTicket(i);
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != g_active_symbol) continue;
      long type = HistoryDealGetInteger(tk, DEAL_TYPE);
      if(type == DEAL_TYPE_BUY || type == DEAL_TYPE_SELL) count++;
   }
   return count;
}

PreTradeCheck ValidateBeforeTrade(ENUM_POSITION_TYPE dir, double entry, double sl, double vol) {
   PreTradeCheck c; c.ok = false;

   // چک ۱: آخر هفته
   if(IsWeekend())         { c.reason = "آخر هفته - بازار بسته"; return c; }
   if(IsNearWeekendClose()){ c.reason = "نزدیک بسته شدن آخر هفته"; return c; }

   // چک ۲: نماد
   if(!SymbolSelect(g_active_symbol, true)) { c.reason = "نماد نامعتبر: " + g_active_symbol; return c; }
   double ask = SymbolInfoDouble(g_active_symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(g_active_symbol, SYMBOL_BID);
   if(ask <= 0 || bid <= 0) { c.reason = "قیمت نماد صفر - بازار بسته؟"; return c; }

   // چک ۳: موجودی
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double margin  = AccountInfoDouble(ACCOUNT_FREEMARGIN);
   if(balance <= 0) { c.reason = "موجودی صفر"; return c; }
   if(margin  <= 0) { c.reason = "مارجین آزاد ندارید"; return c; }

   // چک ۴: مارجین کافی
   double req_margin = 0;
   ENUM_ORDER_TYPE ot = (dir == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(OrderCalcMargin(ot, g_active_symbol, vol, entry, req_margin)) {
      if(margin < req_margin * 1.5) {
         c.reason = StringFormat("مارجین ناکافی: آزاد=%.2f نیاز=%.2f", margin, req_margin * 1.5);
         return c;
      }
   }

   // چک ۵: معاملات روزانه
   int today_count = CountTodayTrades();
   if(today_count >= MaxDailyTrades) {
      c.reason = StringFormat("سقف روزانه: %d/%d", today_count, MaxDailyTrades);
      return c;
   }

   // چک ۶: پوزیشن‌های باز
   if(PositionsTotal() >= MaxOpenPositions) {
      c.reason = StringFormat("سقف پوزیشن: %d/%d", PositionsTotal(), MaxOpenPositions);
      return c;
   }

   // چک ۷: اسپرد
   double spread = (ask - bid) / SymbolInfoDouble(g_active_symbol, SYMBOL_POINT);
   if(spread > MaxSpread) {
      c.reason = StringFormat("اسپرد زیاد: %.0f > %d", spread, MaxSpread);
      return c;
   }

   // چک ۸: فاصله SL
   double sl_dist  = MathAbs(entry - sl);
   double min_dist = SymbolInfoDouble(g_active_symbol, SYMBOL_POINT)
                   * (double)SymbolInfoInteger(g_active_symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(sl_dist < min_dist) {
      c.reason = StringFormat("SL خیلی نزدیک: %.5f < %.5f", sl_dist, min_dist);
      return c;
   }

   c.ok = true;
   PrintFormat("✅ Pre-Trade OK | موجودی=%.2f مارجین=%.2f امروز=%d پوزیشن=%d",
      balance, margin, today_count, PositionsTotal());
   return c;
}


int OnInit() {
   Print("═══════════════════════════════════════════");
   Print("  Bot12 Trading System v3.0 - شروع مقداردهی");
   Print("═══════════════════════════════════════════");

   // --- تعیین نماد معاملاتی ---
   g_active_symbol = (TradingSymbol == "") ? Symbol() : TradingSymbol;
   PrintFormat("📌 نماد فعال: %s", g_active_symbol);

   // --- بررسی لایسنس ---
   g_license = new CLicenseChecker();
   g_license_valid = g_license.CheckLicense(LicenseKey, ServerURL, g_active_symbol);

   if(!g_license_valid) {
      Alert("❌ لایسنس نامعتبر! سیستم متوقف شد.");
      Print("❌ خطا: لایسنس نامعتبر");
      return INIT_FAILED;
   }
   Print("✅ لایسنس معتبر");

   // --- راه‌اندازی ماژول‌های اصلی ---
   g_risk_manager = new CRiskManager(g_active_symbol);
   g_risk_manager.SetMaxDailyLossPercent(MaxDailyLoss);
   g_risk_manager.SetMaxDrawdownPercent(MaxDrawdown);
   Print("✅ RiskManager راه‌اندازی شد");

   g_trade_manager = new CTradeManager(g_active_symbol);
   Print("✅ TradeManager راه‌اندازی شد");

   g_position_manager = new CPositionManager(g_active_symbol);
   Print("✅ PositionManager راه‌اندازی شد");

   g_draw_manager = new CDrawManager(g_active_symbol);
   Print("✅ DrawManager راه‌اندازی شد");

   g_decision = new CDecisionConnector(g_active_symbol, SignalFile);
   Print("✅ DecisionConnector راه‌اندازی شد");

   g_strategy_loader = new CStrategyLoader();
   Print("✅ StrategyLoader راه‌اندازی شد");

   // --- راه‌اندازی ماژول‌های جدید ---
   g_execution = new CExecutionEngine(g_active_symbol, 12345);
   g_execution.SetMaxSlippage(MaxSpread);
   Print("✅ ExecutionEngine راه‌اندازی شد");

   g_risk_complete = new CRiskManagerComplete(g_active_symbol);
   Print("✅ RiskManagerComplete راه‌اندازی شد");

   g_session = new CSessionManager();
   g_session.SetActiveSessions(UseSydney, UseTokyo, UseLondon, UseNewYork, false, OnlyKillZones);
   Print("✅ SessionManager راه‌اندازی شد");

   // --- راه‌اندازی NotificationManager ---
   g_notification = new CNotificationManager();
   if(TelegramToken != "" && TelegramChatID != "") {
      g_notification.SetTelegramCredentials(TelegramToken, TelegramChatID);
      g_notification.EnableTelegram(true);
      Print("✅ تلگرام متصل شد");
   }

   // --- تنظیم تایمر ---
   EventSetMillisecondTimer(SignalCheckMs);

   g_initialized = true;
   g_trading_allowed = true;

   // --- ارسال هشدار شروع ---
   if(NotifyOnSession) {
      string start_msg = StringFormat(
         "🚀 Bot12 راه‌اندازی شد\n"
         "📌 نماد: %s\n"
         "⚙️ ریسک: %.1f%%\n"
         "🔒 لایسنس: معتبر",
         g_active_symbol, RiskPercent
      );
      g_notification.SendText(NOTIF_SYSTEM, start_msg);
   }

   Print("✅ مقداردهی کامل شد");
   Print("═══════════════════════════════════════════");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| پردازش هر تیک                                                    |
//+------------------------------------------------------------------+
void OnTick() {
   if(!g_initialized || !g_license_valid) return;

   // --- بررسی Emergency Stop ---
   if(g_emergency_stop) {
      static datetime last_es_warn = 0;
      if(TimeCurrent() - last_es_warn > 60) {
         Print("⚠️ Emergency Stop فعال - معامله متوقف");
         last_es_warn = TimeCurrent();
      }
      return;
   }

   // --- بررسی محدودیت‌های ریسک ---
   if(g_risk_manager.IsDailyLossLimitReached()) {
      static datetime last_dl_warn = 0;
      if(TimeCurrent() - last_dl_warn > 300) {
         string warn = StringFormat("⚠️ محدودیت ضرر روزانه رسیده! معامله متوقف.");
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

   // --- به‌روزرسانی پوزیشن‌های باز ---
   UpdateOpenPositions();

   // --- بررسی گزارش روزانه ---
   CheckDailyReport();
}

//+------------------------------------------------------------------+
//| پردازش تایمر (بررسی سیگنال‌ها)                                  |
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
   double signal_score = g_decision.GetSignalScore();

   if(entry <= 0 || sl <= 0) {
      Print("❌ سیگنال نامعتبر - قیمت ورود یا SL صفر است");
      return;
   }

   // بررسی امتیاز سیگنال
   if(signal_score < 65.0) {
      PrintFormat("⚠️ امتیاز سیگنال پایین: %.1f - معامله نشد", signal_score);
      return;
   }

   // تعیین جهت
   ENUM_POSITION_TYPE direction = (signal_type == "BUY") ? 
      POSITION_TYPE_BUY : POSITION_TYPE_SELL;

   // محاسبه حجم
   LotCalculationResult lot_result = g_risk_manager.CalculateLot(
      RiskPercent, MathAbs(entry - sl) / SymbolInfoDouble(g_active_symbol, SYMBOL_POINT)
   );

   if(!lot_result.valid) {
      PrintFormat("❌ محاسبه حجم ناموفق: %s", lot_result.error_message);
      return;
   }

   // محاسبه TakeProfit
   TakeProfitResult tp_result = g_risk_complete.CalculateTakeProfits(
      direction, entry, sl,
      g_decision.GetSwingHigh(), g_decision.GetSwingLow(),
      g_decision.GetStructureTarget()
   );

   double final_tp = tp_result.is_valid ? tp_result.recommended_tp : 0;

   // ساخت درخواست معامله
   TradeRequest req;
   req.direction    = direction;
   req.volume       = lot_result.lot;
   req.price        = 0;  // Market Order
   req.stop_loss    = sl;
   req.take_profit  = final_tp;
   req.order_type   = ORDER_TYPE_BUY;
   req.comment      = StringFormat("Bot12|Score:%.0f", signal_score);
   req.magic        = 12345;
   req.max_slippage = MaxSpread;
   req.use_market   = true;

   // ─── اعتبارسنجی قبل از معامله — فاز ۱ ───
   PreTradeCheck ptc = ValidateBeforeTrade(direction, entry, sl, lot_result.lot);
   if(!ptc.ok) {
      PrintFormat("⛔ Pre-Trade Blocked: %s", ptc.reason);
      g_notification.SendText(NOTIF_RISK, "⛔ معامله رد شد: " + ptc.reason);
      return;
   }

   // اجرای معامله
   ExecutionResult exec = g_execution.ExecuteMarketOrder(req);

   if(exec.success) {
      PrintFormat("✅ معامله اجرا شد | تیکت:%d | قیمت:%.5f | اسلیپیج:%.1f",
         exec.ticket, exec.executed_price, exec.slippage_points);

      // تنظیم Scale Out
      if(UseScaleOut && final_tp > 0) {
         g_risk_complete.SetScaleOutLevels(direction, exec.executed_price, sl, final_tp);
      }

      // ارسال هشدار ورود به تلگرام
      if(NotifyOnEntry) {
         g_notification.NotifyTradeOpen(
            exec.ticket, direction, g_active_symbol,
            exec.executed_price, sl, final_tp, lot_result.lot,
            tp_result.risk_reward, g_decision.GetSignalReason()
         );
      }
   } else {
      PrintFormat("❌ اجرای معامله ناموفق: %s", exec.error_message);
   }
}

//+------------------------------------------------------------------+
//| به‌روزرسانی پوزیشن‌های باز (BreakEven, Trailing, ScaleOut)     |
//+------------------------------------------------------------------+
void UpdateOpenPositions() {
   for(int i = PositionsTotal() - 1; i >= 0; i--) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != g_active_symbol) continue;

      // BreakEven
      if(UseBreakEven) {
         g_risk_manager.UpdateBreakEven(ticket, BreakEvenPoints, 2.0);
      }

      // Trailing Stop
      if(UseTrailing) {
         g_risk_manager.UpdateTrailingStop(ticket, TrailingPoints, 5.0);
      }

      // Scale Out
      if(UseScaleOut) {
         g_risk_complete.CheckAndExecuteScaleOut(ticket);
      }
   }
}

//+------------------------------------------------------------------+
//| پایش سشن‌ها و ارسال هشدار تغییر سشن                           |
//+------------------------------------------------------------------+
void MonitorSessions() {
   SessionInfo current = g_session.GetCurrentSession();

   // بررسی تغییر وضعیت سشن
   if(current.can_trade != g_prev_session_active) {
      if(current.can_trade) {
         // سشن باز شد
         g_session_open_time = TimeCurrent();
         if(NotifyOnSession) {
            g_notification.NotifySessionStart(current.session_name);
         }

         // رسم Kill Zones روی چارت
         if(DrawKillZones && g_draw_manager != NULL) {
            g_draw_manager.DrawSessionRange(current.session_name, TimeCurrent());
         }
      } else {
         // سشن بسته شد
         if(NotifyOnSession) {
            datetime duration_sec = TimeCurrent() - g_session_open_time;
            int trades_in_session = g_position_manager.GetSessionTradeCount(g_session_open_time);
            g_notification.NotifySessionEnd(current.session_name, trades_in_session, 0);
         }
      }
      g_prev_session_active = current.can_trade;
   }
}

//+------------------------------------------------------------------+
//| بررسی و ارسال گزارش روزانه                                      |
//+------------------------------------------------------------------+
void CheckDailyReport() {
   if(!SendDailyReport) return;

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   // ارسال گزارش در ساعت ۲۱:۰۰
   if(dt.hour == 21 && dt.min == 0) {
      if(TimeCurrent() - g_last_daily_report > 1800) { // جلوگیری از ارسال مکرر
         g_last_daily_report = TimeCurrent();

         double daily_pnl     = g_risk_manager.GetDailyPnL();
         double daily_pnl_pct = g_risk_manager.GetDailyPnLPercent();
         int    total_trades  = g_position_manager.GetTodayTradeCount();
         double win_rate      = g_position_manager.GetTodayWinRate();

         g_notification.SendDailyReport(
            daily_pnl, daily_pnl_pct, total_trades, win_rate,
            g_risk_manager.GetCurrentDrawdown()
         );
      }
   }
}

//+------------------------------------------------------------------+
//| رویداد تغییر معامله (Trade)                                      |
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
            // تعیین دلیل بستن
            string close_reason = "بسته شدن";
            if(trans.deal_entry == DEAL_ENTRY_OUT) {
               // بررسی SL یا TP
               double profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
               close_reason = (profit < 0) ? "حد ضرر" : "حد سود";
            }

            g_notification.NotifyTradeClose(
               trans.deal,
               (trans.deal_type == DEAL_TYPE_BUY ? POSITION_TYPE_BUY : POSITION_TYPE_SELL),
               trans.symbol,
               trans.price, 0,
               HistoryDealGetDouble(trans.deal, DEAL_PROFIT),
               0, close_reason
            );
         }
      }
   }
}

//+------------------------------------------------------------------+
//| پاک‌سازی منابع در هنگام خروج                                    |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {
   // ارسال هشدار توقف
   if(g_notification != NULL && g_initialized) {
      string reason_str = "";
      switch(reason) {
         case REASON_REMOVE:    reason_str = "حذف EA";           break;
         case REASON_CHARTCLOSE: reason_str = "بستن چارت";       break;
         case REASON_RECOMPILE: reason_str = "کامپایل مجدد";     break;
         default:               reason_str = "نامشخص";           break;
      }
      g_notification.SendText(NOTIF_SYSTEM, 
         StringFormat("⛔ Bot12 متوقف شد\nدلیل: %s\nنماد: %s", reason_str, g_active_symbol)
      );
   }

   // حذف اشیاء
   EventKillTimer();

   if(g_risk_manager)     { delete g_risk_manager;     g_risk_manager = NULL; }
   if(g_trade_manager)    { delete g_trade_manager;    g_trade_manager = NULL; }
   if(g_position_manager) { delete g_position_manager; g_position_manager = NULL; }
   if(g_draw_manager)     { delete g_draw_manager;     g_draw_manager = NULL; }
   if(g_notification)     { delete g_notification;     g_notification = NULL; }
   if(g_decision)         { delete g_decision;         g_decision = NULL; }
   if(g_license)          { delete g_license;          g_license = NULL; }
   if(g_strategy_loader)  { delete g_strategy_loader;  g_strategy_loader = NULL; }
   if(g_execution)        { delete g_execution;        g_execution = NULL; }
   if(g_risk_complete)    { delete g_risk_complete;    g_risk_complete = NULL; }
   if(g_session)          { delete g_session;          g_session = NULL; }

   Print("✅ تمام منابع آزاد شدند | Bot12 متوقف شد");
}
