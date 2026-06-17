//+------------------------------------------------------------------+
//|                                              ExecutionEngine.mqh |
//|                         موتور اجرای مرکزی سیستم معاملاتی حرفه‌ای |
//|                                                                  |
//| این فایل هسته اجرایی سیستم است که تمام ماژول‌ها را به هم وصل    |
//| می‌کند. وظیفه هماهنگی بین SMC، Price Action، Decision، Risk،    |
//| Trade و Notification را دارد. تمام چرخه معاملاتی از تحلیل تا   |
//| اجرا و مدیریت پوزیشن در اینجا کنترل می‌شود.                    |
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

//--- ثابت‌های موتور اجرا
#define ENGINE_VERSION      "2.0.0"
#define ENGINE_TICK_MIN_MS  100
#define ENGINE_MAX_ERRORS   10

//--- حالت‌های موتور
enum ENUM_ENGINE_STATE {
   ENGINE_STOPPED = 0,      // متوقف
   ENGINE_RUNNING = 1,      // در حال اجرا
   ENGINE_PAUSED  = 2,      // مکث
   ENGINE_ERROR   = 3       // خطا
};

//--- نتیجه یک چرخه اجرا
struct EngineTickResult {
   bool              analysisRun;      // آیا تحلیل انجام شد؟
   bool              decisionMade;     // آیا تصمیم گرفته شد؟
   bool              tradeOpened;      // آیا معامله باز شد؟
   bool              positionsManaged; // آیا پوزیشن‌ها مدیریت شدند؟
   string            decisionReason;   // دلیل تصمیم
   double            finalScore;       // امتیاز نهایی
   datetime          tickTime;         // زمان تیک
};

//+------------------------------------------------------------------+
//| کلاس موتور اجرای مرکزی                                          |
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
   Print("🚀 موتور اجرا در حال راه‌اندازی... نماد: ",symbol," تایم‌فریم: ",EnumToString(tf));
   if(!InitializeModules()) { m_state=ENGINE_ERROR; return false; }
   m_initialized=true; m_state=ENGINE_STOPPED;
   Print("✅ موتور اجرا با موفقیت راه‌اندازی شد.");
   return true;
}

bool CExecutionEngine::InitializeModules() {
   m_licenseChecker=new CLicenseChecker();
   if(!m_licenseChecker.Validate()) { m_lastError="❌ لایسنس معتبر نیست"; Print(m_lastError); return false; }
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
   if(!m_initialized) { m_lastError="موتور مقداردهی نشده"; return false; }
   if(m_state==ENGINE_RUNNING) return true;
   m_state=ENGINE_RUNNING; m_enableAutoTrading=true;
   Print("▶️ موتور اجرا شروع به کار کرد.");
   if(m_notificationManager!=NULL)
      m_notificationManager.SendSystemAlert("▶️ ربات معاملاتی فعال شد\n📊 نماد: "+m_symbol);
   return true;
}

void CExecutionEngine::Stop() {
   m_state=ENGINE_STOPPED; m_enableAutoTrading=false;
   Print("⏹ موتور متوقف شد.");
   if(m_notificationManager!=NULL)
      m_notificationManager.SendSystemAlert("⏹ ربات معاملاتی متوقف شد");
}

void CExecutionEngine::Pause() {
   if(m_state==ENGINE_RUNNING) {
      m_state=ENGINE_PAUSED;
      Print("⏸ موتور در حالت مکث");
      if(m_notificationManager!=NULL)
         m_notificationManager.SendSystemAlert("⏸ ربات در حالت مکث قرار گرفت");
   }
}

void CExecutionEngine::Resume() {
   if(m_state==ENGINE_PAUSED) {
      m_state=ENGINE_RUNNING;
      Print("▶️ موتور از مکث خارج شد");
      if(m_notificationManager!=NULL)
         m_notificationManager.SendSystemAlert("▶️ ربات از مکث خارج شد");
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
   if(!m_riskManager.CanOpenTrade()) { result.decisionReason+=" | محدودیت ریسک فعال"; return false; }
   TradeSignal signal=m_decisionConnector.GetTradeSignal();
   string errMsg;
   bool ok=m_tradeManager.OpenTrade(signal,errMsg);
   if(ok && m_notificationManager!=NULL) {
      m_notificationManager.SendTradeEntry(
         signal.direction==POSITION_TYPE_BUY?"خرید":"فروش",
         m_symbol, signal.entryPrice, signal.stopLoss, signal.takeProfit,
         signal.volume, result.finalScore
      );
   }
   return ok;
}

void CExecutionEngine::UpdateStats(const EngineTickResult &result) {
   if(m_totalTicks%1000==0)
      Print("📊 آمار موتور: تیک=",m_totalTicks," | تحلیل=",m_totalAnalyses,
            " | تصمیم=",m_totalDecisions," | معامله=",m_totalTradesOpened);
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
   Print("🔴 موتور اجرا آزادسازی شد.");
}

string CExecutionEngine::GetStatusReport() {
   string states[]={"متوقف","در حال اجرا","مکث","خطا"};
   string r="⚙️ وضعیت موتور اجرا\n";
   r+="نسخه: "+ENGINE_VERSION+"\n";
   r+="حالت: "+states[(int)m_state]+"\n";
   r+="نماد: "+m_symbol+" | تایم‌فریم: "+EnumToString(m_primaryTF)+"\n";
   if(m_riskManager!=NULL) r+=m_riskManager.GetRiskReport();
   return r;
}

string CExecutionEngine::GetStatisticsReport() {
   string r="📈 آمار موتور\n";
   r+=StringFormat("کل تیک: %I64d\n",m_totalTicks);
   r+=StringFormat("کل تحلیل: %I64d\n",m_totalAnalyses);
   r+=StringFormat("کل تصمیم: %I64d\n",m_totalDecisions);
   r+=StringFormat("کل معامله: %I64d\n",m_totalTradesOpened);
   long uptime=(long)(TimeCurrent()-m_startTime);
   r+=StringFormat("آپ‌تایم: %d:%02d:%02d\n",(int)(uptime/3600),(int)((uptime%3600)/60),(int)(uptime%60));
   return r;
}
//+------------------------------------------------------------------+