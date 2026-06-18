import { useEffect, useState } from "react";
import { Brain, Zap, ShieldCheck, Activity } from "lucide-react";
import { aiApi } from "../utils/api";
import { useWS } from "../contexts/WebSocketContext";
import type { AIprediction } from "../types";
import { RadialBarChart, RadialBar, ResponsiveContainer, Tooltip } from "recharts";

type AIprediction = {
  symbol: string; direction: string; probability: number;
  confidence: number; risk: string; model_auc: number; is_tradeable: boolean; reason: string;
};

function RiskBadge({ risk }: { risk: string }) {
  const c = risk === "LOW" ? "text-[#10b981] bg-[#10b981]/15 border-[#10b981]/30"
    : risk === "MEDIUM" ? "text-[#f59e0b] bg-[#f59e0b]/15 border-[#f59e0b]/30"
    : "text-[#ef4444] bg-[#ef4444]/15 border-[#ef4444]/30";
  return <span className={`px-2 py-0.5 rounded-lg text-xs font-bold border ${c}`}>{risk}</span>;
}

function GaugeCard({ label, value, color }: { label: string; value: number; color: string }) {
  const data = [{ value, fill: color }];
  return (
    <div className="text-center">
      <div className="h-28 relative">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart innerRadius="60%" outerRadius="90%" data={data} startAngle={180} endAngle={0}>
            <RadialBar dataKey="value" cornerRadius={6} background={{ fill: "#1e2d40" }} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex items-center justify-center pt-8">
          <span className="text-2xl font-bold" style={{ color }}>{value}%</span>
        </div>
      </div>
      <div className="text-[#475569] text-xs mt-1">{label}</div>
    </div>
  );
}

export default function AIPredictionsPage() {
  const [predictions, setPredictions] = useState<AIprediction[]>([]);
  const [loading, setLoading] = useState(true);
  const { on } = useWS();

  const load = async () => {
    setLoading(true);
    try {
      const r = await aiApi.getLatest();
      if (r.success) setPredictions(r.data ?? []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const off = on("PREDICTION", (d: unknown) => {
      const p = d as AIprediction;
      setPredictions(ps => [p, ...ps.filter(x => x.symbol !== p.symbol)].slice(0, 20));
    });
    return off;
  }, [on]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-[#8b5cf6]/10 border border-[#8b5cf6]/30 flex items-center justify-center">
          <Brain size={20} className="text-[#8b5cf6]" />
        </div>
        <div>
          <h1 className="text-[#f0f6ff] text-xl font-bold">پیش‌بینی‌های AI</h1>
          <p className="text-[#475569] text-sm">XGBoost · 38 ویژگی SMC</p>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-[#8b5cf6] border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <div className="grid gap-4">
          {predictions.length === 0 && (
            <div className="gv-card p-12 text-center">
              <Brain size={40} className="text-[#1e2d40] mx-auto mb-3" />
              <p className="text-[#475569]">هنوز پیش‌بینی‌ای دریافت نشده</p>
            </div>
          )}
          {predictions.map((p, i) => (
            <div key={i} className={`gv-card p-5 border transition-all ${p.is_tradeable ? "border-[#10b981]/30 hover:border-[#10b981]/50" : "border-[#1e2d40]"}`}>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className="text-[#f0f6ff] text-lg font-bold">{p.symbol}</span>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${p.direction === "BUY" ? "text-[#10b981] bg-[#10b981]/10" : "text-[#ef4444] bg-[#ef4444]/10"}`}>{p.direction}</span>
                  {p.is_tradeable && <span className="text-xs text-[#10b981] bg-[#10b981]/10 px-2 py-0.5 rounded-lg border border-[#10b981]/20">✓ قابل معامله</span>}
                </div>
                <RiskBadge risk={p.risk} />
              </div>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <GaugeCard label="احتمال برد"   value={p.probability}  color="#00d4ff" />
                <GaugeCard label="اطمینان"      value={p.confidence}   color="#8b5cf6" />
                <GaugeCard label="AUC مدل"      value={Math.round(p.model_auc * 100)} color="#10b981" />
              </div>
              <div className="text-xs text-[#475569] bg-[#111827] rounded-lg px-3 py-2 border border-[#1e2d40]">
                <Activity size={12} className="inline ml-1 text-[#00d4ff]" />{p.reason}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
