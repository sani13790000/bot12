// ═══════════════════════════════════════════════════════════════
// Galaxy Vast AI Trading Platform — Central Type Definitions v3
// ═══════════════════════════════════════════════════════════════

export type TradingMode     = "SIGNAL_ONLY" | "SEMI_AUTO" | "FULL_AUTO";
export type TradeDirection  = "BUY" | "SELL";
export type TradeStatus     = "OPEN" | "CLOSED" | "CANCELLED";
export type SignalStatus    = "ACTIVE" | "EXECUTED" | "EXPIRED" | "CANCELLED";
export type RiskLevel       = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type BotStatus       = "RUNNING" | "PAUSED" | "STOPPED";
export type ModelStatus     = "ACTIVE" | "TRAINING" | "DEPRECATED" | "ROLLBACK";

// ── Dashboard ─────────────────────────────────────────────────
export interface DashboardStats {
  balance: number;
  equity: number;
  free_margin: number;
  margin_used: number;
  drawdown_percent: number;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  recovery_factor: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  today_pnl: number;
  portfolio_risk_percent: number;
  bot_status: BotStatus;
  trading_mode: TradingMode;
  active_trades_count: number;
  active_signals_count: number;
  expectancy: number;
  max_drawdown: number;
}

// ── Trade ──────────────────────────────────────────────────────
export interface Trade {
  id: string;
  symbol: string;
  direction: TradeDirection;
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  lot_size: number;
  risk_percent: number;
  confidence_score: number;
  risk_level: RiskLevel;
  status: TradeStatus;
  open_time: string;
  close_time?: string;
  close_price?: number;
  pnl?: number;
  pips?: number;
  risk_reward_ratio: number;
  smc_score: number;
  pa_score: number;
  session: string;
  duration_minutes?: number;
  mae?: number;
  mfe?: number;
}

// ── Signal ─────────────────────────────────────────────────────
export interface Signal {
  id: string;
  symbol: string;
  direction: TradeDirection;
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  confidence_score: number;
  risk_level: RiskLevel;
  risk_reward_ratio: number;
  status: SignalStatus;
  created_at: string;
  expires_at: string;
  context_explanation: string;
  smc_details: string;
  pa_pattern: string;
  session: string;
  ai_probability?: number;
  ai_confidence?: number;
}

// ── AI Prediction ──────────────────────────────────────────────
export interface AIPrediction {
  symbol: string;
  direction: TradeDirection;
  probability: number;
  confidence: number;
  risk: RiskLevel;
  model_auc: number;
  is_tradeable: boolean;
  reason: string;
  features_used: number;
  predicted_at: string;
}

// ── Portfolio Risk ─────────────────────────────────────────────
export interface PortfolioRisk {
  total_risk_percent: number;
  max_allowed_percent: number;
  can_open_new_trade: boolean;
  open_positions: PositionRisk[];
  currency_exposure: Record<string, number>;
  correlation_risk: number;
  daily_loss_percent: number;
  weekly_loss_percent: number;
  equity_drawdown: number;
  halt_active: boolean;
  daily_trades_used: number;
  daily_trades_max: number;
}

export interface PositionRisk {
  symbol: string;
  direction: TradeDirection;
  risk_percent: number;
  unrealized_pnl: number;
  correlation_group: string;
}

// ── Equity Curve ───────────────────────────────────────────────
export interface EquityPoint {
  date: string;
  equity: number;
  balance: number;
  drawdown: number;
  pnl: number;
}

// ── Analytics ─────────────────────────────────────────────────
export interface AnalyticsMetrics {
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  profit_factor: number;
  recovery_factor: number;
  expectancy: number;
  expectancy_r: number;
  max_drawdown_pct: number;
  win_rate: number;
  avg_rr: number;
  cagr: number;
  total_trades: number;
  net_profit: number;
  gross_profit: number;
  gross_loss: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  avg_trade_duration_hours: number;
}

export interface BreakdownItem {
  label: string;
  trades: number;
  win_rate: number;
  profit_factor: number;
  net_pnl: number;
}

// ── Model Performance ─────────────────────────────────────────
export interface ModelVersion {
  version: string;
  symbol: string;
  status: ModelStatus;
  auc_score: number;
  train_auc: number;
  test_auc: number;
  samples: number;
  features: number;
  created_at: string;
  is_current: boolean;
  performance_7d?: number;
}

export interface MLWeights {
  bos_weight: number;
  choch_weight: number;
  order_block_weight: number;
  fvg_weight: number;
  liquidity_weight: number;
  pa_engulfing_weight: number;
  pa_pin_bar_weight: number;
  session_weight: number;
  htf_alignment_weight: number;
  last_updated: string;
  total_trades_learned: number;
  model_accuracy: number;
}

// ── Backtest ───────────────────────────────────────────────────
export interface BacktestResult {
  symbol: string;
  start_date: string;
  end_date: string;
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown: number;
  total_return: number;
  initial_balance: number;
  final_balance: number;
  equity_curve: EquityPoint[];
  monte_carlo?: MonteCarloResult;
}

export interface MonteCarloResult {
  simulations: number;
  probability_profit: number;
  median_final_balance: number;
  var_95: number;
  worst_max_drawdown: number;
  risk_of_ruin: number;
}

// ── WebSocket ─────────────────────────────────────────────────
export type WSMessageType =
  | "EQUITY_UPDATE"
  | "NEW_SIGNAL"
  | "TRADE_OPENED"
  | "TRADE_CLOSED"
  | "RISK_ALERT"
  | "BOT_STATUS"
  | "PREDICTION";

export interface WSMessage<T = unknown> {
  type: WSMessageType;
  data: T;
  timestamp: string;
}

// ── System Settings ───────────────────────────────────────────
export interface SystemSettings {
  trading_mode: TradingMode;
  risk_per_trade_percent: number;
  max_portfolio_risk_percent: number;
  max_daily_trades: number;
  max_daily_loss_percent: number;
  max_weekly_loss_percent: number;
  max_monthly_drawdown_percent: number;
  min_confidence_score: number;
  max_spread_points: number;
  enable_smc_engine: boolean;
  enable_pa_engine: boolean;
  enable_ml_learning: boolean;
  enable_news_filter: boolean;
  allowed_sessions: string[];
  allowed_symbols: string[];
}

// ── API Response ───────────────────────────────────────────────
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  error?: string;
}
