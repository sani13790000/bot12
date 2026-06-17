
//+------------------------------------------------------------------+
//|                                          SessionManager.mqh      |
//|                                                                  |
//|  توضیح: مدیریت سشن‌های بازار و Kill Zones برای پروژه Bot12    |
//|                                                                  |
//|  این ماژول سشن‌های معاملاتی را مدیریت می‌کند:                 |
//|  - Sydney: 22:00 - 07:00 UTC                                   |
//|  - Tokyo: 00:00 - 09:00 UTC                                    |
//|  - London: 07:00 - 16:00 UTC                                   |
//|  - New York: 12:00 - 21:00 UTC                                 |
//|  - London/NY Overlap: 12:00 - 16:00 UTC (بهترین سشن)          |
//|                                                                  |
//|  Kill Zones ICT:                                                |
//|  - Asian KZ: 20:00 - 00:00 UTC                                 |
//|  - London KZ: 07:00 - 09:00 UTC (London Open)                  |
//|  - NY AM KZ: 12:00 - 14:00 UTC (NY Open)                       |
//|  - NY PM KZ: 17:00 - 18:00 UTC (NY PM Session)                 |
//+------------------------------------------------------------------+

#ifndef SESSION_MANAGER_MQH
#define SESSION_MANAGER_MQH

//--- انواع سشن
enum ENUM_TRADING_SESSION {
   SESSION_NONE    = 0,
   SESSION_SYDNEY  = 1,
   SESSION_TOKYO   = 2,
   SESSION_LONDON  = 4,
   SESSION_NEWYORK = 8,
   SESSION_OVERLAP = 16   // London + NY
};

//--- انواع Kill Zone
enum ENUM_KILL_ZONE {
   KZ_NONE        = 0,
   KZ_ASIAN       = 1,
   KZ_LONDON_OPEN = 2,
   KZ_NY_OPEN     = 4,
   KZ_NY_PM       = 8,
   KZ_LONDON_CLOSE = 16
};

//--- ساختار اطلاعات سشن
struct SessionInfo {
   ENUM_TRADING_SESSION  active_session;    // سشن فعال
   ENUM_KILL_ZONE        active_kill_zone;  // Kill Zone فعال
   bool                  is_overlap;        // آیا در Overlap هستیم؟
   bool                  is_kill_zone;      // آیا در Kill Zone هستیم؟
   bool                  can_trade;         // آیا می‌توان معامله کرد؟
   string                session_name;      // نام سشن
   string                kill_zone_name;    // نام Kill Zone
   int                   minutes_to_next;   // دقیقه تا شروع سشن بعدی
   double                session_score;     // امتیاز سشن (برای Decision Engine)
};

//+------------------------------------------------------------------+
//| مدیریت سشن‌های بازار                                            |
//+------------------------------------------------------------------+
class CSessionManager
{
private:
   bool     m_use_sydney;     // آیا Sydney فعال است؟
   bool     m_use_tokyo;      // آیا Tokyo فعال است؟
   bool     m_use_london;     // آیا London فعال است؟
   bool     m_use_newyork;    // آیا New York فعال است؟
   bool     m_prefer_overlap; // آیا فقط در Overlap معامله شود؟
   bool     m_only_kill_zones; // آیا فقط در Kill Zones معامله شود؟

   // تبدیل GMT به ساعت UTC
   int GetUTCHour() {
      MqlDateTime dt;
      TimeToStruct(TimeGMT(), dt);
      return dt.hour;
   }

   int GetUTCMinute() {
      MqlDateTime dt;
      TimeToStruct(TimeGMT(), dt);
      return dt.min;
   }

   // محاسبه دقیقه روز (از ابتدای روز UTC)
   int GetUTCMinuteOfDay() {
      return GetUTCHour() * 60 + GetUTCMinute();
   }

