/**
 * frontend/src/pages/DashboardPage.tsx
 * FIX-30: Promise.allSettled — هر API مستقل fail می‌شود
 * FIX-31: refresh animate فقط در loading
 * FIX-32: today_profit fallback 0
 */
import { useEffect, useState, useCallback } from "react";
import { dashboardApi, tradesApi, signalsApi } from "@/utils/api";
import type { DashboardStats, Trade, Signal } from "@/types";
import { TrendingUp, Activity, RefreshCw, AlertCircle } from "lucide-react";

function StatCard({ label, value, color, sub }: { label:string; value:string|number|undefined; color:string; sub?:string }) {
  const colors: Record<string,string> = { green:"text-green-400", blue:"text-blue-400", purple:"text-purple-400", red:"text-red-400" };
  return (
    <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className={`text-2xl font-bold font-mono ${colors[color]??"text-white"}`}>{value??"\u2014"}</p>
      {sub && <p className="text-gray-500 text-xs mt-1">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const [stats,   setStats]   = useState<DashboardStats|null>(null);
  const [trades,  setTrades]  = useState<Trade[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [errors,  setErrors]  = useState<string[]>([]);

  const load = useCallback(() => {
    setLoading(true); setErrors([]);
    Promise.allSettled([
      dashboardApi.getStats(),
      tradesApi.listOpen(),
      signalsApi.list("PENDING"),
    ]).then(([statsRes, tradesRes, signalsRes]) => {
      const errs: string[] = [];
      if (statsRes.status==="fulfilled" && statsRes.value.success) setStats(statsRes.value.data);
      else errs.push("خطا در بارگذاری آمار داشبورد");
      if (tradesRes.status==="fulfilled" && tradesRes.value.success) setTrades(tradesRes.value.data??[]);
      else errs.push("خطا در بارگذاری معاملات باز");
      if (signalsRes.status==="fulfilled" && signalsRes.value.success) setSignals(signalsRes.value.data??[]);
      else errs.push("خطا در بارگذاری سیگنال‌ها");
      if (errs.length) setErrors(errs);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">داشبورد</h1>
        <button onClick={load} disabled={loading}
          className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white disabled:opacity-50 transition-colors">
          <RefreshCw className={`w-4 h-4 ${loading?"animate-spin":""}`} />
        </button>
      </div>
      {errors.map(e => (
        <div key={e} className="flex items-center gap-2 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />{e}
        </div>
      ))}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="موجودی"    value={stats?`$${stats.balance.toLocaleString()}`:undefined} color="green" />
        <StatCard label="Equity"    value={stats?`$${stats.equity.toLocaleString()}`:undefined}  color="blue" />
        <StatCard label="سود امروز" value={stats?`$${(stats.today_profit??0).toFixed(2)}`:undefined}
          color={(stats?.today_profit??0)>=0?"green":"red"} />
        <StatCard label="Win Rate"  value={stats?`${stats.win_rate.toFixed(1)}%`:undefined} color="purple" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <StatCard label="معاملات باز"     value={trades.length}  color="blue" />
        <StatCard label="سیگنال‌های فعال" value={signals.length} color="purple" />
        <StatCard label="امتیاز امنیتی"   value={stats?.security_score}
          color={(stats?.security_score??0)>=70?"green":"red"} sub="حداقل 70" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4 text-blue-400" />معاملات باز
          </h2>
          {trades.length===0
            ? <p className="text-gray-500 text-sm py-4 text-center">معامله باز وجود ندارد</p>
            : trades.slice(0,5).map(t=>(
              <div key={t.id} className="flex items-center justify-between py-2.5 border-b border-gray-800 last:border-0">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${t.direction==="BUY"?"bg-green-900/40 text-green-400":"bg-red-900/40 text-red-400"}`}>{t.direction}</span>
                  <span className="text-white text-sm">{t.symbol}</span>
                </div>
                <span className={`text-sm font-mono font-semibold ${(t.profit_loss??0)>=0?"text-green-400":"text-red-400"}`}>
                  {t.profit_loss!==undefined?`$${t.profit_loss.toFixed(2)}`:"\u2014"}
                </span>
              </div>
            ))}
        </div>
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-purple-400" />سیگنال‌های فعال
          </h2>
          {signals.length===0
            ? <p className="text-gray-500 text-sm py-4 text-center">سیگنال فعال وجود ندارد</p>
            : signals.slice(0,5).map(s=>(
              <div key={s.id} className="flex items-center justify-between py-2.5 border-b border-gray-800 last:border-0">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                    s.direction==="BUY"?"bg-green-900/40 text-green-400":s.direction==="SELL"?"bg-red-900/40 text-red-400":"bg-gray-700 text-gray-400"}`}>{s.direction}</span>
                  <span className="text-white text-sm">{s.symbol}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-1 w-16 bg-gray-800 rounded-full"><div className="h-full bg-purple-500 rounded-full" style={{width:`${s.confidence*100}%`}} /></div>
                  <span className="text-gray-400 text-xs font-mono">{(s.confidence*100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
