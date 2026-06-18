//+------------------------------------------------------------------+
//|                                        NotificationManager.mqh     |
//|                         Ø³ÛØ³ØªÙ ÙØ¹Ø§ÙÙÙâÚ¯Ø±Û Ø­Ø±ÙÙâØ§Û MT5               |
//|                                                                    |
//| ØªÙØ¶ÛØ­ ÙØ§Ø±Ø³Û:                                                       |
//| Ø§ÛÙ ÙØ§ÛÙ ÙØ³Ø¦ÙÙ Ø§Ø±Ø³Ø§Ù ØªÙØ§Ù Ø§Ø¹ÙØ§ÙâÙØ§ Ù ÙØ´Ø¯Ø§Ø±ÙØ§Û Ø³ÛØ³ØªÙ Ø§Ø³Øª.           |
//| Ø§ÙÚ©Ø§ÙØ§Øª: ØªÙÚ¯Ø±Ø§ÙØ Ù¾ÙØ´ ÙÙØªÛÙÛÚ©ÛØ´ÙØ Ø§ÛÙÛÙØ ØµØ¯Ø§ Ù ÙÙØ§ÛØ´ Ø±ÙÛ ÚØ§Ø±Øª     |
//| ØªÙØ§Ù Ù¾ÛØ§ÙâÙØ§ Ø¨Ù ÙØ§Ø±Ø³Û ÙØ³ØªÙØ¯ Ø¨Ø§ ÙØ±ÙØªâØ¨ÙØ¯Û Ø­Ø±ÙÙâØ§Û                   |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"

//+------------------------------------------------------------------+
//| Ø§ÙÙØ§Ø¹ Ø§Ø¹ÙØ§Ù                                                         |
//+------------------------------------------------------------------+
enum ENUM_NOTIFICATION_TYPE {
   NOTIFY_SIGNAL,          // Ø³ÛÚ¯ÙØ§Ù Ø¬Ø¯ÛØ¯
   NOTIFY_TRADE_OPEN,      // Ø¨Ø§Ø² Ø´Ø¯Ù ÙØ¹Ø§ÙÙÙ
   NOTIFY_TRADE_CLOSE,     // Ø¨Ø³ØªÙ Ø´Ø¯Ù ÙØ¹Ø§ÙÙÙ
   NOTIFY_SL_HIT,          // Ø§ØµØ§Ø¨Øª Ø¨Ù Ø­Ø¯ Ø¶Ø±Ø±
   NOTIFY_TP_HIT,          // Ø§ØµØ§Ø¨Øª Ø¨Ù Ø­Ø¯ Ø³ÙØ¯
   NOTIFY_SL_MOVED,        // Ø¬Ø§Ø¨Ø¬Ø§ÛÛ StopLoss
   NOTIFY_BE_ACTIVATED,    // ÙØ¹Ø§Ù Ø´Ø¯Ù Break Even
   NOTIFY_TRAILING_UPDATE, // Ø¨ÙâØ±ÙØ²Ø±Ø³Ø§ÙÛ Trailing Stop
   NOTIFY_SESSION_START,   // Ø´Ø±ÙØ¹ Ø³Ø´Ù
   NOTIFY_SESSION_END,     // Ù¾Ø§ÛØ§Ù Ø³Ø´Ù
   NOTIFY_DAILY_REPORT,    // Ú¯Ø²Ø§Ø±Ø´ Ø±ÙØ²Ø§ÙÙ
   NOTIFY_WEEKLY_REPORT,   // Ú¯Ø²Ø§Ø±Ø´ ÙÙØªÚ¯Û
   NOTIFY_MONTHLY_REPORT,  // Ú¯Ø²Ø§Ø±Ø´ ÙØ§ÙØ§ÙÙ
   NOTIFY_RISK_WARNING,    // ÙØ´Ø¯Ø§Ø± Ø±ÛØ³Ú©
   NOTIFY_EMERGENCY_STOP,  // ØªÙÙÙ Ø§Ø¶Ø·Ø±Ø§Ø±Û
   NOTIFY_LICENSE_WARNING, // ÙØ´Ø¯Ø§Ø± ÙØ§ÛØ³ÙØ³
   NOTIFY_ERROR,           // Ø®Ø·Ø§
   NOTIFY_WARNING,         // ÙØ´Ø¯Ø§Ø±
   NOTIFY_INFO             // Ø§Ø·ÙØ§Ø¹Ø§Øª
};

