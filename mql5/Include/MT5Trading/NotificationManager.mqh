//+------------------------------------------------------------------+
//|                                        NotificationManager.mqh     |
//|                         سیستم معامله‌گری حرفه‌ای MT5               |
//|                                                                    |
//| توضیح فارسی:                                                       |
//| این فایل مسئول ارسال تمام اعلان‌ها و هشدارهای سیستم است.           |
//| امکانات: تلگرام، پوش نوتیفیکیشن، ایمیل، صدا و نمایش روی چارت     |
//| تمام پیام‌ها به فارسی هستند با فرمت‌بندی حرفه‌ای                   |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"

//+------------------------------------------------------------------+
//| انواع اعلان                                                         |
//+------------------------------------------------------------------+
enum ENUM_NOTIFICATION_TYPE {
   NOTIFY_SIGNAL,          // سیگنال جدید
   NOTIFY_TRADE_OPEN,      // باز شدن معامله
   NOTIFY_TRADE_CLOSE,     // بسته شدن معامله
   NOTIFY_SL_HIT,          // اصابت به حد ضرر
   NOTIFY_TP_HIT,          // اصابت به حد سود
   NOTIFY_SL_MOVED,        // جابجایی StopLoss
   NOTIFY_BE_ACTIVATED,    // فعال شدن Break Even
   NOTIFY_TRAILING_UPDATE, // به‌روزرسانی Trailing Stop
   NOTIFY_SESSION_START,   // شروع سشن
   NOTIFY_SESSION_END,     // پایان سشن
   NOTIFY_DAILY_REPORT,    // گزارش روزانه
   NOTIFY_WEEKLY_REPORT,   // گزارش هفتگی
   NOTIFY_MONTHLY_REPORT,  // گزارش ماهانه
   NOTIFY_RISK_WARNING,    // هشدار ریسک
   NOTIFY_EMERGENCY_STOP,  // توقف اضطراری
   NOTIFY_LICENSE_WARNING, // هشدار لایسنس
   NOTIFY_ERROR,           // خطا
   NOTIFY_WARNING,         // هشدار
   NOTIFY_INFO             // اطلاعات
};

//+------------------------------------------------------------------+
//| ساختار اعلان                                                        |
//+------------------------------------------------------------------+
struct Notification {
   ENUM_NOTIFICATION_TYPE type;  // نوع اعلان
   string title;                  // عنوان
   string message;                // متن اصلی
   string symbol;                 // نماد
   string details;                // جزئیات اضافه
   datetime timestamp;            // زمان
   int priority;                  // اولویت (1-5)
   double price;                  // قیمت مرتبط
   double pnl;                    // سود/ضرر مرتبط
};

//+------------------------------------------------------------------+
//| کلاس مدیریت اعلان‌ها                                                |
//+------------------------------------------------------------------+
class CNotificationManager {
private:
   // تنظیمات تلگرام
   string m_telegramToken;        // توکن ربات تلگرام
   string m_telegramChatId;       // شناسه چت
   bool m_telegramEnabled;        // وضعیت تلگرام

   // تنظیمات کلی
   bool m_enabled;                // وضعیت کلی
   bool m_emailEnabled;           // وضعیت ایمیل
   bool m_pushEnabled;            // وضعیت پوش نوتیفیکیشن
   bool m_soundEnabled;           // وضعیت صدا

   // تنظیمات صدا
   string m_soundSignal;          // صدای سیگنال
   string m_soundTrade;           // صدای معامله
   string m_soundAlert;           // صدای هشدار

   // محدودیت‌های ارسال
   int m_maxPerHour;              // حداکثر اعلان در ساعت
   int m_sentThisHour;            // تعداد ارسال شده
   datetime m_hourStart;          // شروع ساعت فعلی

   // صف اعلان‌ها
   Notification m_queue[];        // صف اعلان‌های در انتظار
   int m_queueSize;               // اندازه صف

