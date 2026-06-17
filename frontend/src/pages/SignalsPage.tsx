/**
 * صفحه سیگنال‌ها
 *
 * نویسنده: MT5 Trading Team
 */

import { useState } from 'react';
import {
  Bell,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  RefreshCw
} from 'lucide-react';
import { EmptyCard } from '@/components/common/Card';
import { useActiveSignals, useSignals } from '@/hooks/useApi';
import { formatRelativeTime, getDirectionText } from '@/utils/helpers';

type SignalFilter = 'all' | 'active' | 'executed' | 'expired';

interface SignalData {
  id: string;
  symbol: string;
  direction: 'buy' | 'sell';
  status: string;
  total_score: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  generated_at: string;
  valid_until: string;
  reason?: string;
}

interface ActiveSignalsData {
  active_signals: SignalData[];
}

interface AllSignalsData {
  signals: SignalData[];
}

export function SignalsPage() {
  const [filter, setFilter] = useState<SignalFilter>('all');

  const { data: activeSignals } = useActiveSignals() as { data: ActiveSignalsData | null };
  const { data: allSignals, refetch } = useSignals({ limit: 50 }) as { data: AllSignalsData | null; refetch: () => void };

  // انتخاب داده‌ها
  const signals: SignalData[] = filter === 'active'
    ? activeSignals?.active_signals || []
    : allSignals?.signals || [];

  // آمار
  const total = signals.length;
  const executed = signals.filter(s => s.status === 'executed').length;
  const expired = signals.filter(s => s.status === 'expired').length;
  const pending = signals.filter(s => s.status === 'generated').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">سیگنال‌ها</h1>
          <p className="text-slate-500 mt-1">سیگنال‌های خرید و فروش</p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-4 py-2 bg-slate-700/50 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          به‌روزرسانی
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
          <div className="flex items-center gap-2 mb-2">
            <Bell className="w-5 h-5 text-slate-400" />
            <span className="text-slate-500 text-sm">کل</span>
          </div>
          <p className="text-2xl font-bold text-slate-100">{total}</p>
        </div>

        <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="w-5 h-5 text-emerald-400" />
            <span className="text-slate-500 text-sm">اجرا شده</span>
          </div>
          <p className="text-2xl font-bold text-emerald-500">{executed}</p>
        </div>

        <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle className="w-5 h-5 text-amber-400" />
            <span className="text-slate-500 text-sm">در انتظار</span>
          </div>
          <p className="text-2xl font-bold text-amber-500">{pending}</p>
        </div>

        <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
          <div className="flex items-center gap-2 mb-2">
            <XCircle className="w-5 h-5 text-rose-400" />
            <span className="text-slate-500 text-sm">منقضی</span>
          </div>
          <p className="text-2xl font-bold text-rose-500">{expired}</p>
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2 bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
        <span className="text-slate-500 text-sm">فیلتر:</span>
        <div className="flex bg-slate-700/50 rounded-lg p-1">
          {(['all', 'active', 'executed', 'expired'] as SignalFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                filter === f
                  ? 'bg-sky-500/20 text-sky-400'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {f === 'all' ? 'همه' : f === 'active' ? 'فعال' : f === 'executed' ? 'اجرا شده' : 'منقضی'}
            </button>
          ))}
        </div>
      </div>

      {/* Signals Grid */}
      {signals.length === 0 ? (
        <EmptyCard message="سیگنالی یافت نشد" icon={Bell} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {signals.map((signal: {
            id: string;
            symbol: string;
            direction: 'buy' | 'sell';
            status: string;
            total_score: number;
            entry_price: number;
            stop_loss: number;
            take_profit: number;
            generated_at: string;
            valid_until: string;
            reason?: string;
          }) => (
            <div
              key={signal.id}
              className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4 hover:border-slate-600/50 transition-colors"
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    signal.direction === 'buy'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-rose-500/20 text-rose-400'
                  }`}>
                    {getDirectionText(signal.direction)}
                  </span>
                  <span className="font-semibold text-slate-100">{signal.symbol}</span>
                </div>

                <div className={`px-2 py-1 rounded text-xs font-medium ${
                  signal.status === 'executed'
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : signal.status === 'expired'
                      ? 'bg-rose-500/20 text-rose-400'
                      : 'bg-sky-500/20 text-sky-400'
                }`}>
                  {signal.status === 'executed' ? 'اجرا شده' :
                   signal.status === 'expired' ? 'منقضی' :
                   signal.status === 'generated' ? 'در انتظار' : signal.status}
                </div>
              </div>

              {/* Score */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-slate-500 text-sm">امتیاز</span>
                  <span className={`font-bold text-lg ${
                    signal.total_score >= 80 ? 'text-emerald-500' :
                    signal.total_score >= 65 ? 'text-sky-500' :
                    signal.total_score >= 50 ? 'text-amber-500' : 'text-rose-500'
                  }`}>
                    {signal.total_score}/100
                  </span>
                </div>
                <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full ${
                      signal.total_score >= 80 ? 'bg-emerald-500' :
                      signal.total_score >= 65 ? 'bg-sky-500' :
                      signal.total_score >= 50 ? 'bg-amber-500' : 'bg-rose-500'
                    }`}
                    style={{ width: `${signal.total_score}%` }}
                  />
                </div>
              </div>

              {/* Levels */}
              <div className="grid grid-cols-3 gap-2 mb-4">
                <div className="text-center p-2 bg-slate-700/30 rounded">
                  <p className="text-slate-500 text-xs mb-1">ورود</p>
                  <p className="text-slate-200 text-sm font-medium">{signal.entry_price}</p>
                </div>
                <div className="text-center p-2 bg-slate-700/30 rounded">
                  <p className="text-slate-500 text-xs mb-1">حد ضرر</p>
                  <p className="text-rose-400 text-sm font-medium">{signal.stop_loss}</p>
                </div>
                <div className="text-center p-2 bg-slate-700/30 rounded">
                  <p className="text-slate-500 text-xs mb-1">حد سود</p>
                  <p className="text-emerald-400 text-sm font-medium">{signal.take_profit}</p>
                </div>
              </div>

              {/* Time */}
              <div className="flex items-center justify-between text-slate-500 text-sm border-t border-slate-700/50 pt-3">
                <div className="flex items-center gap-1">
                  <Clock className="w-4 h-4" />
                  <span>{formatRelativeTime(signal.generated_at)}</span>
                </div>
                {signal.reason && (
                  <span className="text-xs text-slate-600 truncate max-w-[150px]">
                    {signal.reason}
                  </span>
                )}
              </div>

              {/* Actions (only for pending) */}
              {signal.status === 'generated' && (
                <div className="flex gap-2 mt-3 pt-3 border-t border-slate-700/50">
                  <button className="flex-1 bg-emerald-500/20 text-emerald-400 py-2 rounded-lg text-sm font-medium hover:bg-emerald-500/30 transition-colors">
                    اجرا
                  </button>
                  <button className="flex-1 bg-slate-700/50 text-slate-300 py-2 rounded-lg text-sm font-medium hover:bg-slate-700 transition-colors">
                    رد
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
