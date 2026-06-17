//+------------------------------------------------------------------+
//|                                           DecisionConnector.mqh     |
//|                                    MT5 Trading System             |
//|                                    اتصال به Decision Engine       |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"
#include "Helpers.mqh"

//+
// ساختار درخواست تصمیم
//+
struct DecisionRequest {
   string symbol;
   string timeframe;
   double currentPrice;
   double previousClose[3];
   double high[10];
   double low[10];
   double open[10];
   double close[10];
   double volume[10];

   // SMC Data
   bool hasBOS;
   bool hasCHOCH;
   bool hasMSS;
   string trendDirection;
   bool hasOrderBlock;
   string obType;
   double obHigh;
   double obLow;
   bool hasFVG;
   double fvgHigh;
   double fvgLow;

   // PA Data
   bool hasPinBar;
   bool hasEngulfing;
   bool hasInsideBar;
   bool hasFakey;
   string patternBias;

   // Context
   string session;
   datetime requestTime;
};

//+
// ساختار پاسخ تصمیم
//+
struct DecisionResponse {
   bool success;
   string decision;
   string direction;
   int confidenceScore;
   int qualityScore;
   bool allowed;

   // Trading Levels
   double entryZone;
   double stopLoss;
   double takeProfit1;
   double takeProfit2;
   double takeProfit3;
   double riskRewardRatio;

   // Reasons
   string reasonCodes[];
   string reasons[];

   // Score Breakdown
   int smcScore;
   int paScore;
   int sessionScore;

   // Metadata
   string decisionId;
   datetime createdAt;
   string errorMessage;
};

//+
// ساختار وضعیت اتصال
//+
struct ConnectionStatus {
   bool isConnected;
   int lastStatusCode;
   string lastError;
   datetime lastSuccessfulCall;
   int failedAttempts;
   int successfulCalls;
   double averageResponseTime;
};

//+
// کلاس اتصال به Decision Engine
//+
class CDecisionConnector {
private:
   string m_apiUrl;
   string m_licenseKey;
   string m_deviceId;
   int m_timeout;
   bool m_enabled;

   // وضعیت اتصال
   ConnectionStatus m_status;

   // کش تصمیمات
   struct DecisionCache {
      string symbol;
      string timeframe;
      double price;
      DecisionResponse response;
      datetime cachedAt;
   };
   DecisionCache m_cache[];

   int m_cacheLifetime;  // ثانیه

   // توابع داخلی
   string GenerateRequestId();
   string BuildDecisionUrl(const DecisionRequest &request);
   bool ParseDecisionResponse(const string data, DecisionResponse &response);
   bool ValidateRequest(const DecisionRequest &request);
   void UpdateConnectionStatus(const bool success, const int statusCode, const string error, const double responseTime);
   void CleanupCache();
   bool GetCachedDecision(const DecisionRequest &request, DecisionResponse &response);
   void CacheDecision(const DecisionRequest &request, const DecisionResponse &response);

public:
   CDecisionConnector();
   ~CDecisionConnector();

   // تنظیمات
   void SetApiUrl(const string url);
   void SetLicenseKey(const string key);
   void SetTimeout(const int ms);
   void Enable(const bool enable);
   void SetCacheLifetime(const int seconds);

   // درخواست تصمیم
   DecisionResponse RequestDecision(DecisionRequest &request);
   DecisionResponse RequestDecisionAsync(DecisionRequest &request);
   DecisionResponse GetDecisionForSymbol(const string symbol, const string timeframe);

   // بررسی تصمیم
   bool IsAllowedToTrade(const string symbol, const string direction);
   bool ValidateDecision(const DecisionResponse &response);
   bool ShouldClosePosition(const string symbol, const string direction);

   // وضعیت اتصال
   bool IsConnected();
   ConnectionStatus GetConnectionStatus();
   int GetSuccessRate();
   void ResetStats();

   // مدیریت کش
   void ClearCache();
   int GetCacheSize();

   // تست اتصال
   bool TestConnection();
   string GetHealthStatus();

   // گزارش
   string GetConnectorReport();
};

//+
// سازنده
//+
CDecisionConnector::CDecisionConnector() {
   m_apiUrl = ApiBaseUrl;
   m_licenseKey = "";
   m_deviceId = "";
   m_timeout = ApiTimeout;
   m_enabled = true;
   m_cacheLifetime = 60;  // 60 ثانیه

   ZeroMemory(m_status);
   m_status.isConnected = false;

   ArrayResize(m_cache, 0);
}