   // بررسی اینکه آیا دقیقه جاری در بازه است
   bool IsInTimeRange(const int start_hour, const int start_min, 
                      const int end_hour, const int end_min) {
      int current = GetUTCMinuteOfDay();
      int start   = start_hour * 60 + start_min;
      int end_t   = end_hour * 60 + end_min;

      if(start <= end_t) {
         return (current >= start && current < end_t);
      } else {
         // برای بازه‌های midnight-crossing (مثل Sydney)
         return (current >= start || current < end_t);
      }
   }

public:
   CSessionManager() {
      m_use_sydney     = false;
      m_use_tokyo      = true;
      m_use_london     = true;
      m_use_newyork    = true;
      m_prefer_overlap = false;
      m_only_kill_zones = false;
   }

   //--- تنظیم سشن‌های فعال
   void SetActiveSessions(
      const bool sydney,
      const bool tokyo,
      const bool london,
      const bool newyork,
      const bool prefer_overlap = false,
      const bool only_kill_zones = false
   ) {
      m_use_sydney      = sydney;
      m_use_tokyo       = tokyo;
      m_use_london      = london;
      m_use_newyork     = newyork;
      m_prefer_overlap  = prefer_overlap;
      m_only_kill_zones = only_kill_zones;
   }

   //+----------------------------------------------------------------+
   //| بررسی سشن فعال جاری                                           |
   //+----------------------------------------------------------------+
   SessionInfo GetCurrentSession() {
      SessionInfo info;
      info.active_session   = SESSION_NONE;
      info.active_kill_zone = KZ_NONE;
      info.is_overlap       = false;
      info.is_kill_zone     = false;
      info.can_trade        = false;
      info.session_score    = 0.0;
      info.minutes_to_next  = 0;

      // --- بررسی سشن‌ها ---
      bool in_sydney  = IsInTimeRange(22, 0, 7, 0);
      bool in_tokyo   = IsInTimeRange(0, 0, 9, 0);
      bool in_london  = IsInTimeRange(7, 0, 16, 0);
      bool in_newyork = IsInTimeRange(12, 0, 21, 0);
      bool in_overlap = IsInTimeRange(12, 0, 16, 0); // London + NY

      // --- بررسی Kill Zones ---
      bool in_kz_asian       = IsInTimeRange(20, 0, 0, 0);
      bool in_kz_london_open = IsInTimeRange(7, 0, 9, 0);
      bool in_kz_ny_open     = IsInTimeRange(12, 0, 14, 0);
      bool in_kz_ny_pm       = IsInTimeRange(17, 0, 18, 0);
      bool in_kz_london_close = IsInTimeRange(15, 0, 16, 0);

      // --- تعیین سشن فعال ---
      int session_flags = 0;
      if(in_sydney  && m_use_sydney)  session_flags |= SESSION_SYDNEY;
      if(in_tokyo   && m_use_tokyo)   session_flags |= SESSION_TOKYO;
      if(in_london  && m_use_london)  session_flags |= SESSION_LONDON;
      if(in_newyork && m_use_newyork) session_flags |= SESSION_NEWYORK;
      if(in_overlap) session_flags |= SESSION_OVERLAP;

      info.active_session = (ENUM_TRADING_SESSION)session_flags;
      info.is_overlap = in_overlap;

      // --- تعیین Kill Zone فعال ---
      int kz_flags = 0;
      if(in_kz_asian)        kz_flags |= KZ_ASIAN;
      if(in_kz_london_open)  kz_flags |= KZ_LONDON_OPEN;
      if(in_kz_ny_open)      kz_flags |= KZ_NY_OPEN;
      if(in_kz_ny_pm)        kz_flags |= KZ_NY_PM;
      if(in_kz_london_close) kz_flags |= KZ_LONDON_CLOSE;

      info.active_kill_zone = (ENUM_KILL_ZONE)kz_flags;
      info.is_kill_zone = (kz_flags != 0);

      // --- نام سشن ---
      if(in_overlap)
         info.session_name = "London/NY Overlap ⭐⭐⭐";
      else if(in_london)
         info.session_name = "London Session ⭐⭐";
      else if(in_newyork)
         info.session_name = "New York Session ⭐⭐";
      else if(in_tokyo)
         info.session_name = "Tokyo Session ⭐";
      else if(in_sydney)
         info.session_name = "Sydney Session";
      else
         info.session_name = "خارج از سشن معاملاتی";

      // --- نام Kill Zone ---
      if(in_kz_london_open)
         info.kill_zone_name = "London Open Kill Zone 🎯";
      else if(in_kz_ny_open)
         info.kill_zone_name = "NY Open Kill Zone 🎯";
      else if(in_kz_ny_pm)
         info.kill_zone_name = "NY PM Kill Zone 🎯";
      else if(in_kz_london_close)
         info.kill_zone_name = "London Close Kill Zone";
      else if(in_kz_asian)
         info.kill_zone_name = "Asian Kill Zone";
      else
         info.kill_zone_name = "خارج از Kill Zone";

      // --- محاسبه امتیاز سشن (برای Decision Engine) ---
      if(in_kz_london_open || in_kz_ny_open)
         info.session_score = 100.0;     // بهترین زمان
      else if(in_overlap)
         info.session_score = 90.0;      // Overlap خیلی خوب
      else if(in_kz_ny_pm)
         info.session_score = 75.0;      // NY PM خوب
      else if(in_london)
         info.session_score = 70.0;      // London خوب
      else if(in_newyork)
         info.session_score = 65.0;      // NY معقول
      else if(in_kz_asian)
         info.session_score = 50.0;      // Asian متوسط
      else if(in_tokyo)
         info.session_score = 40.0;      // Tokyo ضعیف
      else if(in_sydney)
         info.session_score = 25.0;      // Sydney ضعیف
      else
         info.session_score = 0.0;       // خارج از سشن

      // --- تعیین قابلیت معامله ---
      if(m_only_kill_zones) {
         info.can_trade = info.is_kill_zone;
      } else if(m_prefer_overlap) {
         info.can_trade = info.is_overlap || info.is_kill_zone;
      } else {
         // در هر سشن فعال شده می‌توان معامله کرد
         info.can_trade = (session_flags != 0);
      }

      return info;
   }

