// frontend/src/pages/DashboardPage.tsx
import React from "react";
import { TrendingUp, TrendingDown, Activity, DollarSign, BarChart2, Shield, Target, Zap } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { format } from "date-fns";
import { dashboardApi } from "@/utils/api";
import { usePoll } from "@/hooks/useApi";
import StatCard from "@/components/StatCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

export default function DashboardPage() {
  const { data: stats, isLoading: sl, error: se, refetch: sr } = usePoll(dashboardApi.getStats, 15_000);
  const { data: equity, isLoading: el, error: ee, refetch: er } = usePoll(() => dashboardApi.getEquity(30), 60_000);

  if (sl || el) return <LoadingSpinner text="در حال بارگذاری داشبورد..." />;
  if (se) return <div className="p-6"><ErrorAlert message={se} onRetry={sr} /></div>;
  if (ee) return <div className="p-6"><ErrorAlert message={ee} onRetry={er} /></div>;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">داشبورد</h1>
        <p className="text-sm text-gray-400 mt-1">خلاصه وضعیت حساب و معاملات</p>
      </div>
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="موجودی" value={`$${stats.equity.toLocaleString()}`} subtitle={`بالانس: $${stats.balance.toLocaleString()}`} icon={DollarSign} color="blue" />
          <StatCard title="سود/زیان روز" value={`$${stats.daily_pnl.toFixed(2)}`} subtitle={stats.daily_pnl >= 0 ? "▲ مثبت" : "▼ منفی"} icon={stats.daily_pnl >= 0 ? TrendingUp : TrendingDown} trend={stats.daily_pnl >= 0 ? "up" : "down"} color={stats.daily_pnl >= 0 ? "green" : "red"} />
          <StatCard title="نرخ موفقیت" value={`${stats.win_rate.toFixed(1)}%`} subtitle={`${stats.total_trades} معامله کل`} icon={Target} color="purple" />
          <StatCard title="معاملات باز" value={stats.open_trades} subtitle={`DD: ${stats.drawdown.toFixed(1)}%`} icon={Activity} color="yellow" />
          <StatCard title="Profit Factor" value={stats.profit_factor.toFixed(2)} icon={BarChart2} color="green" />
          <StatCard title="Sharpe Ratio" value={stats.sharpe_ratio.toFixed(2)} icon={Shield} color="blue" />
          <StatCard title="سود کل" value={`$${stats.total_pnl.toFixed(2)}`} trend={stats.total_pnl >= 0 ? "up" : "down"} icon={TrendingUp} color={stats.total_pnl >= 0 ? "green" : "red"} />
          <StatCard title="Drawdown" value={`${stats.drawdown.toFixed(2)}%`} icon={Zap} color="yellow" />
        </div>
      )}
      {equity && equity.length > 0 && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="text-sm font-semibold text-white mb-4">منحنی سرمایه — ۳۰ روز گذشته</h2>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={equity}>
              <defs>
                <linearGradient id="eg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="timestamp" tickFormatter={v => format(new Date(v), "dd/MM")} tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v.toLocaleString()}`} />
              <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151", borderRadius: 8 }} labelStyle={{ color: "#9ca3af", fontSize: 11 }} formatter={(v: number) => [`$${v.toLocaleString()}`, "سرمایه"]} labelFormatter={v => format(new Date(v as string), "yyyy/MM/dd")} />
              <Area type="monotone" dataKey="equity" stroke="#3b82f6" strokeWidth={2} fill="url(#eg)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