//+------------------------------------------------------------------+
//| Ø³Ø§Ø®ØªØ§Ø± Ø§Ø¹ÙØ§Ù                                                        |
//+------------------------------------------------------------------+
struct Notification {
   ENUM_NOTIFICATION_TYPE type;  // ÙÙØ¹ Ø§Ø¹ÙØ§Ù
   string title;                  // Ø¹ÙÙØ§Ù
   string message;                // ÙØªÙ Ø§ØµÙÛ
   string symbol;                 // ÙÙØ§Ø¯
   string details;                // Ø¬Ø²Ø¦ÛØ§Øª Ø§Ø¶Ø§ÙÙ
   datetime timestamp;            // Ø²ÙØ§Ù
   int priority;                  // Ø§ÙÙÙÛØª (1-5)
   double price;                  // ÙÛÙØª ÙØ±ØªØ¨Ø·
   double pnl;                    // Ø³ÙØ¯/Ø¶Ø±Ø± ÙØ±ØªØ¨Ø·
};

//+------------------------------------------------------------------+
//| Ú©ÙØ§Ø³ ÙØ¯ÛØ±ÛØª Ø§Ø¹ÙØ§ÙâÙØ§                                                |
//+------------------------------------------------------------------+
class CNotificationManager {
private:
   // ØªÙØ¸ÛÙØ§Øª ØªÙÚ¯Ø±Ø§Ù
   string m_telegramToken;        // ØªÙÚ©Ù Ø±Ø¨Ø§Øª ØªÙÚ¯Ø±Ø§Ù
   string m_telegramChatId;       // Ø´ÙØ§Ø³Ù ÚØª
   bool m_telegramEnabled;        // ÙØ¶Ø¹ÛØª ØªÙÚ¯Ø±Ø§Ù

   // ØªÙØ¸ÛÙØ§Øª Ú©ÙÛ
   bool m_enabled;                // ÙØ¶Ø¹ÛØª Ú©ÙÛ
   bool m_emailEnabled;           // ÙØ¶Ø¹ÛØª Ø§ÛÙÛÙ
   bool m_pushEnabled;            // ÙØ¶Ø¹ÛØª Ù¾ÙØ´ ÙÙØªÛÙÛÚ©ÛØ´Ù
   bool m_soundEnabled;           // ÙØ¶Ø¹ÛØª ØµØ¯Ø§

   // ØªÙØ¸ÛÙØ§Øª ØµØ¯Ø§
   string m_soundSignal;          // ØµØ¯Ø§Û Ø³ÛÚ¯ÙØ§Ù
   string m_soundTrade;           // ØµØ¯Ø§Û ÙØ¹Ø§ÙÙÙ
   string m_soundAlert;           // ØµØ¯Ø§Û ÙØ´Ø¯Ø§Ø±

   // ÙØ­Ø¯ÙØ¯ÛØªâÙØ§Û Ø§Ø±Ø³Ø§Ù
   int m_maxPerHour;              // Ø­Ø¯Ø§Ú©Ø«Ø± Ø§Ø¹ÙØ§Ù Ø¯Ø± Ø³Ø§Ø¹Øª
   int m_sentThisHour;            // ØªØ¹Ø¯Ø§Ø¯ Ø§Ø±Ø³Ø§Ù Ø´Ø¯Ù
   datetime m_hourStart;          // Ø´Ø±ÙØ¹ Ø³Ø§Ø¹Øª ÙØ¹ÙÛ

   // ØµÙ Ø§Ø¹ÙØ§ÙâÙØ§
   Notification m_queue[];        // ØµÙ Ø§Ø¹ÙØ§ÙâÙØ§Û Ø¯Ø± Ø§ÙØªØ¸Ø§Ø±
   int m_queueSize;               // Ø§ÙØ¯Ø§Ø²Ù ØµÙ

   // ØªÙØ§Ø¨Ø¹ Ú©ÙÚ©Û Ø¯Ø§Ø®ÙÛ
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

   // ØªÙØ¸ÛÙØ§Øª
   void SetTelegramCredentials(const string token, const string chatId);
   void EnableTelegram(const bool enable);
   void EnableEmail(const bool enable);
   void EnablePush(const bool enable);
   void EnableSound(const bool enable);
   void SetMaxPerHour(const int max);

   // Ø§Ø±Ø³Ø§Ù Ø§Ø¹ÙØ§Ù Ø¹ÙÙÙÛ
   bool Send(const Notification &notif);
   bool SendText(const ENUM_NOTIFICATION_TYPE type, const string message, const int priority = 3);

   // ===== Ø§Ø¹ÙØ§ÙâÙØ§Û ÙØ¹Ø§ÙÙØ§ØªÛ =====

