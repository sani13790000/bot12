//+------------------------------------------------------------------+
//| APIClient.mqh - Secure HTTP client for Galaxy Vast EA            |
//| Security:                                                        |
//|   - Bearer token in Authorization header                         |
//|   - SSL certificate verification                                 |
//|   - Timeout enforced                                             |
//|   - No secrets in URL query params                               |
//+------------------------------------------------------------------+
#ifndef GALAXY_VAST_API_CLIENT_MQH
#define GALAXY_VAST_API_CLIENT_MQH

#include "Config.mqh"

//+------------------------------------------------------------------+
//| Secure POST request with Bearer token auth                       |
//+------------------------------------------------------------------+
bool APIPost(
   const string endpoint,     // e.g. "/api/v1/analysis/smc"
   const string jsonBody,
   string &responseBody
) {
   string url = InpAPIBaseURL + endpoint;
   
   // Validate URL (prevent SSRF to internal networks)
   if(StringFind(url, "http://169.254") >= 0 ||   // AWS metadata
      StringFind(url, "http://10.")     >= 0 ||   // private class A
      StringFind(url, "http://192.168") >= 0) {   // private class C
      Print("[GalaxyVast] SECURITY: Blocked request to private network: ", url);
      return false;
   }
   
   // Headers: Authorization + Content-Type
   string headers =
      "Authorization: Bearer " + InpAPIToken + "\r\n" +
      "Content-Type: application/json\r\n" +
      "Accept: application/json\r\n";
   
   char   postData[];
   char   result[];
   string resultHeaders;
   
   StringToCharArray(jsonBody, postData, 0, StringLen(jsonBody), CP_UTF8);
   
   int statusCode = WebRequest(
      "POST",
      url,
      headers,
      InpAPITimeoutMs,
      postData,
      result,
      resultHeaders
   );
   
   if(statusCode == -1) {
      int err = GetLastError();
      if(err == 4014) {
         Print("[GalaxyVast] ERROR: URL not in MT5 allowed list: ", url);
         Print("[GalaxyVast] Add '", InpAPIBaseURL, "' to MT5 Tools > Options > Expert Advisors");
      } else {
         Print("[GalaxyVast] HTTP error: ", err, " for ", url);
      }
      return false;
   }
   
   if(statusCode == 401) {
      Print("[GalaxyVast] ERROR: Authentication failed. Check your API token.");
      return false;
   }
   
   if(statusCode < 200 || statusCode >= 300) {
      Print("[GalaxyVast] HTTP ", statusCode, " for ", url);
      return false;
   }
   
   responseBody = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   return true;
}

//+------------------------------------------------------------------+
//| Secure GET request with Bearer token auth                        |
//+------------------------------------------------------------------+
bool APIGet(
   const string endpoint,
   string &responseBody
) {
   string url = InpAPIBaseURL + endpoint;
   
   string headers =
      "Authorization: Bearer " + InpAPIToken + "\r\n" +
      "Accept: application/json\r\n";
   
   char   postData[];
   char   result[];
   string resultHeaders;
   
   int statusCode = WebRequest(
      "GET",
      url,
      headers,
      InpAPITimeoutMs,
      postData,
      result,
      resultHeaders
   );
   
   if(statusCode == -1) {
      Print("[GalaxyVast] GET error for ", url, ": ", GetLastError());
      return false;
   }
   
   if(statusCode == 401) {
      Print("[GalaxyVast] ERROR: Authentication failed.");
      return false;
   }
   
   if(statusCode < 200 || statusCode >= 300) {
      Print("[GalaxyVast] GET HTTP ", statusCode);
      return false;
   }
   
   responseBody = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
   return true;
}

#endif // GALAXY_VAST_API_CLIENT_MQH