   //+----------------------------------------------------------------+
   //| بررسی ساده: آیا الان می‌توان معامله کرد؟                     |
   //+----------------------------------------------------------------+
   bool CanTradeNow() {
      SessionInfo info = GetCurrentSession();
      return info.can_trade;
   }

   //+----------------------------------------------------------------+
   //| بررسی ساده: آیا در Kill Zone هستیم؟                          |
   //+----------------------------------------------------------------+
   bool IsInKillZone() {
      SessionInfo info = GetCurrentSession();
      return info.is_kill_zone;
   }

   //+----------------------------------------------------------------+
   //| دریافت امتیاز سشن برای Decision Engine                        |
   //+----------------------------------------------------------------+
   double GetSessionScore() {
      SessionInfo info = GetCurrentSession();
      return info.session_score;
   }

   //+----------------------------------------------------------------+
   //| گزارش وضعیت سشن جاری                                         |
   //+----------------------------------------------------------------+
   string GetSessionReport() {
      SessionInfo info = GetCurrentSession();
      MqlDateTime dt;
      TimeToStruct(TimeGMT(), dt);

      return StringFormat(
         "🕐 سشن جاری: %s\n"
         "🎯 Kill Zone: %s\n"
         "⏰ زمان UTC: %02d:%02d\n"
         "📊 امتیاز سشن: %.0f/100\n"
         "✅ قابل معامله: %s",
         info.session_name,
         info.kill_zone_name,
         dt.hour, dt.min,
         info.session_score,
         info.can_trade ? "بله" : "خیر"
      );
   }
};

#endif // SESSION_MANAGER_MQH
