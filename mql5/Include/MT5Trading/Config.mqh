//+------------------------------------------------------------------+
//|                                                    Config.mqh      |
//|                         Ø³ÛØ³ØªÙ ÙØ¹Ø§ÙÙÙâÚ¯Ø±Û Ø­Ø±ÙÙâØ§Û MT5               |
//|                                                                    |
//| ØªÙØ¶ÛØ­ ÙØ§Ø±Ø³Û:                                                       |
//| Ø§ÛÙ ÙØ§ÛÙ Ø´Ø§ÙÙ ØªÙØ§Ù ØªÙØ¸ÛÙØ§Øª ÙØ§Ø¨Ù ØªØºÛÛØ± Ø³ÛØ³ØªÙ ÙØ¹Ø§ÙÙÙâÚ¯Ø±Û Ø§Ø³Øª.        |
//| ØªÙØ§Ù Ù¾Ø§Ø±Ø§ÙØªØ±ÙØ§ Ø§Ø² Ø§ÛÙØ¬Ø§ Ø®ÙØ§ÙØ¯Ù ÙÛâØ´ÙÙØ¯ Ù ÙØ§Ø¨Ù ØªÙØ¸ÛÙ ÙØ³ØªÙØ¯.         |
//| ÙØ± Ú¯Ø±ÙÙ Ø§Ø² ØªÙØ¸ÛÙØ§Øª Ø¨Ø§ ØªÙØ¶ÛØ­ ÙØ§Ø±Ø³Û ÙØ´Ø®Øµ Ø´Ø¯Ù Ø§Ø³Øª.                   |
//+------------------------------------------------------------------+
#property strict

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª Ø§ØµÙÛ Ø±Ø¨Ø§Øª =====                                      |
//+------------------------------------------------------------------+
input string   RobotName         = "MT5TradingSystem";  // ÙØ§Ù Ø±Ø¨Ø§Øª
input int      MagicNumber        = 20240101;            // Ø´ÙØ§Ø±Ù Ø¬Ø§Ø¯ÙÛÛ
input bool     RobotEnabled       = true;                // Ø±Ø¨Ø§Øª ÙØ¹Ø§Ù Ø¨Ø§Ø´Ø¯
input bool     TradeEnabled       = true;                // ÙØ¹Ø§ÙÙÙ ÙØ¹Ø§Ù Ø¨Ø§Ø´Ø¯

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª ÙÙØ§Ø¯ =====                                           |
//+------------------------------------------------------------------+
input string   AllowedSymbol      = "XAUUSD";            // ÙÙØ§Ø¯ ÙØ¬Ø§Ø² (Ø®Ø§ÙÛ = ÙÙØ§Ø¯ ÙØ¹Ø§Ù)
input bool     UseCurrentSymbol   = true;                // Ø§Ø² ÙÙØ§Ø¯ ÙØ¹Ø§Ù ÚØ§Ø±Øª Ø§Ø³ØªÙØ§Ø¯Ù Ú©Ù

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª ÙØ¯ÛØ±ÛØª Ø±ÛØ³Ú© =====                                   |
//+------------------------------------------------------------------+
input double   RiskPercent        = 1.0;                 // Ø¯Ø±ØµØ¯ Ø±ÛØ³Ú© ÙØ± ÙØ¹Ø§ÙÙÙ
input double   FixedLot           = 0.0;                 // ÙØ§Øª Ø«Ø§Ø¨Øª (0 = ÙØ­Ø§Ø³Ø¨Ù Ø§ØªÙÙØ§ØªÛÚ©)
input double   MinLot             = 0.01;                // Ø­Ø¯Ø§ÙÙ ÙØ§Øª
input double   MaxLot             = 10.0;                // Ø­Ø¯Ø§Ú©Ø«Ø± ÙØ§Øª
input bool     UseEquityForRisk   = false;               // Ø§Ø³ØªÙØ§Ø¯Ù Ø§Ø² Ø§Ú©ÙØ¦ÛØªÛ Ø¨Ø±Ø§Û Ø±ÛØ³Ú©
input double   MaxDailyLossPercent = 5.0;                // Ø­Ø¯Ø§Ú©Ø«Ø± Ø¶Ø±Ø± Ø±ÙØ²Ø§ÙÙ (%)
input double   MaxDrawdownPercent = 10.0;                // Ø­Ø¯Ø§Ú©Ø«Ø± drawdown (%)
input int      MaxOpenTrades      = 3;                   // Ø­Ø¯Ø§Ú©Ø«Ø± ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²
input int      MaxDailyTrades     = 10;                  // Ø­Ø¯Ø§Ú©Ø«Ø± ÙØ¹Ø§ÙÙØ§Øª Ø±ÙØ²Ø§ÙÙ
input int      MaxSpread          = 30;                  // Ø­Ø¯Ø§Ú©Ø«Ø± Ø§Ø³Ù¾Ø±Ø¯ ÙØ¬Ø§Ø² (Ù¾ÙÛÙØª)

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª SL/TP =====                                         |
//+------------------------------------------------------------------+
input double   DefaultRR          = 2.0;                 // ÙØ³Ø¨Øª Ù¾ÛØ´âÙØ±Ø¶ Ø³ÙØ¯ Ø¨Ù Ø±ÛØ³Ú©
input double   ATRMultiplierSL    = 1.5;                 // Ø¶Ø±ÛØ¨ ATR Ø¨Ø±Ø§Û StopLoss
input double   ATRMultiplierTP    = 3.0;                 // Ø¶Ø±ÛØ¨ ATR Ø¨Ø±Ø§Û TakeProfit
input int      ATRPeriod          = 14;                  // Ø¯ÙØ±Ù ATR
input double   MinRR              = 1.5;                 // Ø­Ø¯Ø§ÙÙ ÙØ³Ø¨Øª Ø³ÙØ¯ Ø¨Ù Ø±ÛØ³Ú©

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª Trailing Stop Ù Break Even =====                    |
//+------------------------------------------------------------------+
input bool     UseTrailingStop    = true;                // Ø§Ø³ØªÙØ§Ø¯Ù Ø§Ø² Trailing Stop
input double   TrailingPoints     = 200;                 // ÙØ§ØµÙÙ Trailing Stop (Ù¾ÙÛÙØª)
input double   TrailingStep       = 50;                  // Ú¯Ø§Ù Ø¬Ø§Ø¨Ø¬Ø§ÛÛ Trailing (Ù¾ÙÛÙØª)
input bool     UseBreakEven       = true;                // Ø§Ø³ØªÙØ§Ø¯Ù Ø§Ø² Break Even
input double   BreakEvenTrigger   = 100;                 // ÙØ¹Ø§Ù Ø´Ø¯Ù BE Ø¨Ø¹Ø¯ Ø§Ø² (Ù¾ÙÛÙØª)
input double   BreakEvenOffset    = 5;                   // Ø¨Ø§ÙØ± Break Even (Ù¾ÙÛÙØª)

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª Smart Money Concept =====                            |
//+------------------------------------------------------------------+
input bool     SMCEnabled         = true;                // SMC ÙØ¹Ø§Ù Ø¨Ø§Ø´Ø¯
input bool     DetectBOS          = true;                // ØªØ´Ø®ÛØµ Break of Structure
input bool     DetectCHOCH        = true;                // ØªØ´Ø®ÛØµ Change of Character
input bool     DetectOrderBlocks  = true;                // ØªØ´Ø®ÛØµ Order Block
input bool     DetectFVG          = true;                // ØªØ´Ø®ÛØµ Fair Value Gap
input bool     DetectLiquidity    = true;                // ØªØ´Ø®ÛØµ ÙÙØ¯ÛÙÚ¯Û
input bool     DetectKillZones    = true;                // ØªØ´Ø®ÛØµ Kill Zones
input int      SMCLookback        = 100;                 // ØªØ¹Ø¯Ø§Ø¯ Ú©ÙØ¯Ù Ø¨Ø±Ø§Û Ø¨Ø±Ø±Ø³Û SMC
input double   MinSMCScore        = 60.0;                // Ø­Ø¯Ø§ÙÙ Ø§ÙØªÛØ§Ø² SMC Ø¨Ø±Ø§Û ÙØ±ÙØ¯
input bool     SMCMultiTimeframe  = true;                // Ø¨Ø±Ø±Ø³Û ÚÙØ¯ ØªØ§ÛÙâÙØ±ÛÙ

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª Price Action =====                                   |
//+------------------------------------------------------------------+
input bool     PAEnabled          = true;                // Price Action ÙØ¹Ø§Ù Ø¨Ø§Ø´Ø¯
input bool     DetectPinBar       = true;                // ØªØ´Ø®ÛØµ Pin Bar
input bool     DetectEngulfing    = true;                // ØªØ´Ø®ÛØµ Engulfing
input bool     DetectFakey        = true;                // ØªØ´Ø®ÛØµ Fakey
input bool     DetectInsideBar    = true;                // ØªØ´Ø®ÛØµ Inside Bar
input double   MinPAScore         = 50.0;                // Ø­Ø¯Ø§ÙÙ Ø§ÙØªÛØ§Ø² PA Ø¨Ø±Ø§Û ÙØ±ÙØ¯
input int      PALookback         = 50;                  // ØªØ¹Ø¯Ø§Ø¯ Ú©ÙØ¯Ù Ø¨Ø±Ø§Û Ø¨Ø±Ø±Ø³Û PA

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª Decision Engine =====                                |
//+------------------------------------------------------------------+
input double   MinTotalScore      = 65.0;                // Ø­Ø¯Ø§ÙÙ Ø§ÙØªÛØ§Ø² Ú©Ù Ø¨Ø±Ø§Û ÙØ±ÙØ¯
input double   WeightSMC          = 0.35;                // ÙØ²Ù Ø§ÙØªÛØ§Ø² SMC
input double   WeightMTF          = 0.25;                // ÙØ²Ù ÙÙØ³ÙÛÛ ØªØ§ÛÙâÙØ±ÛÙ
input double   WeightPA           = 0.20;                // ÙØ²Ù Ø§ÙØªÛØ§Ø² Price Action
input double   WeightRisk         = 0.10;                // ÙØ²Ù Ø±ÛØ³Ú©
input double   WeightSession      = 0.10;                // ÙØ²Ù Ø³Ø´Ù

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª Multi-Timeframe =====                               |
//+------------------------------------------------------------------+
input ENUM_TIMEFRAMES HTF_Period  = PERIOD_H4;           // ØªØ§ÛÙâÙØ±ÛÙ Ø¨Ø§ÙØ§ (HTF)
input ENUM_TIMEFRAMES MTF_Period  = PERIOD_H1;           // ØªØ§ÛÙâÙØ±ÛÙ ÙÛØ§ÙÛ (MTF)
input ENUM_TIMEFRAMES LTF_Period  = PERIOD_M15;          // ØªØ§ÛÙâÙØ±ÛÙ Ù¾Ø§ÛÛÙ (LTF)
input bool     RequireHTFAlign    = true;                // Ø§ÙØ²Ø§Ù ÙÙØ³ÙÛÛ HTF
input bool     RequireMTFAlign    = true;                // Ø§ÙØ²Ø§Ù ÙÙØ³ÙÛÛ MTF

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª ÙÛÙØªØ± Ø²ÙØ§ÙÛ Ù Ø³Ø´Ù =====                            |
//+------------------------------------------------------------------+
input bool     UseTimeFilter      = true;                // ÙÛÙØªØ± Ø²ÙØ§ÙÛ ÙØ¹Ø§Ù Ø¨Ø§Ø´Ø¯
input bool     TradeAsianSession  = false;               // ÙØ¹Ø§ÙÙÙ Ø¯Ø± Ø³Ø´Ù Ø¢Ø³ÛØ§
input bool     TradeLondonSession = true;                // ÙØ¹Ø§ÙÙÙ Ø¯Ø± Ø³Ø´Ù ÙÙØ¯Ù
input bool     TradeNYSession     = true;                // ÙØ¹Ø§ÙÙÙ Ø¯Ø± Ø³Ø´Ù ÙÛÙÛÙØ±Ú©
input int      LondonOpenHour     = 8;                   // Ø³Ø§Ø¹Øª Ø¨Ø§Ø² Ø´Ø¯Ù ÙÙØ¯Ù (UTC)
input int      LondonCloseHour    = 17;                  // Ø³Ø§Ø¹Øª Ø¨Ø³ØªÙ Ø´Ø¯Ù ÙÙØ¯Ù (UTC)
input int      NYOpenHour         = 13;                  // Ø³Ø§Ø¹Øª Ø¨Ø§Ø² Ø´Ø¯Ù ÙÛÙÛÙØ±Ú© (UTC)
input int      NYCloseHour        = 22;                  // Ø³Ø§Ø¹Øª Ø¨Ø³ØªÙ Ø´Ø¯Ù ÙÛÙÛÙØ±Ú© (UTC)
input int      AsianOpenHour      = 23;                  // Ø³Ø§Ø¹Øª Ø¨Ø§Ø² Ø´Ø¯Ù Ø¢Ø³ÛØ§ (UTC)
input int      AsianCloseHour     = 8;                   // Ø³Ø§Ø¹Øª Ø¨Ø³ØªÙ Ø´Ø¯Ù Ø¢Ø³ÛØ§ (UTC)

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª Kill Zones =====                                     |
//+------------------------------------------------------------------+
input bool     TradeLondonKZ      = true;                // ÙØ¹Ø§ÙÙÙ Ø¯Ø± London Kill Zone
input bool     TradeNYKZ          = true;                // ÙØ¹Ø§ÙÙÙ Ø¯Ø± NY Kill Zone
input bool     TradeLondonCloseKZ = false;               // ÙØ¹Ø§ÙÙÙ Ø¯Ø± London Close KZ
input int      LKZ_StartHour      = 8;                   // Ø´Ø±ÙØ¹ London KZ
input int      LKZ_EndHour        = 10;                  // Ù¾Ø§ÛØ§Ù London KZ
input int      NYKZ_StartHour     = 13;                  // Ø´Ø±ÙØ¹ NY KZ
input int      NYKZ_EndHour       = 15;                  // Ù¾Ø§ÛØ§Ù NY KZ

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª ØªÙÚ¯Ø±Ø§Ù =====                                         |
//+------------------------------------------------------------------+
input bool     TelegramEnabled    = false;               // ØªÙÚ¯Ø±Ø§Ù ÙØ¹Ø§Ù Ø¨Ø§Ø´Ø¯
input string   TelegramToken      = "";                  // ØªÙÚ©Ù Ø±Ø¨Ø§Øª ØªÙÚ¯Ø±Ø§Ù
input string   TelegramChatId     = "";                  // Ø´ÙØ§Ø³Ù ÚØª ØªÙÚ¯Ø±Ø§Ù
input bool     NotifyOnEntry      = true;                // Ø§Ø¹ÙØ§Ù ÙØ±ÙØ¯
input bool     NotifyOnExit       = true;                // Ø§Ø¹ÙØ§Ù Ø®Ø±ÙØ¬
input bool     NotifyOnSL         = true;                // Ø§Ø¹ÙØ§Ù StopLoss
input bool     NotifyOnTP         = true;                // Ø§Ø¹ÙØ§Ù TakeProfit
input bool     NotifyOnSession    = true;                // Ø§Ø¹ÙØ§Ù Ø³Ø´Ù
input bool     SendDailyReports   = true;                // Ø§Ø±Ø³Ø§Ù Ú¯Ø²Ø§Ø±Ø´ Ø±ÙØ²Ø§ÙÙ
input int      DailyReportHour    = 22;                  // Ø³Ø§Ø¹Øª Ú¯Ø²Ø§Ø±Ø´ Ø±ÙØ²Ø§ÙÙ

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª Ø±Ø³Ù Ø±ÙÛ ÚØ§Ø±Øª =====                                  |
//+------------------------------------------------------------------+
input bool     DrawEnabled        = true;                // Ø±Ø³Ù Ø±ÙÛ ÚØ§Ø±Øª ÙØ¹Ø§Ù Ø¨Ø§Ø´Ø¯
input bool     DrawOrderBlocks    = true;                // Ø±Ø³Ù Order Block
input bool     DrawFVG            = true;                // Ø±Ø³Ù Fair Value Gap
input bool     DrawBOSCHOCH       = true;                // Ø±Ø³Ù BOS/CHOCH
input bool     DrawLiquidity      = true;                // Ø±Ø³Ù Ø³Ø·ÙØ­ ÙÙØ¯ÛÙÚ¯Û
input bool     DrawKillZones      = true;                // Ø±Ø³Ù Kill Zones
input bool     DrawEntryArrows    = true;                // Ø±Ø³Ù ÙÙØ´âÙØ§Û ÙØ±ÙØ¯
input color    ColorBullish       = clrLime;             // Ø±ÙÚ¯ ØµØ¹ÙØ¯Û
input color    ColorBearish       = clrRed;              // Ø±ÙÚ¯ ÙØ²ÙÙÛ
input color    ColorNeutral       = clrGray;             // Ø±ÙÚ¯ Ø®ÙØ«Û
input color    ColorFVG           = clrCyan;             // Ø±ÙÚ¯ FVG
input color    ColorKillZone      = clrYellow;           // Ø±ÙÚ¯ Kill Zone
input int      LabelFontSize      = 8;                   // Ø§ÙØ¯Ø§Ø²Ù ÙÙÙØª Ø¨Ø±ÚØ³Ø¨âÙØ§

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª ÙØ§ÛØ³ÙØ³ =====                                        |
//+------------------------------------------------------------------+
input string   LicenseKey         = "";                  // Ú©ÙÛØ¯ ÙØ§ÛØ³ÙØ³
input string   LicenseServer      = "https://api.yourserver.com"; // Ø³Ø±ÙØ± ÙØ§ÛØ³ÙØ³
input bool     CheckLicenseOnline = true;                // Ø¨Ø±Ø±Ø³Û Ø¢ÙÙØ§ÛÙ ÙØ§ÛØ³ÙØ³

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª API =====                                           |
//+------------------------------------------------------------------+
input string   APIBaseURL         = "http://YOUR_SERVER_IP:8000";       // آدرس API سرور (localhost را با IP واقعی جایگزین کنید) // Ø¢Ø¯Ø±Ø³ API
input string   APIKey             = "";                  // Ú©ÙÛØ¯ API
input bool     APIEnabled         = false;               // API ÙØ¹Ø§Ù Ø¨Ø§Ø´Ø¯
input int      APITimeoutMs       = 5000;                // timeout Ø¯Ø±Ø®ÙØ§Ø³Øª (ÙÛÙÛâØ«Ø§ÙÛÙ)

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª ÙØ§Ú¯ =====                                           |
//+------------------------------------------------------------------+
input bool     LogEnabled         = true;                // ÙØ§Ú¯ ÙØ¹Ø§Ù Ø¨Ø§Ø´Ø¯
input bool     LogToFile          = true;                // ÙØ§Ú¯ Ø¨Ù ÙØ§ÛÙ
input string   LogFileName        = "MT5Trading.log";    // ÙØ§Ù ÙØ§ÛÙ ÙØ§Ú¯
input bool     LogDebug           = false;               // ÙØ§Ú¯ Ø¯ÛØ¨Ø§Ú¯