//+
// مخرب
//+
CDecisionConnector::~CDecisionConnector() {
   ArrayResize(m_cache, 0);
}

//+
// تولید شناسه درخواست
//+
string CDecisionConnector::GenerateRequestId() {
   return StringFormat("REQ-%I64X-%d", TimeCurrent(), MathRand());
}

//+
// تنظیم آدرس API
//+
void CDecisionConnector::SetApiUrl(const string url) {
   m_apiUrl = url;
   m_status.isConnected = false;
}

//+
// تنظیم کلید لایسنس
//+
void CDecisionConnector::SetLicenseKey(const string key) {
   m_licenseKey = key;
}

//+
// تنظیم تایم‌اوت
//+
void CDecisionConnector::SetTimeout(const int ms) {
   m_timeout = MathMax(1000, MathMin(30000, ms));
}

//+
// فعال/غیرفعال کردن
//+
void CDecisionConnector::Enable(const bool enable) {
   m_enabled = enable;
}

//+
// تنظیم عمر کش
//+
void CDecisionConnector::SetCacheLifetime(const int seconds) {
   m_cacheLifetime = MathMax(10, seconds);
}

//+
// اعتبارسنجی درخواست
//+
bool CDecisionConnector::ValidateRequest(const DecisionRequest &request) {
   if(request.symbol == "") {
      LogMessage("نماد خالی است", "ERROR");
      return false;
   }

   if(request.currentPrice <= 0) {
      LogMessage("قیمت نامعتبر است", "ERROR");
      return false;
   }

   return true;
}

//+
// ساخت URL درخواست
//+
string CDecisionConnector::BuildDecisionUrl(const DecisionRequest &request) {
   string url = m_apiUrl + "/decision";

   url += "?symbol=" + request.symbol;
   url += "&timeframe=" + request.timeframe;
   url += "&price=" + DoubleToString(request.currentPrice, 5);

   if(m_licenseKey != "") {
      url += "&license=" + m_licenseKey;
   }

   return url;
}

//+
// پارس پاسخ تصمیم
//+
bool CDecisionConnector::ParseDecisionResponse(const string data, DecisionResponse &response) {
   ZeroMemory(response);
   response.success = false;

   if(StringLen(data) == 0) {
      response.errorMessage = "پاسخ خالی";
      return false;
   }

   // بررسی خطا
   if(StringFind(data, "\"error\"") >= 0) {
      int errorPos = StringFind(data, "\"message\":");
      if(errorPos >= 0) {
         int start = errorPos + 11;
         int end = StringFind(data, "\"", start + 1);
         if(end > start) {
            response.errorMessage = StringSubstr(data, start, end - start);
         }
      }
      return false;
   }

   // استخراج success
   if(StringFind(data, "\"success\":true") >= 0 || StringFind(data, "\"decision\":") >= 0) {
      response.success = true;
   }

   // استخراج decision
   int decisionPos = StringFind(data, "\"decision\":");
   if(decisionPos >= 0) {
      int start = decisionPos + 12;
      if(data[start] == '"') {
         start++;
         int end = StringFind(data, "\"", start);
         if(end > start) {
            response.decision = StringSubstr(data, start, end - start);
         }
      }
   }

   // استخراج direction
   int dirPos = StringFind(data, "\"direction\":");
   if(dirPos >= 0) {
      int start = dirPos + 12;
      if(data[start] == '"') {
         start++;
         int end = StringFind(data, "\"", start);
         if(end > start) {
            response.direction = StringSubstr(data, start, end - start);
         }
      }
   }

   // استخراج confidence_score
   int confPos = StringFind(data, "\"confidence_score\":");
   if(confPos >= 0) {
      string numStr = "";
      int start = confPos + 19;
      while(start < StringLen(data) && (data[start] >= '0' && data[start] <= '9')) {
         numStr += CharToString(data[start]);
         start++;
      }
      response.confidenceScore = (int)StringToInteger(numStr);
   }

   // استخراج quality_score
   int qualPos = StringFind(data, "\"quality_score\":");
   if(qualPos >= 0) {
      string numStr = "";
      int start = qualPos + 16;
      while(start < StringLen(data) && (data[start] >= '0' && data[start] <= '9')) {
         numStr += CharToString(data[start]);
         start++;
      }
      response.qualityScore = (int)StringToInteger(numStr);
   }

   // استخراج allowed
   int allowedPos = StringFind(data, "\"allowed\":");
   if(allowedPos >= 0) {
      int start = allowedPos + 10;
      if(StringFind(data, "true", start) <= start + 6) {
         response.allowed = true;
      }
   }

   // استخراج trading_levels
   int entryPos = StringFind(data, "\"entry_zone\":");
   if(entryPos >= 0) {
      string numStr = "";
      int start = entryPos + 13;
      while(start < StringLen(data) && ((data[start] >= '0' && data[start] <= '9') || data[start] == '.' || data[start] == '-')) {
         numStr += CharToString(data[start]);
         start++;
      }
      response.entryZone = StringToDouble(numStr);
   }

   int slPos = StringFind(data, "\"stop_loss\":");
   if(slPos >= 0) {
      string numStr = "";
      int start = slPos + 12;
      while(start < StringLen(data) && ((data[start] >= '0' && data[start] <= '9') || data[start] == '.' || data[start] == '-')) {
         numStr += CharToString(data[start]);
         start++;
      }
      response.stopLoss = StringToDouble(numStr);
   }

   int tp1Pos = StringFind(data, "\"take_profit_1\":");
   if(tp1Pos >= 0) {
      string numStr = "";
      int start = tp1Pos + 16;
      while(start < StringLen(data) && ((data[start] >= '0' && data[start] <= '9') || data[start] == '.' || data[start] == '-')) {
         numStr += CharToString(data[start]);
         start++;
      }
      response.takeProfit1 = StringToDouble(numStr);
   }

   int rrPos = StringFind(data, "\"risk_reward_ratio\":");
   if(rrPos >= 0) {
      string numStr = "";
      int start = rrPos + 19;
      while(start < StringLen(data) && ((data[start] >= '0' && data[start] <= '9') || data[start] == '.')) {
         numStr += CharToString(data[start]);
         start++;
      }
      response.riskRewardRatio = StringToDouble(numStr);
   }

   response.createdAt = TimeCurrent();

   return true;
}

