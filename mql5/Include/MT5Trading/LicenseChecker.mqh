//+------------------------------------------------------------------+
//|                                              LicenseChecker.mqh     |
//|                                    MT5 Trading System              |
//|                                    بررسی‌گر لایسنس                 |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"

//+
// انواع لایسنس
//+
enum ENUM_LICENSE_TYPE {
   LICENSE_TRIAL,
   LICENSE_BASIC,
   LICENSE_PRO,
   LICENSE_ENTERPRISE,
   LICENSE_LIFETIME
};

//+
// ویژگی‌های لایسنس
//+
enum ENUM_LICENSE_FEATURE {
   FEATURE_SMC,
   FEATURE_PA,
   FEATURE_MTF,
   FEATURE_AUTO_TRADE,
   FEATURE_TELEGRAM,
   FEATURE_DASHBOARD
};

//+
// ساختار لایسنس
//+
struct LicenseInfo {
   string key;
   ENUM_LICENSE_TYPE type;
   datetime expiresAt;
   bool isValid;
   int devicesLimit;
   int devicesUsed;
   string features[];
};

//+
// کلاس بررسی لایسنس
//+
class CLicenseChecker {
private:
   string m_licenseKey;
   string m_deviceId;
   LicenseInfo m_info;

   // وضعیت
   bool m_verified;
   datetime m_lastCheck;
   datetime m_nextCheck;

   // تنظیمات API
   string m_apiUrl;
   int m_checkInterval;  // ساعت

   // توابع کمکی
   string GenerateDeviceId();
   bool ParseLicenseData(const string data);
   bool IsExpired();
   bool HasFeatureLocal(const ENUM_LICENSE_FEATURE feature);

public:
   CLicenseChecker();
   ~CLicenseChecker();

   // تنظیمات
   void SetLicenseKey(const string key);
   void SetApiUrl(const string url);
   void SetCheckInterval(const int hours);

   // اعتبارسنجی
   bool Verify();
   bool VerifyOnline();
   bool VerifyOffline();
   bool Revoke();

   // بررسی
   bool IsValid();
   bool IsExpiredStatus();
   bool HasFeature(const ENUM_LICENSE_FEATURE feature);
   int GetDaysRemaining();

   // اطلاعات
   LicenseInfo GetInfo();
   string GetTypeString();
   ENUM_LICENSE_TYPE GetType();

   // دستگاه
   bool ActivateDevice();
   bool DeactivateDevice();
   int GetDevicesLimit();
   int GetDevicesUsed();

   // گزارش
   string GetLicenseReport();
};

//+
// سازنده
//+
CLicenseChecker::CLicenseChecker() {
   m_licenseKey = "";
   m_deviceId = "";
   m_verified = false;
   m_lastCheck = 0;
   m_nextCheck = 0;
   m_checkInterval = 24;  // هر 24 ساعت

   m_apiUrl = ApiBaseUrl + "/license";

   // مقداردهی اولیه info
   m_info.key = "";
   m_info.type = LICENSE_TRIAL;
   m_info.expiresAt = D'1970.01.01';
   m_info.isValid = false;
   m_info.devicesLimit = 1;
   m_info.devicesUsed = 0;
}

//+
// مخرب
//+
CLicenseChecker::~CLicenseChecker() {
}

//+
// تنظیم کلید لایسنس
//+
void CLicenseChecker::SetLicenseKey(const string key) {
   m_licenseKey = key;
   m_verified = false;
}

//+
// تنظیم آدرس API
//+
void CLicenseChecker::SetApiUrl(const string url) {
   m_apiUrl = url;
}

//+
// تنظیم فاصله بررسی
//+
void CLicenseChecker::SetCheckInterval(const int hours) {
   m_checkInterval = MathMax(1, hours);
}

//+
// تولید شناسه دستگاه
//+
string CLicenseChecker::GenerateDeviceId() {
   if(m_deviceId != "") return m_deviceId;

   // تولید از اطلاعات سیستم
   string id = "";

   id += IntegerToString(TerminalInfoInteger(TERMINAL_BUILD));
   id += "_" + AccountInfoString(ACCOUNT_NAME);
   id += "_" + TerminalInfoString(TERMINAL_NAME);

   // هش کردن
   int hash = 0;
   for(int i = 0; i < StringLen(id); i++) {
      hash = (hash * 31 + id[i]) % 1000000007;
   }

   m_deviceId = StringFormat("DEV-%08X", hash);

   return m_deviceId;
}