   // توابع کمکی داخلی
   string FormatTelegramMessage(const Notification &notif);
   string GetEmoji(const ENUM_NOTIFICATION_TYPE type);
   string GetPersianType(const ENUM_NOTIFICATION_TYPE type);
   string GetPriorityStars(const int priority);
   bool CanSendNotification();
   void ResetHourlyCounter();
   bool SendToTelegram(const string message);
   void PlayNotificationSound(const ENUM_NOTIFICATION_TYPE type);
   string FormatPrice(const double price);
   string FormatPnL(const double pnl);
   string GetDirectionEmoji(const ENUM_POSITION_TYPE dir);

public:
   CNotificationManager();
   ~CNotificationManager();

   // تنظیمات
   void SetTelegramCredentials(const string token, const string chatId);
   void EnableTelegram(const bool enable);
   void EnableEmail(const bool enable);
   void EnablePush(const bool enable);
   void EnableSound(const bool enable);
   void SetMaxPerHour(const int max);

   // ارسال اعلان عمومی
   bool Send(const Notification &notif);
   bool SendText(const ENUM_NOTIFICATION_TYPE type, const string message, const int priority = 3);

   // ===== اعلان‌های معاملاتی =====

   // هشدار ورود به معامله
   bool NotifyTradeOpen(
      const ulong ticket,
      const ENUM_POSITION_TYPE direction,
      const string symbol,
      const double lot,
      const double entryPrice,
      const double stopLoss,
      const double takeProfit,
      const double riskAmount,
      const string strategy = ""
   );

   // هشدار خروج از معامله
   bool NotifyTradeClose(
      const ulong ticket,
      const ENUM_POSITION_TYPE direction,
      const string symbol,
      const double lot,
      const double openPrice,
      const double closePrice,
      const double pnl,
      const string reason = ""
   );

   // هشدار اصابت StopLoss
   bool NotifySLHit(
      const ulong ticket,
      const string symbol,
      const double loss,
      const double slPrice
   );

   // هشدار اصابت TakeProfit
   bool NotifyTPHit(
      const ulong ticket,
      const string symbol,
      const double profit,
      const double tpPrice
   );

   // هشدار جابجایی SL
   bool NotifySLMoved(
      const ulong ticket,
      const string symbol,
      const double oldSL,
      const double newSL,
      const string reason = "Trailing Stop"
   );

   // هشدار Break Even
   bool NotifyBreakEvenActivated(
      const ulong ticket,
      const string symbol,
      const double bePrice
   );

   // ===== اعلان‌های سشن =====

   // هشدار باز شدن سشن
   bool NotifySessionStart(
      const string sessionName,
      const string startTime,
      const string endTime
   );

   // هشدار بسته شدن سشن
   bool NotifySessionEnd(
      const string sessionName,
      const double sessionPnL,
      const int sessionTrades
   );

   // ===== گزارش‌ها =====

   // گزارش روزانه
   bool SendDailyReport(
      const double balance,
      const double equity,
      const double dailyPnL,
      const double dailyPnLPct,
      const int totalTrades,
      const int winTrades,
      const int lossTrades,
      const double winRate,
      const double maxDrawdown
   );

   // گزارش هفتگی
   bool SendWeeklyReport(
      const double weeklyPnL,
      const double weeklyPnLPct,
      const int totalTrades,
      const double winRate,
      const double bestDay,
      const double worstDay
   );

   // گزارش ماهانه
   bool SendMonthlyReport(
      const double monthlyPnL,
      const double monthlyPnLPct,
      const int totalTrades,
      const double winRate,
      const double profitFactor,
      const double maxDrawdown
   );

   // ===== هشدارهای ریسک =====

   // هشدار ریسک
   bool NotifyRiskWarning(
      const string reason,
      const double currentValue,
      const double maxAllowed
   );

   // هشدار توقف اضطراری
   bool NotifyEmergencyStop(const string reason);