   // ÙØ´Ø¯Ø§Ø± ÙØ±ÙØ¯ Ø¨Ù ÙØ¹Ø§ÙÙÙ
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

   // ÙØ´Ø¯Ø§Ø± Ø®Ø±ÙØ¬ Ø§Ø² ÙØ¹Ø§ÙÙÙ
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

   // ÙØ´Ø¯Ø§Ø± Ø§ØµØ§Ø¨Øª StopLoss
   bool NotifySLHit(
      const ulong ticket,
      const string symbol,
      const double loss,
      const double slPrice
   );

   // ÙØ´Ø¯Ø§Ø± Ø§ØµØ§Ø¨Øª TakeProfit
   bool NotifyTPHit(
      const ulong ticket,
      const string symbol,
      const double profit,
      const double tpPrice
   );

   // ÙØ´Ø¯Ø§Ø± Ø¬Ø§Ø¨Ø¬Ø§ÛÛ SL
   bool NotifySLMoved(
      const ulong ticket,
      const string symbol,
      const double oldSL,
      const double newSL,
      const string reason = "Trailing Stop"
   );

   // ÙØ´Ø¯Ø§Ø± Break Even
   bool NotifyBreakEvenActivated(
      const ulong ticket,
      const string symbol,
      const double bePrice
   );

   // ===== Ø§Ø¹ÙØ§ÙâÙØ§Û Ø³Ø´Ù =====

   // ÙØ´Ø¯Ø§Ø± Ø¨Ø§Ø² Ø´Ø¯Ù Ø³Ø´Ù
   bool NotifySessionStart(
      const string sessionName,
      const string startTime,
      const string endTime
   );

   // ÙØ´Ø¯Ø§Ø± Ø¨Ø³ØªÙ Ø´Ø¯Ù Ø³Ø´Ù
   bool NotifySessionEnd(
      const string sessionName,
      const double sessionPnL,
      const int sessionTrades
   );

   // ===== Ú¯Ø²Ø§Ø±Ø´âÙØ§ =====

   // Ú¯Ø²Ø§Ø±Ø´ Ø±ÙØ²Ø§ÙÙ
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

   // Ú¯Ø²Ø§Ø±Ø´ ÙÙØªÚ¯Û
   bool SendWeeklyReport(
      const double weeklyPnL,
      const double weeklyPnLPct,
      const int totalTrades,
      const double winRate,
      const double bestDay,
      const double worstDay
   );

   // Ú¯Ø²Ø§Ø±Ø´ ÙØ§ÙØ§ÙÙ
   bool SendMonthlyReport(
      const double monthlyPnL,
      const double monthlyPnLPct,
      const int totalTrades,
      const double winRate,
      const double profitFactor,
      const double maxDrawdown
   );

   // ===== ÙØ´Ø¯Ø§Ø±ÙØ§Û Ø±ÛØ³Ú© =====

   // ÙØ´Ø¯Ø§Ø± Ø±ÛØ³Ú©
   bool NotifyRiskWarning(
      const string reason,
      const double currentValue,
      const double maxAllowed
   );

   // ÙØ´Ø¯Ø§Ø± ØªÙÙÙ Ø§Ø¶Ø·Ø±Ø§Ø±Û
   bool NotifyEmergencyStop(const string reason);

   // ===== ØªÙØ§Ø¨Ø¹ Ø¹ÙÙÙÛ =====
   bool IsEnabled() const { return m_enabled; }
   void SetEnabled(const bool enable) { m_enabled = enable; }
   int GetQueueSize() const { return m_queueSize; }
   void ProcessQueue();
};

//+------------------------------------------------------------------+
//| Ø³Ø§Ø²ÙØ¯Ù                                                             |
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
//| ÙØ®Ø±Ø¨                                                               |
//+------------------------------------------------------------------+
CNotificationManager::~CNotificationManager() {
   ArrayFree(m_queue);
}

//+------------------------------------------------------------------+
//| ØªÙØ¸ÛÙ Ø§Ø·ÙØ§Ø¹Ø§Øª ØªÙÚ¯Ø±Ø§Ù                                               |
//+------------------------------------------------------------------+
void CNotificationManager::SetTelegramCredentials(const string token, const string chatId) {
   m_telegramToken  = token;
   m_telegramChatId = chatId;
   m_telegramEnabled = (StringLen(token) > 10 && StringLen(chatId) > 0);
}

//+------------------------------------------------------------------+
//| ÙØ¹Ø§Ù/ØºÛØ±ÙØ¹Ø§Ù Ú©Ø±Ø¯Ù ØªÙÚ¯Ø±Ø§Ù                                           |
//+------------------------------------------------------------------+
void CNotificationManager::EnableTelegram(const bool enable) {
   m_telegramEnabled = enable && StringLen(m_telegramToken) > 10;
}

