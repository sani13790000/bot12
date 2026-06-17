//+------------------------------------------------------------------+
//|                                        DecisionConnector.mqh    |
//|                                    MT5 Trading System           |
//|                                    اتصال به Decision Engine     |
//+------------------------------------------------------------------+
#property strict

#include "Config.mqh"
#include "Helpers.mqh"

//+
// ===================== کمک‌کار JSON =====================
// جایگزین StringFind دستی — ایمن در برابر whitespace و nested objects
//+

// استخراج مقدار string از JSON با کلید مشخص
bool JsonGetString(const string json, const string key, string &value) {
   string searchKey = "\"" + key + "\"";
   int keyPos = StringFind(json, searchKey);
   if(keyPos < 0) return false;

   int colonPos = StringFind(json, ":", keyPos + StringLen(searchKey));
   if(colonPos < 0) return false;

   // رد کردن فضای خالی
   int i = colonPos + 1;
   while(i < StringLen(json) && (json[i] == ' ' || json[i] == '\t' || json[i] == '\r' || json[i] == '\n'))
      i++;

   if(i >= StringLen(json)) return false;

   // اگر مقدار با " شروع شود
   if(json[i] == '"') {
      i++;  // رد کردن "
      string result = "";
      while(i < StringLen(json)) {
         if(json[i] == '\\' && i + 1 < StringLen(json)) {
            i++;
            if(json[i] == '"') result += "\"";
            else if(json[i] == 'n') result += "\n";
            else if(json[i] == 't') result += "\t";
            else if(json[i] == '\\') result += "\\";
            else result += CharToString(json[i]);
         }
         else if(json[i] == '"') {
            break;
         }
         else {
            result += CharToString(json[i]);
         }
         i++;
      }
      value = result;
      return true;
   }

   return false;
}

// استخراج مقدار عدد صحیح
bool JsonGetInt(const string json, const string key, int &value) {
   string searchKey = "\"" + key + "\"";
   int keyPos = StringFind(json, searchKey);
   if(keyPos < 0) return false;

   int colonPos = StringFind(json, ":", keyPos + StringLen(searchKey));
   if(colonPos < 0) return false;

   int i = colonPos + 1;
   while(i < StringLen(json) && (json[i] == ' ' || json[i] == '\t')) i++;

   string numStr = "";
   bool negative = false;
   if(i < StringLen(json) && json[i] == '-') { negative = true; i++; }

   while(i < StringLen(json) && json[i] >= '0' && json[i] <= '9') {
      numStr += CharToString(json[i]);
      i++;
   }

   if(StringLen(numStr) == 0) return false;
   value = (int)StringToInteger(numStr) * (negative ? -1 : 1);
   return true;
}

// استخراج مقدار double
bool JsonGetDouble(const string json, const string key, double &value) {
   string searchKey = "\"" + key + "\"";
   int keyPos = StringFind(json, searchKey);
   if(keyPos < 0) return false;

   int colonPos = StringFind(json, ":", keyPos + StringLen(searchKey));
   if(colonPos < 0) return false;

   int i = colonPos + 1;
   while(i < StringLen(json) && (json[i] == ' ' || json[i] == '\t')) i++;

   string numStr = "";
   bool negative = false;
   if(i < StringLen(json) && json[i] == '-') { negative = true; i++; }

   while(i < StringLen(json) && ((json[i] >= '0' && json[i] <= '9') || json[i] == '.' || json[i] == 'e' || json[i] == 'E' || json[i] == '+' || (json[i] == '-' && StringLen(numStr) > 0))) {
      numStr += CharToString(json[i]);
      i++;
   }

   if(StringLen(numStr) == 0) return false;
   value = StringToDouble(numStr) * (negative ? -1.0 : 1.0);
   return true;
}

