/**
 * frontend/src/pages/EquityCurvePage.tsx
 * FIX-28: stub → Recharts LineChart با dashboardApi.getEquityCurve()
 */
import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { dashboardApi } from "@/utils/api";
import type { EquityPoint } from "@/types";
import { LineChart as ChartIcon, RefreshCw } from "lucide-react";

const PERIODS = [{ label: "۷ روز", days: 7 }, { label: "۳۰ روز", days: 30 }, { label: "۹۰ روز", days: 90 }];

function fmt(ts: string) {
  const d = new Date(ts);
  return `${String(d.getMonth()+1).padStart(2,"0")}/${String(d.getDate()).padStart(2,"0")}`;
}

export default function EquityCurvePage() {
  const [points,  setPoints]  = useState<EquityPoint[]>([]);
  const [days,    setDays]    = useState(30);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    dashboardApi.getEquityCurve(days)
      .then(r => { if (r.success) setPoints(r.data?.points ?? []); else setError(r.error ?? "خطا"); })
      .finally(() => setLoading(false));
  }, [days]);

  const startEquity = points[0]?.equity ?? 0;
  const formatted   = points.map(p => ({ ...p, label: fmt(p.timestamp), pnl: p.equity - startEquity }));

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <ChartIcon className="w-6 h-6 text-blue-400" />منحنی سرمایه (Equity Curve)
        </h1>
        <div className="flex gap-2">
          {PERIODS.map(p => (
            <button key={p.days} onClick={() => setDays(p.days)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${days === p.days ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"}`}>
              {p.label}
            </button>
          ))}
        </div>
      </div>
      {error && <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">{error}</div>}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        {loading
          ? <div className="flex justify-center py-20"><RefreshCw className="w-6 h-6 text-blue-400 animate-spin" /></div>
          : formatted.length === 0
            ? <div className="text-center py-20 text-gray-500">داده‌ای برای نمایش وجود ندارد</div>
            : (
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={formatted} margin={{ top:5, right:20, bottom:5, left:0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="label" tick={{ fill:"#9ca3af", fontSize:11 }} />
                  <YAxis tick={{ fill:"#9ca3af", fontSize:11 }} tickFormatter={v => `$${Number(v).toLocaleString()}`} />
                  <Tooltip
                    contentStyle={{ background:"#111827", border:"1px solid #374151", borderRadius:8 }}
                    formatter={(v: number, name: string) => [`$${v.toLocaleString()}`, name==="equity"?"اكویتی":"موجودی"]}
                  />
                  <ReferenceLine y={startEquity} stroke="#374151" strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="equity"  stroke="#3b82f6" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="balance" stroke="#10b981" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
                </LineChart>
              </ResponsiveContainer>
            )}
      </div>
      {formatted.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label:"شروع",   value:`$${startEquity.toLocaleString()}`,                         color:"text-gray-300" },
            { label:"فعلی",   value:`$${(formatted.at(-1)?.equity??0).toLocaleString()}`,     color:"text-blue-400" },
            { label:"P&L کل",  value:`$${(formatted.at(-1)?.pnl??0).toFixed(2)}`,              color:(formatted.at(-1)?.pnl??0)>=0?"text-green-400":"text-red-400" },
            { label:"Max DD",  value:`${Math.max(...formatted.map(p=>p.drawdown)).toFixed(1)}%`, color:"text-red-400" },
          ].map(({label,value,color}) => (
            <div key={label} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <p className="text-gray-400 text-xs mb-1">{label}</p>
              <p className={`text-xl font-bold font-mono ${color}`}>{value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
