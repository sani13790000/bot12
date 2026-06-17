//+------------------------------------------------------------------+
//|                                              NotificationManager.mqh|
//|                                    MT5 Trading System              |
//|                                    مدیریت اعلان‌ها                 |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"

//+
// انواع اعلان
//+
enum ENUM_NOTIFICATION_TYPE {
   NOTIFY_SIGNAL,        // سیگنال جدید
   NOTIFY_TRADE_OPEN,    // باز شدن معامله
   NOTIFY_TRADE_CLOSE,   // بسته شدن معامله
   NOTIFY_SL_HIT,        // اصابت به حد ضرر
   NOTIFY_TP_HIT,        // اصابت به حد سود
   NOTIFY_SESSION_START, // شروع سشن
   NOTIFY_SESSION_END,   // پایان سشن
   NOTIFY_ERROR,         // خطا
   NOTIFY_WARNING,       // هشدار
   NOTIFY_INFO           // اطلاعات
};

//+
// ساختار اعلان
//+
struct Notification {
   ENUM_NOTIFICATION_TYPE type;
   string title;
   string message;
   string symbol;
   string details;
   datetime timestamp;
   int priority;
};

//+
// کلاس مدیریت اعلان‌ها
//+
class CNotificationManager {
private:
   string m_telegramToken;
   string m_telegramChatId;
   bool m_enabled;
   bool m_telegramEnabled;
   bool m_emailEnabled;
   bool m_pushEnabled;
   bool m_soundEnabled;

   // تنظیمات صدا
   string m_soundSignal;
   string m_soundTrade;
   string m_soundAlert;

   // محدودیت‌ها
   int m_maxNotificationsPerHour;
   int m_notificationCount;
   datetime m_lastResetTime;

   // صف اعلان‌ها
   Notification m_queue[];

   // توابع کمکی
   string FormatTelegramMessage(const Notification &notif);
   string GetEmoji(const ENUM_NOTIFICATION_TYPE type);
   string GetPersianType(const ENUM_NOTIFICATION_TYPE type);
   bool CanSendNotification();

public:
   CNotificationManager();
   ~CNotificationManager();

   // تنظیمات
   void SetTelegram(const string token, const string chatId);
   void EnableTelegram(const bool enable);
   void EnableEmail(const bool enable);
   void EnablePush(const bool enable);
   void EnableSound(const bool enable);
   void SetRateLimit(const int perHour);

   // ارسال اعلان
   bool SendNotification(const Notification &notif);
   bool SendSignalAlert(
      const string symbol,
      const string direction,
      const double entry,
      const double sl,
      const double tp,
      const int score
   );
   bool SendTradeAlert(
      const string symbol,
      const string direction,
      const double profit,
      const string status
   );
   bool SendSessionAlert(const string session, const bool isStart);
   bool SendErrorAlert(const string message);

   // مدیریت صف
   void ProcessQueue();
   void ClearQueue();
   int GetQueueSize();

   // وضعیت
   bool IsEnabled();
   void Enable(const bool enable);
};

//+
// سازنده
//+
CNotificationManager::CNotificationManager() {
   m_enabled = true;
   m_telegramEnabled = EnableTelegram;
   m_emailEnabled = false;
   m_pushEnabled = false;
   m_soundEnabled = true;

   m_soundSignal = "alert.wav";
   m_soundTrade = "ok.wav";
   m_soundAlert = "alert2.wav";

   m_maxNotificationsPerHour = 50;
   m_notificationCount = 0;
   m_lastResetTime = TimeCurrent();

   ArraySetAsSeries(m_queue, false);

   // خواندن تنظیمات
   m_telegramToken = "";
   m_telegramChatId = "";
}

//+
// مخرب
//+
CNotificationManager::~CNotificationManager() {
   ClearQueue();
}

//+
// تنظیم تلگرام
//+
void CNotificationManager::SetTelegram(const string token, const string chatId) {
   m_telegramToken = token;
   m_telegramChatId = chatId;
   LogMessage("تلگرام پیکربندی شد", "INFO");
}

//+
// فعال‌سازی تلگرام
//+
void CNotificationManager::EnableTelegram(const bool enable) {
   m_telegramEnabled = enable;
   LogMessage("تلگرام " + (enable ? "فعال" : "غیرفعال") + " شد", "INFO");
}

//+
// فعال‌سازی ایمیل
//+
void CNotificationManager::EnableEmail(const bool enable) {
   m_emailEnabled = enable;
}

//+
// فعال‌سازی Push
//+
void CNotificationManager::EnablePush(const bool enable) {
   m_pushEnabled = enable;
}

