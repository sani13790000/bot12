// ============================================================
// Galaxy Vast — Central Type Definitions
// ============================================================

export type TradingMode = "SIGNAL_ONLY" | "SEMI_AUTO" | "FULL_AUTO";
export type TradeDirection = "BUY" | "SELL";
export type TradeStatus = "OPEN" | "CLOSED" | "CANCELLED";
export type SignalStatus = "ACTIVE" | "EXECUTED" | "EXPIRED" | "CANCELLED";
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type BotStatus = "RUNNING" | "PAUSED" | "STOPPED";

// ── Dashboard Stats ─────────────────────────────────────────
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
}

// ── Trade ───────────────────────────────────────────────────
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
}

// ── Signal ──────────────────────────────────────────────────
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
}

// ── Portfolio Risk ───────────────────────────────────────────
export interface PortfolioRisk {
  total_risk_percent: number;
  max_allowed_percent: number;
  can_open_new_trade: boolean;
  open_positions: PositionRisk[];
  currency_exposure: Record<string, number>;
  correlation_risk: number;
}

export interface PositionRisk {
  symbol: string;
  direction: TradeDirection;
  risk_percent: number;
  unrealized_pnl: number;
  correlation_group: string;
}

// ── Equity Curve Point ───────────────────────────────────────
export interface EquityPoint {
  date: string;
  equity: number;
  balance: number;
  drawdown: number;
}

// ── ML Weights ───────────────────────────────────────────────
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

// ── Backtest Result ──────────────────────────────────────────
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
}

// ── System Settings ──────────────────────────────────────────
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

// ── API Response Wrapper ─────────────────────────────────────
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  error?: string;
}
