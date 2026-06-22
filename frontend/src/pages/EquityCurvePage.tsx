/**
 * frontend/src/pages/EquityCurvePage.tsx
 * FIX-FE15: stub -> real Recharts line chart
 */
import { useEffect, useState } from "react";
import { dashboardApi } from "../utils/api";
import type { EquityPoint } from "../types";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { LineChart as LineIcon, RefreshCw } from "lucide-react";

export default function EquityCurvePage() {
  const [points,  setPoints]  = useState<EquityPoint[]>([]);
  const [days,    setDays]    = useState(30);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    dashboardApi.getEquityCurve(days)
      .then(r => {
        if (r.success) setPoints((r.data as { points: EquityPoint[] }).points ?? []);
        else setError(r.error ?? "\u062e\u0637\u0627");
      })
      .finally(() => setLoading(false));
  }, [days]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <LineIcon className="w-6 h-6 text-blue-400" /> \u0645\u0646\u062d\u0646\u06cc \u0633\u0631\u0645\u0627\u06cc\u0647
        </h1>
        <div className="flex gap-2">
          {[7, 30, 90].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                days === d ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}>{d} \u0631\u0648\u0632</button>
          ))}
        </div>
      </div>
      {error && <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">{error}</div>}
      {loading
        ? <div className="flex justify-center pt-20"><RefreshCw className="w-6 h-6 text-blue-400 animate-spin" /></div>
        : points.length === 0
          ? <div className="bg-gray-900 rounded-xl border border-gray-800 p-10 text-center text-gray-500">\u062f\u0627\u062f\u0647\u0627\u06cc\u06cc \u0645\u0648\u062c\u0648\u062f \u0646\u06cc\u0633\u062a</div>
          : <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={points}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="timestamp" tick={{ fill: "#6b7280", fontSize: 11 }}
                    tickFormatter={v => new Date(v).toLocaleDateString("fa-IR")} />
                  <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} tickFormatter={v => `$${Number(v).toLocaleString()}`} />
                  <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151", borderRadius: 8 }}
                    labelStyle={{ color: "#9ca3af" }}
                    formatter={(v: number) => [`$${v.toLocaleString()}`, ""]}
                    labelFormatter={l => new Date(l).toLocaleDateString("fa-IR")} />
                  <Line type="monotone" dataKey="equity"  stroke="#3b82f6" strokeWidth={2} dot={false} name="Equity" />
                  <Line type="monotone" dataKey="balance" stroke="#10b981" strokeWidth={1.5} dot={false} strokeDasharray="5 3" name="Balance" />
                </LineChart>
              </ResponsiveContainer>
            </div>}
    </div>
  );
}
