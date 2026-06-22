/**
 * frontend/src/types/index.ts
 * FIX-13: WSMessageType اضافه شد
 * FIX-19: User.first_name و last_name اضافه شد
 * FIX-20: Signal fields کامل شد
 * FIX-21: RiskStatus اضافه شد
 * FIX-22: SecurityEvent اضافه شد
 */

export interface ApiResponse<T> { success: boolean; data: T; error?: string; message?: string; }

export interface User {
  id: string; email: string;
  first_name?: string; last_name?: string; full_name?: string;
  role: "USER" | "TRADER" | "ADMIN";
  is_active: boolean; created_at: string;
}

export interface UserSettings {
  risk_percentage: number; max_trades: number; symbols: string[];
  trading_mode: "AUTO" | "SEMI_AUTO" | "MANUAL";
  notifications_enabled: boolean; telegram_alerts: boolean;
}

export interface Trade {
  id: string; symbol: string; direction: "BUY" | "SELL";
  volume: number; entry_price: number; current_price?: number;
  stop_loss?: number; take_profit?: number; profit_loss?: number;
  status: "OPEN" | "CLOSED" | "PENDING" | "CANCELLED";
  opened_at: string; closed_at?: string; user_id: string;
}

export interface Signal {
  id: string; symbol: string; direction: "BUY" | "SELL" | "NEUTRAL";
  confidence: number; score: number;
  entry_price?: number; take_profit?: number; take_profit_1?: number;
  take_profit_2?: number; stop_loss?: number;
  status: "PENDING" | "EXECUTED" | "CANCELLED" | "EXPIRED";
  reasoning?: string; risk_level?: "LOW" | "MEDIUM" | "HIGH";
  session?: string; expires_at?: string; confidence_score?: number;
  created_at: string;
}

export interface DashboardStats {
  total_trades: number; open_trades: number; win_rate: number;
  total_profit: number; today_profit: number;
  equity: number; balance: number; margin_level: number;
  security_score: number; active_signals: number;
}

export interface EquityPoint { timestamp: string; equity: number; balance: number; drawdown: number; }

export interface PortfolioRisk {
  total_exposure: number; daily_pnl: number; max_drawdown: number;
  sharpe_ratio: number; win_rate: number; profit_factor: number;
}

export interface RiskStatus {
  equity_protection: boolean; daily_limit_reached: boolean;
  circuit_breaker_open: boolean; current_exposure: number;
  max_allowed_exposure: number; daily_loss: number; daily_limit: number;
  open_trades_count: number; max_trades: number;
}

export interface MLWeights { smc_weight: number; pa_weight: number; ml_weight: number; rl_weight: number; news_weight: number; }

export interface BacktestResult {
  id: string; symbol: string; start_date: string; end_date: string;
  total_trades: number; win_rate: number; profit_factor: number;
  max_drawdown: number; net_profit: number; sharpe_ratio: number;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED"; created_at: string;
}

export interface SystemSettings {
  trading_enabled: boolean; max_daily_trades: number;
  risk_per_trade: number; max_drawdown_limit: number; allowed_symbols: string[];
}

export interface AnalyticsMetrics {
  period: string; total_trades: number; winning_trades: number; losing_trades: number;
  win_rate: number; profit_factor: number; total_profit: number; max_drawdown: number;
  avg_trade_duration: string; best_trade: number; worst_trade: number;
}

export interface AIPrediction {
  symbol: string; direction: "BUY" | "SELL" | "NEUTRAL";
  confidence: number; predicted_price?: number;
  features_used: string[]; model_version: string; created_at: string;
}

export interface ModelVersion {
  version: string; symbol: string; accuracy: number;
  trained_at: string; samples: number; is_active: boolean;
}

export interface SecurityEvent {
  id: string; event_type: string; risk_score: number;
  ip_address?: string; user_id?: string; created_at: string;
}

export interface SecurityMetrics {
  security_score: number;
  score_level: "critical" | "high" | "medium" | "low" | "excellent";
  anomaly_rate: number; blocked_ips: number; failed_logins_24h: number;
  recent_events: SecurityEvent[];
}

export type WSMessageType =
  | "TRADE_OPEN" | "TRADE_CLOSE" | "TRADE_UPDATE"
  | "SIGNAL_NEW" | "SIGNAL_EXECUTED" | "SIGNAL_CANCELLED"
  | "RISK_ALERT" | "EQUITY_UPDATE" | "MARKET_DATA"
  | "AUTH_REQUIRED" | "AUTH_OK" | "AUTH_FAIL"
  | "PING" | "PONG" | "ERROR";
