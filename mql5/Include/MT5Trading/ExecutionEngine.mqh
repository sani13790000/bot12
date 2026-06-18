//+------------------------------------------------------------------+
//|                                              ExecutionEngine.mqh |
//|                         ÙÙØªÙØ± Ø§Ø¬Ø±Ø§Û ÙØ±Ú©Ø²Û Ø³ÛØ³ØªÙ ÙØ¹Ø§ÙÙØ§ØªÛ Ø­Ø±ÙÙâØ§Û |
//|                                                                  |
//| Ø§ÛÙ ÙØ§ÛÙ ÙØ³ØªÙ Ø§Ø¬Ø±Ø§ÛÛ Ø³ÛØ³ØªÙ Ø§Ø³Øª Ú©Ù ØªÙØ§Ù ÙØ§ÚÙÙâÙØ§ Ø±Ø§ Ø¨Ù ÙÙ ÙØµÙ    |
//| ÙÛâÚ©ÙØ¯. ÙØ¸ÛÙÙ ÙÙØ§ÙÙÚ¯Û Ø¨ÛÙ SMCØ Price ActionØ DecisionØ RiskØ    |
//| Trade Ù Notification Ø±Ø§ Ø¯Ø§Ø±Ø¯. ØªÙØ§Ù ÚØ±Ø®Ù ÙØ¹Ø§ÙÙØ§ØªÛ Ø§Ø² ØªØ­ÙÛÙ ØªØ§   |
//| Ø§Ø¬Ø±Ø§ Ù ÙØ¯ÛØ±ÛØª Ù¾ÙØ²ÛØ´Ù Ø¯Ø± Ø§ÛÙØ¬Ø§ Ú©ÙØªØ±Ù ÙÛâØ´ÙØ¯.                    |
//+------------------------------------------------------------------+
#pragma once
#include "Config.mqh"
#include "TradeManager.mqh"
#include "RiskManager.mqh"
#include "PositionManager.mqh"
#include "DrawManager.mqh"
#include "NotificationManager.mqh"
#include "StrategyLoader.mqh"
#include "LicenseChecker.mqh"
#include "DecisionConnector.mqh"
#include "SMCAnalyzer.mqh"
#include "PAAnalyzer.mqh"
#include "Helpers.mqh"

//--- Ø«Ø§Ø¨ØªâÙØ§Û ÙÙØªÙØ± Ø§Ø¬Ø±Ø§
#define ENGINE_VERSION      "2.0.0"
#define ENGINE_TICK_MIN_MS  100
#define ENGINE_MAX_ERRORS   10

//--- Ø­Ø§ÙØªâÙØ§Û ÙÙØªÙØ±
enum ENUM_ENGINE_STATE {
   ENGINE_STOPPED = 0,      // ÙØªÙÙÙ
   ENGINE_RUNNING = 1,      // Ø¯Ø± Ø­Ø§Ù Ø§Ø¬Ø±Ø§
   ENGINE_PAUSED  = 2,      // ÙÚ©Ø«
   ENGINE_ERROR   = 3       // Ø®Ø·Ø§
};

//--- ÙØªÛØ¬Ù ÛÚ© ÚØ±Ø®Ù Ø§Ø¬Ø±Ø§
struct EngineTickResult {
   bool              analysisRun;      // Ø¢ÛØ§ ØªØ­ÙÛÙ Ø§ÙØ¬Ø§Ù Ø´Ø¯Ø
   bool              decisionMade;     // Ø¢ÛØ§ ØªØµÙÛÙ Ú¯Ø±ÙØªÙ Ø´Ø¯Ø
   bool              tradeOpened;      // Ø¢ÛØ§ ÙØ¹Ø§ÙÙÙ Ø¨Ø§Ø² Ø´Ø¯Ø
   bool              positionsManaged; // Ø¢ÛØ§ Ù¾ÙØ²ÛØ´ÙâÙØ§ ÙØ¯ÛØ±ÛØª Ø´Ø¯ÙØ¯Ø
   string            decisionReason;   // Ø¯ÙÛÙ ØªØµÙÛÙ
   double            finalScore;       // Ø§ÙØªÛØ§Ø² ÙÙØ§ÛÛ
   datetime          tickTime;         // Ø²ÙØ§Ù ØªÛÚ©
};

