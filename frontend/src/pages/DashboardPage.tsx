import { useEffect, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar, Cell,
} from "recharts";
import {
  TrendingUp, TrendingDown, DollarSign, Activity,
  ShieldCheck, Target, Zap, Brain, Play, Pause, Square,
} from "lucide-react";
import { dashboardApi, botApi } from "../utils/api";
import type { DashboardStats } from "../types";

// ── Mock equity curve for demo ───────────────────────────────
const MOCK_EQUITY = Array.from({ length: 30 }, (_, i) => {
  const base = 10000 + i * 120 + Math.sin(i * 0.7) * 300;
  return {
    date: `${i + 1}/6`,
    equity: Math.round(base),
    balance: Math.round(base - 80),
    drawdown: +(Math.random() * 3).toFixed(2),
  };
});

// ── Mock daily pnl ────────────────────────────────────────────
const MOCK_DAILY = [
  { day: "شن", pnl: 42 }, { day: "یک", pnl: -18 }, { day: "دو", pnl: 95 },
  { day: "سه", pnl: 61 }, { day: "چه", pnl: -23 }, { day: "پن", pnl: 110 },
  { day: "جم", pnl: 78 },
];

// ── Metric Card ───────────────────────────────────────────────
interface MetricCardProps {
  label: string;
  value: string;
  subValue?: string;
  icon: React.ReactNode;
  color: string;
  trend?: "up" | "down" | "neutral";
}

function MetricCard({ label, value, subValue, icon, color, trend }: MetricCardProps) {
  return (
    <div
      className="gv-card p-4 fade-in-up"
      style={{ borderColor: `${color}22` }}
    >
      <div className="flex items-start justify-between mb-3">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center"
          style={{ background: `${color}18`, border: `1px solid ${color}30` }}
        >
          <div style={{ color }}>{icon}</div>
        </div>
        {trend && (
          <div
            className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
            style={{
              background: trend === "up" ? "rgba(16,185,129,0.12)" : trend === "down" ? "rgba(239,68,68,0.12)" : "rgba(148,163,184,0.12)",
              color: trend === "up" ? "#10b981" : trend === "down" ? "#ef4444" : "#94a3b8",
            }}
          >
            {trend === "up" ? <TrendingUp size={10} /> : trend === "down" ? <TrendingDown size={10} /> : null}
            {trend === "up" ? "صعود" : trend === "down" ? "نزول" : "—"}
          </div>
        )}
      </div>
      <div className="metric-value" style={{ color }}>{value}</div>
      <div className="mt-1 text-xs" style={{ color: "var(--gv-text-muted)" }}>{label}</div>
      {subValue && (
        <div className="mt-1 text-xs font-mono" style={{ color: "var(--gv-text-secondary)" }}>
          {subValue}
        </div>
      )}
    </div>
  );
}

// ── Bot Control Button ────────────────────────────────────────
interface BotControlProps {
  status: string;
  onAction: (action: "start" | "stop" | "pause" | "resume") => void;
}

