import { useEffect, useState } from "react";
import { Activity, DollarSign, TrendingUp, TrendingDown, ShieldAlert, Zap, BarChart2, Target } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { StatCard } from "../components/common/StatCard";
import { dashboardApi, botApi } from "../utils/api";
import { useWS } from "../contexts/WebSocketContext";
import type { DashboardStats, EquityPoint } from "../types";

export default function DashboardPage() {
  const [stats, setStats]   = useState<DashboardStats | null>(null);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const { on } = useWS();

  const load = async () => {
    setLoading(true);
    const [s, e] = await Promise.all([dashboardApi.getStats(), dashboardApi.getEquityCurve(30)]);
    if (s.success) setStats(s.data);
    if (e.success) setEquity(e.data.points ?? []);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    const off1 = on("EQUITY_UPDATE",  (d: Partial<DashboardStats>) => setStats(s => s ? { ...s, ...d } : s));
    const off2 = on("TRADE_OPENED",   () => load());
    const off3 = on("TRADE_CLOSED",   () => load());
    const off4 = on("BOT_STATUS",     (d: Partial<DashboardStats>) => setStats(s => s ? { ...s, ...d } : s));
    return () => { off1(); off2(); off3(); off4(); };
  }, [on]);

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin" />
    </div>
  );

  const modeColor  = stats?.bot_status === "RUNNING" ? "green" : stats?.bot_status === "PAUSED" ? "gold" : "red";
  const modeLabel  = stats?.bot_status === "RUNNING" ? "در حال اجرا" : stats?.bot_status === "PAUSED" ? "متوقف موقت" : "متوقف";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[#f0f6ff] text-2xl font-bold">داشبورد</h1>
          <p className="text-[#475569] text-sm mt-1">Galaxy Vast AI Trading Platform</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`badge-${modeColor === "green" ? "active" : modeColor === "gold" ? "wait" : "sell"} text-xs`}>
            {modeLabel}
          </span>
          <span className="badge-wait text-xs">{stats?.trading_mode}</span>
          {stats?.bot_status !== "RUNNING" ? (
            <button onClick={() => botApi.start().then(load)}
              className="px-4 py-2 bg-[#10b981] text-[#070b12] rounded-xl text-sm font-bold hover:bg-[#059669] transition-all">
              شروع
            </button>
          ) : (
            <button onClick={() => botApi.pause().then(load)}
              className="px-4 py-2 bg-[#f59e0b] text-[#070b12] rounded-xl text-sm font-bold hover:bg-[#d97706] transition-all">
              توقف موقت
            </button>
          )}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="موجودی" value={stats?.balance ?? 0} format="currency" color="accent" icon={<DollarSign size={18} />} glow trend={stats?.today_pnl} />
        <StatCard title="Equity" value={stats?.equity ?? 0} format="currency" color="green" icon={<TrendingUp size={18} />} />
        <StatCard title="P&L امروز" value={stats?.today_pnl ?? 0} format="currency"
          color={(stats?.today_pnl ?? 0) >= 0 ? "green" : "red"}
          icon={(stats?.today_pnl ?? 0) >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />} />
        <StatCard title="Drawdown" value={stats?.drawdown_percent ?? 0} format="percent" color="red" icon={<ShieldAlert size={18} />} />
      </div>

      {/* Secondary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard title="Win Rate" value={`${((stats?.win_rate ?? 0) * 100).toFixed(1)}%`} color="green" icon={<Target size={18} />} />
        <StatCard title="Profit Factor" value={stats?.profit_factor ?? 0} format="ratio" color="accent" icon={<BarChart2 size={18} />} />
        <StatCard title="Sharpe Ratio" value={stats?.sharpe_ratio ?? 0} format="ratio" color="purple" icon={<Activity size={18} />} />
        <StatCard title="Expectancy" value={stats?.expectancy ?? 0} format="currency" color="gold" icon={<Zap size={18} />} />
      </div>

      {/* Equity Chart */}
      <div className="gv-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-[#f0f6ff] font-semibold">منحنی Equity — ۳۰ روز اخیر</h2>
          <div className="flex items-center gap-4 text-xs text-[#475569]">
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[#00d4ff] inline-block" /> Equity</span>
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[#10b981] inline-block" /> Balance</span>
          </div>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={equity} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
              <defs>
                <linearGradient id="gvEquity" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#00d4ff" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#00d4ff" stopOpacity={0}    />
                </linearGradient>
                <linearGradient id="gvBalance" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#10b981" stopOpacity={0.2}  />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0}    />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
              <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1e2d40", borderRadius: 8, color: "#f0f6ff" }}
                formatter={(v: number) => [`$${v.toLocaleString()}`, ""]} />
              <Area type="monotone" dataKey="equity"  stroke="#00d4ff" strokeWidth={2} fill="url(#gvEquity)"  dot={false} />
              <Area type="monotone" dataKey="balance" stroke="#10b981" strokeWidth={2} fill="url(#gvBalance)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bottom Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard title="کل معاملات" value={stats?.total_trades ?? 0} color="accent" />
        <StatCard title="معاملات باز" value={stats?.active_trades_count ?? 0} color="green" />
        <StatCard title="سیگنال‌های فعال" value={stats?.active_signals_count ?? 0} color="gold" />
        <StatCard title="ریسک پرتفولیو" value={stats?.portfolio_risk_percent ?? 0} format="percent"
          color={(stats?.portfolio_risk_percent ?? 0) > 4 ? "red" : "green"} />
      </div>
    </div>
  );
}
