/**
 * صفحه داشبورد
 *
 * نویسنده: MT5 Trading Team
 */

import {
  TrendingUp,
  DollarSign,
  Target,
  Activity,
  Bell,
  Clock
} from 'lucide-react';
import { StatCard, SignalCard, TradeCard, ScoreCard, EmptyCard, ErrorCard } from '@/components/common/Card';
import { useOpenTrades, useActiveSignals, useDailyReport, usePerformance } from '@/hooks/useApi';
import { formatCurrency, formatNumber, formatRelativeTime } from '@/utils/helpers';

interface TradeItem {
  id: string;
  symbol: string;
  direction: 'buy' | 'sell';
  status: string;
  profit_money: number;
  entry_price: number;
  volume: number;
  opened_at: string;
}

interface OpenTradesData {
  positions: TradeItem[];
}

interface ActiveSignalsData {
  active_signals: Array<{
    id: string;
    symbol: string;
    direction: 'buy' | 'sell';
    total_score: number;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    valid_until: string;
  }>;
}

interface DailyReportData {
  summary: {
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    win_rate: number;
    net_profit: number;
  };
}

interface PerformanceData {
  metrics: {
    win_rate: number;
  };
}

export function DashboardPage() {
  const { data: openTrades, isLoading: tradesLoading, error: tradesError } = useOpenTrades() as unknown as { data: OpenTradesData | null; isLoading: boolean; error: string | null };
  const { data: activeSignals } = useActiveSignals() as unknown as { data: ActiveSignalsData | null };
  const { data: dailyReport, isLoading: reportLoading } = useDailyReport() as unknown as { data: DailyReportData | null; isLoading: boolean };
  const { data: performance } = usePerformance('month') as unknown as { data: PerformanceData | null };

  // استخراج داده‌ها
  const trades = openTrades?.positions || [];
  const signals = activeSignals?.active_signals || [];
  const summary = dailyReport?.summary || { total_trades: 0, winning_trades: 0, losing_trades: 0, win_rate: 0, net_profit: 0 };

  // محاسبات
  const openPnL = trades.reduce((sum, t) => sum + (t.profit_money || 0), 0);
  const dailyPnL = summary?.net_profit || 0;
  const winRate = performance?.metrics?.win_rate || 0;
  const totalTrades = trades.length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">داشبورد</h1>
          <p className="text-slate-500 mt-1">نمای کلی وضعیت معاملات</p>
        </div>
        <div className="flex items-center gap-2 text-slate-500">
          <Clock className="w-4 h-4" />
          <span className="text-sm">به‌روزرسانی: {formatRelativeTime(new Date().toISOString())}</span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="سود/ضرر باز"
          value={formatCurrency(openPnL)}
          icon={<Activity className="w-6 h-6" />}
          color={openPnL >= 0 ? 'success' : 'danger'}
          isLoading={tradesLoading}
        />

        <StatCard
          title="سود/ضرر امروز"
          value={formatCurrency(dailyPnL)}
          icon={<DollarSign className="w-6 h-6" />}
          color={dailyPnL >= 0 ? 'success' : 'danger'}
          isLoading={reportLoading}
        />

        <StatCard
          title="وین ریت"
          value={`${formatNumber(winRate)}%`}
          icon={<Target className="w-6 h-6" />}
          color={winRate >= 60 ? 'success' : winRate >= 50 ? 'warning' : 'danger'}
        />

        <StatCard
          title="معاملات باز"
          value={totalTrades}
          icon={<TrendingUp className="w-6 h-6" />}
          color="info"
          isLoading={tradesLoading}
        />
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Trades */}
        <div className="lg:col-span-2">
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-sky-500" />
                معاملات باز
              </h2>
              <span className="text-sm text-slate-500">{totalTrades} معامله</span>
            </div>

            {tradesError ? (
              <ErrorCard message="خطا در دریافت معاملات" />
            ) : trades.length === 0 ? (
              <EmptyCard message="معامله‌ای باز نیست" icon={TrendingUp} />
            ) : (
              <div className="space-y-3">
                {(trades as TradeItem[]).slice(0, 5).map((trade) => (
                  <TradeCard
                    key={trade.id}
                    symbol={trade.symbol}
                    direction={trade.direction}
                    volume={trade.volume}
                    entry={trade.entry_price}
                    profit={trade.profit_money}
                    openedAt={formatRelativeTime(trade.opened_at)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Active Signals */}
        <div>
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
                <Bell className="w-5 h-5 text-amber-500" />
                سیگنال‌های فعال
              </h2>
            </div>

            {signals.length === 0 ? (
              <EmptyCard message="سیگنال فعالی نیست" icon={Bell} />
            ) : (
              <div className="space-y-3">
                {signals.slice(0, 3).map((signal: {
                  id: string;
                  symbol: string;
                  direction: 'buy' | 'sell';
                  total_score: number;
                  entry_price: number;
                  stop_loss: number;
                  take_profit: number;
                  valid_until: string;
                }) => (
                  <SignalCard
                    key={signal.id}
                    id={signal.id}
                    symbol={signal.symbol}
                    direction={signal.direction}
                    score={signal.total_score}
                    entry={signal.entry_price}
                    sl={signal.stop_loss}
                    tp={signal.take_profit}
                    time={formatRelativeTime(signal.valid_until)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Today Summary */}
        <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
          <h3 className="text-lg font-semibold text-slate-100 mb-4">خلاصه امروز</h3>

          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 bg-slate-700/30 rounded-lg">
              <p className="text-slate-500 text-sm mb-1">معاملات</p>
              <p className="text-2xl font-bold text-slate-100">{summary?.total_trades || 0}</p>
            </div>
            <div className="p-4 bg-slate-700/30 rounded-lg">
              <p className="text-slate-500 text-sm mb-1">برنده</p>
              <p className="text-2xl font-bold text-emerald-500">{summary?.winning_trades || 0}</p>
            </div>
            <div className="p-4 bg-slate-700/30 rounded-lg">
              <p className="text-slate-500 text-sm mb-1">بازنده</p>
              <p className="text-2xl font-bold text-rose-500">{summary?.losing_trades || 0}</p>
            </div>
            <div className="p-4 bg-slate-700/30 rounded-lg">
              <p className="text-slate-500 text-sm mb-1">وین ریت</p>
              <p className="text-2xl font-bold text-sky-500">
                {summary?.win_rate ? `${summary.win_rate.toFixed(1)}%` : '0%'}
              </p>
            </div>
          </div>
        </div>

        {/* Performance Score */}
        <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
          <h3 className="text-lg font-semibold text-slate-100 mb-4">عملکرد ماهانه</h3>

          <ScoreCard
            score={winRate}
            label="وین ریت"
            breakdown={[
              { name: 'SMC', score: 75, weight: 0.35 },
              { name: 'Price Action', score: 68, weight: 0.30 },
              { name: 'زمان', score: 85, weight: 0.15 },
              { name: 'ریسک', score: 90, weight: 0.10 },
              { name: 'مومنتوم', score: 60, weight: 0.10 }
            ]}
          />
        </div>
      </div>

      {/* Kill Zones */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
        <h3 className="text-lg font-semibold text-slate-100 mb-4">Kill Zones</h3>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { name: 'توکیو', start: '00:00', end: '03:00', active: false, color: 'bg-amber-500' },
            { name: 'لندن', start: '08:00', end: '11:00', active: true, color: 'bg-sky-500' },
            { name: 'نیویورک', start: '13:00', end: '16:00', active: false, color: 'bg-emerald-500' },
            { name: 'سیدنی', start: '22:00', end: '01:00', active: false, color: 'bg-violet-500' }
          ].map((kz) => (
            <div
              key={kz.name}
              className={`p-4 rounded-lg border ${
                kz.active
                  ? 'bg-slate-700/50 border-sky-500/50'
                  : 'bg-slate-800/50 border-slate-700/50'
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-2 h-2 rounded-full ${kz.color} ${kz.active ? 'animate-pulse' : ''}`}></div>
                <span className="font-medium text-slate-200">{kz.name}</span>
                {kz.active && (
                  <span className="text-xs text-emerald-400 font-medium">فعال</span>
                )}
              </div>
              <p className="text-slate-500 text-sm">
                {kz.start} - {kz.end} UTC
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