//+
// اعتبارسنجی
//+
bool CLicenseChecker::Verify() {
   // بررسی نیاز به اعتبارسنجی مجدد
   if(m_verified && TimeCurrent() < m_nextCheck) {
      return true;
   }

   // تلاش آنلاین
   if(VerifyOnline()) {
      m_lastCheck = TimeCurrent();
      m_nextCheck = m_lastCheck + m_checkInterval * 3600;
      return true;
   }

   // fallback به آفلاین
   if(m_verified) {
      // قبلاً تأیید شده، ادامه بده
      return true;
   }

   return VerifyOffline();
}

//+
// اعتبارسنجی آنلاین
//+
bool CLicenseChecker::VerifyOnline() {
   if(m_licenseKey == "") {
      LogMessage("کلید لایسنس تنظیم نشده", "WARNING");
      return false;
   }

   string deviceId = GenerateDeviceId();

   // ارسال درخواست به API
   string url = m_apiUrl + "/validate?key=" + m_licenseKey + "&device=" + deviceId;

   char data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";

   int res = WebRequest("GET", url, headers, ApiTimeout / 1000, data, result, headers);

   if(res == -1) {
      LogMessage("خطا در ارتباط با سرور لایسنس: " + IntegerToString(GetLastError()), "ERROR");
      return false;
   }

   string response = CharArrayToString(result);

   return ParseLicenseData(response);
}

//+
// اعتبارسنجی آفلاین
//+
bool CLicenseChecker::VerifyOffline() {
   // بررسی لایسنس ذخیره شده
   string filename = "MT5Trading\\license.dat";

   int handle = FileOpen(filename, FILE_READ|FILE_BIN);

   if(handle == INVALID_HANDLE) {
      LogMessage("فایل لایسنس یافت نشد", "WARNING");
      return false;
   }

   // خواندن اطلاعات
   FileReadStruct(handle, m_info);
   FileClose(handle);

   if(m_info.key != m_licenseKey) {
      LogMessage("کلید لایسنس مطابقت ندارد", "WARNING");
      return false;
   }

   m_verified = !IsExpired();

   return m_verified;
}

//+
// پردازش داده لایسنس
//+
bool CLicenseChecker::ParseLicenseData(const string data) {
   // پارس JSON ساده
   // فرمت انتظار: {"valid":true,"type":"pro","expires":"2025-12-31","devices":3}

   if(StringFind(data, "\"valid\":true") < 0) {
      m_info.isValid = false;
      return false;
   }

   m_info.isValid = true;

   // استخراج نوع
   if(StringFind(data, "\"type\":\"trial\"") >= 0) m_info.type = LICENSE_TRIAL;
   else if(StringFind(data, "\"type\":\"basic\"") >= 0) m_info.type = LICENSE_BASIC;
   else if(StringFind(data, "\"type\":\"pro\"") >= 0) m_info.type = LICENSE_PRO;
   else if(StringFind(data, "\"type\":\"enterprise\"") >= 0) m_info.type = LICENSE_ENTERPRISE;
   else if(StringFind(data, "\"type\":\"lifetime\"") >= 0) m_info.type = LICENSE_LIFETIME;

   // استخراج تاریخ انقضا
   int expiryPos = StringFind(data, "\"expires\":\"");
   if(expiryPos >= 0) {
      string expiryDate = StringSubstr(data, expiryPos + 11, 10);
      m_info.expiresAt = StringToTime(expiryDate + " 00:00:00");
   }

   // استخراج دستگاه‌ها
   int devicesPos = StringFind(data, "\"devices\":");
   if(devicesPos >= 0) {
      string numStr = "";
      int start = devicesPos + 11;
      while(start < StringLen(data) && data[start] >= '0' && data[start] <= '9') {
         numStr += CharToString(data[start]);
         start++;
      }
      m_info.devicesLimit = (int)StringToInteger(numStr);
   }

   m_info.key = m_licenseKey;
   m_verified = true;

   // ذخیره محلی
   string filename = "MT5Trading\\license.dat";
   int handle = FileOpen(filename, FILE_WRITE|FILE_BIN);
   if(handle != INVALID_HANDLE) {
      FileWriteStruct(handle, m_info);
      FileClose(handle);
   }

   LogMessage("لایسنس معتبر شد: " + GetTypeString(), "INFO");

   return true;
}

//+
// بررسی انقضا
//+
bool CLicenseChecker::IsExpired() {
   if(m_info.type == LICENSE_LIFETIME) return false;

   return TimeCurrent() > m_info.expiresAt;
}

