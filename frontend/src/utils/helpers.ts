/**
 * توابع کمکی
 *
 * نویسنده: MT5 Trading Team
 */

// تعریف نوع‌های محلی
interface Trade {
  id: string;
  symbol: string;
  direction: 'buy' | 'sell';
  status: 'pending' | 'open' | 'closed' | 'cancelled';
  volume: number;
  entry_price: number;
  profit_money: number;
  stop_loss: number;
  take_profit: number;
  opened_at: string;
  closed_at?: string;
}

type TradeStatus = Trade['status'];
type SignalStatus = 'generated' | 'sent' | 'executed' | 'expired' | 'skipped';

// فرمت عدد
export function formatNumber(num: number, decimals: number = 2): string {
  return num.toLocaleString('fa-IR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

// فرمت ارز
export function formatCurrency(amount: number, currency: string = 'USD'): string {
  return new Intl.NumberFormat('fa-IR', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(amount);
}

// فرمت درصد
export function formatPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

// فرمت تاریخ
export function formatDate(date: string | Date, format: 'short' | 'long' = 'short'): string {
  const d = typeof date === 'string' ? new Date(date) : date;

  if (format === 'short') {
    return d.toLocaleDateString('fa-IR');
  }

  return d.toLocaleDateString('fa-IR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

// فرمت زمان نسبی
export function formatRelativeTime(date: string): string {
  const now = new Date();
  const d = new Date(date);
  const diffMs = now.getTime() - d.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return 'همین الان';
  if (diffMins < 60) return `${diffMins} دقیقه پیش`;
  if (diffHours < 24) return `${diffHours} ساعت پیش`;
  if (diffDays < 7) return `${diffDays} روز پیش`;

  return formatDate(date);
}

// محاسبه وین ریت
export function calculateWinRate(trades: Trade[]): number {
  if (trades.length === 0) return 0;

  const wins = trades.filter(t => t.profit_money > 0).length;
  return (wins / trades.length) * 100;
}

// محاسبه فاکتور سود
export function calculateProfitFactor(trades: Trade[]): number {
  const wins = trades.filter(t => t.profit_money > 0);
  const losses = trades.filter(t => t.profit_money < 0);

  const grossProfit = wins.reduce((sum, t) => sum + t.profit_money, 0);
  const grossLoss = Math.abs(losses.reduce((sum, t) => sum + t.profit_money, 0));

  if (grossLoss === 0) return grossProfit > 0 ? Infinity : 0;

  return grossProfit / grossLoss;
}

// محاسبه میانگین سود/ضرر
export function calculateAvgProfit(trades: Trade[]): number {
  if (trades.length === 0) return 0;

  const totalProfit = trades.reduce((sum, t) => sum + t.profit_money, 0);
  return totalProfit / trades.length;
}

// محاسبه Drawdown
export function calculateDrawdown(trades: Trade[]): { max: number; current: number } {
  if (trades.length === 0) return { max: 0, current: 0 };

  let peak = 0;
  let maxDrawdown = 0;
  let currentEquity = 0;

  // مرتب‌سازی بر اساس تاریخ
  const sortedTrades = [...trades].sort((a, b) =>
    new Date(a.closed_at || '').getTime() - new Date(b.closed_at || '').getTime()
  );

  for (const trade of sortedTrades) {
    currentEquity += trade.profit_money;

    if (currentEquity > peak) {
      peak = currentEquity;
    }

    const drawdown = peak > 0 ? ((peak - currentEquity) / peak) * 100 : 0;
    maxDrawdown = Math.max(maxDrawdown, drawdown);
  }

  return {
    max: maxDrawdown,
    current: peak > 0 ? ((peak - currentEquity) / peak) * 100 : 0
  };
}

// فرمت وضعیت معامله
export function getTradeStatusText(status: TradeStatus): string {
  const statusMap: Record<TradeStatus, string> = {
    pending: 'در انتظار',
    open: 'باز',
    closed: 'بسته شده',
    cancelled: 'لغو شده'
  };

  return statusMap[status] || status;
}

// فرمت جهت معامله
export function getDirectionText(direction: 'buy' | 'sell'): string {
  return direction === 'buy' ? 'خرید' : 'فروش';
}

// فرمت وضعیت سیگنال
export function getSignalStatusText(status: SignalStatus): string {
  const statusMap: Record<SignalStatus, string> = {
    generated: 'تولید شده',
    sent: 'ارسال شده',
    executed: 'اجرا شده',
    expired: 'منقضی',
    skipped: 'رد شده'
  };

  return statusMap[status] || status;
}

// رنگ بر اساس سود/ضرر
export function getProfitColor(profit: number): string {
  if (profit > 0) return 'text-emerald-500';
  if (profit < 0) return 'text-rose-500';
  return 'text-slate-400';
}

// رنگ پس‌زمینه بر اساس سود/ضرر
export function getProfitBgColor(profit: number): string {
  if (profit > 0) return 'bg-emerald-500/10';
  if (profit < 0) return 'bg-rose-500/10';
  return 'bg-slate-500/10';
}

// محاسبه R:R
export function calculateRR(entry: number, sl: number, tp: number, _direction: 'buy' | 'sell'): number {
  const risk = Math.abs(entry - sl);
  const reward = Math.abs(tp - entry);

  if (risk === 0) return 0;

  return reward / risk;
}

// بررسی Kill Zone فعال
export function getActiveKillZone(): string {
  const now = new Date();
  const hour = now.getUTCHours();

  if (hour >= 8 && hour < 11) return 'لندن';
  if (hour >= 13 && hour < 16) return 'نیویورک';
  if (hour >= 0 && hour < 3) return 'توکیو';
  if (hour >= 22) return 'سیدنی';

  return 'خارج از Kill Zone';
}

// کلاس امتیاز
export function getScoreClass(score: number): string {
  if (score >= 80) return 'text-emerald-500 bg-emerald-500/10';
  if (score >= 65) return 'text-sky-500 bg-sky-500/10';
  if (score >= 50) return 'text-amber-500 bg-amber-500/10';
  return 'text-rose-500 bg-rose-500/10';
}

// کوتاه کردن متن
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '...';
}

// تولید ID
export function generateId(): string {
  return Math.random().toString(36).substring(2, 9);
}

// Deep clone
export function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj));
}

// Debounce
export function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;

  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

// Sleep
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