// استخراج مقدار bool
bool JsonGetBool(const string json, const string key, bool &value) {
   string searchKey = "\"" + key + "\"";
   int keyPos = StringFind(json, searchKey);
   if(keyPos < 0) return false;

   int colonPos = StringFind(json, ":", keyPos + StringLen(searchKey));
   if(colonPos < 0) return false;

   int i = colonPos + 1;
   while(i < StringLen(json) && (json[i] == ' ' || json[i] == '\t')) i++;

   if(StringFind(json, "true", i) == i) { value = true; return true; }
   if(StringFind(json, "false", i) == i) { value = false; return true; }
   return false;
}

// استخراج یک آبجکت nested با کلید
bool JsonGetObject(const string json, const string key, string &obj) {
   string searchKey = "\"" + key + "\"";
   int keyPos = StringFind(json, searchKey);
   if(keyPos < 0) return false;

   int colonPos = StringFind(json, ":", keyPos + StringLen(searchKey));
   if(colonPos < 0) return false;

   int i = colonPos + 1;
   while(i < StringLen(json) && (json[i] == ' ' || json[i] == '\t')) i++;

   if(i >= StringLen(json) || json[i] != '{') return false;

   int depth = 0;
   int start = i;
   while(i < StringLen(json)) {
      if(json[i] == '{') depth++;
      else if(json[i] == '}') {
         depth--;
         if(depth == 0) {
            obj = StringSubstr(json, start, i - start + 1);
            return true;
         }
      }
      i++;
   }
   return false;
}

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
   double open_[10];
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

   ConnectionStatus m_status;

   struct DecisionCache {
      string symbol;
      string timeframe;
      double price;
      DecisionResponse response;
      datetime cachedAt;
   };
   DecisionCache m_cache[];
   int m_cacheLifetime;

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

   void SetApiUrl(const string url);
   void SetLicenseKey(const string key);
   void SetTimeout(const int ms);
   void Enable(const bool enable);
   void SetCacheLifetime(const int seconds);

   DecisionResponse RequestDecision(DecisionRequest &request);
   DecisionResponse RequestDecisionAsync(DecisionRequest &request);
   DecisionResponse GetDecisionForSymbol(const string symbol, const string timeframe);

   bool IsAllowedToTrade(const string symbol, const string direction);
   bool ValidateDecision(const DecisionResponse &response);
   bool ShouldClosePosition(const string symbol, const string direction);

   bool IsConnected();
   ConnectionStatus GetConnectionStatus();
   int GetSuccessRate();
   void ResetStats();

   void ClearCache();
   int GetCacheSize();

   bool TestConnection();
   string GetHealthStatus();
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
   m_cacheLifetime = 60;

   ZeroMemory(m_status);
   m_status.isConnected = false;
   ArrayResize(m_cache, 0);
}

CDecisionConnector::~CDecisionConnector() {
   ArrayResize(m_cache, 0);
}

string CDecisionConnector::GenerateRequestId() {
   return StringFormat("REQ-%I64X-%d", TimeCurrent(), MathRand());
}

void CDecisionConnector::SetApiUrl(const string url) {
   m_apiUrl = url;
   m_status.isConnected = false;
}

void CDecisionConnector::SetLicenseKey(const string key) { m_licenseKey = key; }
void CDecisionConnector::SetTimeout(const int ms) { m_timeout = MathMax(1000, MathMin(30000, ms)); }
void CDecisionConnector::Enable(const bool enable) { m_enabled = enable; }
void CDecisionConnector::SetCacheLifetime(const int seconds) { m_cacheLifetime = MathMax(10, seconds); }

bool CDecisionConnector::ValidateRequest(const DecisionRequest &request) {
   if(request.symbol == "") { LogMessage("نماد خالی است", "ERROR"); return false; }
   if(request.currentPrice <= 0) { LogMessage("قیمت نامعتبر است", "ERROR"); return false; }
   return true;
}