//+
// بررسی دسترسی به ویژگی
//+
bool CLicenseChecker::HasFeatureLocal(const ENUM_LICENSE_FEATURE feature) {
   switch(m_info.type) {
      case LICENSE_TRIAL:
         return feature == FEATURE_SMC || feature == FEATURE_PA;

      case LICENSE_BASIC:
         return feature != FEATURE_AUTO_TRADE;

      case LICENSE_PRO:
      case LICENSE_ENTERPRISE:
      case LICENSE_LIFETIME:
         return true;
   }

   return false;
}

//+
// بررسی دسترسی عمومی
//+
bool CLicenseChecker::HasFeature(const ENUM_LICENSE_FEATURE feature) {
   if(!m_verified) return false;

   return HasFeatureLocal(feature);
}

//+
// بررسی معتبر بودن
//+
bool CLicenseChecker::IsValid() {
   return m_verified && m_info.isValid && !IsExpired();
}

//+
// بررسی انقضا
//+
bool CLicenseChecker::IsExpiredStatus() {
   return IsExpired();
}

//+
// دریافت روزهای باقی‌مانده
//+
int CLicenseChecker::GetDaysRemaining() {
   if(m_info.type == LICENSE_LIFETIME) return 36500;

   int seconds = (int)(m_info.expiresAt - TimeCurrent());
   return MathMax(0, seconds / 86400);
}

//+
// دریافت اطلاعات
//+
LicenseInfo CLicenseChecker::GetInfo() {
   return m_info;
}

//+
// دریافت نوع به صورت متن
//+
string CLicenseChecker::GetTypeString() {
   switch(m_info.type) {
      case LICENSE_TRIAL: return "آزمایی";
      case LICENSE_BASIC: return "پایه";
      case LICENSE_PRO: return "حرفه‌ای";
      case LICENSE_ENTERPRISE: return "سازمانی";
      case LICENSE_LIFETIME: return "مادام‌العمر";
   }
   return "نامشخص";
}

//+
// دریافت نوع
//+
ENUM_LICENSE_TYPE CLicenseChecker::GetType() {
   return m_info.type;
}

//+
// فعال‌سازی دستگاه
//+
bool CLicenseChecker::ActivateDevice() {
   if(!m_verified) return false;

   string deviceId = GenerateDeviceId();

   // ارسال درخواست فعال‌سازی
   string url = m_apiUrl + "/activate";
   string body = StringFormat("{\"key\":\"%s\",\"device\":\"%s\"}", m_licenseKey, deviceId);

   char data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";

   StringToCharArray(body, data, 0, WHOLE_ARRAY, CP_UTF8);

   int res = WebRequest("POST", url, headers, ApiTimeout / 1000, data, result, headers);

   if(res == -1) {
      LogMessage("خطا در فعال‌سازی دستگاه", "ERROR");
      return false;
   }

   string response = CharArrayToString(result);

   if(StringFind(response, "\"success\":true") >= 0) {
      LogMessage("دستگاه فعال شد: " + deviceId, "INFO");
      return true;
   }

   LogMessage("خطا در فعال‌سازی دستگاه", "ERROR");
   return false;
}

//+
// غیرفعال‌سازی دستگاه
//+
bool CLicenseChecker::DeactivateDevice() {
   // پیاده‌سازی مشابه ActivateDevice
   return false;
}

//+
// دریافت محدودیت دستگاه
//+
int CLicenseChecker::GetDevicesLimit() {
   return m_info.devicesLimit;
}

//+
// دریافت دستگاه‌های استفاده شده
//+
int CLicenseChecker::GetDevicesUsed() {
   return m_info.devicesUsed;
}

//+
// ابطال لایسنس
//+
bool CLicenseChecker::Revoke() {
   m_verified = false;
   m_info.isValid = false;
   m_licenseKey = "";

   // حذف فایل محلی
   FileDelete("MT5Trading\\license.dat");

   LogMessage("لایسنس ابطال شد", "WARNING");

   return true;
}

//+
// گزارش لایسنس
//+
string CLicenseChecker::GetLicenseReport() {
   string report = "📋 گزارش لایسنس\n\n";

   if(!m_verified) {
      report += "❌ لایسنس نامعتبر\n";
      report += "لطفاً کلید لایسنس معتبر وارد کنید.";
      return report;
   }

   report += StringFormat("نوع: %s\n", GetTypeString());
   report += StringFormat("وضعیت: %s\n", IsValid() ? "✅ معتبر" : "❌ نامعتبر");

   if(m_info.type != LICENSE_LIFETIME) {
      report += StringFormat("روزهای باقی‌مانده: %d\n", GetDaysRemaining());
   }

   report += StringFormat("دستگاه‌ها: %d/%d\n", m_info.devicesUsed, m_info.devicesLimit);

   return report;
}
//+------------------------------------------------------------------+