//+------------------------------------------------------------------+
//| ÙØ¹Ø§Ù/ØºÛØ±ÙØ¹Ø§Ù Ú©Ø±Ø¯Ù Ø§ÛÙÛÙ                                            |
//+------------------------------------------------------------------+
void CNotificationManager::EnableEmail(const bool enable) {
   m_emailEnabled = enable;
}

//+------------------------------------------------------------------+
//| ÙØ¹Ø§Ù/ØºÛØ±ÙØ¹Ø§Ù Ú©Ø±Ø¯Ù Ù¾ÙØ´                                              |
//+------------------------------------------------------------------+
void CNotificationManager::EnablePush(const bool enable) {
   m_pushEnabled = enable;
}

//+------------------------------------------------------------------+
//| ÙØ¹Ø§Ù/ØºÛØ±ÙØ¹Ø§Ù Ú©Ø±Ø¯Ù ØµØ¯Ø§                                              |
//+------------------------------------------------------------------+
void CNotificationManager::EnableSound(const bool enable) {
   m_soundEnabled = enable;
}

//+------------------------------------------------------------------+
//| ØªÙØ¸ÛÙ Ø­Ø¯Ø§Ú©Ø«Ø± Ø§Ø¹ÙØ§Ù Ø¯Ø± Ø³Ø§Ø¹Øª                                         |
//+------------------------------------------------------------------+
void CNotificationManager::SetMaxPerHour(const int max) {
   m_maxPerHour = MathMax(1, max);
}

//+------------------------------------------------------------------+
//| Ø¯Ø±ÛØ§ÙØª Ø§ÛÙÙØ¬Û ÙÙØ¹ Ø§Ø¹ÙØ§Ù                                             |
//+------------------------------------------------------------------+
string CNotificationManager::GetEmoji(const ENUM_NOTIFICATION_TYPE type) {
   switch(type) {
      case NOTIFY_SIGNAL:          return "ð¯";
      case NOTIFY_TRADE_OPEN:      return "â";
      case NOTIFY_TRADE_CLOSE:     return "ð";
      case NOTIFY_SL_HIT:          return "â";
      case NOTIFY_TP_HIT:          return "ð°";
      case NOTIFY_SL_MOVED:        return "ð";
      case NOTIFY_BE_ACTIVATED:    return "ð¡ï¸";
      case NOTIFY_TRAILING_UPDATE: return "ð";
      case NOTIFY_SESSION_START:   return "ð";
      case NOTIFY_SESSION_END:     return "ð";
      case NOTIFY_DAILY_REPORT:    return "ð";
      case NOTIFY_WEEKLY_REPORT:   return "ð";
      case NOTIFY_MONTHLY_REPORT:  return "ð";
      case NOTIFY_RISK_WARNING:    return "â ï¸";
      case NOTIFY_EMERGENCY_STOP:  return "ð¨";
      case NOTIFY_LICENSE_WARNING: return "ð";
      case NOTIFY_ERROR:           return "ð´";
      case NOTIFY_WARNING:         return "ð¡";
      case NOTIFY_INFO:            return "ðµ";
      default:                     return "ð¢";
   }
}