//+
// به‌روزرسانی وضعیت اتصال
//+
void CDecisionConnector::UpdateConnectionStatus(const bool success, const int statusCode,
   const string error, const double responseTime) {

   if(success) {
      m_status.isConnected = true;
      m_status.lastSuccessfulCall = TimeCurrent();
      m_status.successfulCalls++;
      m_status.failedAttempts = 0;

      double totalTime = m_status.averageResponseTime * (m_status.successfulCalls - 1) + responseTime;
      m_status.averageResponseTime = totalTime / m_status.successfulCalls;
   } else {
      m_status.failedAttempts++;

      if(m_status.failedAttempts >= 3) {
         m_status.isConnected = false;
      }
   }

   m_status.lastStatusCode = statusCode;
   m_status.lastError = error;
}

//+
// پاکسازی کش قدیمی
//+
void CDecisionConnector::CleanupCache() {
   if(ArraySize(m_cache) == 0) return;

   datetime threshold = TimeCurrent() - m_cacheLifetime;
   int validCount = 0;

   for(int i = 0; i < ArraySize(m_cache); i++) {
      if(m_cache[i].cachedAt > threshold) {
         validCount++;
      }
   }

   if(validCount < ArraySize(m_cache)) {
      DecisionCache temp[];
      ArrayResize(temp, validCount);

      int index = 0;
      for(int i = 0; i < ArraySize(m_cache); i++) {
         if(m_cache[i].cachedAt > threshold) {
            temp[index] = m_cache[i];
            index++;
         }
      }

      ArrayCopy(m_cache, temp);
      LogMessage(StringFormat("کش پاکسازی شد: %d ورودی قدیمی حذف", ArraySize(temp) - validCount), "INFO");
   }
}

//+
// دریافت تصمیم از کش
//+
bool CDecisionConnector::GetCachedDecision(const DecisionRequest &request, DecisionResponse &response) {
   for(int i = 0; i < ArraySize(m_cache); i++) {
      if(m_cache[i].symbol == request.symbol &&
         m_cache[i].timeframe == request.timeframe) {

         double priceTolerance = request.currentPrice * 0.0001;

         if(MathAbs(m_cache[i].price - request.currentPrice) < priceTolerance) {
            if(m_cache[i].cachedAt > TimeCurrent() - m_cacheLifetime) {
               response = m_cache[i].response;
               return true;
            }
         }
      }
   }

   return false;
}