//+------------------------------------------------------------------+
//| ===== ØªÙØ¸ÛÙØ§Øª Ø§Ø·ÙØ§Ø¹Ø§Øª Ø±ÙÛ ÚØ§Ø±Øª =====                              |
//+------------------------------------------------------------------+
input bool     ShowDashboard      = true;                // ÙÙØ§ÛØ´ Ø¯Ø§Ø´Ø¨ÙØ±Ø¯ Ø±ÙÛ ÚØ§Ø±Øª
input bool     ShowScore          = true;                // ÙÙØ§ÛØ´ Ø§ÙØªÛØ§Ø²
input bool     ShowRiskInfo       = true;                // ÙÙØ§ÛØ´ Ø§Ø·ÙØ§Ø¹Ø§Øª Ø±ÛØ³Ú©
input bool     ShowSessionInfo    = true;                // ÙÙØ§ÛØ´ Ø§Ø·ÙØ§Ø¹Ø§Øª Ø³Ø´Ù
input int      DashboardX         = 10;                  // ÙÙÙØ¹ÛØª Ø§ÙÙÛ Ø¯Ø§Ø´Ø¨ÙØ±Ø¯
input int      DashboardY         = 30;                  // ÙÙÙØ¹ÛØª Ø¹ÙÙØ¯Û Ø¯Ø§Ø´Ø¨ÙØ±Ø¯
//+------------------------------------------------------------------+