   // ===== توابع عمومی =====
   bool IsEnabled() const { return m_enabled; }
   void SetEnabled(const bool enable) { m_enabled = enable; }
   int GetQueueSize() const { return m_queueSize; }
   void ProcessQueue();
};

//+------------------------------------------------------------------+
//| سازنده                                                             |
//+------------------------------------------------------------------+
CNotificationManager::CNotificationManager() {
   m_telegramToken   = "";
   m_telegramChatId  = "";
   m_telegramEnabled = false;
   m_enabled         = true;
   m_emailEnabled    = false;
   m_pushEnabled     = false;
   m_soundEnabled    = true;

   m_soundSignal = "alert.wav";
   m_soundTrade  = "tick.wav";
   m_soundAlert  = "news.wav";

   m_maxPerHour   = 30;
   m_sentThisHour = 0;
   m_hourStart    = TimeCurrent();
   m_queueSize    = 0;

   ArrayResize(m_queue, 0);
}

//+------------------------------------------------------------------+
//| مخرب                                                               |
//+------------------------------------------------------------------+
CNotificationManager::~CNotificationManager() {
   ArrayFree(m_queue);
}

//+------------------------------------------------------------------+
//| تنظیم اطلاعات تلگرام                                               |
//+------------------------------------------------------------------+
void CNotificationManager::SetTelegramCredentials(const string token, const string chatId) {
   m_telegramToken  = token;
   m_telegramChatId = chatId;
   m_telegramEnabled = (StringLen(token) > 10 && StringLen(chatId) > 0);
}

//+------------------------------------------------------------------+
//| فعال/غیرفعال کردن تلگرام                                           |
//+------------------------------------------------------------------+
void CNotificationManager::EnableTelegram(const bool enable) {
   m_telegramEnabled = enable && StringLen(m_telegramToken) > 10;
}

//+------------------------------------------------------------------+
//| فعال/غیرفعال کردن ایمیل                                            |
//+------------------------------------------------------------------+
void CNotificationManager::EnableEmail(const bool enable) {
   m_emailEnabled = enable;
}

//+------------------------------------------------------------------+
//| فعال/غیرفعال کردن پوش                                              |
//+------------------------------------------------------------------+
void CNotificationManager::EnablePush(const bool enable) {
   m_pushEnabled = enable;
}

//+------------------------------------------------------------------+
//| فعال/غیرفعال کردن صدا                                              |
//+------------------------------------------------------------------+
void CNotificationManager::EnableSound(const bool enable) {
   m_soundEnabled = enable;
}

//+------------------------------------------------------------------+
//| تنظیم حداکثر اعلان در ساعت                                         |
//+------------------------------------------------------------------+
void CNotificationManager::SetMaxPerHour(const int max) {
   m_maxPerHour = MathMax(1, max);
}

//+------------------------------------------------------------------+
//| دریافت ایموجی نوع اعلان                                             |
//+------------------------------------------------------------------+
string CNotificationManager::GetEmoji(const ENUM_NOTIFICATION_TYPE type) {
   switch(type) {
      case NOTIFY_SIGNAL:          return "🎯";
      case NOTIFY_TRADE_OPEN:      return "✅";
      case NOTIFY_TRADE_CLOSE:     return "🔒";
      case NOTIFY_SL_HIT:          return "❌";
      case NOTIFY_TP_HIT:          return "💰";
      case NOTIFY_SL_MOVED:        return "🔄";
      case NOTIFY_BE_ACTIVATED:    return "🛡️";
      case NOTIFY_TRAILING_UPDATE: return "📈";
      case NOTIFY_SESSION_START:   return "🌅";
      case NOTIFY_SESSION_END:     return "🌆";
      case NOTIFY_DAILY_REPORT:    return "📊";
      case NOTIFY_WEEKLY_REPORT:   return "📅";
      case NOTIFY_MONTHLY_REPORT:  return "📆";
      case NOTIFY_RISK_WARNING:    return "⚠️";
      case NOTIFY_EMERGENCY_STOP:  return "🚨";
      case NOTIFY_LICENSE_WARNING: return "🔑";
      case NOTIFY_ERROR:           return "🔴";
      case NOTIFY_WARNING:         return "🟡";
      case NOTIFY_INFO:            return "🔵";
      default:                     return "📢";
   }
}