//+
// کش کردن تصمیم
//+
void CDecisionConnector::CacheDecision(const DecisionRequest &request, const DecisionResponse &response) {
   int size = ArraySize(m_cache);
   ArrayResize(m_cache, size + 1);

   m_cache[size].symbol = request.symbol;
   m_cache[size].timeframe = request.timeframe;
   m_cache[size].price = request.currentPrice;
   m_cache[size].response = response;
   m_cache[size].cachedAt = TimeCurrent();
}

//+
// درخواست تصمیم
//+
DecisionResponse CDecisionConnector::RequestDecision(DecisionRequest &request) {
   DecisionResponse response;
   ZeroMemory(response);

   if(!m_enabled) {
      response.success = false;
      response.errorMessage = "Decision Connector غیرفعال است";
      return response;
   }

   if(!ValidateRequest(request)) {
      response.success = false;
      response.errorMessage = "درخواست نامعتبر";
      return response;
   }

   if(GetCachedDecision(request, response)) {
      LogMessage("تصمیم از کش دریافت شد", "INFO");
      return response;
   }

   string url = BuildDecisionUrl(request);

   char data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";
   headers += "X-Request-ID: " + GenerateRequestId() + "\r\n";

   if(m_licenseKey != "") {
      headers += "X-License-Key: " + m_licenseKey + "\r\n";
   }

   datetime startTime = TimeCurrent();
   int timeoutSeconds = m_timeout / 1000;

   int res = WebRequest("GET", url, headers, timeoutSeconds, data, result, headers);

   double responseTime = (double)(TimeCurrent() - startTime) * 1000;

   if(res == -1) {
      int lastError = GetLastError();
      string errorMsg = "خطا در ارتباط با سرور: " + IntegerToString(lastError);
      LogMessage(errorMsg, "ERROR");

      UpdateConnectionStatus(false, lastError, errorMsg, responseTime);

      response.success = false;
      response.errorMessage = errorMsg;
      return response;
   }

   if(res >= 400) {
      string errorMsg = "خطای سرور: HTTP " + IntegerToString(res);
      UpdateConnectionStatus(false, res, errorMsg, responseTime);

      response.success = false;
      response.errorMessage = errorMsg;
      return response;
   }

   string responseData = CharArrayToString(result);

   if(ParseDecisionResponse(responseData, response)) {
      UpdateConnectionStatus(true, res, "", responseTime);
      CacheDecision(request, response);

      LogMessage(StringFormat("تصمیم دریافت شد: %s | Score: %d",
         response.decision, response.confidenceScore), "INFO");
   } else {
      UpdateConnectionStatus(false, res, response.errorMessage, responseTime);
   }

   return response;
}

//+
// درخواست تصمیم غیرهمزمان
//+
DecisionResponse CDecisionConnector::RequestDecisionAsync(DecisionRequest &request) {
   return RequestDecision(request);
}

//+
// دریافت تصمیم برای نماد
//+
DecisionResponse CDecisionConnector::GetDecisionForSymbol(const string symbol, const string timeframe) {
   DecisionRequest request;
   ZeroMemory(request);

   request.symbol = symbol;
   request.timeframe = timeframe;
   request.currentPrice = SymbolInfoDouble(symbol, SYMBOL_BID);
   request.requestTime = TimeCurrent();

   return RequestDecision(request);
}

//+
// آیا معامله مجاز است
//+
bool CDecisionConnector::IsAllowedToTrade(const string symbol, const string direction) {
   DecisionResponse response = GetDecisionForSymbol(symbol, "H1");

   if(!response.success) {
      return false;
   }

   if(!response.allowed) {
      return false;
   }

   if(response.decision == "NO_TRADE") {
      return false;
   }

   if(direction == "buy" && response.direction != "bullish") {
      return false;
   }

   if(direction == "sell" && response.direction != "bearish") {
      return false;
   }

   return true;
}

//+
// اعتبارسنجی تصمیم
//+
bool CDecisionConnector::ValidateDecision(const DecisionResponse &response) {
   if(!response.success) return false;
   if(!response.allowed) return false;

   if(response.decision != "BUY" && response.decision != "SELL") {
      if(response.decision != "NO_TRADE") {
         return false;
      }
   }

   if(response.confidenceScore < MinEntryScore) {
      LogMessage(StringFormat("امتیاز پایین: %d < %d",
         response.confidenceScore, MinEntryScore), "WARNING");
      return false;
   }

   if(response.decision == "BUY" || response.decision == "SELL") {
      if(response.entryZone <= 0 || response.stopLoss <= 0 || response.takeProfit1 <= 0) {
         LogMessage("سطوح معاملاتی نامعتبر", "ERROR");
         return false;
      }
   }

   return true;
}