//+
// فعال‌سازی صدا
//+
void CNotificationManager::EnableSound(const bool enable) {
   m_soundEnabled = enable;
}

//+
// تنظیم محدودیت نرخ
//+
void CNotificationManager::SetRateLimit(const int perHour) {
   m_maxNotificationsPerHour = perHour;
}

//+
// بررسی امکان ارسال
//+
bool CNotificationManager::CanSendNotification() {
   datetime currentHour = TimeCurrent() - (TimeCurrent() % 3600);

   // ریست شمارنده
   if(currentHour > m_lastResetTime) {
      m_notificationCount = 0;
      m_lastResetTime = currentHour;
   }

   return m_notificationCount < m_maxNotificationsPerHour;
}

//+
// دریافت ایموجی
//+
string CNotificationManager::GetEmoji(const ENUM_NOTIFICATION_TYPE type) {
   switch(type) {
      case NOTIFY_SIGNAL:      return "🔔";
      case NOTIFY_TRADE_OPEN:  return "📈";
      case NOTIFY_TRADE_CLOSE: return "📉";
      case NOTIFY_SL_HIT:      return "🛑";
      case NOTIFY_TP_HIT:      return "🎯";
      case NOTIFY_SESSION_START: return "⏰";
      case NOTIFY_SESSION_END:   return "⏱";
      case NOTIFY_ERROR:       return "❌";
      case NOTIFY_WARNING:     return "⚠️";
      case NOTIFY_INFO:        return "ℹ️";
   }
   return "📌";
}

//+
// دریافت نام فارسی
//+
string CNotificationManager::GetPersianType(const ENUM_NOTIFICATION_TYPE type) {
   switch(type) {
      case NOTIFY_SIGNAL:      return "سیگنال";
      case NOTIFY_TRADE_OPEN:  return "معامله باز";
      case NOTIFY_TRADE_CLOSE: return "معامله بسته";
      case NOTIFY_SL_HIT:      return "حد ضرر";
      case NOTIFY_TP_HIT:      return "حد سود";
      case NOTIFY_SESSION_START: return "شروع سشن";
      case NOTIFY_SESSION_END:   return "پایان سشن";
      case NOTIFY_ERROR:       return "خطا";
      case NOTIFY_WARNING:     return "هشدار";
      case NOTIFY_INFO:        return "اطلاعات";
   }
   return "نامشخص";
}

//+
// فرمت پیام تلگرام
//+
string CNotificationManager::FormatTelegramMessage(const Notification &notif) {
   string emoji = GetEmoji(notif.type);
   string persianType = GetPersianType(notif.type);

   string message = StringFormat(
      "%s <b>%s</b>\n\n"
      "<b>%s</b>\n\n"
      "%s\n\n"
      "⏰ %s",
      emoji,
      persianType,
      notif.title,
      notif.message,
      TimeToString(notif.timestamp, TIME_DATE|TIME_MINUTES)
   );

   if(notif.symbol != "") {
      message += StringFormat("\n📊 نماد: %s", notif.symbol);
   }

   if(notif.details != "") {
      message += StringFormat("\n\n%s", notif.details);
   }

   return message;
}

//+
// ارسال اعلان
//+
bool CNotificationManager::SendNotification(const Notification &notif) {
   if(!m_enabled) return false;
   if(!CanSendNotification()) {
      LogMessage("محدودیت اعلان‌ها", "WARNING");
      return false;
   }

   m_notificationCount++;

   // پخش صدا
   if(m_soundEnabled) {
      string soundFile = "";
      switch(notif.type) {
         case NOTIFY_SIGNAL: soundFile = m_soundSignal; break;
         case NOTIFY_TRADE_OPEN:
         case NOTIFY_TP_HIT: soundFile = m_soundTrade; break;
         case NOTIFY_ERROR:
         case NOTIFY_SL_HIT: soundFile = m_soundAlert; break;
      }

      if(soundFile != "") {
         PlaySound(soundFile);
      }
   }

   // ارسال تلگرام
   if(m_telegramEnabled && m_telegramToken != "" && m_telegramChatId != "") {
      string message = FormatTelegramMessage(notif);

      // ارسال به API
      string body = StringFormat(
         "{\"chat_id\":\"%s\",\"text\":\"%s\",\"parse_mode\":\"HTML\"}",
         m_telegramChatId,
         message
      );

      // فراخوانی API تلگرام
      // ...

      LogMessage("اعلان به تلگرام ارسال شد: " + notif.title, "INFO");
   }

   // ارسال Push
   if(m_pushEnabled) {
      // MobilePushSend(notif.title, notif.message);
   }

   // ارسال ایمیل
   if(m_emailEnabled) {
      // SendMail(notif.title, notif.message);
   }

   // لاگ
   LogMessage(StringFormat("اعلان ارسال شد: %s | %s",
      GetPersianType(notif.type), notif.title), "NOTIFY");

   return true;
}