//+------------------------------------------------------------------+
//| Ø¯Ø±ÛØ§ÙØª ÙØ§Ù ÙØ§Ø±Ø³Û ÙÙØ¹ Ø§Ø¹ÙØ§Ù                                         |
//+------------------------------------------------------------------+
string CNotificationManager::GetPersianType(const ENUM_NOTIFICATION_TYPE type) {
   switch(type) {
      case NOTIFY_SIGNAL:          return "Ø³ÛÚ¯ÙØ§Ù Ø¬Ø¯ÛØ¯";
      case NOTIFY_TRADE_OPEN:      return "ÙØ±ÙØ¯ Ø¨Ù ÙØ¹Ø§ÙÙÙ";
      case NOTIFY_TRADE_CLOSE:     return "Ø®Ø±ÙØ¬ Ø§Ø² ÙØ¹Ø§ÙÙÙ";
      case NOTIFY_SL_HIT:          return "Ø§ØµØ§Ø¨Øª Ø¨Ù Ø­Ø¯ Ø¶Ø±Ø±";
      case NOTIFY_TP_HIT:          return "Ø§ØµØ§Ø¨Øª Ø¨Ù Ø­Ø¯ Ø³ÙØ¯";
      case NOTIFY_SL_MOVED:        return "Ø¬Ø§Ø¨Ø¬Ø§ÛÛ StopLoss";
      case NOTIFY_BE_ACTIVATED:    return "Break Even ÙØ¹Ø§Ù";
      case NOTIFY_TRAILING_UPDATE: return "Trailing Stop";
      case NOTIFY_SESSION_START:   return "Ø´Ø±ÙØ¹ Ø³Ø´Ù";
      case NOTIFY_SESSION_END:     return "Ù¾Ø§ÛØ§Ù Ø³Ø´Ù";
      case NOTIFY_DAILY_REPORT:    return "Ú¯Ø²Ø§Ø±Ø´ Ø±ÙØ²Ø§ÙÙ";
      case NOTIFY_WEEKLY_REPORT:   return "Ú¯Ø²Ø§Ø±Ø´ ÙÙØªÚ¯Û";
      case NOTIFY_MONTHLY_REPORT:  return "Ú¯Ø²Ø§Ø±Ø´ ÙØ§ÙØ§ÙÙ";
      case NOTIFY_RISK_WARNING:    return "ÙØ´Ø¯Ø§Ø± Ø±ÛØ³Ú©";
      case NOTIFY_EMERGENCY_STOP:  return "ØªÙÙÙ Ø§Ø¶Ø·Ø±Ø§Ø±Û";
      case NOTIFY_LICENSE_WARNING: return "ÙØ´Ø¯Ø§Ø± ÙØ§ÛØ³ÙØ³";
      case NOTIFY_ERROR:           return "Ø®Ø·Ø§";
      case NOTIFY_WARNING:         return "ÙØ´Ø¯Ø§Ø±";
      case NOTIFY_INFO:            return "Ø§Ø·ÙØ§Ø¹Ø§Øª";
      default:                     return "Ø§Ø¹ÙØ§Ù";
   }
}

//+------------------------------------------------------------------+
//| Ø¯Ø±ÛØ§ÙØª Ø³ØªØ§Ø±ÙâÙØ§Û Ø§ÙÙÙÛØª                                             |
//+------------------------------------------------------------------+
string CNotificationManager::GetPriorityStars(const int priority) {
   string stars = "";
   for(int i = 0; i < MathMin(priority, 5); i++) stars += "â­";
   return stars;
}

//+------------------------------------------------------------------+
//| Ø¨Ø±Ø±Ø³Û Ø§ÙÚ©Ø§Ù Ø§Ø±Ø³Ø§Ù                                                   |
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
//| Ø¨Ø§Ø²ÙØ´Ø§ÙÛ Ø´ÙØ§Ø±ÙØ¯Ù Ø³Ø§Ø¹ØªÛ                                             |
//+------------------------------------------------------------------+
void CNotificationManager::ResetHourlyCounter() {
   m_sentThisHour = 0;
   m_hourStart = TimeCurrent();
}

//+------------------------------------------------------------------+
//| ÙØ±ÙØªâØ¨ÙØ¯Û ÙÛÙØª                                                      |
//+------------------------------------------------------------------+
string CNotificationManager::FormatPrice(const double price) {
   return StringFormat("%.5f", price);
}

//+------------------------------------------------------------------+
//| ÙØ±ÙØªâØ¨ÙØ¯Û Ø³ÙØ¯/Ø¶Ø±Ø±                                                   |
//+------------------------------------------------------------------+
string CNotificationManager::FormatPnL(const double pnl) {
   if(pnl > 0) return StringFormat("+$%.2f", pnl);
   return StringFormat("-$%.2f", MathAbs(pnl));
}

//+------------------------------------------------------------------+
//| Ø§ÛÙÙØ¬Û Ø¬ÙØª ÙØ¹Ø§ÙÙÙ                                                   |
//+------------------------------------------------------------------+
string CNotificationManager::GetDirectionEmoji(const ENUM_POSITION_TYPE dir) {
   return (dir == POSITION_TYPE_BUY) ? "ð Ø®Ø±ÛØ¯" : "ð ÙØ±ÙØ´";
}

