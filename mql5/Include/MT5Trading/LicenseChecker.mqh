//+------------------------------------------------------------------+
//| Galaxy Vast AI Trading Platform                                    |
//| LicenseChecker.mqh                                                |
//|                                                                    |
//| وظیفه: بررسی اعتبار لایسنس از طریق backend API               |
//+------------------------------------------------------------------+
#ifndef LICENSE_CHECKER_MQH
#define LICENSE_CHECKER_MQH

#include <MT5Trading/Config.mqh>

#define LICENSE_HEARTBEAT_SECONDS  300
#define LICENSE_RETRY_ATTEMPTS     3
#define LICENSE_TIMEOUT_MS         10000

class LicenseChecker
{
private:
   string   m_license_key;
   string   m_device_id;
   string   m_device_token;
   string   m_api_base_url;
   bool     m_is_valid;
   datetime m_last_heartbeat;
   datetime m_expires_at;
   string   m_plan;

public:
   LicenseChecker(void)
   {
      m_is_valid       = false;
      m_last_heartbeat = 0;
      m_expires_at     = 0;
      m_plan           = "";
      m_api_base_url   = API_BASE_URL;
   }

   bool Init(const string license_key, const string device_id, const string api_url = "")
   {
      m_license_key  = license_key;
      m_device_id    = device_id;
      if(api_url != "") m_api_base_url = api_url;
      if(license_key == "" || device_id == "") {
         Print("LicenseChecker: کلید لایسنس یا شناسه دستگاه خالی است");
         return false;
      }
      return Activate();
   }

   bool Activate(void)
   {
      string url  = m_api_base_url + "/license/activate";
      string body = StringFormat(
         "{\"license_key\":\"%s\",\"device_id\":\"%s\",\"device_name\":\"MT5_EA_%s\"}",
         m_license_key, m_device_id, AccountInfoString(ACCOUNT_SERVER)
      );
      string headers = "Content-Type: application/json\r\n";
      char post[], result[];
      string result_headers;
      StringToCharArray(body, post, 0, WHOLE_ARRAY, CP_UTF8);
      for(int i = 0; i < LICENSE_RETRY_ATTEMPTS; i++) {
         int res = WebRequest("POST", url, headers, LICENSE_TIMEOUT_MS,
                              post, result, result_headers);
         if(res == 200 || res == 201)
            return ParseActivationResponse(CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8));
         if(res == 409) return CheckStatus();
         Sleep(2000);
      }
      return false;
   }

   bool CheckStatus(void)
   {
      string url     = m_api_base_url + "/license/status";
      string headers = "Authorization: Bearer " + m_device_token + "\r\n";
      char post[], result[];
      string result_headers;
      int res = WebRequest("GET", url, headers, LICENSE_TIMEOUT_MS,
                           post, result, result_headers);
      if(res == 200) {
         string json = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
         m_is_valid  = (StringFind(json, "\"is_valid\":true") >= 0);
         return m_is_valid;
      }
      return false;
   }

   bool SendHeartbeat(void)
   {
      if(TimeCurrent() - m_last_heartbeat < LICENSE_HEARTBEAT_SECONDS) return true;
      string nonce   = GenerateNonce();
      string url     = m_api_base_url + "/license/heartbeat";
      string body    = StringFormat("{\"device_id\":\"%s\",\"nonce\":\"%s\"}",
                                    m_device_id, nonce);
      string headers = StringFormat(
         "Content-Type: application/json\r\nAuthorization: Bearer %s\r\n",
         m_device_token
      );
      char post[], result[];
      string result_headers;
      StringToCharArray(body, post, 0, WHOLE_ARRAY, CP_UTF8);
      int res = WebRequest("POST", url, headers, LICENSE_TIMEOUT_MS,
                           post, result, result_headers);
      if(res == 204) { m_last_heartbeat = TimeCurrent(); return true; }
      if(res == 403) { Print("LicenseChecker: تعلیق شد"); m_is_valid = false; return false; }
      return false;
   }

   bool OnTick(void)
   {
      if(!m_is_valid) return false;
      if(!SendHeartbeat()) return false;
      if(m_expires_at > 0 && TimeCurrent() > m_expires_at) {
         Print("LicenseChecker: منقضی شد");
         m_is_valid = false;
         return false;
      }
      return true;
   }

   bool     IsValid(void)   const { return m_is_valid;   }
   string   GetPlan(void)   const { return m_plan;       }
   datetime ExpiresAt(void) const { return m_expires_at; }

   void Revoke(void)
   {
      string url     = m_api_base_url + "/license/revoke-device";
      string body    = StringFormat("{\"device_id\":\"%s\"}", m_device_id);
      string headers = StringFormat(
         "Content-Type: application/json\r\nAuthorization: Bearer %s\r\n",
         m_device_token
      );
      char post[], result[];
      string result_headers;
      StringToCharArray(body, post, 0, WHOLE_ARRAY, CP_UTF8);
      WebRequest("POST", url, headers, LICENSE_TIMEOUT_MS, post, result, result_headers);
      m_is_valid = false;
      Print("LicenseChecker: لغو شد");
   }

private:
   bool ParseActivationResponse(const string json)
   {
      int ts = StringFind(json, "\"token\":\"");
      if(ts >= 0) {
         ts += 9;
         int te = StringFind(json, "\"", ts);
         if(te > ts) m_device_token = StringSubstr(json, ts, te - ts);
      }
      int ps = StringFind(json, "\"plan\":\"");
      if(ps >= 0) {
         ps += 8;
         int pe = StringFind(json, "\"", ps);
         if(pe > ps) m_plan = StringSubstr(json, ps, pe - ps);
      }
      m_is_valid       = (m_device_token != "");
      m_last_heartbeat = TimeCurrent();
      return m_is_valid;
   }

   string GenerateNonce(void)
   {
      string chars = "abcdefghijklmnopqrstuvwxyz0123456789";
      string nonce = "";
      MathSrand((uint)TimeCurrent());
      for(int i = 0; i < 32; i++)
         nonce += StringSubstr(chars, MathRand() % StringLen(chars), 1);
      return nonce;
   }
};

#endif // LICENSE_CHECKER_MQH
