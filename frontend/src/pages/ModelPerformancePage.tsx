import { useState, useEffect } from "react";
import { Cpu, RefreshCw, TrendingUp, RotateCcw, Play, ChevronDown } from "lucide-react";
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer } from "recharts";
import { modelApi } from "../utils/api";
import type { ModelVersion, MLWeights } from "../types";

const STATUS_COLOR: Record<string, string> = {
  ACTIVE:     "badge-active",
  TRAINING:   "badge-wait",
  DEPRECATED: "text-[#475569] bg-[#111827] border border-[#1e2d40] rounded-full px-2 py-0.5 text-xs",
  ROLLBACK:   "badge-sell",
};

const SYMBOLS = ["XAUUSD","EURUSD","GBPUSD"];

export default function ModelPerformancePage() {
  const [versions, setVersions]   = useState<ModelVersion[]>([]);
  const [weights, setWeights]     = useState<MLWeights | null>(null);
  const [symbol, setSymbol]       = useState("XAUUSD");
  const [loading, setLoading]     = useState(true);
  const [retraining, setRetraining] = useState(false);

  const load = async () => {
    setLoading(true);
    const [v, w] = await Promise.all([modelApi.getVersions(symbol), modelApi.getWeights()]);
    if (v.success) setVersions(v.data);
    if (w.success) setWeights(w.data);
    setLoading(false);
  };

  useEffect(() => { load(); }, [symbol]);

  const handleRetrain = async () => {
    setRetraining(true);
    await modelApi.retrain(symbol);
    setTimeout(() => { load(); setRetraining(false); }, 3000);
  };

  const handleRollback = async () => {
    await modelApi.rollback(symbol);
    load();
  };

  const radarData = weights ? [
    { subject: "BOS",       value: weights.bos_weight * 100 },
    { subject: "CHOCH",     value: weights.choch_weight * 100 },
    { subject: "OB",        value: weights.order_block_weight * 100 },
    { subject: "FVG",       value: weights.fvg_weight * 100 },
    { subject: "Liquidity", value: weights.liquidity_weight * 100 },
    { subject: "PA",        value: weights.pa_engulfing_weight * 100 },
    { subject: "Session",   value: weights.session_weight * 100 },
    { subject: "HTF",       value: weights.htf_alignment_weight * 100 },
  ] : [];

  const current = versions.find(v => v.is_current);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[#f0f6ff] text-2xl font-bold">عملکرد مدل</h1>
          <p className="text-[#475569] text-sm mt-1">
            {current ? `v${current.version} — AUC: ${(current.auc_score * 100).toFixed(1)}%` : "لود..."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select value={symbol} onChange={e => setSymbol(e.target.value)}
            className="bg-[#111827] border border-[#1e2d40] rounded-xl px-3 py-2 text-sm text-[#f0f6ff] outline-none">
            {SYMBOLS.map(s => <option key={s}>{s}</option>)}
          </select>
          <button onClick={handleRetrain} disabled={retraining}
            className="px-4 py-2 bg-[#8b5cf6]/10 border border-[#8b5cf6]/30 text-[#8b5cf6] rounded-xl text-sm hover:bg-[#8b5cf6]/20 flex items-center gap-2 disabled:opacity-50">
            <Play size={14} className={retraining ? "animate-pulse" : ""} />
            {retraining ? "در حال آموزش..." : "آموزش مجدد"}
          </button>
          <button onClick={handleRollback}
            className="px-4 py-2 bg-[#f59e0b]/10 border border-[#f59e0b]/30 text-[#f59e0b] rounded-xl text-sm hover:bg-[#f59e0b]/20 flex items-center gap-2">
            <RotateCcw size={14} /> بازگشت
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-[#8b5cf6] border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

          {/* Radar Chart - ML Weights */}
          <div className="gv-card p-5">
            <h2 className="text-[#f0f6ff] font-semibold mb-4 flex items-center gap-2">
              <Cpu size={16} className="text-[#8b5cf6]" /> وزن‌های Decision Engine
            </h2>
            {weights && (
              <>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData}>
                      <PolarGrid stroke="#1e2d40" />
                      <PolarAngleAxis dataKey="subject" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                      <Radar name="وزن" dataKey="value" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.2} strokeWidth={2} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-4">
                  {radarData.map(d => (
                    <div key={d.subject} className="flex items-center justify-between text-xs">
                      <span className="text-[#94a3b8]">{d.subject}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1 bg-[#1e2d40] rounded-full overflow-hidden">
                          <div className="h-full bg-[#8b5cf6] rounded-full" style={{ width: `${d.value}%` }} />
                        </div>
                        <span className="text-[#8b5cf6] font-mono">{d.value.toFixed(0)}%</span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-3 pt-3 border-t border-[#1e2d40] flex items-center justify-between text-xs text-[#475569]">
                  <span>معاملات یادگرفته: <span className="text-[#f0f6ff]">{weights.total_trades_learned}</span></span>
                  <span>دقت مدل: <span className="text-[#8b5cf6]">{(weights.model_accuracy * 100).toFixed(1)}%</span></span>
                </div>
              </>
            )}
          </div>

          {/* Version History */}
          <div className="gv-card p-5">
            <h2 className="text-[#f0f6ff] font-semibold mb-4 flex items-center gap-2">
              <TrendingUp size={16} className="text-[#00d4ff]" /> تاریخچه نسخه‌ها — {symbol}
            </h2>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {versions.length === 0 ? (
                <p className="text-[#475569] text-sm text-center py-8">هنوز مدلی آموزش نداده‌اید</p>
              ) : versions.map(v => (
                <div key={v.version} className={`p-4 rounded-xl border transition-all ${v.is_current ? "border-[#00d4ff]/30 bg-[#00d4ff]/5" : "border-[#1e2d40] bg-[#111827]"}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-[#f0f6ff]">v{v.version}</span>
                      {v.is_current && <span className="badge-active text-[9px]">فعال</span>}
                    </div>
                    <span className={STATUS_COLOR[v.status]}>{v.status}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div><span className="text-[#475569]">AUC: </span><span className="text-[#00d4ff] font-mono">{(v.auc_score * 100).toFixed(1)}%</span></div>
                    <div><span className="text-[#475569]">Train: </span><span className="text-[#10b981] font-mono">{(v.train_auc * 100).toFixed(1)}%</span></div>
                    <div><span className="text-[#475569]">Test: </span><span className="text-[#8b5cf6] font-mono">{(v.test_auc * 100).toFixed(1)}%</span></div>
                    <div><span className="text-[#475569]">نمونه: </span><span className="text-[#94a3b8] font-mono">{v.samples}</span></div>
                    <div><span className="text-[#475569]">ویژگی: </span><span className="text-[#94a3b8] font-mono">{v.features}</span></div>
                    <div className="text-[#475569]">{new Date(v.created_at).toLocaleDateString("fa-IR")}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
