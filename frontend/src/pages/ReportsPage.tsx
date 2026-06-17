/**
 * صفحه گزارش‌ها
 *
 * نویسنده: MT5 Trading Team
 */

import { useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Target,
  BarChart3
} from 'lucide-react';
import { StatCard } from '@/components/common/Card';
import { EquityChart, BarChart } from '@/components/common/Chart';
import { useDailyReport, useWeeklyReport, useMonthlyReport, usePerformance } from '@/hooks/useApi';
import { formatCurrency, formatNumber } from '@/utils/helpers';

type ReportPeriod = 'daily' | 'weekly' | 'monthly';

interface ReportSummary {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  net_profit: number;
}

interface ReportData {
  summary: ReportSummary;
  daily_breakdown?: Array<{
    date: string;
    trades: number;
    profit: number;
  }>;
}

interface PerformanceData {
  metrics: {
    profit_factor: number;
    avg_trade: number;
    win_rate: number;
    total_trades: number;
  };
}

export function ReportsPage() {
  const [period, setPeriod] = useState<ReportPeriod>('daily');

  const { data: dailyData, isLoading: dailyLoading } = useDailyReport() as { data: ReportData | null; isLoading: boolean };
  const { data: weeklyData, isLoading: weeklyLoading } = useWeeklyReport() as { data: ReportData | null; isLoading: boolean };
  const { data: monthlyData, isLoading: monthlyLoading } = useMonthlyReport() as { data: ReportData | null; isLoading: boolean };
  const { data: performanceData } = usePerformance('month') as { data: PerformanceData | null };

  // انتخاب داده‌ها
  const { data, isLoading } = period === 'daily'
    ? { data: dailyData, isLoading: dailyLoading }
    : period === 'weekly'
      ? { data: weeklyData, isLoading: weeklyLoading }
      : { data: monthlyData, isLoading: monthlyLoading };

  const summary: ReportSummary = data?.summary || { total_trades: 0, winning_trades: 0, losing_trades: 0, win_rate: 0, gross_profit: 0, gross_loss: 0, net_profit: 0 };
  const performance = performanceData?.metrics || { profit_factor: 0, avg_trade: 0, win_rate: 0, total_trades: 0 };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">گزارش‌ها</h1>
          <p className="text-slate-500 mt-1">تحلیل عملکرد معاملات</p>
        </div>
      </div>

      {/* Period Tabs */}
      <div className="flex bg-slate-800/50 rounded-xl p-1 border border-slate-700/50">
        {(['daily', 'weekly', 'monthly'] as ReportPeriod[]).map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              period === p
                ? 'bg-sky-500/20 text-sky-400'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {p === 'daily' ? 'روزانه' : p === 'weekly' ? 'هفتگی' : 'ماهانه'}
          </button>
        ))}
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard
          title="تعداد معاملات"
          value={summary?.total_trades || 0}
          icon={<BarChart3 className="w-6 h-6" />}
          isLoading={isLoading}
        />

        <StatCard
          title="برنده"
          value={summary?.winning_trades || 0}
          icon={<TrendingUp className="w-6 h-6" />}
          color="success"
          isLoading={isLoading}
        />

        <StatCard
          title="بازنده"
          value={summary?.losing_trades || 0}
          icon={<TrendingDown className="w-6 h-6" />}
          color="danger"
          isLoading={isLoading}
        />

        <StatCard
          title="وین ریت"
          value={`${formatNumber(summary?.win_rate || 0)}%`}
          icon={<Target className="w-6 h-6" />}
          color={(summary?.win_rate || 0) >= 60 ? 'success' : 'warning'}
          isLoading={isLoading}
        />
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Profit/Loss */}
        <div className="lg:col-span-2">
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
            <h2 className="text-lg font-semibold text-slate-100 mb-6">سود و ضرر</h2>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="p-4 bg-emerald-500/10 rounded-lg border border-emerald-500/20">
                <p className="text-emerald-400 text-sm mb-1">سود ناخالص</p>
                <p className="text-2xl font-bold text-emerald-500">
                  {formatCurrency(summary?.gross_profit || 0)}
                </p>
              </div>

              <div className="p-4 bg-rose-500/10 rounded-lg border border-rose-500/20">
                <p className="text-rose-400 text-sm mb-1">ضرر ناخالص</p>
                <p className="text-2xl font-bold text-rose-500">
                  {formatCurrency(Math.abs(summary?.gross_loss || 0))}
                </p>
              </div>

              <div className={`p-4 rounded-lg border ${
                (summary?.net_profit || 0) >= 0
                  ? 'bg-emerald-500/10 border-emerald-500/20'
                  : 'bg-rose-500/10 border-rose-500/20'
              }`}>
                <p className={`text-sm mb-1 ${
                  (summary?.net_profit || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}>
                  سود خالص
                </p>
                <p className={`text-2xl font-bold ${
                  (summary?.net_profit || 0) >= 0 ? 'text-emerald-500' : 'text-rose-500'
                }`}>
                  {formatCurrency(summary?.net_profit || 0)}
                </p>
              </div>
            </div>

            {/* Weekly Breakdown (if weekly) */}
            {period === 'weekly' && weeklyData?.daily_breakdown && (
              <div className="mt-6">
                <h3 className="text-slate-200 font-medium mb-3">تفکیک روزانه</h3>
                <div className="space-y-2">
                  {weeklyData.daily_breakdown.map((day: {
                    date: string;
                    trades: number;
                    profit: number;
                  }, index: number) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-slate-400 text-sm">{day.date}</span>
                        <span className="text-slate-500 text-xs">
                          {day.trades} معامله
                        </span>
                      </div>
                      <span className={`font-medium ${
                        day.profit >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                        {formatCurrency(day.profit)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Performance Metrics */}
        <div>
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
            <h2 className="text-lg font-semibold text-slate-100 mb-4">معیارهای عملکرد</h2>

            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg">
                <span className="text-slate-400">فاکتور سود</span>
                <span className={`font-semibold ${
                  (performance?.profit_factor || 0) >= 2 ? 'text-emerald-500' :
                  (performance?.profit_factor || 0) >= 1 ? 'text-sky-500' : 'text-rose-500'
                }`}>
                  {formatNumber(performance?.profit_factor || 0)}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg">
                <span className="text-slate-400">میانگین هر معامله</span>
                <span className={`font-semibold ${
                  (performance?.avg_trade || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}>
                  {formatCurrency(performance?.avg_trade || 0)}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg">
                <span className="text-slate-400">وین ریت</span>
                <span className="font-semibold text-sky-400">
                  {formatNumber(performance?.win_rate || 0)}%
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-slate-700/30 rounded-lg">
                <span className="text-slate-400">کل معاملات</span>
                <span className="font-semibold text-slate-200">
                  {performance?.total_trades || 0}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Chart Placeholder */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
        <h2 className="text-lg font-semibold text-slate-100 mb-4">نمودار Equity</h2>
        <EquityChart
          data={
            (() => {
              const breakdown = weeklyData?.daily_breakdown || [];
              let cumulative = 0;
              return breakdown.map((day: {
                date: string;
                trades: number;
                profit: number;
              }) => {
                cumulative += day.profit;
                return {
                  date: day.date,
                  value: cumulative
                };
              });
            })()
          }
          height={256}
        />
      </div>

      {/* Daily Breakdown Bar Chart */}
      {period === 'weekly' && weeklyData?.daily_breakdown && (
        <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
          <h2 className="text-lg font-semibold text-slate-100 mb-4">تفکیک روزانه</h2>
          <BarChart
            data={weeklyData.daily_breakdown.map((day: {
              date: string;
              trades: number;
              profit: number;
            }) => ({
              label: day.date.slice(5),
              value: day.profit,
              color: day.profit >= 0 ? 'rgba(34, 197, 94, 0.5)' : 'rgba(239, 68, 68, 0.5)'
            }))}
            height={150}
          />
        </div>
      )}
    </div>
  );
}
