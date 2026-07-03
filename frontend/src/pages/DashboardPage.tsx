// frontend/src/pages/DashboardPage.tsx
import React from "react";
import { TrendingUp, TrendingDown, Activity, DollarSign, BarChart2, Shield, Target, Zap, AlertTriangle } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { format } from "date-fns";
import { dashboardApi, tradesApi, signalsApi } from "@/utils/api";
import { usePoll, useApi } from "@/hooks/useApi";
import StatCard from "@/components/StatCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";
import Badge from "@/components/Badge";

export default function DashboardPage() {
  const { data: stats, isLoading: sl, error: se, refetch: sr } = usePoll(dashboardApi.getStats, 15_000);
  const { data: equity, isLoading: el, error: ee }             = usePoll(() => dashboardApi.getEquity(30), 60_000);
  const { data: openTrades }  = useApi(() => tradesApi.listOpen(1, 5).then((r: any) => r.items));
  const { data: recentSignals } = useApi(() => signalsApi.list(1, 4).then((r: any) => r.items));

  if (sl || el) return <LoadingSpinner text="در حال بارگذاری داشبورد..." />;
  if (se) return <div className="p-6"><ErrorAlert message={se} onRetry={sr} /></div>;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">داشبورد</h1>
        <p className="text-sm text-gray-400 mt-1">خلاصه وضعیت حساب و معاملات</p>
      </div>
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="موجودی" value={`$${stats.equity?.toLocaleString()}`} subtitle={`بالانس: $${stats.balance?.toLocaleString()}`} icon={DollarSign} color="blue" />
          <StatCard title="سود/زیان روز" value={`$${stats.daily_pnl?.toFixed(2)}`} subtitle={stats.daily_pnl >= 0 ? "▲ مثبت" : "▼ منفی"} icon={stats.daily_pnl >= 0 ? TrendingUp : TrendingDown} trend={stats.daily_pnl >= 0 ? "up" : "down"} color={stats.daily_pnl >= 0 ? "green" : "red"} />
          <StatCard title="نرخ موفقیت" value={`${stats.win_rate?.toFixed(1)}%`} subtitle={`${stats.total_trades} معامله کل`} icon={Target} color="purple" />
          <StatCard title="Drawdown" value={`${stats.drawdown?.toFixed(2)}%`} subtitle={stats.drawdown < 10 ? "ریسک پایین" : stats.drawdown < 20 ? "ریسک متوسط" : "⚠️ هشدار"} icon={Shield} color={stats.drawdown < 10 ? "green" : stats.drawdown < 20 ? "yellow" : "red"} />
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {equity && (
          <div className="lg:col-span-2 rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="text-sm font-semibold text-white mb-4">منحنی سرمایه — ۳۰ روز</h2>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={equity}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="date" tick={{ fill: "#9ca3af", fontSize: 10 }} tickFormatter={(d: string) => format(new Date(d), "MM/dd")} />
                <YAxis tick={{ fill: "#9ca3af", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 8 }} formatter={(v: number) => [`$${v.toLocaleString()}`, "موجودی"]} />
                <Area type="monotone" dataKey="equity" stroke="#3b82f6" fill="#3b82f620" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
            <Zap size={15} className="text-yellow-400" /> سیگنال‌های اخیر
          </h2>
          {recentSignals?.length ? (
            <div className="space-y-2">
              {recentSignals.map((s: any) => (
                <div key={s.id} className="flex items-center justify-between p-2 rounded-lg bg-gray-800/50">
                  <div><p className="text-xs font-mono text-white">{s.symbol}</p><p className="text-xs text-gray-500">{s.timeframe}</p></div>
                  <div className="text-right">
                    <Badge label={s.direction === "buy" ? "خرید" : "فروش"} color={s.direction === "buy" ? "green" : "red"} />
                    <p className="text-xs text-gray-500 mt-0.5">{(s.confidence * 100).toFixed(0)}%</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-6">
              <Activity size={32} className="mx-auto mb-2 text-gray-600" />
              <p className="text-xs text-gray-500">سیگنالی موجود نیست</p>
            </div>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><BarChart2 size={15} className="text-blue-400" /> معاملات باز</h2>
        </div>
        {openTrades?.length ? (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-gray-800 text-gray-400 text-xs">{["نماد","جهت","حجم","قیمت ورود","P&L فعلی"].map(h => <th key={h} className="text-right px-4 py-3 font-medium">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-gray-800">
              {openTrades.map((t: any) => {
                const pnl = t.pnl ?? 0;
                return (<tr key={t.id} className="hover:bg-gray-800/50 transition-colors">
                  <td className="px-4 py-3 font-mono text-white">{t.symbol}</td>
                  <td className="px-4 py-3"><Badge label={t.direction === "buy" ? "خرید" : "فروش"} color={t.direction === "buy" ? "green" : "red"} /></td>
                  <td className="px-4 py-3 text-gray-300">{t.lot_size}</td>
                  <td className="px-4 py-3 font-mono text-gray-300 text-xs">{t.entry_price?.toFixed(5)}</td>
                  <td className={`px-4 py-3 font-mono font-medium ${pnl >= 0 ? "text-green-400" : "text-red-400"}`}>{pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}</td>
                </tr>);
              })}
            </tbody>
          </table>
        ) : (
          <div className="text-center py-8"><AlertTriangle size={32} className="mx-auto mb-2 text-gray-600" /><p className="text-sm text-gray-500">هیچ معامله بازی وجود ندارد</p></div>
        )}
      </div>
    </div>
  );
}
