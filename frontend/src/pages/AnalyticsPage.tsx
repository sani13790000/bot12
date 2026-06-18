import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { BarChart2 } from "lucide-react";
import { analyticsApi } from "../utils/api";
import { StatCard } from "../components/common/StatCard";
import type { AnalyticsMetrics, BreakdownItem } from "../types";

export default function AnalyticsPage() {
  const [metrics, setMetrics]   = useState<AnalyticsMetrics | null>(null);
  const [symbols, setSymbols]   = useState<BreakdownItem[]>([]);
  const [sessions, setSessions] = useState<BreakdownItem[]>([]);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    Promise.all([
      analyticsApi.getMetrics(),
      analyticsApi.getBySymbol(),
      analyticsApi.getBySession(),
    ]).then(([m, s, ss]) => {
      if (m.success)  setMetrics(m.data);
      if (s.success)  setSymbols(s.data);
      if (ss.success) setSessions(ss.data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="flex justify-center py-20"><div className="w-8 h-8 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[#f0f6ff] text-2xl font-bold">آنالیتیکس</h1>
        <p className="text-[#475569] text-sm mt-1">متریک‌های کوانتیتاتیو — Galaxy Vast</p>
      </div>

      {/* Primary Ratios */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard title="Sharpe Ratio"  value={metrics?.sharpe_ratio ?? 0}  format="ratio" color="accent"  glow />
        <StatCard title="Sortino Ratio" value={metrics?.sortino_ratio ?? 0} format="ratio" color="green"  />
        <StatCard title="Calmar Ratio"  value={metrics?.calmar_ratio ?? 0}  format="ratio" color="purple" />
        <StatCard title="Profit Factor" value={metrics?.profit_factor ?? 0} format="ratio" color="gold"   />
      </div>

      {/* Secondary Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard title="Recovery Factor" value={metrics?.recovery_factor ?? 0}  format="ratio"    color="accent" />
        <StatCard title="Expectancy"      value={metrics?.expectancy ?? 0}        format="currency" color="green" />
        <StatCard title="Max Drawdown"    value={metrics?.max_drawdown_pct ?? 0}  format="percent"  color="red" />
        <StatCard title="Win Rate"        value={`${((metrics?.win_rate ?? 0) * 100).toFixed(1)}%`} color="accent" />
      </div>

      {/* Additional */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard title="Net Profit"     value={metrics?.net_profit ?? 0}    format="currency" color="green" />
        <StatCard title="CAGR"           value={metrics?.cagr ?? 0}          format="percent"  color="accent" />
        <StatCard title="Avg R:R"        value={metrics?.avg_rr ?? 0}        format="ratio"    color="purple" />
        <StatCard title="Expectancy R"   value={metrics?.expectancy_r ?? 0}  format="ratio"    color="gold" />
      </div>

      {/* Streak */}
      <div className="grid grid-cols-2 gap-4">
        <div className="gv-card p-4 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#10b981]/10 border border-[#10b981]/30 flex items-center justify-center">
            <span className="text-[#10b981] font-bold font-mono text-lg">{metrics?.max_consecutive_wins ?? 0}</span>
          </div>
          <div><div className="text-[#f0f6ff] font-semibold">حداکثر برد متوالی</div><div className="text-[#475569] text-xs">Maximum Consecutive Wins</div></div>
        </div>
        <div className="gv-card p-4 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#ef4444]/10 border border-[#ef4444]/30 flex items-center justify-center">
            <span className="text-[#ef4444] font-bold font-mono text-lg">{metrics?.max_consecutive_losses ?? 0}</span>
          </div>
          <div><div className="text-[#f0f6ff] font-semibold">حداکثر باخت متوالی</div><div className="text-[#475569] text-xs">Maximum Consecutive Losses</div></div>
        </div>
      </div>

      {/* Symbol Breakdown */}
      {symbols.length > 0 && (
        <div className="gv-card p-5">
          <h2 className="text-[#f0f6ff] font-semibold mb-4 flex items-center gap-2">
            <BarChart2 size={16} className="text-[#00d4ff]" /> عملکرد per Symbol
          </h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={symbols} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" vertical={false} />
                <XAxis dataKey="label" tick={{ fill:"#475569", fontSize:11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill:"#475569", fontSize:11 }} axisLine={false} tickLine={false} tickFormatter={v=>`$${v}`} />
                <Tooltip contentStyle={{ background:"#111827", border:"1px solid #1e2d40", borderRadius:8, color:"#f0f6ff" }} formatter={(v:number) => [`$${v.toFixed(2)}`,""]} />
                <Bar dataKey="net_pnl" fill="#00d4ff" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-4">
            {symbols.map(s => (
              <div key={s.label} className="p-3 bg-[#111827] rounded-xl border border-[#1e2d40]">
                <div className="font-mono font-semibold text-[#f0f6ff] text-sm">{s.label}</div>
                <div className="flex justify-between text-xs mt-1">
                  <span className="text-[#475569]">WR: <span className="text-[#10b981]">{(s.win_rate * 100).toFixed(0)}%</span></span>
                  <span className="text-[#475569]">PF: <span className="text-[#00d4ff]">{s.profit_factor.toFixed(2)}</span></span>
                  <span className={(s.net_pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]")}>${s.net_pnl.toFixed(0)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Session Breakdown */}
      {sessions.length > 0 && (
        <div className="gv-card p-5">
          <h2 className="text-[#f0f6ff] font-semibold mb-4">عملکرد per Session</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {sessions.map(s => (
              <div key={s.label} className="p-4 bg-[#111827] rounded-xl border border-[#1e2d40] text-center">
                <div className="font-semibold text-[#f0f6ff]">{s.label}</div>
                <div className="text-2xl font-mono font-bold text-[#00d4ff] mt-1">{s.trades}</div>
                <div className="text-xs text-[#475569] mt-1">معامله</div>
                <div className="text-xs mt-2"><span className="text-[#10b981]">WR: {(s.win_rate * 100).toFixed(0)}%</span></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