//+------------------------------------------------------------------+
//| Ú©ÙØ§Ø³ ÙÙØªÙØ± Ø§Ø¬Ø±Ø§Û ÙØ±Ú©Ø²Û                                          |
//+------------------------------------------------------------------+
class CExecutionEngine {
private:
   CTradeManager*       m_tradeManager;
   CRiskManager*        m_riskManager;
   CPositionManager*    m_positionManager;
   CDrawManager*        m_drawManager;
   CNotificationManager* m_notificationManager;
   CStrategyLoader*     m_strategyLoader;
   CLicenseChecker*     m_licenseChecker;
   CDecisionConnector*  m_decisionConnector;
   CSMCAnalyzer*        m_smcAnalyzer;
   CPAAnalyzer*         m_paAnalyzer;

   ENUM_ENGINE_STATE    m_state;
   bool                 m_initialized;
   int                  m_errorCount;
   datetime             m_lastTickTime;
   datetime             m_lastAnalysisTime;
   long                 m_totalTicks;
   long                 m_totalAnalyses;
   long                 m_totalDecisions;
   long                 m_totalTradesOpened;
   datetime             m_startTime;
   string               m_lastError;
   string               m_symbol;
   ENUM_TIMEFRAMES      m_primaryTF;
   int                  m_analysisIntervalSec;
   bool                 m_enableAutoTrading;
   bool                 m_enableNotifications;
   bool                 m_enableDrawing;

   bool                 InitializeModules();
   bool                 RunAnalysisCycle();
   bool                 RunDecisionCycle(EngineTickResult &result);
   bool                 RunTradingCycle(EngineTickResult &result);
   bool                 RunPositionManagement();
   bool                 ShouldRunAnalysis();
   void                 UpdateStats(const EngineTickResult &result);

public:
                        CExecutionEngine();
                       ~CExecutionEngine();
   bool                 Initialize(const string symbol, const ENUM_TIMEFRAMES tf);
   void                 Deinitialize();
   bool                 Start();
   void                 Stop();
   void                 Pause();
   void                 Resume();
   EngineTickResult     OnTick();
   ENUM_ENGINE_STATE    GetState()         const { return m_state; }
   bool                 IsRunning()        const { return m_state == ENGINE_RUNNING; }
   bool                 IsInitialized()    const { return m_initialized; }
   string               GetLastError()     const { return m_lastError; }
   string               GetVersion()       const { return ENGINE_VERSION; }
   string               GetStatusReport();
   string               GetStatisticsReport();
};

CExecutionEngine::CExecutionEngine() {
   m_tradeManager=NULL; m_riskManager=NULL; m_positionManager=NULL;
   m_drawManager=NULL; m_notificationManager=NULL; m_strategyLoader=NULL;
   m_licenseChecker=NULL; m_decisionConnector=NULL;
   m_smcAnalyzer=NULL; m_paAnalyzer=NULL;
   m_state=ENGINE_STOPPED; m_initialized=false; m_errorCount=0;
   m_totalTicks=0; m_totalAnalyses=0; m_totalDecisions=0; m_totalTradesOpened=0;
   m_startTime=0; m_lastTickTime=0; m_lastAnalysisTime=0; m_lastError="";
   m_symbol=""; m_primaryTF=PERIOD_H1; m_analysisIntervalSec=60;
   m_enableAutoTrading=false; m_enableNotifications=true; m_enableDrawing=true;
}

CExecutionEngine::~CExecutionEngine() { Deinitialize(); }