//+------------------------------------------------------------------+
//| دریافت نام فارسی نوع اعلان                                         |
//+------------------------------------------------------------------+
string CNotificationManager::GetPersianType(const ENUM_NOTIFICATION_TYPE type) {
   switch(type) {
      case NOTIFY_SIGNAL:          return "سیگنال جدید";
      case NOTIFY_TRADE_OPEN:      return "ورود به معامله";
      case NOTIFY_TRADE_CLOSE:     return "خروج از معامله";
      case NOTIFY_SL_HIT:          return "اصابت به حد ضرر";
      case NOTIFY_TP_HIT:          return "اصابت به حد سود";
      case NOTIFY_SL_MOVED:        return "جابجایی StopLoss";
      case NOTIFY_BE_ACTIVATED:    return "Break Even فعال";
      case NOTIFY_TRAILING_UPDATE: return "Trailing Stop";
      case NOTIFY_SESSION_START:   return "شروع سشن";
      case NOTIFY_SESSION_END:     return "پایان سشن";
      case NOTIFY_DAILY_REPORT:    return "گزارش روزانه";
      case NOTIFY_WEEKLY_REPORT:   return "گزارش هفتگی";
      case NOTIFY_MONTHLY_REPORT:  return "گزارش ماهانه";
      case NOTIFY_RISK_WARNING:    return "هشدار ریسک";
      case NOTIFY_EMERGENCY_STOP:  return "توقف اضطراری";
      case NOTIFY_LICENSE_WARNING: return "هشدار لایسنس";
      case NOTIFY_ERROR:           return "خطا";
      case NOTIFY_WARNING:         return "هشدار";
      case NOTIFY_INFO:            return "اطلاعات";
      default:                     return "اعلان";
   }
}

//+------------------------------------------------------------------+
//| دریافت ستاره‌های اولویت                                             |
//+------------------------------------------------------------------+
string CNotificationManager::GetPriorityStars(const int priority) {
   string stars = "";
   for(int i = 0; i < MathMin(priority, 5); i++) stars += "⭐";
   return stars;
}

//+------------------------------------------------------------------+
//| بررسی امکان ارسال                                                   |
//+------------------------------------------------------------------+
bool CNotificationManager::CanSendNotification() {
   if(!m_enabled) return false;

   datetime now = TimeCurrent();
   if(now - m_hourStart >= 3600) {
      ResetHourlyCounter();
   }

   return m_sentThisHour < m_maxPerHour;
}

//+------------------------------------------------------------------+
//| بازنشانی شمارنده ساعتی                                             |
//+------------------------------------------------------------------+
void CNotificationManager::ResetHourlyCounter() {
   m_sentThisHour = 0;
   m_hourStart = TimeCurrent();
}

//+------------------------------------------------------------------+
//| فرمت‌بندی قیمت                                                      |
//+------------------------------------------------------------------+
string CNotificationManager::FormatPrice(const double price) {
   return StringFormat("%.5f", price);
}

//+------------------------------------------------------------------+
//| فرمت‌بندی سود/ضرر                                                   |
//+------------------------------------------------------------------+
string CNotificationManager::FormatPnL(const double pnl) {
   if(pnl > 0) return StringFormat("+$%.2f", pnl);
   return StringFormat("-$%.2f", MathAbs(pnl));
}

//+------------------------------------------------------------------+
//| ایموجی جهت معامله                                                   |
//+------------------------------------------------------------------+
string CNotificationManager::GetDirectionEmoji(const ENUM_POSITION_TYPE dir) {
   return (dir == POSITION_TYPE_BUY) ? "📗 خرید" : "📕 فروش";
}