//+
// ارسال هشدار سیگنال
//+
bool CNotificationManager::SendSignalAlert(
   const string symbol,
   const string direction,
   const double entry,
   const double sl,
   const double tp,
   const int score
) {
   Notification notif;
   notif.type = NOTIFY_SIGNAL;
   notif.title = "سیگنال جدید";
   notif.symbol = symbol;
   notif.message = StringFormat(
      "جهت: %s\n"
      "امتیاز: %d/100\n\n"
      "📍 ورود: %.5f\n"
      "🛑 حد ضرر: %.5f\n"
      "🎯 حد سود: %.5f",
      direction == "buy" ? "خرید 🟢" : "فروش 🔴",
      score,
      entry, sl, tp
   );
   notif.timestamp = TimeCurrent();
   notif.priority = score >= 80 ? 1 : 2;

   return SendNotification(notif);
}

//+
// ارسال هشدار معامله
//+
bool CNotificationManager::SendTradeAlert(
   const string symbol,
   const string direction,
   const double profit,
   const string status
) {
   Notification notif;

   if(status == "open") {
      notif.type = NOTIFY_TRADE_OPEN;
      notif.title = "معامله باز شد";
   } else if(profit > 0) {
      notif.type = NOTIFY_TP_HIT;
      notif.title = "سود محقق شد";
   } else if(profit < 0) {
      notif.type = NOTIFY_SL_HIT;
      notif.title = "ضرر قطع شد";
   } else {
      notif.type = NOTIFY_TRADE_CLOSE;
      notif.title = "معامله بسته شد";
   }

   notif.symbol = symbol;
   notif.message = StringFormat(
      "جهت: %s\n"
      "سود/ضرر: $%.2f",
      direction == "buy" ? "خرید" : "فروش",
      profit
   );
   notif.timestamp = TimeCurrent();
   notif.priority = 1;

   return SendNotification(notif);
}

//+
// ارسال هشدار سشن
//+
bool CNotificationManager::SendSessionAlert(const string session, const bool isStart) {
   Notification notif;
   notif.type = isStart ? NOTIFY_SESSION_START : NOTIFY_SESSION_END;
   notif.title = StringFormat("سشن %s %s", session, isStart ? "شروع شد" : "به پایان رسید");
   notif.message = isStart ?
      StringFormat("سشن معاملاتی %s فعال شد.\nفرصت‌های معاملاتی در حال بررسی.", session) :
      StringFormat("سشن %s به پایان رسید.\nمعاملات فعال در حال بررسی.", session);
   notif.timestamp = TimeCurrent();
   notif.priority = 3;

   return SendNotification(notif);
}

//+
// ارسال هشدار خطا
//+
bool CNotificationManager::SendErrorAlert(const string message) {
   Notification notif;
   notif.type = NOTIFY_ERROR;
   notif.title = "خطای سیستمی";
   notif.message = message;
   notif.timestamp = TimeCurrent();
   notif.priority = 1;

   return SendNotification(notif);
}

//+
// پردازش صف
//+
void CNotificationManager::ProcessQueue() {
   if(ArraySize(m_queue) == 0) return;

   // پردازش حداکثر 5 اعلان
   int count = MathMin(5, ArraySize(m_queue));

   for(int i = 0; i < count; i++) {
      SendNotification(m_queue[0]);

      // حذف از صف
      for(int j = 0; j < ArraySize(m_queue) - 1; j++) {
         m_queue[j] = m_queue[j + 1];
      }
      ArrayResize(m_queue, ArraySize(m_queue) - 1);
   }
}

//+
// پاک کردن صف
//+
void CNotificationManager::ClearQueue() {
   ArrayResize(m_queue, 0);
}

//+
// دریافت اندازه صف
//+
int CNotificationManager::GetQueueSize() {
   return ArraySize(m_queue);
}

//+
// بررسی فعال بودن
//+
bool CNotificationManager::IsEnabled() {
   return m_enabled;
}

//+
// فعال‌سازی
//+
void CNotificationManager::Enable(const bool enable) {
   m_enabled = enable;
   LogMessage("سیستم اعلان‌ها " + (enable ? "فعال" : "غیرفعال") + " شد", "INFO");
}
//+------------------------------------------------------------------+
