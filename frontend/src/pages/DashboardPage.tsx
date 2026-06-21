/**
 * frontend/src/pages/DashboardPage.tsx
 * FIX-E4: Missing page
 */
import { useEffect, useState } from "react";
import { dashboardApi, tradesApi, signalsApi } from "../utils/api";
import type { DashboardStats, Trade, Signal } from "../types";
import { TrendingUp, Activity, RefreshCw } from "lucide-react";

function StatCard({ label, value, color }: { label: string; value: string | number | undefined; color: string }) {
  const c: Record<string,string> = { green: "text-green-400", blue: "text-blue-400", purple: "text-purple-400", red: "text-red-400" };
  return (
    <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
      <p className="text-gray-400 text-sm mb-1">{label}</p>
      <p className={`text-2xl font-bold ${c[color] ?? "text-white"}`}>{value ?? "\u2014"}</p>
    </div>
  );
}

export default function DashboardPage() {
  const [stats,   setStats]   = useState<DashboardStats | null>(null);
  const [trades,  setTrades]  = useState<Trade[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = () => {
    setLoading(true); setError(null);
    Promise.all([dashboardApi.getStats(), tradesApi.listOpen(), signalsApi.list("PENDING")])
      .then(([s, t, sg]) => {
        if (s.success) setStats(s.data); else setError(s.error ?? "\u062e\u0637\u0627");
        if (t.success)  setTrades(t.data ?? []);
        if (sg.success) setSignals(sg.data ?? []);
      }).finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (loading) return <div className="flex justify-center pt-20"><RefreshCw className="w-6 h-6 text-blue-400 animate-spin" /></div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">\u062f\u0627\u0634\u0628\u0648\u0631\u062f</h1>
        <button onClick={load} className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white"><RefreshCw className="w-4 h-4" /></button>
      </div>
      {error && <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">{error}</div>}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="\u0645\u0648\u062c\u0648\u062f\u06cc" value={stats ? `$${stats.balance.toLocaleString()}` : undefined} color="green" />
        <StatCard label="Equity" value={stats ? `$${stats.equity.toLocaleString()}` : undefined} color="blue" />
        <StatCard label="\u0633\u0648\u062f \u0627\u0645\u0631\u0648\u0632" value={stats ? `$${stats.today_profit.toFixed(2)}` : undefined} color={stats && stats.today_profit >= 0 ? "green" : "red"} />
        <StatCard label="Win Rate" value={stats ? `${stats.win_rate.toFixed(1)}%` : undefined} color="purple" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <StatCard label="\u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0628\u0627\u0632" value={trades.length} color="blue" />
        <StatCard label="\u0633\u06cc\u06af\u0646\u0627\u0644\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644" value={signals.length} color="purple" />
        <StatCard label="\u0627\u0645\u062a\u06cc\u0627\u0632 \u0627\u0645\u0646\u06cc\u062a\u06cc" value={stats?.security_score} color={stats && stats.security_score >= 70 ? "green" : "red"} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2"><Activity className="w-4 h-4 text-blue-400" />\u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0628\u0627\u0632</h2>
          {trades.length === 0 ? <p className="text-gray-500 text-sm">\u0645\u0639\u0627\u0645\u0644\u0647 \u0628\u0627\u0632 \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f</p>
            : trades.slice(0,5).map(t => (
              <div key={t.id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${t.direction === "BUY" ? "bg-green-900/40 text-green-400" : "bg-red-900/40 text-red-400"}`}>{t.direction}</span>
                  <span className="text-white text-sm">{t.symbol}</span>
                </div>
                <span className={`text-sm font-mono ${(t.profit_loss ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {t.profit_loss !== undefined ? `$${t.profit_loss.toFixed(2)}` : "\u2014"}
                </span>
              </div>
            ))}
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-purple-400" />\u0633\u06cc\u06af\u0646\u0627\u0644\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644</h2>
          {signals.length === 0 ? <p className="text-gray-500 text-sm">\u0633\u06cc\u06af\u0646\u0627\u0644 \u0641\u0639\u0627\u0644 \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f</p>
            : signals.slice(0,5).map(s => (
              <div key={s.id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${s.direction === "BUY" ? "bg-green-900/40 text-green-400" : s.direction === "SELL" ? "bg-red-900/40 text-red-400" : "bg-gray-700 text-gray-400"}`}>{s.direction}</span>
                  <span className="text-white text-sm">{s.symbol}</span>
                </div>
                <span className="text-gray-400 text-sm">{(s.confidence*100).toFixed(0)}%</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
