/**
 * کامپوننت‌های پایه
 *
 * نویسنده: MT5 Trading Team
 */

import { AlertCircle, TrendingUp, TrendingDown } from 'lucide-react';
import { formatCurrency, formatNumber, formatPercent, getProfitColor } from '@/utils/helpers';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: number;
  isLoading?: boolean;
  color?: 'default' | 'success' | 'danger' | 'warning' | 'info';
}

export function StatCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  trendValue,
  isLoading,
  color = 'default'
}: StatCardProps) {
  const colorClasses = {
    default: 'bg-slate-500/10 text-slate-400',
    success: 'bg-emerald-500/10 text-emerald-500',
    danger: 'bg-rose-500/10 text-rose-500',
    warning: 'bg-amber-500/10 text-amber-500',
    info: 'bg-sky-500/10 text-sky-500'
  };

  if (isLoading) {
    return (
      <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700/50">
        <div className="animate-pulse">
          <div className="h-4 bg-slate-700 rounded w-1/2 mb-4"></div>
          <div className="h-8 bg-slate-700 rounded w-3/4"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700/50 hover:border-slate-600/50 transition-colors">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-slate-400 text-sm mb-1">{title}</p>
          <p className={`text-2xl font-bold ${
            color !== 'default' ? colorClasses[color].split(' ')[1] : 'text-slate-100'
          }`}>
            {typeof value === 'number' && title.includes('سود')
              ? formatCurrency(value)
              : typeof value === 'number'
                ? formatNumber(value)
                : value}
          </p>
          {subtitle && (
            <p className="text-slate-500 text-sm mt-1">{subtitle}</p>
          )}
        </div>
        {icon && (
          <div className={`p-3 rounded-lg ${colorClasses[color].split(' ')[0]}`}>
            {icon}
          </div>
        )}
      </div>
      {trend && (
        <div className="mt-4 flex items-center gap-2">
          {trend === 'up' && <TrendingUp className="w-4 h-4 text-emerald-500" />}
          {trend === 'down' && <TrendingDown className="w-4 h-4 text-rose-500" />}
          <span className={`text-sm ${
            trend === 'up' ? 'text-emerald-500' : trend === 'down' ? 'text-rose-500' : 'text-slate-400'
          }`}>
            {trendValue !== undefined ? formatPercent(trendValue) : trend}
          </span>
        </div>
      )}
    </div>
  );
}

// کارت خالی
export function EmptyCard({ message, icon: Icon }: { message: string; icon?: React.ComponentType<{ className?: string }> }) {
  return (
    <div className="bg-slate-800/30 rounded-xl p-8 border border-dashed border-slate-700 flex flex-col items-center justify-center text-center">
      {Icon && <Icon className="w-12 h-12 text-slate-600 mb-4" />}
      <p className="text-slate-400">{message}</p>
    </div>
  );
}

// کارت خطا
export function ErrorCard({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="bg-rose-500/10 rounded-xl p-6 border border-rose-500/30">
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-rose-500 mt-0.5" />
        <div>
          <p className="text-rose-400">{message}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 text-sm text-rose-300 hover:text-rose-200 underline"
            >
              تلاش مجدد
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// کارت سیگنال
interface SignalCardProps {
  id: string;
  symbol: string;
  direction: 'buy' | 'sell';
  score: number;
  entry: number;
  sl: number;
  tp: number;
  time: string;
  onExecute?: () => void;
  onSkip?: () => void;
}

export function SignalCard({
  symbol,
  direction,
  score,
  entry,
  sl,
  tp,
  time,
  onExecute,
  onSkip
}: SignalCardProps) {
  return (
    <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-1 rounded text-xs font-medium ${
            direction === 'buy'
              ? 'bg-emerald-500/20 text-emerald-400'
              : 'bg-rose-500/20 text-rose-400'
          }`}>
            {direction === 'buy' ? 'خرید' : 'فروش'}
          </span>
          <span className="font-semibold text-slate-100">{symbol}</span>
        </div>
        <div className={`text-sm font-semibold ${
          score >= 80 ? 'text-emerald-400' :
          score >= 65 ? 'text-sky-400' :
          score >= 50 ? 'text-amber-400' : 'text-rose-400'
        }`}>
          {score}/100
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="text-center">
          <p className="text-slate-500 text-xs mb-1">ورود</p>
          <p className="text-slate-200 font-medium">{entry}</p>
        </div>
        <div className="text-center">
          <p className="text-slate-500 text-xs mb-1">حد ضرر</p>
          <p className="text-rose-400 font-medium">{sl}</p>
        </div>
        <div className="text-center">
          <p className="text-slate-500 text-xs mb-1">حد سود</p>
          <p className="text-emerald-400 font-medium">{tp}</p>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={onExecute}
          className="flex-1 bg-emerald-500/20 text-emerald-400 py-2 rounded-lg text-sm font-medium hover:bg-emerald-500/30 transition-colors"
        >
          اجرا
        </button>
        <button
          onClick={onSkip}
          className="flex-1 bg-slate-700/50 text-slate-300 py-2 rounded-lg text-sm font-medium hover:bg-slate-700 transition-colors"
        >
          رد
        </button>
      </div>

      <p className="text-slate-600 text-xs text-center mt-3">{time}</p>
    </div>
  );
}

// کارت معامله
interface TradeCardProps {
  symbol: string;
  direction: 'buy' | 'sell';
  status?: string;
  volume: number;
  entry: number;
  current?: number;
  profit: number;
  openedAt: string;
  onClick?: () => void;
}

export function TradeCard({
  symbol,
  direction,
  volume,
  entry,
  profit,
  openedAt,
  onClick
}: TradeCardProps) {
  return (
    <div
      onClick={onClick}
      className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 hover:border-slate-600/50 cursor-pointer transition-colors"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-lg ${
            direction === 'buy' ? 'text-emerald-500' : 'text-rose-500'
          }`}>
            {direction === 'buy' ? '↑' : '↓'}
          </span>
          <span className="font-semibold text-slate-100">{symbol}</span>
        </div>
        <span className={`font-semibold ${getProfitColor(profit)}`}>
          {formatCurrency(profit)}
        </span>
      </div>

      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-500">
          {volume} • {entry}
        </span>
        <span className="text-slate-600">{openedAt}</span>
      </div>
    </div>
  );
}

// کارت امتیاز
interface ScoreCardProps {
  score: number;
  label: string;
  breakdown?: { name: string; score: number; weight: number }[];
}

export function ScoreCard({ score, label, breakdown }: ScoreCardProps) {
  const getScoreColor = (s: number) => {
    if (s >= 80) return 'text-emerald-500';
    if (s >= 65) return 'text-sky-500';
    if (s >= 50) return 'text-amber-500';
    return 'text-rose-500';
  };

  const getBarColor = (s: number) => {
    if (s >= 80) return 'bg-emerald-500';
    if (s >= 65) return 'bg-sky-500';
    if (s >= 50) return 'bg-amber-500';
    return 'bg-rose-500';
  };

  return (
    <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
      <div className="flex items-center justify-between mb-3">
        <span className="text-slate-400 text-sm">{label}</span>
        <span className={`font-bold text-xl ${getScoreColor(score)}`}>
          {score}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden mb-4">
        <div
          className={`h-full ${getBarColor(score)} transition-all duration-500`}
          style={{ width: `${score}%` }}
        />
      </div>

      {/* Breakdown */}
      {breakdown && breakdown.length > 0 && (
        <div className="space-y-2">
          {breakdown.map((item) => (
            <div key={item.name} className="flex items-center justify-between">
              <span className="text-slate-500 text-xs">{item.name}</span>
              <div className="flex items-center gap-2">
                <span className="text-slate-400 text-xs">{item.score}</span>
                <span className="text-slate-600 text-xs">({(item.weight * 100).toFixed(0)}%)</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