function BotControl({ status, onAction }: BotControlProps) {
  const isRunning = status === "RUNNING";
  const isPaused  = status === "PAUSED";
  const isStopped = status === "STOPPED";

  return (
    <div
      className="gv-card p-4 flex items-center justify-between"
      style={{ borderColor: isRunning ? "rgba(16,185,129,0.3)" : "var(--gv-border)" }}
    >
      <div className="flex items-center gap-3">
        <div
          className="pulse-dot rounded-full"
          style={{
            width: 10, height: 10,
            background: isRunning ? "var(--gv-green)" : isPaused ? "var(--gv-gold)" : "#475569",
          }}
        />
        <div>
          <div className="text-sm font-semibold" style={{ color: "var(--gv-text-primary)" }}>
            وضعیت ربات
          </div>
          <div
            className="text-xs"
            style={{
              color: isRunning ? "var(--gv-green)" : isPaused ? "var(--gv-gold)" : "var(--gv-text-muted)",
            }}
          >
            {isRunning ? "در حال اجرا" : isPaused ? "متوقف موقت" : "خاموش"}
          </div>
        </div>
      </div>

      <div className="flex gap-2">
        {(isStopped || isPaused) && (
          <button
            onClick={() => onAction(isStopped ? "start" : "resume")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
            style={{ background: "rgba(16,185,129,0.15)", color: "#10b981", border: "1px solid rgba(16,185,129,0.3)" }}
          >
            <Play size={12} />
            {isStopped ? "شروع" : "ادامه"}
          </button>
        )}
        {isRunning && (
          <button
            onClick={() => onAction("pause")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
            style={{ background: "rgba(245,158,11,0.15)", color: "#f59e0b", border: "1px solid rgba(245,158,11,0.3)" }}
          >
            <Pause size={12} />
            مکث
          </button>
        )}
        {!isStopped && (
          <button
            onClick={() => onAction("stop")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
            style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" }}
          >
            <Square size={12} />
            توقف
          </button>
        )}
      </div>
    </div>
  );
}

// ── Custom Tooltip ────────────────────────────────────────────
function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="px-3 py-2 rounded-lg text-xs"
      style={{ background: "var(--gv-bg-card)", border: "1px solid var(--gv-border)", color: "var(--gv-text-primary)" }}
    >
      <div className="font-medium mb-1">{label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {typeof p.value === "number" ? p.value.toLocaleString() : p.value}
        </div>
      ))}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────
export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [botStatus, setBotStatus] = useState<"RUNNING" | "PAUSED" | "STOPPED">("RUNNING");

  useEffect(() => {
    dashboardApi.getStats().then((res) => {
      if (res.success) setStats(res.data);
      setLoading(false);
    });
  }, []);

  const handleBotAction = async (action: "start" | "stop" | "pause" | "resume") => {
    await botApi[action]();
    const map = { start: "RUNNING", stop: "STOPPED", pause: "PAUSED", resume: "RUNNING" } as const;
    setBotStatus(map[action]);
  };

  // Use mock data if API not available
  const balance        = stats?.balance        ?? 12_450.80;
  const equity         = stats?.equity         ?? 12_680.40;
  const drawdown       = stats?.drawdown_percent ?? 4.2;
  const winRate        = stats?.win_rate        ?? 62.5;
  const profitFactor   = stats?.profit_factor   ?? 1.84;
  const sharpe         = stats?.sharpe_ratio    ?? 1.42;
  const totalPnl       = stats?.total_pnl       ?? 2_450.80;
  const todayPnl       = stats?.today_pnl       ?? 128.40;
  const portfolioRisk  = stats?.portfolio_risk_percent ?? 2.8;
  const totalTrades    = stats?.total_trades    ?? 147;

  return (
    <div className="space-y-5">

      {/* ── Bot control bar ──────────────────────────────── */}
      <BotControl status={botStatus} onAction={handleBotAction} />

      {/* ── Metric cards ─────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          label="موجودی حساب"
          value={`$${balance.toLocaleString()}`}
          subValue={`Equity: $${equity.toLocaleString()}`}
          icon={<DollarSign size={16} />}
          color="#00d4ff"
          trend="up"
        />
        <MetricCard
          label="سود/زیان کل"
          value={totalPnl >= 0 ? `+$${totalPnl.toLocaleString()}` : `-$${Math.abs(totalPnl).toLocaleString()}`}
          subValue={`امروز: ${todayPnl >= 0 ? "+" : ""}$${todayPnl.toFixed(2)}`}
          icon={<TrendingUp size={16} />}
          color={totalPnl >= 0 ? "#10b981" : "#ef4444"}
          trend={totalPnl >= 0 ? "up" : "down"}
        />
        <MetricCard
          label="نرخ موفقیت"
          value={`${winRate}%`}
          subValue={`${totalTrades} معامله`}
          icon={<Target size={16} />}
          color="#8b5cf6"
          trend="up"
        />
        <MetricCard
          label="ریسک پرتفولیو"
          value={`${portfolioRisk}%`}
          subValue={`Drawdown: ${drawdown}%`}
          icon={<ShieldCheck size={16} />}
          color={portfolioRisk > 4 ? "#ef4444" : "#f59e0b"}
          trend={portfolioRisk > 4 ? "down" : "neutral"}
        />
      </div>

      {/* ── Second row metrics ───────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Profit Factor"   value={profitFactor.toFixed(2)} icon={<Activity size={16} />} color="#00d4ff" />
        <MetricCard label="Sharpe Ratio"    value={sharpe.toFixed(2)}       icon={<Activity size={16} />} color="#10b981" />
        <MetricCard label="معاملات باز"     value={String(stats?.active_trades_count ?? 2)} icon={<Zap size={16} />} color="#f59e0b" />
        <MetricCard label="سیگنال‌های فعال" value={String(stats?.active_signals_count ?? 3)} icon={<Brain size={16} />} color="#8b5cf6" />
      </div>

      {/* ── Charts row ───────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        {/* Equity curve — 2/3 width */}
        <div className="gv-card p-4 md:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold" style={{ color: "var(--gv-text-primary)" }}>
              منحنی اکوئیتی — ۳۰ روز اخیر
            </h3>
            <div className="flex gap-3 text-xs" style={{ color: "var(--gv-text-muted)" }}>
              <span className="flex items-center gap-1">
                <span style={{ width: 12, height: 2, background: "#00d4ff", display: "inline-block", borderRadius: 1 }} />
                Equity
              </span>
              <span className="flex items-center gap-1">
                <span style={{ width: 12, height: 2, background: "#10b981", display: "inline-block", borderRadius: 1 }} />
                Balance
              </span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={MOCK_EQUITY} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#00d4ff" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="balGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#10b981" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#475569" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#475569" }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="equity"  name="Equity"  stroke="#00d4ff" fill="url(#eqGrad)"  strokeWidth={2} dot={false} />
              <Area type="monotone" dataKey="balance" name="Balance" stroke="#10b981" fill="url(#balGrad)" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Daily PnL — 1/3 width */}
        <div className="gv-card p-4">
          <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--gv-text-primary)" }}>
            سود/زیان روزانه
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={MOCK_DAILY} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#475569" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#475569" }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="pnl" name="PnL" radius={[4, 4, 0, 0]}>
                {MOCK_DAILY.map((entry, i) => (
                  <Cell key={i} fill={entry.pnl >= 0 ? "#10b981" : "#ef4444"} fillOpacity={0.8} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Performance summary ───────────────────────────── */}
      <div className="gv-card p-4">
        <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--gv-text-primary)" }}>
          خلاصه عملکرد
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
          {[
            { label: "Win Rate",        value: `${winRate}%`,               color: "#10b981" },
            { label: "Profit Factor",   value: profitFactor.toFixed(2),     color: "#00d4ff" },
            { label: "Sharpe Ratio",    value: sharpe.toFixed(2),           color: "#8b5cf6" },
            { label: "Sortino Ratio",   value: (stats?.sortino_ratio ?? 1.91).toFixed(2), color: "#f59e0b" },
            { label: "Calmar Ratio",    value: (stats?.calmar_ratio ?? 2.14).toFixed(2),  color: "#00d4ff" },
            { label: "Max Drawdown",    value: `${drawdown}%`,              color: "#ef4444" },
          ].map(({ label, value, color }) => (
            <div key={label} className="text-center">
              <div className="font-mono text-lg font-bold" style={{ color }}>{value}</div>
              <div className="text-xs mt-1" style={{ color: "var(--gv-text-muted)" }}>{label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
