import { useEffect, useState } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";
import { analyticsApi } from "../utils/api";
import { StatCard } from "../components/common/StatCard";
import type { EquityPoint } from "../types";
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Brush
} from "recharts";

type Range = "7d" | "30d" | "90d" | "all";

export default function EquityCurvePage() {
  const [data,    setData]    = useState<EquityPoint[]>([]);
  const [range,   setRange]   = useState<Range>("30d");
  const [loading, setLoading] = useState(true);

  const RANGE_DAYS: Record<Range, number> = { "7d": 7, "30d": 30, "90d": 90, "all": 365 };

  useEffect(() => {
    (async () => {
      setLoading(true);
      const r = await analyticsApi.getEquityCurve(RANGE_DAYS[range]);
      if (r.success) setData(r.data?.points ?? []);
      setLoading(false);
    })();
  }, [range]);

  const last = data[data.length - 1];
  const first = data[0];
  const totalReturn = first && last ? ((last.equity - first.equity) / first.equity * 100) : 0;
  const maxDD = data.reduce((acc, d) => Math.max(acc, d.drawdown), 0);
  const maxEquity = data.reduce((acc, d) => Math.max(acc, d.equity), 0);

  const RANGES: Range[] = ["7d", "30d", "90d", "all"];

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#10b981]/10 border border-[#10b981]/30 flex items-center justify-center">
            <TrendingUp size={20} className="text-[#10b981]" />
          </div>
          <div>
            <h1 className="text-[#f0f6ff] text-xl font-bold">منحنی Equity</h1>
            <p className="text-[#475569] text-sm">{data.length} نقطه داده</p>
          </div>
        </div>
        <div className="flex gap-1 bg-[#111827] border border-[#1e2d40] rounded-xl p-1">
          {RANGES.map(r => (
            <button key={r} onClick={() => setRange(r)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${range === r ? "bg-[#00d4ff]/15 text-[#00d4ff] border border-[#00d4ff]/30" : "text-[#475569] hover:text-[#f0f6ff]"}`}>
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Equity فعلی"  value={last?.equity    ?? 0} format="currency" color="accent" glow icon={<TrendingUp  size={18} />} />
        <StatCard title="بازده کل"     value={totalReturn}          format="percent"  color={totalReturn >= 0 ? "green" : "red"} icon={totalReturn >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />} />
        <StatCard title="Max Drawdown" value={maxDD}                 format="percent"  color="red"    icon={<TrendingDown size={18} />} />
        <StatCard title="اوج Equity"   value={maxEquity}            format="currency" color="gold"   icon={<TrendingUp  size={18} />} />
      </div>

      {/* Main chart */}
      <div className="gv-card p-5">
        <h2 className="text-[#f0f6ff] font-semibold mb-4 flex items-center gap-2">
          منحنی Equity و Balance
          <span className="flex items-center gap-3 mr-auto text-xs text-[#475569]">
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[#00d4ff] inline-block" /> Equity</span>
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[#10b981] inline-block" /> Balance</span>
          </span>
        </h2>
        {loading ? (
          <div className="h-72 flex items-center justify-center"><div className="w-8 h-8 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin" /></div>
        ) : (
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
                <defs>
                  <linearGradient id="ecEquity"  x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#00d4ff" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="ecBalance" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#10b981" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#475569", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#475569", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1e2d40", borderRadius: 8, color: "#f0f6ff" }}
                  formatter={(v: number) => [`$${v.toLocaleString()}`, ""]} />
                <ReferenceLine y={first?.equity} stroke="#1e2d40" strokeDasharray="4 4" />
                <Area type="monotone" dataKey="equity"  stroke="#00d4ff" strokeWidth={2} fill="url(#ecEquity)"  dot={false} />
                <Area type="monotone" dataKey="balance" stroke="#10b981" strokeWidth={1.5} fill="url(#ecBalance)" dot={false} />
                <Brush dataKey="date" height={20} stroke="#1e2d40" fill="#0d1420" travellerWidth={8}
                  style={{ fontSize: 10, color: "#475569" }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Drawdown chart */}
      <div className="gv-card p-5">
        <h2 className="text-[#f0f6ff] font-semibold mb-4">Drawdown</h2>
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
              <defs>
                <linearGradient id="ecDD" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: "#475569", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#475569", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `${v.toFixed(1)}%`} />
              <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1e2d40", borderRadius: 8, color: "#f0f6ff" }}
                formatter={(v: number) => [`${v.toFixed(2)}%`, "Drawdown"]} />
              <Area type="monotone" dataKey="drawdown" stroke="#ef4444" strokeWidth={1.5} fill="url(#ecDD)" dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