//+------------------------------------------------------------------+
//| ÙØ±ÙØªâØ¨ÙØ¯Û Ù¾ÛØ§Ù ØªÙÚ¯Ø±Ø§Ù                                               |
//+------------------------------------------------------------------+
string CNotificationManager::FormatTelegramMessage(const Notification &notif) {
   string msg = "";

   // ÙØ¯Ø±
   msg += GetEmoji(notif.type) + " *" + GetPersianType(notif.type) + "*";
   if(notif.priority >= 4) msg += "  " + GetPriorityStars(notif.priority);
   msg += "\n";
   msg += "ââââââââââââââââââââ\n";

   // Ù¾ÛØ§Ù Ø§ØµÙÛ
   if(notif.title != "") {
      msg += "ð " + notif.title + "\n";
   }
   msg += notif.message + "\n";

   // Ø¬Ø²Ø¦ÛØ§Øª
   if(notif.details != "") {
      msg += "\n" + notif.details + "\n";
   }

   // ÙÙØªØ±
   msg += "ââââââââââââââââââââ\n";
   msg += "ð " + TimeToString(notif.timestamp, TIME_DATE|TIME_MINUTES);
   if(notif.symbol != "") msg += " | " + notif.symbol;

   return msg;
}

//+------------------------------------------------------------------+
//| Ø§Ø±Ø³Ø§Ù Ø¨Ù ØªÙÚ¯Ø±Ø§Ù                                                     |
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

   LogMessage(StringFormat("خطا در ارسال تلگرام: %s", res), "ERROR");
   return false;
}

//+------------------------------------------------------------------+
//| Ù¾Ø®Ø´ ØµØ¯Ø§Û Ø§Ø¹ÙØ§Ù                                                      |
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
//| Ø§Ø±Ø³Ø§Ù Ø§Ø¹ÙØ§Ù Ø¹ÙÙÙÛ                                                   |
//+------------------------------------------------------------------+
bool CNotificationManager::Send(const Notification &notif) {
   if(!CanSendNotification()) return false;

   bool sent = false;
   string formattedMsg = FormatTelegramMessage(notif);

   // Ø§Ø±Ø³Ø§Ù Ø¨Ù ØªÙÚ¯Ø±Ø§Ù
   if(m_telegramEnabled) {
      sent = SendToTelegram(formattedMsg) || sent;
   }

   // Ø§Ø±Ø³Ø§Ù Push Notification
   if(m_pushEnabled) {
      SendNotification(notif.message);
      sent = true;
   }

   // Ù¾Ø®Ø´ ØµØ¯Ø§
   PlayNotificationSound(notif.type);

   // ÙØ§Ú¯
   LogMessage(StringFormat("📢 اعلان: [%s] %s", GetPersianType(notif.type), notif.message), "INFO");

   return sent;
}

//+------------------------------------------------------------------+
//| Ø§Ø±Ø³Ø§Ù ÙØªÙ Ø³Ø§Ø¯Ù                                                      |
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
//| ÙØ´Ø¯Ø§Ø± ÙØ±ÙØ¯ Ø¨Ù ÙØ¹Ø§ÙÙÙ                                                |
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

   notif.title   = StringFormat("%s | ÙØ¹Ø§ÙÙÙ Ø¬Ø¯ÛØ¯", symbol);
   notif.message = StringFormat(
      "%s\n"
      "ð« Ø´ÙØ§Ø³Ù: #%d\n"
      "ð¦ Ø­Ø¬Ù: %.2f ÙØ§Øª\n"
      "ðµ ÙÛÙØª ÙØ±ÙØ¯: %s\n"
      "ð Ø­Ø¯ Ø¶Ø±Ø±: %s\n"
      "ð¯ Ø­Ø¯ Ø³ÙØ¯: %s\n"
      "ð¸ Ø±ÛØ³Ú©: $%.2f",
      GetDirectionEmoji(direction),
      ticket, lot,
      FormatPrice(entryPrice),
      (stopLoss > 0) ? FormatPrice(stopLoss) : "ÙØ¯Ø§Ø±Ø¯",
      (takeProfit > 0) ? FormatPrice(takeProfit) : "ÙØ¯Ø§Ø±Ø¯",
      riskAmount
   );

   if(strategy != "") {
      notif.details = "ð Ø§Ø³ØªØ±Ø§ØªÚÛ: " + strategy;
   }

   return Send(notif);
}

