import { useEffect, useState } from "react";
import { BarChart3, TrendingUp } from "lucide-react";
import { analyticsApi } from "../utils/api";
import { StatCard } from "../components/common/StatCard";
import type { AnalyticsMetrics, BreakdownItem } from "../types";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, PieChart, Pie, Legend
} from "recharts";

const PIE_COLORS = ["#10b981", "#ef4444", "#f59e0b"];

export default function AnalyticsPage() {
  const [metrics,   setMetrics]   = useState<AnalyticsMetrics | null>(null);
  const [bySymbol,  setBySymbol]  = useState<BreakdownItem[]>([]);
  const [bySession, setBySession] = useState<BreakdownItem[]>([]);
  const [loading,   setLoading]   = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      const [m, s, ss] = await Promise.all([analyticsApi.getMetrics(), analyticsApi.getBySymbol(), analyticsApi.getBySession()]);
      if (m.success)  setMetrics(m.data);
      if (s.success)  setBySymbol(s.data ?? []);
      if (ss.success) setBySession(ss.data ?? []);
      setLoading(false);
    })();
  }, []);

  if (loading) return <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin" /></div>;

  const winLossData = metrics ? [
    { name: "Win",       value: Math.round((metrics.win_rate)       * (metrics.total_trades ?? 100)) },
    { name: "Loss",      value: Math.round((1 - metrics.win_rate)   * (metrics.total_trades ?? 100)) },
  ] : [];

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-[#00d4ff]/10 border border-[#00d4ff]/30 flex items-center justify-center">
          <BarChart3 size={20} className="text-[#00d4ff]" />
        </div>
        <div>
          <h1 className="text-[#f0f6ff] text-xl font-bold">آنالیتیکس</h1>
          <p className="text-[#475569] text-sm">معیارهای کمّی حرفه‌ای</p>
        </div>
      </div>

      {/* Primary ratios */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Sharpe Ratio"   value={metrics?.sharpe_ratio   ?? 0} format="ratio"   color="accent" glow icon={<TrendingUp size={18} />} subtitle={`Sortino: ${(metrics?.sortino_ratio ?? 0).toFixed(3)}`} />
        <StatCard title="Calmar Ratio"   value={metrics?.calmar_ratio   ?? 0} format="ratio"   color="purple" />
        <StatCard title="Profit Factor"  value={metrics?.profit_factor  ?? 0} format="ratio"   color="green"  />
        <StatCard title="Recovery Factor" value={metrics?.recovery_factor ?? 0} format="ratio" color="gold"   />
      </div>

      {/* Secondary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Expectancy"     value={metrics?.expectancy      ?? 0} format="currency" color="green" />
        <StatCard title="Max Drawdown"   value={metrics?.max_drawdown_pct ?? 0} format="percent"  color="red"   />
        <StatCard title="Win Rate"       value={(metrics?.win_rate ?? 0) * 100} format="percent"  color="accent"/>
        <StatCard title="CAGR"           value={metrics?.cagr ?? 0}            format="percent"  color="gold"  />
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-5">
        {/* Win/Loss Pie */}
        <div className="gv-card p-5">
          <h2 className="text-[#f0f6ff] font-semibold mb-4">Win / Loss</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={winLossData} dataKey="value" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false}>
                  {winLossData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1e2d40", borderRadius: 8, color: "#f0f6ff" }} />
                <Legend wrapperStyle={{ color: "#475569", fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* By Session */}
        <div className="gv-card p-5">
          <h2 className="text-[#f0f6ff] font-semibold mb-4">عملکرد به تفکیک جلسه</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bySession} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1e2d40", borderRadius: 8, color: "#f0f6ff" }} />
                <Bar dataKey="net_pnl" fill="#00d4ff" radius={[4, 4, 0, 0]}>
                  {bySession.map((s, i) => <Cell key={i} fill={s.net_pnl >= 0 ? "#10b981" : "#ef4444"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* By Symbol table */}
      <div className="gv-card p-5">
        <h2 className="text-[#f0f6ff] font-semibold mb-4">عملکرد به تفکیک نماد</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e2d40]">
                {["نماد","معاملات","Win Rate","PF","Net P&L"].map(h => (
                  <th key={h} className="text-right text-[#475569] py-2 px-3 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bySymbol.map((s, i) => (
                <tr key={i} className="border-b border-[#1e2d40]/50 hover:bg-[#111827] transition-colors">
                  <td className="py-2.5 px-3 text-[#f0f6ff] font-semibold">{s.label}</td>
                  <td className="py-2.5 px-3 text-[#475569]">{s.trades}</td>
                  <td className="py-2.5 px-3 text-[#10b981]">{(s.win_rate * 100).toFixed(1)}%</td>
                  <td className="py-2.5 px-3 text-[#00d4ff]">{s.profit_factor.toFixed(2)}</td>
                  <td className={`py-2.5 px-3 font-bold ${s.net_pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                    {s.net_pnl >= 0 ? "+" : ""}{s.net_pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {bySymbol.length === 0 && <p className="text-center text-[#475569] py-8">داده‌ای وجود ندارد</p>}
        </div>
      </div>
    </div>
  );
}
