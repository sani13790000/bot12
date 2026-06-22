// frontend/src/types/index.ts
// FIX-FE4: WSMessageType added
// FIX-FE7: Signal/Trade fields aligned with real page usage

export type WSMessageType =
  | "PRICE"
  | "SIGNAL"
  | "TRADE_UPDATE"
  | "HEARTBEAT"
  | "PONG"
  | "*";

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  error?: string;
  message?: string;
}

export interface User {
  id: string;
  email: string;
  full_name?: string;
  first_name?: string;
  last_name?: string;
  role: "USER" | "TRADER" | "ADMIN";
  is_active: boolean;
  created_at: string;
}

export interface UserSettings {
  risk_percentage: number;
  max_trades: number;
  symbols: string[];
  trading_mode: "AUTO" | "SEMI_AUTO" | "MANUAL";
  notifications_enabled: boolean;
  telegram_alerts: boolean;
}

export interface Trade {
  id: string;
  symbol: string;
  direction: "BUY" | "SELL" | "buy" | "sell";
  volume: number;
  lot_size?: number;
  entry_price: number;
  current_price?: number;
  stop_loss?: number;
  take_profit?: number;
  take_profit_1?: number;
  take_profit_2?: number;
  profit_loss?: number;
  profit_money?: number;
  pnl?: number;
  status: "OPEN" | "CLOSED" | "PENDING" | "CANCELLED" | "open" | "closed" | "pending" | "cancelled";
  opened_at?: string;
  open_time?: string;
  closed_at?: string;
  close_time?: string;
  close_price?: number;
  user_id?: string;
  risk_percent?: number;
  confidence_score?: number;
  risk_level?: "LOW" | "MEDIUM" | "HIGH";
  risk_reward_ratio?: number;
  smc_score?: number;
  pa_score?: number;
  session?: string;
}

export interface Signal {
  id: string;
  symbol: string;
  direction: "BUY" | "SELL" | "NEUTRAL";
  confidence: number;
  confidence_score?: number;
  score?: number;
  entry_price?: number;
  stop_loss?: number;
  take_profit?: number;
  take_profit_1?: number;
  take_profit_2?: number;
  status: "PENDING" | "EXECUTED" | "CANCELLED" | "EXPIRED" | "ACTIVE" | "active" | "pending";
  reasoning?: string;
  context_explanation?: string;
  smc_details?: string;
  pa_pattern?: string;
  session?: string;
  risk_level?: "LOW" | "MEDIUM" | "HIGH";
  risk_reward_ratio?: number;
  created_at: string;
  expires_at?: string;
}

export interface DashboardStats {
  total_trades: number;
  open_trades: number;
  win_rate: number;
  total_profit: number;
  today_profit: number;
  equity: number;
  balance: number;
  margin_level: number;
  security_score: number;
  active_signals: number;
}

export interface PortfolioRisk {
  total_exposure: number;
  daily_pnl: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  profit_factor: number;
}

export interface MLWeights {
  smc_weight: number;
  pa_weight: number;
  ml_weight: number;
  rl_weight: number;
  news_weight: number;
}

export interface BacktestResult {
  id: string;
  symbol: string;
  start_date: string;
  end_date: string;
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown: number;
  net_profit: number;
  sharpe_ratio: number;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  created_at: string;
}

export interface SystemSettings {
  trading_enabled: boolean;
  max_daily_trades: number;
  risk_per_trade: number;
  max_drawdown_limit: number;
  allowed_symbols: string[];
}

export interface AnalyticsMetrics {
  period: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  profit_factor: number;
  total_profit: number;
  max_drawdown: number;
  avg_trade_duration: string;
  best_trade: number;
  worst_trade: number;
}

export interface AIPrediction {
  symbol: string;
  direction: "BUY" | "SELL" | "NEUTRAL";
  confidence: number;
  predicted_price?: number;
  features_used: string[];
  model_version: string;
  created_at: string;
}

export interface ModelVersion {
  version: string;
  symbol: string;
  accuracy: number;
  trained_at: string;
  samples: number;
  is_active: boolean;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
  balance: number;
  drawdown: number;
}

export interface SecurityMetrics {
  security_score: number;
  score_level: "critical" | "high" | "medium" | "low" | "excellent";
  anomaly_rate: number;
  blocked_ips: number;
  failed_logins_24h: number;
  recent_events: SecurityEvent[];
}

export interface SecurityEvent {
  id: string;
  event_type: string;
  risk_score: number;
  ip_address?: string;
  user_id?: string;
  created_at: string;
}

export interface RiskStatus {
  equity_protection: boolean;
  daily_limit_reached: boolean;
  circuit_breaker_open: boolean;
  current_exposure: number;
  max_allowed_exposure: number;
  daily_loss: number;
  daily_limit: number;
  open_trades_count: number;
  max_trades: number;
}
