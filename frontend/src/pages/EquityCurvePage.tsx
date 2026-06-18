import { useState, useEffect } from "react";
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from "recharts";
import { TrendingUp, TrendingDown } from "lucide-react";
import { analyticsApi } from "../utils/api";
import type { EquityPoint } from "../types";

const PERIODS = [
  { label: "۷ روز",   value: 7  },
  { label: "۳۰ روز",  value: 30 },
  { label: "۹۰ روز",  value: 90 },
  { label: "۱ سال",   value: 365 },
];

export default function EquityCurvePage() {
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [period, setPeriod] = useState(30);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    analyticsApi.getEquity().then(r => {
      if (r.success) setEquity(r.data.points ?? []);
      setLoading(false);
    });
  }, [period]);

  const maxDD  = Math.min(...equity.map(e => e.drawdown));
  const finalEq = equity.at(-1)?.equity ?? 0;
  const firstEq = equity.at(0)?.equity ?? finalEq;
  const totalReturn = firstEq > 0 ? ((finalEq - firstEq) / firstEq * 100) : 0;
  const positive = totalReturn >= 0;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[#f0f6ff] text-2xl font-bold">منحنی سرمایه</h1>
          <p className="text-[#475569] text-sm mt-1">
            بازده کل:&nbsp;
            <span className={positive ? "text-[#10b981]" : "text-[#ef4444]"}>
              {positive ? "+" : ""}{totalReturn.toFixed(2)}%
            </span>
            &nbsp;|&nbsp; حداکثر Drawdown: <span className="text-[#ef4444]">{maxDD.toFixed(2)}%</span>
          </p>
        </div>
        <div className="flex gap-2">
          {PERIODS.map(p => (
            <button key={p.value} onClick={() => setPeriod(p.value)}
              className={`px-3 py-1.5 rounded-xl text-xs transition-all ${period === p.value ? "bg-[#00d4ff] text-[#070b12] font-bold" : "bg-[#111827] border border-[#1e2d40] text-[#94a3b8] hover:border-[#00d4ff]/30"}`}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20"><div className="w-8 h-8 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <>
          {/* Equity + Balance Chart */}
          <div className="gv-card p-5">
            <h2 className="text-[#f0f6ff] font-semibold mb-4 flex items-center gap-2">
              <TrendingUp size={18} className="text-[#00d4ff]" /> Equity & Balance
            </h2>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equity} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
                  <defs>
                    <linearGradient id="gEq"  x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#00d4ff" stopOpacity={0.3}/><stop offset="95%" stopColor="#00d4ff" stopOpacity={0}/></linearGradient>
                    <linearGradient id="gBal" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#10b981" stopOpacity={0.2}/><stop offset="95%" stopColor="#10b981" stopOpacity={0}/></linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill:"#475569", fontSize:11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill:"#475569", fontSize:11 }} axisLine={false} tickLine={false} tickFormatter={v=>`$${(v/1000).toFixed(0)}k`} />
                  <Tooltip contentStyle={{ background:"#111827", border:"1px solid #1e2d40", borderRadius:8, color:"#f0f6ff" }} formatter={(v:number) => [`$${v.toLocaleString()}`,""]} />
                  <Area type="monotone" dataKey="equity"  stroke="#00d4ff" strokeWidth={2} fill="url(#gEq)"  dot={false} />
                  <Area type="monotone" dataKey="balance" stroke="#10b981" strokeWidth={2} fill="url(#gBal)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Drawdown Chart */}
          <div className="gv-card p-5">
            <h2 className="text-[#f0f6ff] font-semibold mb-4 flex items-center gap-2">
              <TrendingDown size={18} className="text-[#ef4444]" /> Drawdown
            </h2>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equity} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
                  <defs>
                    <linearGradient id="gDD" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#ef4444" stopOpacity={0.3}/><stop offset="95%" stopColor="#ef4444" stopOpacity={0}/></linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill:"#475569", fontSize:11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill:"#475569", fontSize:11 }} axisLine={false} tickLine={false} tickFormatter={v=>`${v.toFixed(1)}%`} />
                  <Tooltip contentStyle={{ background:"#111827", border:"1px solid #1e2d40", borderRadius:8, color:"#f0f6ff" }} formatter={(v:number) => [`${v.toFixed(2)}%`,""]} />
                  <ReferenceLine y={0} stroke="#1e2d40" />
                  <Area type="monotone" dataKey="drawdown" stroke="#ef4444" strokeWidth={2} fill="url(#gDD)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Daily PnL */}
          <div className="gv-card p-5">
            <h2 className="text-[#f0f6ff] font-semibold mb-4">P&L روزانه</h2>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={equity} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill:"#475569", fontSize:11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill:"#475569", fontSize:11 }} axisLine={false} tickLine={false} tickFormatter={v=>`$${v}`} />
                  <Tooltip contentStyle={{ background:"#111827", border:"1px solid #1e2d40", borderRadius:8, color:"#f0f6ff" }} formatter={(v:number) => [`$${v.toFixed(2)}`,""]} />
                  <ReferenceLine y={0} stroke="#1e2d40" />
                  <Bar dataKey="pnl" fill="#10b981" radius={[2,2,0,0]}
                    label={false}
                    background={false}
                    shape={(props: Record<string,unknown>) => {
                      const { x, y, width, height, value } = props as { x:number;y:number;width:number;height:number;value:number };
                      return <rect x={x} y={y} width={width} height={height} fill={(value ?? 0) >= 0 ? "#10b981" : "#ef4444"} rx={2} />;
                    }}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
