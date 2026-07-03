// frontend/src/types/index.ts
export type Role = "ADMIN" | "USER" | "VIEWER";
export interface User { id: string; email: string; full_name: string; role: Role; is_active: boolean; created_at: string; }
export interface AuthTokens { access_token: string; refresh_token: string; token_type: "bearer"; }
export interface LoginPayload { email: string; password: string; }
export interface RegisterPayload { email: string; password: string; full_name: string; }
export type TradeDirection = "buy" | "sell";
export type TradeStatus = "open" | "closed" | "pending" | "cancelled";
export interface Trade { id: string; symbol: string; direction: TradeDirection; lot_size: number; entry_price: number; stop_loss: number; take_profit: number; current_price?: number; pnl?: number; status: TradeStatus; ticket?: number; opened_at: string; closed_at?: string; close_price?: number; }
export interface OpenTradePayload { symbol: string; direction: TradeDirection; lot_size: number; stop_loss: number; take_profit: number; }
export type SignalStatus = "pending" | "approved" | "rejected" | "executed" | "expired";
export interface Signal { id: string; symbol: string; direction: TradeDirection; confidence: number; entry_price: number; stop_loss: number; take_profit: number; lot_size: number; status: SignalStatus; source: string; reasoning?: string; created_at: string; executed_at?: string; }
export interface DashboardStats { total_trades: number; open_trades: number; win_rate: number; total_pnl: number; daily_pnl: number; equity: number; balance: number; drawdown: number; profit_factor: number; sharpe_ratio: number; }
export interface EquityPoint { timestamp: string; equity: number; balance: number; }
export interface SMCAnalysis { symbol: string; timeframe: string; bias: "bullish" | "bearish" | "neutral"; order_blocks: Array<{ price: number; type: "bull" | "bear"; strength: number }>; fvg_zones: Array<{ high: number; low: number; type: "bull" | "bear" }>; liquidity_levels: Array<{ price: number; type: "high" | "low"; swept: boolean }>; bos_points: Array<{ price: number; direction: "up" | "down"; confirmed: boolean }>; confidence: number; updated_at: string; }
export interface PriceActionAnalysis { symbol: string; timeframe: string; trend: "up" | "down" | "sideways"; patterns: Array<{ name: string; reliability: number; price: number }>; support_levels: number[]; resistance_levels: number[]; rsi: number; macd: { value: number; signal: number; histogram: number }; updated_at: string; }
export interface DecisionEngineResult { symbol: string; action: "BUY" | "SELL" | "HOLD" | "NO_TRADE"; confidence: number; risk_reward: number; lot_size: number; entry_price: number; stop_loss: number; take_profit: number; reasoning: string; votes: Array<{ agent: string; vote: string; weight: number }>; updated_at: string; }
export interface AdminStats { total_users: number; active_users: number; total_trades_today: number; system_health: "healthy" | "degraded" | "down"; kill_switch_active: boolean; }
export interface SecurityMetrics { failed_logins_24h: number; blocked_ips: number; active_sessions: number; license_violations: number; }
export interface LicenseStatus { is_valid: boolean; license_key: string; expires_at: string; max_accounts: number; active_accounts: number; plan: "trial" | "basic" | "pro" | "enterprise"; }
export interface PaginatedResponse<T> { items: T[]; total: number; page: number; per_page: number; pages: number; }
export type WSEventType = "trade_update" | "signal_new" | "price_update" | "kill_switch" | "equity_update" | "alert";
export interface WSMessage { event: WSEventType; data: unknown; timestamp: string; }
