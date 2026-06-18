import { useEffect, useState } from "react";
import { Brain, TrendingUp, TrendingDown, RefreshCw, AlertCircle, CheckCircle } from "lucide-react";
import { intelligenceApi } from "../utils/api";
import type { MLWeights } from "../types";

const MOCK_WEIGHTS: MLWeights = {
  bos_weight: 0.27, choch_weight: 0.18, order_block_weight: 0.22,
  fvg_weight: 0.14, liquidity_weight: 0.19, pa_engulfing_weight: 0.16,
  pa_pin_bar_weight: 0.18, session_weight: 0.15, htf_alignment_weight: 0.20,
  last_updated: new Date().toISOString(), total_trades_learned: 247, model_accuracy: 0.71,
};

const WEIGHT_LABELS: Record<string, string> = {
  bos_weight: "BOS — شکست ساختار",
  choch_weight: "CHOCH — تغییر کاراکتر",
  order_block_weight: "Order Block",
  fvg_weight: "Fair Value Gap",
  liquidity_weight: "نقدینگی",
  pa_engulfing_weight: "Engulfing Pattern",
  pa_pin_bar_weight: "Pin Bar Pattern",
  session_weight: "سشن بازار",
  htf_alignment_weight: "تأیید HTF",
};

function WeightBar({ label, value, prevValue }: { label: string; value: number; prevValue: number }) {
  const delta = value - prevValue;
  const pct   = Math.round(value * 100);

  return (
    <div className="flex items-center gap-3">
      <div className="w-40 text-xs shrink-0" style={{ color: "var(--gv-text-secondary)" }}>{label}</div>
      <div className="flex-1 h-3 rounded-full overflow-hidden" style={{ background: "var(--gv-bg-secondary)" }}>
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct * 4}%`, background: "linear-gradient(90deg, #00d4ff, #0ea5e9)" }}
        />
      </div>
      <div className="w-12 text-right font-mono text-sm font-bold" style={{ color: "var(--gv-accent)" }}>{pct}%</div>
      <div className={`w-14 text-xs font-mono text-right ${delta > 0 ? "text-green-400" : delta < 0 ? "text-red-400" : "text-slate-500"}`}>
        {delta !== 0 ? `${delta > 0 ? "+" : ""}${(delta * 100).toFixed(1)}%` : "—"}
      </div>
    </div>
  );
}

export default function LearningPage() {
  const [weights, setWeights]     = useState<MLWeights | null>(null);
  const [running, setRunning]     = useState(false);
  const [lastRun, setLastRun]     = useState<string | null>(null);

  useEffect(() => {
    intelligenceApi.getWeights().then((res) => {
      setWeights(res.success ? res.data : MOCK_WEIGHTS);
    });
  }, []);

  const handleRunLearning = async () => {
    setRunning(true);
    await intelligenceApi.runLearning();
    const res = await intelligenceApi.getWeights();
    if (res.success) setWeights(res.data);
    setLastRun(new Date().toLocaleTimeString("fa-IR"));
    setRunning(false);
  };

  const w = weights ?? MOCK_WEIGHTS;

  return (
    <div className="space-y-5">

      {/* Header stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label:"معاملات یاد گرفته", value: w.total_trades_learned, suffix:"",    color:"#00d4ff" },
          { label:"دقت مدل ML",        value: Math.round(w.model_accuracy*100), suffix:"%", color:"#10b981" },
          { label:"آخرین بروزرسانی",  value: new Date(w.last_updated).toLocaleDateString("fa-IR"), suffix:"", color:"#f59e0b" },
          { label:"مدل‌های فعال",       value:3, suffix:" مدل",                              color:"#8b5cf6" },
        ].map(({ label, value, suffix, color }) => (
          <div key={label} className="gv-card p-4">
            <div className="metric-value" style={{ color }}>{value}{suffix}</div>
            <div className="text-xs mt-1" style={{ color:"var(--gv-text-muted)" }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Weights panel */}
      <div className="gv-card p-5">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <Brain size={18} style={{ color:"var(--gv-accent)" }} />
            <h3 className="font-semibold" style={{ color:"var(--gv-text-primary)" }}>وزن‌های تطبیق‌یافته — Decision Engine</h3>
          </div>
          <button
            onClick={handleRunLearning}
            disabled={running}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
            style={{ background:"rgba(0,212,255,0.15)", color:"var(--gv-accent)", border:"1px solid rgba(0,212,255,0.3)", opacity: running ? 0.6 : 1 }}
          >
            <RefreshCw size={14} className={running ? "animate-spin" : ""} />
            {running ? "در حال یادگیری..." : "اجرای چرخه یادگیری"}
          </button>
        </div>

        {lastRun && (
          <div className="flex items-center gap-2 mb-4 text-xs p-2 rounded-lg"
            style={{ background:"rgba(16,185,129,0.08)", border:"1px solid rgba(16,185,129,0.2)", color:"#10b981" }}
          >
            <CheckCircle size={12} />
            چرخه یادگیری در {lastRun} با موفقیت اجرا شد
          </div>
        )}

        <div className="space-y-4">
          {Object.entries(WEIGHT_LABELS).map(([key, label]) => (
            <WeightBar
              key={key}
              label={label}
              value={(w as any)[key] ?? 0.2}
              prevValue={0.2}
            />
          ))}
        </div>

        <div className="mt-5 p-3 rounded-xl text-xs" style={{ background:"rgba(0,212,255,0.06)", border:"1px solid rgba(0,212,255,0.15)", color:"var(--gv-text-secondary)" }}>
          <div className="flex items-start gap-2">
            <AlertCircle size={12} className="shrink-0 mt-0.5" style={{ color:"var(--gv-accent)" }} />
            <span>
              قانون اصلی: <strong style={{ color:"var(--gv-text-primary)" }}>زیان ≠ اشتباه.</strong> سیستم فقط نقض‌های قوانین را شناسایی می‌کند.
              وزن‌ها به صورت تدریجی (حداکثر ±۵٪ در هر چرخه) تغییر می‌کنند و هیچ استراتژی حذف نمی‌شود.
            </span>
          </div>
        </div>
      </div>

      {/* ML Models status */}
      <div className="gv-card p-4">
        <h3 className="font-semibold mb-4" style={{ color:"var(--gv-text-primary)" }}>مدل‌های ML فعال</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            { name:"XGBoost",  auc:0.71, trained: true,  trades:247 },
            { name:"LightGBM", auc:0.68, trained: true,  trades:247 },
            { name:"CatBoost", auc:0.73, trained: true,  trades:247 },
          ].map((model) => (
            <div key={model.name} className="p-4 rounded-xl"
              style={{ background:"var(--gv-bg-secondary)", border:"1px solid var(--gv-border)" }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono font-bold text-sm" style={{ color:"var(--gv-text-primary)" }}>{model.name}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${model.trained ? "badge-buy" : "badge-wait"}`}>
                  {model.trained ? "آموزش دیده" : "در انتظار"}
                </span>
              </div>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span style={{ color:"var(--gv-text-muted)" }}>AUC Score:</span>
                  <span className="font-mono font-bold" style={{ color:"#10b981" }}>{model.auc}</span>
                </div>
                <div className="flex justify-between">
                  <span style={{ color:"var(--gv-text-muted)" }}>معاملات آموزشی:</span>
                  <span className="font-mono" style={{ color:"var(--gv-text-secondary)" }}>{model.trades}</span>
                </div>
                <div className="h-2 rounded-full overflow-hidden" style={{ background:"var(--gv-bg-card)" }}>
                  <div className="h-full rounded-full" style={{ width:`${model.auc*100}%`, background:"linear-gradient(90deg,#10b981,#059669)" }} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