bool CExecutionEngine::Initialize(const string symbol, const ENUM_TIMEFRAMES tf) {
   m_symbol=symbol; m_primaryTF=tf; m_startTime=TimeCurrent();
   LogMessage(StringFormat("🚀 موتور اجرا در حال راه‌اندازی... نماد: %s تایم‌فریم: %s", symbol, EnumToString(tf)), "INFO");
   if(!InitializeModules()) { m_state=ENGINE_ERROR; return false; }
   m_initialized=true; m_state=ENGINE_STOPPED;
   LogMessage("✅ موتور اجرا با موفقیت راه‌اندازی شد.", "INFO");
   return true;
}

bool CExecutionEngine::InitializeModules() {
   m_licenseChecker=new CLicenseChecker();
   if(!m_licenseChecker.Validate()) { m_lastError="❌ لایسنس معتبر نیست"; LogMessage(m_lastError, "ERROR"); return false; }
   m_riskManager=new CRiskManager(m_symbol);
   m_riskManager.InitializeATR(14,m_primaryTF);
   m_tradeManager=new CTradeManager(m_symbol);
   m_tradeManager.SetRiskManager(m_riskManager);
   m_tradeManager.SetMagicNumber(MagicNumber);
   m_tradeManager.SetMaxSlippage(MaxSlippage);
   m_positionManager=new CPositionManager(m_symbol,MagicNumber);
   m_positionManager.SetRiskManager(m_riskManager);
   m_decisionConnector=new CDecisionConnector();
   m_decisionConnector.SetApiUrl(ApiUrl);
   m_decisionConnector.SetApiKey(ApiKey);
   m_decisionConnector.SetSymbol(m_symbol);
   m_drawManager=new CDrawManager();
   m_notificationManager=new CNotificationManager();
   m_notificationManager.SetTelegramToken(TelegramToken);
   m_notificationManager.SetTelegramChatId(TelegramChatId);
   m_notificationManager.SetEnabled(EnableTelegramAlerts);
   m_smcAnalyzer=new CSMCAnalyzer(m_symbol,m_primaryTF);
   m_paAnalyzer=new CPAAnalyzer(m_symbol,m_primaryTF);
   m_strategyLoader=new CStrategyLoader();
   m_strategyLoader.SetDecisionConnector(m_decisionConnector);
   return true;
}

bool CExecutionEngine::Start() {
   if(!m_initialized) { m_lastError="ÙÙØªÙØ± ÙÙØ¯Ø§Ø±Ø¯ÙÛ ÙØ´Ø¯Ù"; return false; }
   if(m_state==ENGINE_RUNNING) return true;
   m_state=ENGINE_RUNNING; m_enableAutoTrading=true;
   LogMessage("▶️ موتور اجرا شروع به کار کرد.", "INFO");
   if(m_notificationManager!=NULL)
      m_notificationManager.SendSystemAlert("â¶ï¸ Ø±Ø¨Ø§Øª ÙØ¹Ø§ÙÙØ§ØªÛ ÙØ¹Ø§Ù Ø´Ø¯\nð ÙÙØ§Ø¯: "+m_symbol);
   return true;
}

void CExecutionEngine::Stop() {
   m_state=ENGINE_STOPPED; m_enableAutoTrading=false;
   LogMessage("⏹ موتور متوقف شد.", "INFO");
   if(m_notificationManager!=NULL)
      m_notificationManager.SendSystemAlert("â¹ Ø±Ø¨Ø§Øª ÙØ¹Ø§ÙÙØ§ØªÛ ÙØªÙÙÙ Ø´Ø¯");
}

void CExecutionEngine::Pause() {
   if(m_state==ENGINE_RUNNING) {
      m_state=ENGINE_PAUSED;
      LogMessage("⏸ موتور در حالت مکث", "INFO");
      if(m_notificationManager!=NULL)
         m_notificationManager.SendSystemAlert("â¸ Ø±Ø¨Ø§Øª Ø¯Ø± Ø­Ø§ÙØª ÙÚ©Ø« ÙØ±Ø§Ø± Ú¯Ø±ÙØª");
   }
}

