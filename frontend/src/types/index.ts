/**
 * انواع TypeScript پروژه
 *
 * نویسنده: MT5 Trading Team
 */

// کاربر
export interface User {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  role: 'user' | 'admin' | 'trader';
  status: 'active' | 'inactive' | 'suspended';
  created_at: string;
  last_login_at?: string;
}

// تنظیمات کاربر
export interface UserSettings {
  user_id: string;
  default_symbol: string;
  default_lot: number;
  risk_per_trade: number;
  max_daily_trades: number;
  min_entry_score: number;
  telegram_notifications: boolean;
  default_timeframe: string;
}

// معامله
export interface Trade {
  id: string;
  user_id: string;
  symbol: string;
  direction: 'buy' | 'sell';
  status: 'pending' | 'open' | 'closed' | 'cancelled';
  volume: number;
  entry_price: number;
  current_price?: number;
  exit_price?: number;
  stop_loss: number;
  take_profit: number;
  profit_money: number;
  profit_points: number;
  open_reason: string;
  close_reason?: string;
  opened_at: string;
  closed_at?: string;
  signal_id?: string;
}

// سیگنال
export interface Signal {
  id: string;
  user_id: string;
  symbol: string;
  direction: 'buy' | 'sell';
  status: 'generated' | 'sent' | 'executed' | 'expired' | 'skipped';
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  total_score: number;
  smc_score: number;
  pa_score: number;
  reason: string;
  generated_at: string;
  valid_until: string;
  executed_at?: string;
  result?: 'win' | 'loss' | 'breakeven';
}

// تحلیل SMC
export interface SMCAnalysis {
  structure: {
    trend: 'bullish' | 'bearish' | 'ranging' | 'neutral';
    has_bos: boolean;
    has_choch: boolean;
    has_mss: boolean;
  };
  liquidity: {
    has_sweep: boolean;
    sweep_type?: 'wick' | 'impulse';
  };
  order_block: {
    detected: boolean;
    type?: 'bullish' | 'bearish';
    high?: number;
    low?: number;
  };
  fvg: {
    detected: boolean;
    high?: number;
    low?: number;
  };
  score: number;
}

// تحلیل Price Action
export interface PriceActionAnalysis {
  patterns: Pattern[];
  structure: {
    is_breakout: boolean;
    is_compression: boolean;
    is_expansion: boolean;
    momentum: number;
  };
  score: number;
}

// الگو
export interface Pattern {
  name: string;
  bias: 'bullish' | 'bearish' | 'neutral';
  strength: 'weak' | 'moderate' | 'strong';
  bar: number;
}

// تصمیم معاملاتی
export interface TradeDecision {
  symbol: string;
  timeframe: string;
  direction: 'buy' | 'sell' | 'neutral';
  total_score: number;
  entry_allowed: boolean;
  reason: string;
  levels: {
    entry: number;
    sl: number;
    tp: number;
  };
  filters_passed: string[];
  filters_failed: string[];
}

// گزارش
export interface Report {
  date: string;
  summary: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
    gross_profit: number;
    gross_loss: number;
    net_profit: number;
  };
  trades?: Trade[];
}

// آمار عملکرد
export interface PerformanceStats {
  period: string;
  metrics: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
    profit_factor: number;
    net_profit: number;
    avg_trade: number;
    gross_profit: number;
    gross_loss: number;
  };
}

// پاسخ API
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  message?: string;
  error?: string;
}

// وضعیت اکانت
export interface AccountState {
  balance: number;
  equity: number;
  margin: number;
  free_margin: number;
  open_pnl: number;
  daily_pnl: number;
}

// Kill Zone
export interface KillZone {
  name: string;
  start: number;
  end: number;
  active: boolean;
}

// نماد
export interface Symbol {
  name: string;
  bid: number;
  ask: number;
  spread: number;
  change: number;
  change_percent: number;
}

// نمودار
export interface ChartData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