//+------------------------------------------------------------------+
//| فرمت‌بندی پیام تلگرام                                               |
//+------------------------------------------------------------------+
string CNotificationManager::FormatTelegramMessage(const Notification &notif) {
   string msg = "";

   // هدر
   msg += GetEmoji(notif.type) + " *" + GetPersianType(notif.type) + "*";
   if(notif.priority >= 4) msg += "  " + GetPriorityStars(notif.priority);
   msg += "\n";
   msg += "━━━━━━━━━━━━━━━━━━━━\n";

   // پیام اصلی
   if(notif.title != "") {
      msg += "📌 " + notif.title + "\n";
   }
   msg += notif.message + "\n";

   // جزئیات
   if(notif.details != "") {
      msg += "\n" + notif.details + "\n";
   }

   // فوتر
   msg += "━━━━━━━━━━━━━━━━━━━━\n";
   msg += "🕐 " + TimeToString(notif.timestamp, TIME_DATE|TIME_MINUTES);
   if(notif.symbol != "") msg += " | " + notif.symbol;

   return msg;
}

//+------------------------------------------------------------------+
//| ارسال به تلگرام                                                     |
//+------------------------------------------------------------------+
bool CNotificationManager::SendToTelegram(const string message) {
   if(!m_telegramEnabled || m_telegramToken == "" || m_telegramChatId == "") {
      return false;
   }

   string url = "https://api.telegram.org/bot" + m_telegramToken + "/sendMessage";
   string params = "chat_id=" + m_telegramChatId + 
                   "&text=" + message + 
                   "&parse_mode=Markdown";

   char post[], result[];
   string headers = "Content-Type: application/x-www-form-urlencoded\r\n";
   StringToCharArray(params, post, 0, StringLen(params));

   int timeout = 5000;
   string resultHeaders;

   int res = WebRequest("POST", url, headers, timeout, post, result, resultHeaders);

   if(res == 200) {
      m_sentThisHour++;
      return true;
   }

   Print("خطا در ارسال تلگرام: ", res);
   return false;
}

//+------------------------------------------------------------------+
//| پخش صدای اعلان                                                      |
//+------------------------------------------------------------------+
void CNotificationManager::PlayNotificationSound(const ENUM_NOTIFICATION_TYPE type) {
   if(!m_soundEnabled) return;

   string sound = "";
   switch(type) {
      case NOTIFY_TRADE_OPEN:
      case NOTIFY_SIGNAL:
         sound = m_soundSignal;
         break;
      case NOTIFY_SL_HIT:
      case NOTIFY_EMERGENCY_STOP:
         sound = m_soundAlert;
         break;
      default:
         sound = m_soundTrade;
   }

   if(sound != "") PlaySound(sound);
}

//+------------------------------------------------------------------+
//| ارسال اعلان عمومی                                                   |
//+------------------------------------------------------------------+
bool CNotificationManager::Send(const Notification &notif) {
   if(!CanSendNotification()) return false;

   bool sent = false;
   string formattedMsg = FormatTelegramMessage(notif);

   // ارسال به تلگرام
   if(m_telegramEnabled) {
      sent = SendToTelegram(formattedMsg) || sent;
   }

   // ارسال Push Notification
   if(m_pushEnabled) {
      SendNotification(notif.message);
      sent = true;
   }

   // پخش صدا
   PlayNotificationSound(notif.type);

   // لاگ
   Print("📢 اعلان: [", GetPersianType(notif.type), "] ", notif.message);

   return sent;
}

//+------------------------------------------------------------------+
//| ارسال متن ساده                                                      |
//+------------------------------------------------------------------+
bool CNotificationManager::SendText(
   const ENUM_NOTIFICATION_TYPE type,
   const string message,
   const int priority
) {
   Notification notif;
   notif.type      = type;
   notif.message   = message;
   notif.timestamp = TimeCurrent();
   notif.priority  = priority;
   notif.symbol    = "";
   notif.price     = 0;
   notif.pnl       = 0;
   return Send(notif);
}