string CDecisionConnector::BuildDecisionUrl(const DecisionRequest &request) {
   string url = m_apiUrl + "/decision";
   url += "?symbol=" + request.symbol;
   url += "&timeframe=" + request.timeframe;
   url += "&price=" + DoubleToString(request.currentPrice, 5);
   if(m_licenseKey != "") url += "&license=" + m_licenseKey;
   return url;
}

//+
// ParseDecisionResponse — ایمن با کمک‌کارهای JSON
//+
bool CDecisionConnector::ParseDecisionResponse(const string data, DecisionResponse &response) {
   ZeroMemory(response);
   response.success = false;

   if(StringLen(data) == 0) {
      response.errorMessage = "پاسخ خالی";
      return false;
   }

   // بررسی خطا در ابتدا
   string errMsg = "";
   if(JsonGetString(data, "error", errMsg) || StringFind(data, "\"error\"") >= 0) {
      JsonGetString(data, "message", response.errorMessage);
      if(response.errorMessage == "") response.errorMessage = "خطای ناشناخته سرور";
      return false;
   }

   // success
   JsonGetBool(data, "success", response.success);

   // استخراج بلاک data اگر وجود داشت
   string dataBlock = "";
   string parseTarget = data;
   if(JsonGetObject(data, "data", dataBlock)) {
      parseTarget = dataBlock;
   }

   // decision
   if(!JsonGetString(parseTarget, "decision", response.decision)) {
      response.errorMessage = "فیلد decision یافت نشد";
      return false;
   }

   // direction
   JsonGetString(parseTarget, "direction", response.direction);

   // confidence_score / total_score
   if(!JsonGetInt(parseTarget, "confidence_score", response.confidenceScore)) {
      JsonGetInt(parseTarget, "total_score", response.confidenceScore);
   }

   // quality_score
   JsonGetInt(parseTarget, "quality_score", response.qualityScore);

   // allowed
   JsonGetBool(parseTarget, "allowed", response.allowed);

   // trading levels — ابتدا در nested object بعد مستقیم
   string levelsObj = "";
   string levelsSrc = parseTarget;
   if(JsonGetObject(parseTarget, "trading_levels", levelsObj)) {
      levelsSrc = levelsObj;
   }

   JsonGetDouble(levelsSrc, "entry_zone", response.entryZone);
   JsonGetDouble(levelsSrc, "stop_loss", response.stopLoss);
   JsonGetDouble(levelsSrc, "take_profit_1", response.takeProfit1);
   JsonGetDouble(levelsSrc, "take_profit_2", response.takeProfit2);
   JsonGetDouble(levelsSrc, "take_profit_3", response.takeProfit3);
   JsonGetDouble(levelsSrc, "risk_reward_ratio", response.riskRewardRatio);

   // fallback برای فیلدهای مستقیم
   if(response.entryZone == 0) JsonGetDouble(parseTarget, "suggested_entry", response.entryZone);
   if(response.stopLoss == 0) JsonGetDouble(parseTarget, "suggested_sl", response.stopLoss);
   if(response.takeProfit1 == 0) JsonGetDouble(parseTarget, "suggested_tp", response.takeProfit1);
   if(response.riskRewardRatio == 0) JsonGetDouble(parseTarget, "risk_reward", response.riskRewardRatio);

   // score breakdown
   string scoresObj = "";
   if(JsonGetObject(parseTarget, "score_breakdown", scoresObj)) {
      JsonGetInt(scoresObj, "smc", response.smcScore);
      JsonGetInt(scoresObj, "price_action", response.paScore);
      JsonGetInt(scoresObj, "session", response.sessionScore);
   }

   // decisionId
   JsonGetString(parseTarget, "decision_id", response.decisionId);

   response.createdAt = TimeCurrent();
   response.success = (response.decision == "BUY" || response.decision == "SELL" || response.decision == "NO_TRADE");

   return response.success;
}

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
      if(m_status.failedAttempts >= 3) m_status.isConnected = false;
   }
   m_status.lastStatusCode = statusCode;
   m_status.lastError = error;
}