//+
// آیا باید پوزیشن بسته شود
//+
bool CDecisionConnector::ShouldClosePosition(const string symbol, const string direction) {
   DecisionResponse response = GetDecisionForSymbol(symbol, "H1");

   if(!response.success) {
      return false;
   }

   if(response.direction == "neutral") {
      return true;
   }

   if(direction == "buy" && response.direction == "bearish") {
      return true;
   }

   if(direction == "sell" && response.direction == "bullish") {
      return true;
   }

   return false;
}

//+
// آیا متصل است
//+
bool CDecisionConnector::IsConnected() {
   if(!m_enabled) return false;

   if(m_status.failedAttempts >= 3) {
      return false;
   }

   if(m_status.lastSuccessfulCall > 0) {
      int secondsSinceLast = (int)(TimeCurrent() - m_status.lastSuccessfulCall);
      return secondsSinceLast < 300;
   }

   return false;
}

//+
// دریافت وضعیت اتصال
//+
ConnectionStatus CDecisionConnector::GetConnectionStatus() {
   return m_status;
}

//+
// نرخ موفقیت
//+
int CDecisionConnector::GetSuccessRate() {
   int total = m_status.successfulCalls + m_status.failedAttempts;

   if(total == 0) return 0;

   return (int)(m_status.successfulCalls * 100.0 / total);
}

//+
// بازنشانی آمار
//+
void CDecisionConnector::ResetStats() {
   ZeroMemory(m_status);
   m_status.isConnected = false;
}

//+
// پاک کردن کش
//+
void CDecisionConnector::ClearCache() {
   ArrayResize(m_cache, 0);
   LogMessage("کش تصمیمات پاک شد", "INFO");
}

//+
// اندازه کش
//+
int CDecisionConnector::GetCacheSize() {
   CleanupCache();
   return ArraySize(m_cache);
}

//+
// تست اتصال
//+
bool CDecisionConnector::TestConnection() {
   string url = m_apiUrl + "/health";

   char data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";

   int res = WebRequest("GET", url, headers, m_timeout / 1000, data, result, headers);

   if(res == 200) {
      m_status.isConnected = true;
      LogMessage("اتصال به Decision Engine برقرار شد", "INFO");
      return true;
   }

   m_status.isConnected = false;
   LogMessage("خطا در اتصال به Decision Engine: " + IntegerToString(res), "ERROR");
   return false;
}

//+
// وضعیت سلامت
//+
string CDecisionConnector::GetHealthStatus() {
   if(!m_enabled) {
      return "Decision Connector غیرفعال";
   }

   if(IsConnected()) {
      return StringFormat("متصل | نرخ موفقیت: %d%% | میانگین پاسخ: %.0f ms",
         GetSuccessRate(), m_status.averageResponseTime);
   }

   return StringFormat("قطع | آخرین خطا: %s | تلاش ناموفق: %d",
      m_status.lastError, m_status.failedAttempts);
}

//+
// گزارش Connector
//+
string CDecisionConnector::GetConnectorReport() {
   string report = "📊 گزارش Decision Connector\n\n";

   report += StringFormat("وضعیت: %s\n", IsConnected() ? "✅ متصل" : "❌ قطع");
   report += StringFormat("URL: %s\n", m_apiUrl);
   report += StringFormat("Enabled: %s\n\n", m_enabled ? "بله" : "خیر");

   report += "📈 آمار:\n";
   report += StringFormat("   موفق: %d\n", m_status.successfulCalls);
   report += StringFormat("   ناموفق: %d\n", m_status.failedAttempts);
   report += StringFormat("   نرخ موفقیت: %d%%\n", GetSuccessRate());
   report += StringFormat("   میانگین پاسخ: %.0f ms\n\n", m_status.averageResponseTime);

   report += StringFormat("Cache: %d تصمیم\n", GetCacheSize());

   if(m_status.lastSuccessfulCall > 0) {
      report += StringFormat("آخرین موفقیت: %s\n",
         TimeToString(m_status.lastSuccessfulCall, TIME_DATE|TIME_MINUTES));
   }

   if(m_status.lastError != "") {
      report += StringFormat("آخرین خطا: %s\n", m_status.lastError);
   }

   return report;
}
//+------------------------------------------------------------------+