//+------------------------------------------------------------------+
//| هشدار ورود به معامله                                                |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifyTradeOpen(
   const ulong ticket,
   const ENUM_POSITION_TYPE direction,
   const string symbol,
   const double lot,
   const double entryPrice,
   const double stopLoss,
   const double takeProfit,
   const double riskAmount,
   const string strategy
) {
   Notification notif;
   notif.type      = NOTIFY_TRADE_OPEN;
   notif.timestamp = TimeCurrent();
   notif.symbol    = symbol;
   notif.price     = entryPrice;
   notif.priority  = 4;

   notif.title   = StringFormat("%s | معامله جدید", symbol);
   notif.message = StringFormat(
      "%s\n"
      "🎫 شناسه: #%d\n"
      "📦 حجم: %.2f لات\n"
      "💵 قیمت ورود: %s\n"
      "🛑 حد ضرر: %s\n"
      "🎯 حد سود: %s\n"
      "💸 ریسک: $%.2f",
      GetDirectionEmoji(direction),
      ticket, lot,
      FormatPrice(entryPrice),
      (stopLoss > 0) ? FormatPrice(stopLoss) : "ندارد",
      (takeProfit > 0) ? FormatPrice(takeProfit) : "ندارد",
      riskAmount
   );

   if(strategy != "") {
      notif.details = "📐 استراتژی: " + strategy;
   }

   return Send(notif);
}