void CDecisionConnector::CleanupCache() {
   if(ArraySize(m_cache) == 0) return;
   datetime threshold = TimeCurrent() - m_cacheLifetime;
   int validCount = 0;
   for(int i = 0; i < ArraySize(m_cache); i++)
      if(m_cache[i].cachedAt > threshold) validCount++;

   if(validCount < ArraySize(m_cache)) {
      DecisionCache temp[];
      ArrayResize(temp, validCount);
      int index = 0;
      for(int i = 0; i < ArraySize(m_cache); i++)
         if(m_cache[i].cachedAt > threshold) { temp[index] = m_cache[i]; index++; }
      ArrayCopy(m_cache, temp);
   }
}

bool CDecisionConnector::GetCachedDecision(const DecisionRequest &request, DecisionResponse &response) {
   for(int i = 0; i < ArraySize(m_cache); i++) {
      if(m_cache[i].symbol == request.symbol && m_cache[i].timeframe == request.timeframe) {
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

void CDecisionConnector::CacheDecision(const DecisionRequest &request, const DecisionResponse &response) {
   int size = ArraySize(m_cache);
   ArrayResize(m_cache, size + 1);
   m_cache[size].symbol = request.symbol;
   m_cache[size].timeframe = request.timeframe;
   m_cache[size].price = request.currentPrice;
   m_cache[size].response = response;
   m_cache[size].cachedAt = TimeCurrent();
}

DecisionResponse CDecisionConnector::RequestDecision(DecisionRequest &request) {
   DecisionResponse response;
   ZeroMemory(response);

   if(!m_enabled) { response.errorMessage = "Decision Connector غیرفعال است"; return response; }
   if(!ValidateRequest(request)) { response.errorMessage = "درخواست نامعتبر"; return response; }
   if(GetCachedDecision(request, response)) { LogMessage("تصمیم از کش دریافت شد", "INFO"); return response; }

   string url = BuildDecisionUrl(request);
   char data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";
   headers += "X-Request-ID: " + GenerateRequestId() + "\r\n";
   if(m_licenseKey != "") headers += "X-License-Key: " + m_licenseKey + "\r\n";

   datetime startTime = TimeCurrent();
   int res = WebRequest("GET", url, headers, m_timeout / 1000, data, result, headers);
   double responseTime = (double)(TimeCurrent() - startTime) * 1000;

   if(res == -1) {
      int lastError = GetLastError();
      string errorMsg = "خطا در ارتباط با سرور: " + IntegerToString(lastError);
      LogMessage(errorMsg, "ERROR");
      UpdateConnectionStatus(false, lastError, errorMsg, responseTime);
      response.errorMessage = errorMsg;
      return response;
   }

   if(res >= 400) {
      string errorMsg = "خطای سرور: HTTP " + IntegerToString(res);
      UpdateConnectionStatus(false, res, errorMsg, responseTime);
      response.errorMessage = errorMsg;
      return response;
   }

   string responseData = CharArrayToString(result);

   if(ParseDecisionResponse(responseData, response)) {
      UpdateConnectionStatus(true, res, "", responseTime);
      CacheDecision(request, response);
      LogMessage(StringFormat("تصمیم دریافت شد: %s | Score: %d", response.decision, response.confidenceScore), "INFO");
   } else {
      UpdateConnectionStatus(false, res, response.errorMessage, responseTime);
      LogMessage("خطا در parse پاسخ: " + response.errorMessage, "ERROR");
   }

   return response;
}

DecisionResponse CDecisionConnector::RequestDecisionAsync(DecisionRequest &request) {
   return RequestDecision(request);
}

DecisionResponse CDecisionConnector::GetDecisionForSymbol(const string symbol, const string timeframe) {
   DecisionRequest request;
   ZeroMemory(request);
   request.symbol = symbol;
   request.timeframe = timeframe;
   request.currentPrice = SymbolInfoDouble(symbol, SYMBOL_BID);
   request.requestTime = TimeCurrent();
   return RequestDecision(request);
}

bool CDecisionConnector::IsAllowedToTrade(const string symbol, const string direction) {
   DecisionResponse response = GetDecisionForSymbol(symbol, "H1");
   if(!response.success || !response.allowed || response.decision == "NO_TRADE") return false;
   if(direction == "buy" && response.direction != "bullish") return false;
   if(direction == "sell" && response.direction != "bearish") return false;
   return true;
}

bool CDecisionConnector::ValidateDecision(const DecisionResponse &response) {
   if(!response.success || !response.allowed) return false;
   if(response.decision != "BUY" && response.decision != "SELL" && response.decision != "NO_TRADE") return false;
   if(response.confidenceScore < MinEntryScore) {
      LogMessage(StringFormat("امتیاز پایین: %d < %d", response.confidenceScore, MinEntryScore), "WARNING");
      return false;
   }
   if((response.decision == "BUY" || response.decision == "SELL") &&
      (response.entryZone <= 0 || response.stopLoss <= 0 || response.takeProfit1 <= 0)) {
      LogMessage("سطوح معاملاتی نامعتبر", "ERROR");
      return false;
   }
   return true;
}

bool CDecisionConnector::ShouldClosePosition(const string symbol, const string direction) {
   DecisionResponse response = GetDecisionForSymbol(symbol, "H1");
   if(!response.success) return false;
   if(response.direction == "neutral") return true;
   if(direction == "buy" && response.direction == "bearish") return true;
   if(direction == "sell" && response.direction == "bullish") return true;
   return false;
}

bool CDecisionConnector::IsConnected() {
   if(!m_enabled || m_status.failedAttempts >= 3) return false;
   if(m_status.lastSuccessfulCall > 0)
      return (int)(TimeCurrent() - m_status.lastSuccessfulCall) < 300;
   return false;
}

ConnectionStatus CDecisionConnector::GetConnectionStatus() { return m_status; }

int CDecisionConnector::GetSuccessRate() {
   int total = m_status.successfulCalls + m_status.failedAttempts;
   if(total == 0) return 0;
   return (int)(m_status.successfulCalls * 100.0 / total);
}

void CDecisionConnector::ResetStats() { ZeroMemory(m_status); m_status.isConnected = false; }

void CDecisionConnector::ClearCache() { ArrayResize(m_cache, 0); LogMessage("کش تصمیمات پاک شد", "INFO"); }

int CDecisionConnector::GetCacheSize() { CleanupCache(); return ArraySize(m_cache); }

bool CDecisionConnector::TestConnection() {
   string url = m_apiUrl + "/health";
   char data[]; char result[];
   string headers = "Content-Type: application/json\r\n";
   int res = WebRequest("GET", url, headers, m_timeout / 1000, data, result, headers);
   if(res == 200) { m_status.isConnected = true; LogMessage("اتصال به Decision Engine برقرار شد", "INFO"); return true; }
   m_status.isConnected = false;
   LogMessage("خطا در اتصال به Decision Engine: " + IntegerToString(res), "ERROR");
   return false;
}

string CDecisionConnector::GetHealthStatus() {
   if(!m_enabled) return "Decision Connector غیرفعال";
   if(IsConnected()) return StringFormat("متصل | نرخ موفقیت: %d%% | میانگین پاسخ: %.0f ms", GetSuccessRate(), m_status.averageResponseTime);
   return StringFormat("قطع | آخرین خطا: %s | تلاش ناموفق: %d", m_status.lastError, m_status.failedAttempts);
}

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
   if(m_status.lastSuccessfulCall > 0)
      report += StringFormat("آخرین موفقیت: %s\n", TimeToString(m_status.lastSuccessfulCall, TIME_DATE|TIME_MINUTES));
   if(m_status.lastError != "")
      report += StringFormat("آخرین خطا: %s\n", m_status.lastError);
   return report;
}
//+------------------------------------------------------------------+