//+------------------------------------------------------------------+
//| ÙØ´Ø¯Ø§Ø± Ø®Ø±ÙØ¬ Ø§Ø² ÙØ¹Ø§ÙÙÙ                                                |
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

   string pnlEmoji = (pnl >= 0) ? "â" : "â";
   double pips = MathAbs(closePrice - openPrice) / SymbolInfoDouble(symbol, SYMBOL_POINT) / 10.0;

   notif.title   = StringFormat("%s | Ø¨Ø³ØªÙ Ø´Ø¯", symbol);
   notif.message = StringFormat(
      "%s | %s\n"
      "ð« Ø´ÙØ§Ø³Ù: #%d\n"
      "ð¦ Ø­Ø¬Ù: %.2f ÙØ§Øª\n"
      "ð¥ ÙÛÙØª ÙØ±ÙØ¯: %s\n"
      "ð¤ ÙÛÙØª Ø®Ø±ÙØ¬: %s\n"
      "ð Ù¾ÛÙ¾: %.1f\n"
      "%s ÙØªÛØ¬Ù: %s",
      GetDirectionEmoji(direction),
      (reason != "") ? reason : "Ø¯Ø³ØªÛ",
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
//| ÙØ´Ø¯Ø§Ø± Ø§ØµØ§Ø¨Øª StopLoss                                               |
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

   notif.title   = StringFormat("â %s | Ø­Ø¯ Ø¶Ø±Ø± ÙØ¹Ø§Ù Ø´Ø¯", symbol);
   notif.message = StringFormat(
      "ð« Ø´ÙØ§Ø³Ù: #%d\n"
      "ð ÙÛÙØª SL: %s\n"
      "ð¸ Ø¶Ø±Ø±: %s",
      ticket,
      FormatPrice(slPrice),
      FormatPnL(-MathAbs(loss))
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| ÙØ´Ø¯Ø§Ø± Ø§ØµØ§Ø¨Øª TakeProfit                                             |
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

   notif.title   = StringFormat("ð° %s | Ø­Ø¯ Ø³ÙØ¯ ÙØ¹Ø§Ù Ø´Ø¯", symbol);
   notif.message = StringFormat(
      "ð« Ø´ÙØ§Ø³Ù: #%d\n"
      "ð¯ ÙÛÙØª TP: %s\n"
      "ð° Ø³ÙØ¯: %s",
      ticket,
      FormatPrice(tpPrice),
      FormatPnL(profit)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| ÙØ´Ø¯Ø§Ø± Ø¬Ø§Ø¨Ø¬Ø§ÛÛ StopLoss                                             |
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
      "ð« #%d | %s\n"
      "ð SL ÙØ¨ÙÛ: %s\n"
      "ð SL Ø¬Ø¯ÛØ¯: %s\n"
      "ð Ø¯ÙÛÙ: %s",
      ticket, symbol,
      FormatPrice(oldSL),
      FormatPrice(newSL),
      reason
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| ÙØ´Ø¯Ø§Ø± ÙØ¹Ø§Ù Ø´Ø¯Ù Break Even                                          |
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
      "ð« #%d | %s\n"
      "ð¡ï¸ Break Even ÙØ¹Ø§Ù Ø´Ø¯\n"
      "ð ÙÛÙØª BE: %s",
      ticket, symbol,
      FormatPrice(bePrice)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| ÙØ´Ø¯Ø§Ø± Ø¨Ø§Ø² Ø´Ø¯Ù Ø³Ø´Ù                                                  |
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

   notif.title   = "ð Ø³Ø´Ù " + sessionName + " Ø´Ø±ÙØ¹ Ø´Ø¯";
   notif.message = StringFormat(
      "ð Ø³Ø´Ù: %s\n"
      "ð Ø´Ø±ÙØ¹: %s\n"
      "ð Ù¾Ø§ÛØ§Ù: %s\n"
      "ð Ø³ÛØ³ØªÙ Ø¢ÙØ§Ø¯Ù ÙØ¹Ø§ÙÙÙ Ø§Ø³Øª",
      sessionName, startTime, endTime
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| ÙØ´Ø¯Ø§Ø± Ø¨Ø³ØªÙ Ø´Ø¯Ù Ø³Ø´Ù                                                 |
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

   notif.title   = "ð Ø³Ø´Ù " + sessionName + " Ù¾Ø§ÛØ§Ù ÛØ§ÙØª";
   notif.message = StringFormat(
      "ð Ø³Ø´Ù: %s\n"
      "ð ØªØ¹Ø¯Ø§Ø¯ ÙØ¹Ø§ÙÙØ§Øª: %d\n"
      "ð° ÙØªÛØ¬Ù Ø³Ø´Ù: %s",
      sessionName,
      sessionTrades,
      FormatPnL(sessionPnL)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| Ú¯Ø²Ø§Ø±Ø´ Ø±ÙØ²Ø§ÙÙ                                                        |
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

   string pnlEmoji = (dailyPnL >= 0) ? "ð" : "ð";

   notif.title   = "ð Ú¯Ø²Ø§Ø±Ø´ Ø±ÙØ²Ø§ÙÙ - " + TimeToString(TimeCurrent(), TIME_DATE);
   notif.message = StringFormat(
      "ð° ÙÙØ¬ÙØ¯Û: $%.2f\n"
      "ð Ø§Ú©ÙØ¦ÛØªÛ: $%.2f\n"
      "\n"
      "%s ÙØªÛØ¬Ù Ø±ÙØ²: %s (%.2f%%)\n"
      "\n"
      "ð Ø¢ÙØ§Ø± ÙØ¹Ø§ÙÙØ§Øª:\n"
      "â¢ Ú©Ù ÙØ¹Ø§ÙÙØ§Øª: %d\n"
      "â¢ Ø¨Ø±ÙØ¯Ù: %d | Ø¨Ø§Ø²ÙØ¯Ù: %d\n"
      "â¢ ÙØ±Ø® Ø¨Ø±ÙØ¯Ù: %.1f%%\n"
      "\n"
      "ð Ø­Ø¯Ø§Ú©Ø«Ø± Drawdown: %.2f%%",
      balance, equity,
      pnlEmoji,
      FormatPnL(dailyPnL), dailyPnLPct,
      totalTrades, winTrades, lossTrades, winRate,
      maxDrawdown
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| Ú¯Ø²Ø§Ø±Ø´ ÙÙØªÚ¯Û                                                         |
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

   notif.title   = "ð Ú¯Ø²Ø§Ø±Ø´ ÙÙØªÚ¯Û";
   notif.message = StringFormat(
      "ð° ÙØªÛØ¬Ù ÙÙØªÙ: %s (%.2f%%)\n"
      "ð Ú©Ù ÙØ¹Ø§ÙÙØ§Øª: %d\n"
      "ð ÙØ±Ø® Ø¨Ø±ÙØ¯Ù: %.1f%%\n"
      "ð Ø¨ÙØªØ±ÛÙ Ø±ÙØ²: %s\n"
      "ð Ø¨Ø¯ØªØ±ÛÙ Ø±ÙØ²: %s",
      FormatPnL(weeklyPnL), weeklyPnLPct,
      totalTrades,
      winRate,
      FormatPnL(bestDay),
      FormatPnL(worstDay)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| Ú¯Ø²Ø§Ø±Ø´ ÙØ§ÙØ§ÙÙ                                                        |
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

   notif.title   = "ð Ú¯Ø²Ø§Ø±Ø´ ÙØ§ÙØ§ÙÙ";
   notif.message = StringFormat(
      "ð° ÙØªÛØ¬Ù ÙØ§Ù: %s (%.2f%%)\n"
      "ð Ú©Ù ÙØ¹Ø§ÙÙØ§Øª: %d\n"
      "ð ÙØ±Ø® Ø¨Ø±ÙØ¯Ù: %.1f%%\n"
      "âï¸ Profit Factor: %.2f\n"
      "ð Max Drawdown: %.2f%%",
      FormatPnL(monthlyPnL), monthlyPnLPct,
      totalTrades,
      winRate,
      profitFactor,
      maxDrawdown
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| ÙØ´Ø¯Ø§Ø± Ø±ÛØ³Ú©                                                          |
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

   notif.title   = "â ï¸ ÙØ´Ø¯Ø§Ø± Ø±ÛØ³Ú©";
   notif.message = StringFormat(
      "ð Ø¯ÙÛÙ: %s\n"
      "ð ÙÙØ¯Ø§Ø± ÙØ¹ÙÛ: %.2f\n"
      "ð´ Ø­Ø¯Ø§Ú©Ø«Ø± ÙØ¬Ø§Ø²: %.2f",
      reason, currentValue, maxAllowed
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| ÙØ´Ø¯Ø§Ø± ØªÙÙÙ Ø§Ø¶Ø·Ø±Ø§Ø±Û                                                  |
//+------------------------------------------------------------------+
bool CNotificationManager::NotifyEmergencyStop(const string reason) {
   Notification notif;
   notif.type      = NOTIFY_EMERGENCY_STOP;
   notif.timestamp = TimeCurrent();
   notif.priority  = 5;

   notif.title   = "ð¨ ØªÙÙÙ Ø§Ø¶Ø·Ø±Ø§Ø±Û!";
   notif.message = StringFormat(
      "ð ØªÙØ§Ù ÙØ¹Ø§ÙÛØªâÙØ§Û ÙØ¹Ø§ÙÙØ§ØªÛ ÙØªÙÙÙ Ø´Ø¯\n"
      "ð Ø¯ÙÛÙ: %s\n"
      "â° Ø²ÙØ§Ù: %s",
      reason,
      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)
   );

   return Send(notif);
}

//+------------------------------------------------------------------+
//| Ù¾Ø±Ø¯Ø§Ø²Ø´ ØµÙ Ø§Ø¹ÙØ§ÙâÙØ§                                                  |
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