//+------------------------------------------------------------------+
//| هشدار خروج از معامله                                                |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifyTradeClose(
   const ulong ticket,
   const ENUM_POSITION_TYPE direction,
   const string symbol,
   const double lot,
   const double openPrice,
   const double closePrice,
   const double pnl,
   const string reason
) {
   Notification notif;
   notif.type      = NOTIFY_TRADE_CLOSE;
   notif.timestamp = TimeCurrent();
   notif.symbol    = symbol;
   notif.price     = closePrice;
   notif.pnl       = pnl;
   notif.priority  = 4;

   string pnlEmoji = (pnl >= 0) ? "✅" : "❌";
   double pips = MathAbs(closePrice - openPrice) / SymbolInfoDouble(symbol, SYMBOL_POINT) / 10.0;

   notif.title   = StringFormat("%s | بسته شد", symbol);
   notif.message = StringFormat(
      "%s | %s\n"
      "🎫 شناسه: #%d\n"
      "📦 حجم: %.2f لات\n"
      "📥 قیمت ورود: %s\n"
      "📤 قیمت خروج: %s\n"
      "📏 پیپ: %.1f\n"
      "%s نتیجه: %s",
      GetDirectionEmoji(direction),
      (reason != "") ? reason : "دستی",
      ticket, lot,
      FormatPrice(openPrice),
      FormatPrice(closePrice),
      pips,
      pnlEmoji,
      FormatPnL(pnl)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| هشدار اصابت StopLoss                                               |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifySLHit(
   const ulong ticket,
   const string symbol,
   const double loss,
   const double slPrice
) {
   Notification notif;
   notif.type      = NOTIFY_SL_HIT;
   notif.timestamp = TimeCurrent();
   notif.symbol    = symbol;
   notif.price     = slPrice;
   notif.pnl       = -MathAbs(loss);
   notif.priority  = 5;

   notif.title   = StringFormat("❌ %s | حد ضرر فعال شد", symbol);
   notif.message = StringFormat(
      "🎫 شناسه: #%d\n"
      "🛑 قیمت SL: %s\n"
      "💸 ضرر: %s",
      ticket,
      FormatPrice(slPrice),
      FormatPnL(-MathAbs(loss))
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| هشدار اصابت TakeProfit                                             |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifyTPHit(
   const ulong ticket,
   const string symbol,
   const double profit,
   const double tpPrice
) {
   Notification notif;
   notif.type      = NOTIFY_TP_HIT;
   notif.timestamp = TimeCurrent();
   notif.symbol    = symbol;
   notif.price     = tpPrice;
   notif.pnl       = profit;
   notif.priority  = 5;

   notif.title   = StringFormat("💰 %s | حد سود فعال شد", symbol);
   notif.message = StringFormat(
      "🎫 شناسه: #%d\n"
      "🎯 قیمت TP: %s\n"
      "💰 سود: %s",
      ticket,
      FormatPrice(tpPrice),
      FormatPnL(profit)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| هشدار جابجایی StopLoss                                             |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifySLMoved(
   const ulong ticket,
   const string symbol,
   const double oldSL,
   const double newSL,
   const string reason
) {
   Notification notif;
   notif.type      = NOTIFY_SL_MOVED;
   notif.timestamp = TimeCurrent();
   notif.symbol    = symbol;
   notif.priority  = 2;

   notif.message = StringFormat(
      "🎫 #%d | %s\n"
      "📍 SL قبلی: %s\n"
      "📍 SL جدید: %s\n"
      "📝 دلیل: %s",
      ticket, symbol,
      FormatPrice(oldSL),
      FormatPrice(newSL),
      reason
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| هشدار فعال شدن Break Even                                          |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifyBreakEvenActivated(
   const ulong ticket,
   const string symbol,
   const double bePrice
) {
   Notification notif;
   notif.type      = NOTIFY_BE_ACTIVATED;
   notif.timestamp = TimeCurrent();
   notif.symbol    = symbol;
   notif.priority  = 3;

   notif.message = StringFormat(
      "🎫 #%d | %s\n"
      "🛡️ Break Even فعال شد\n"
      "📍 قیمت BE: %s",
      ticket, symbol,
      FormatPrice(bePrice)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| هشدار باز شدن سشن                                                  |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifySessionStart(
   const string sessionName,
   const string startTime,
   const string endTime
) {
   Notification notif;
   notif.type      = NOTIFY_SESSION_START;
   notif.timestamp = TimeCurrent();
   notif.priority  = 3;

   notif.title   = "🌅 سشن " + sessionName + " شروع شد";
   notif.message = StringFormat(
      "📍 سشن: %s\n"
      "🕐 شروع: %s\n"
      "🕐 پایان: %s\n"
      "📊 سیستم آماده معامله است",
      sessionName, startTime, endTime
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| هشدار بسته شدن سشن                                                 |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifySessionEnd(
   const string sessionName,
   const double sessionPnL,
   const int sessionTrades
) {
   Notification notif;
   notif.type      = NOTIFY_SESSION_END;
   notif.timestamp = TimeCurrent();
   notif.priority  = 3;

   notif.title   = "🌆 سشن " + sessionName + " پایان یافت";
   notif.message = StringFormat(
      "📍 سشن: %s\n"
      "📋 تعداد معاملات: %d\n"
      "💰 نتیجه سشن: %s",
      sessionName,
      sessionTrades,
      FormatPnL(sessionPnL)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| گزارش روزانه                                                        |
//+------------------------------------------------------------------+
bool CNotificationManager::SendDailyReport(
   const double balance,
   const double equity,
   const double dailyPnL,
   const double dailyPnLPct,
   const int totalTrades,
   const int winTrades,
   const int lossTrades,
   const double winRate,
   const double maxDrawdown
) {
   Notification notif;
   notif.type      = NOTIFY_DAILY_REPORT;
   notif.timestamp = TimeCurrent();
   notif.pnl       = dailyPnL;
   notif.priority  = 4;

   string pnlEmoji = (dailyPnL >= 0) ? "📈" : "📉";

   notif.title   = "📊 گزارش روزانه - " + TimeToString(TimeCurrent(), TIME_DATE);
   notif.message = StringFormat(
      "💰 موجودی: $%.2f\n"
      "📊 اکوئیتی: $%.2f\n"
      "\n"
      "%s نتیجه روز: %s (%.2f%%)\n"
      "\n"
      "📋 آمار معاملات:\n"
      "• کل معاملات: %d\n"
      "• برنده: %d | بازنده: %d\n"
      "• نرخ برنده: %.1f%%\n"
      "\n"
      "📉 حداکثر Drawdown: %.2f%%",
      balance, equity,
      pnlEmoji,
      FormatPnL(dailyPnL), dailyPnLPct,
      totalTrades, winTrades, lossTrades, winRate,
      maxDrawdown
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| گزارش هفتگی                                                         |
//+------------------------------------------------------------------+
bool CNotificationManager::SendWeeklyReport(
   const double weeklyPnL,
   const double weeklyPnLPct,
   const int totalTrades,
   const double winRate,
   const double bestDay,
   const double worstDay
) {
   Notification notif;
   notif.type      = NOTIFY_WEEKLY_REPORT;
   notif.timestamp = TimeCurrent();
   notif.pnl       = weeklyPnL;
   notif.priority  = 4;

   notif.title   = "📅 گزارش هفتگی";
   notif.message = StringFormat(
      "💰 نتیجه هفته: %s (%.2f%%)\n"
      "📋 کل معاملات: %d\n"
      "🏆 نرخ برنده: %.1f%%\n"
      "🌟 بهترین روز: %s\n"
      "💔 بدترین روز: %s",
      FormatPnL(weeklyPnL), weeklyPnLPct,
      totalTrades,
      winRate,
      FormatPnL(bestDay),
      FormatPnL(worstDay)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| گزارش ماهانه                                                        |
//+------------------------------------------------------------------+
bool CNotificationManager::SendMonthlyReport(
   const double monthlyPnL,
   const double monthlyPnLPct,
   const int totalTrades,
   const double winRate,
   const double profitFactor,
   const double maxDrawdown
) {
   Notification notif;
   notif.type      = NOTIFY_MONTHLY_REPORT;
   notif.timestamp = TimeCurrent();
   notif.pnl       = monthlyPnL;
   notif.priority  = 5;

   notif.title   = "📆 گزارش ماهانه";
   notif.message = StringFormat(
      "💰 نتیجه ماه: %s (%.2f%%)\n"
      "📋 کل معاملات: %d\n"
      "🏆 نرخ برنده: %.1f%%\n"
      "⚖️ Profit Factor: %.2f\n"
      "📉 Max Drawdown: %.2f%%",
      FormatPnL(monthlyPnL), monthlyPnLPct,
      totalTrades,
      winRate,
      profitFactor,
      maxDrawdown
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| هشدار ریسک                                                          |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifyRiskWarning(
   const string reason,
   const double currentValue,
   const double maxAllowed
) {
   Notification notif;
   notif.type      = NOTIFY_RISK_WARNING;
   notif.timestamp = TimeCurrent();
   notif.priority  = 5;

   notif.title   = "⚠️ هشدار ریسک";
   notif.message = StringFormat(
      "📌 دلیل: %s\n"
      "📊 مقدار فعلی: %.2f\n"
      "🔴 حداکثر مجاز: %.2f",
      reason, currentValue, maxAllowed
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| هشدار توقف اضطراری                                                  |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifyEmergencyStop(const string reason) {
   Notification notif;
   notif.type      = NOTIFY_EMERGENCY_STOP;
   notif.timestamp = TimeCurrent();
   notif.priority  = 5;

   notif.title   = "🚨 توقف اضطراری!";
   notif.message = StringFormat(
      "🛑 تمام فعالیت‌های معاملاتی متوقف شد\n"
      "📌 دلیل: %s\n"
      "⏰ زمان: %s",
      reason,
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| پردازش صف اعلان‌ها                                                  |
//+------------------------------------------------------------------+
void CNotificationManager::ProcessQueue() {
   if(m_queueSize <= 0) return;

   for(int i = 0; i < m_queueSize; i++) {
      if(CanSendNotification()) {
         Send(m_queue[i]);
      }
   }

   m_queueSize = 0;
   ArrayResize(m_queue, 0);
}
//+------------------------------------------------------------------+