void CExecutionEngine::Resume() {
   if(m_state==ENGINE_PAUSED) {
      m_state=ENGINE_RUNNING;
      LogMessage("▶️ موتور از مکث خارج شد", "INFO");
      if(m_notificationManager!=NULL)
         m_notificationManager.SendSystemAlert("â¶ï¸ Ø±Ø¨Ø§Øª Ø§Ø² ÙÚ©Ø« Ø®Ø§Ø±Ø¬ Ø´Ø¯");
   }
}

bool CExecutionEngine::ShouldRunAnalysis() {
   if(m_lastAnalysisTime==0) return true;
   return (TimeCurrent()-m_lastAnalysisTime)>=m_analysisIntervalSec;
}

EngineTickResult CExecutionEngine::OnTick() {
   EngineTickResult result;
   result.analysisRun=false; result.decisionMade=false;
   result.tradeOpened=false; result.positionsManaged=false;
   result.finalScore=0; result.tickTime=TimeCurrent(); result.decisionReason="";
   m_totalTicks++; m_lastTickTime=TimeCurrent();
   if(m_state!=ENGINE_RUNNING) return result;
   if(m_positionManager!=NULL) { m_positionManager.ManageAll(); result.positionsManaged=true; }
   if(ShouldRunAnalysis()) {
      m_lastAnalysisTime=TimeCurrent(); m_totalAnalyses++;
      if(RunAnalysisCycle()) {
         result.analysisRun=true;
         if(RunDecisionCycle(result)) {
            result.decisionMade=true; m_totalDecisions++;
            if(m_enableAutoTrading && result.finalScore>0) {
               if(RunTradingCycle(result)) { result.tradeOpened=true; m_totalTradesOpened++; }
            }
         }
      }
   }
   UpdateStats(result);
   return result;
}

bool CExecutionEngine::RunAnalysisCycle() {
   bool smcOk=false,paOk=false;
   if(m_smcAnalyzer!=NULL) {
      smcOk=m_smcAnalyzer.Analyze();
      if(smcOk && m_enableDrawing && m_drawManager!=NULL) {
         SMCAnalysisResult smcResult=m_smcAnalyzer.GetResult();
         m_drawManager.DrawSMCZones(smcResult);
      }
   }
   if(m_paAnalyzer!=NULL) paOk=m_paAnalyzer.Analyze();
   return smcOk||paOk;
}

bool CExecutionEngine::RunDecisionCycle(EngineTickResult &result) {
   if(m_decisionConnector==NULL) return false;
   DecisionRequest req;
   req.symbol=m_symbol; req.timeframe=EnumToString(m_primaryTF); req.timestamp=TimeCurrent();
   if(m_smcAnalyzer!=NULL) req.smcData=m_smcAnalyzer.GetJsonData();
   if(m_paAnalyzer!=NULL)  req.paData=m_paAnalyzer.GetJsonData();
   if(m_riskManager!=NULL) req.riskData=m_riskManager.GetRiskJsonData();
   DecisionResponse resp=m_decisionConnector.GetDecision(req);
   result.finalScore=resp.score; result.decisionReason=resp.reason;
   return resp.valid;
}

bool CExecutionEngine::RunTradingCycle(EngineTickResult &result) {
   if(m_tradeManager==NULL||m_riskManager==NULL) return false;
   if(!m_riskManager.CanOpenTrade()) { result.decisionReason+=" | ÙØ­Ø¯ÙØ¯ÛØª Ø±ÛØ³Ú© ÙØ¹Ø§Ù"; return false; }
   TradeSignal signal=m_decisionConnector.GetTradeSignal();
   string errMsg;
   bool ok=m_tradeManager.OpenTrade(signal,errMsg);
   if(ok && m_notificationManager!=NULL) {
      m_notificationManager.SendTradeEntry(
         signal.direction==POSITION_TYPE_BUY?"Ø®Ø±ÛØ¯":"ÙØ±ÙØ´",
         m_symbol, signal.entryPrice, signal.stopLoss, signal.takeProfit,
         signal.volume, result.finalScore
      );
   }
   return ok;
}

void CExecutionEngine::UpdateStats(const EngineTickResult &result) {
   if(m_totalTicks%1000==0)
      LogMessage(StringFormat("📊 آمار موتور: تیک=%I64d | تحلیل=%I64d | تصمیم=%I64d | معاملون=%I64d",
            m_totalTicks, m_totalAnalyses, m_totalDecisions, m_totalTradesOpened), "INFO");
}

void CExecutionEngine::Deinitialize() {
   Stop();
   if(m_tradeManager)        { delete m_tradeManager;        m_tradeManager=NULL; }
   if(m_riskManager)         { delete m_riskManager;         m_riskManager=NULL; }
   if(m_positionManager)     { delete m_positionManager;     m_positionManager=NULL; }
   if(m_drawManager)         { delete m_drawManager;         m_drawManager=NULL; }
   if(m_notificationManager) { delete m_notificationManager; m_notificationManager=NULL; }
   if(m_strategyLoader)      { delete m_strategyLoader;      m_strategyLoader=NULL; }
   if(m_licenseChecker)      { delete m_licenseChecker;      m_licenseChecker=NULL; }
   if(m_decisionConnector)   { delete m_decisionConnector;   m_decisionConnector=NULL; }
   if(m_smcAnalyzer)         { delete m_smcAnalyzer;         m_smcAnalyzer=NULL; }
   if(m_paAnalyzer)          { delete m_paAnalyzer;          m_paAnalyzer=NULL; }
   m_initialized=false;
   LogMessage("🔴 موتور اجرا آزادسازی شد.", "INFO");
}

string CExecutionEngine::GetStatusReport() {
   string states[]={"ÙØªÙÙÙ","Ø¯Ø± Ø­Ø§Ù Ø§Ø¬Ø±Ø§","ÙÚ©Ø«","Ø®Ø·Ø§"};
   string r="âï¸ ÙØ¶Ø¹ÛØª ÙÙØªÙØ± Ø§Ø¬Ø±Ø§\n";
   r+="ÙØ³Ø®Ù: "+ENGINE_VERSION+"\n";
   r+="Ø­Ø§ÙØª: "+states[(int)m_state]+"\n";
   r+="ÙÙØ§Ø¯: "+m_symbol+" | ØªØ§ÛÙâÙØ±ÛÙ: "+EnumToString(m_primaryTF)+"\n";
   if(m_riskManager!=NULL) r+=m_riskManager.GetRiskReport();
   return r;
}

string CExecutionEngine::GetStatisticsReport() {
   string r="ð Ø¢ÙØ§Ø± ÙÙØªÙØ±\n";
   r+=StringFormat("Ú©Ù ØªÛÚ©: %I64d\n",m_totalTicks);
   r+=StringFormat("Ú©Ù ØªØ­ÙÛÙ: %I64d\n",m_totalAnalyses);
   r+=StringFormat("Ú©Ù ØªØµÙÛÙ: %I64d\n",m_totalDecisions);
   r+=StringFormat("Ú©Ù ÙØ¹Ø§ÙÙÙ: %I64d\n",m_totalTradesOpened);
   long uptime=(long)(TimeCurrent()-m_startTime);
   r+=StringFormat("Ø¢Ù¾âØªØ§ÛÙ: %d:%02d:%02d\n",(int)(uptime/3600),(int)((uptime%3600)/60),(int)(uptime%60));
   return r;
}
//+------------------------------------------------------------------+