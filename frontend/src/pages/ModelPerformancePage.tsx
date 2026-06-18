import { useEffect, useState } from "react";
import { Cpu, RefreshCw, CheckCircle, AlertCircle } from "lucide-react";
import { aiApi, selfLearningApi } from "../utils/api";
import type { ModelVersion, MLWeights } from "../types";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

function StatusBadge({ status }: { status: string }) {
  const c = status === "ACTIVE"     ? "text-[#10b981] bg-[#10b981]/10 border-[#10b981]/20"
          : status === "TRAINING"   ? "text-[#f59e0b] bg-[#f59e0b]/10 border-[#f59e0b]/20"
          : status === "DEPRECATED" ? "text-[#475569] bg-[#1e2d40]    border-[#1e2d40]"
          :                           "text-[#ef4444] bg-[#ef4444]/10 border-[#ef4444]/20";
  return <span className={`px-2 py-0.5 rounded text-xs font-bold border ${c}`}>{status}</span>;
}

export default function ModelPerformancePage() {
  const [models,   setModels]   = useState<ModelVersion[]>([]);
  const [weights,  setWeights]  = useState<MLWeights | null>(null);
  const [retraining, setRetraining] = useState(false);
  const [loading,  setLoading]  = useState(true);

  const load = async () => {
    setLoading(true);
    const [m, w] = await Promise.all([aiApi.listModels(), aiApi.getWeights()]);
    if (m.success) setModels(m.data ?? []);
    if (w.success) setWeights(w.data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleRetrain = async (symbol: string) => {
    setRetraining(true);
    await selfLearningApi.retrain(symbol);
    await load();
    setRetraining(false);
  };

  const aucHistory = models.map(m => ({ version: m.version, auc: m.auc_score, train: m.train_auc, test: m.test_auc }));
  const currentModel = models.find(m => m.is_current);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#f59e0b]/10 border border-[#f59e0b]/30 flex items-center justify-center">
            <Cpu size={20} className="text-[#f59e0b]" />
          </div>
          <div>
            <h1 className="text-[#f0f6ff] text-xl font-bold">عملکرد مدل ML</h1>
            <p className="text-[#475569] text-sm">XGBoost · Self-Learning · Versioned</p>
          </div>
        </div>
        <button onClick={() => handleRetrain(currentModel?.symbol ?? "XAUUSD")} disabled={retraining}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#f59e0b]/10 border border-[#f59e0b]/30 text-[#f59e0b] text-sm font-semibold hover:bg-[#f59e0b]/20 transition-all disabled:opacity-50">
          <RefreshCw size={15} className={retraining ? "animate-spin" : ""} /> بازآموزی
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-[#f59e0b] border-t-transparent rounded-full animate-spin" /></div>
      ) : (
        <>
          {/* Current model banner */}
          {currentModel && (
            <div className="gv-card p-5 border border-[#f59e0b]/30 bg-[#f59e0b]/5">
              <div className="flex items-center gap-3 mb-3">
                <CheckCircle size={18} className="text-[#10b981]" />
                <span className="text-[#f0f6ff] font-semibold">مدل فعلی: {currentModel.symbol} · {currentModel.version}</span>
                <StatusBadge status={currentModel.status} />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  ["AUC Score",    currentModel.auc_score.toFixed(4)],
                  ["Train AUC",    currentModel.train_auc.toFixed(4)],
                  ["Test AUC",     currentModel.test_auc.toFixed(4)],
                  ["نمونه‌های آموزشی", currentModel.samples.toLocaleString()],
                ].map(([k, v]) => (
                  <div key={k} className="bg-[#111827] rounded-xl p-3 border border-[#1e2d40]">
                    <div className="text-[#475569] text-xs">{k}</div>
                    <div className="text-[#f0f6ff] font-bold text-lg mt-1">{v}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AUC History chart */}
          {aucHistory.length > 1 && (
            <div className="gv-card p-5">
              <h2 className="text-[#f0f6ff] font-semibold mb-4">روند AUC به تفکیک نسخه</h2>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={aucHistory} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e2d40" vertical={false} />
                    <XAxis dataKey="version" tick={{ fill: "#475569", fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis domain={[0.5, 1]} tick={{ fill: "#475569", fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1e2d40", borderRadius: 8, color: "#f0f6ff" }} />
                    <Line type="monotone" dataKey="auc"   stroke="#00d4ff" strokeWidth={2} dot={{ fill: "#00d4ff", r: 4 }} name="AUC" />
                    <Line type="monotone" dataKey="train" stroke="#10b981" strokeWidth={1.5} dot={false} name="Train" strokeDasharray="4 4" />
                    <Line type="monotone" dataKey="test"  stroke="#f59e0b" strokeWidth={1.5} dot={false} name="Test"  strokeDasharray="4 4" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* ML Feature Weights */}
          {weights && (
            <div className="gv-card p-5">
              <h2 className="text-[#f0f6ff] font-semibold mb-4">وزن‌های ویژگی‌های SMC</h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(weights)
                  .filter(([k]) => k.endsWith("_weight"))
                  .map(([k, v]) => {
                    const pct = Math.round((v as number) * 100);
                    const label = k.replace(/_weight$/, "").replace(/_/g, " ").toUpperCase();
                    return (
                      <div key={k} className="bg-[#111827] rounded-xl p-3 border border-[#1e2d40]">
                        <div className="flex justify-between mb-1.5">
                          <span className="text-[#475569] text-xs">{label}</span>
                          <span className="text-[#f0f6ff] text-xs font-bold">{pct}%</span>
                        </div>
                        <div className="h-1.5 bg-[#1e2d40] rounded-full overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-[#00d4ff] to-[#8b5cf6] rounded-full transition-all" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
              </div>
              <div className="mt-4 flex items-center gap-2 text-xs text-[#475569]">
                <AlertCircle size={12} />
                آخرین آپدیت: {weights.last_updated} · {weights.total_trades_learned} معامله یاد گرفته
              </div>
            </div>
          )}

          {/* Version history table */}
          <div className="gv-card p-5">
            <h2 className="text-[#f0f6ff] font-semibold mb-4">تاریخچه نسخه‌ها</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1e2d40]">
                    {["نسخه","نماد","وضعیت","AUC","نمونه","ساخته شده"].map(h => (
                      <th key={h} className="text-right text-[#475569] py-2 px-3 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {models.map((m, i) => (
                    <tr key={i} className={`border-b border-[#1e2d40]/50 hover:bg-[#111827] transition-colors ${m.is_current ? "bg-[#f59e0b]/5" : ""}`}>
                      <td className="py-2.5 px-3 text-[#f0f6ff] font-mono text-xs">{m.version}</td>
                      <td className="py-2.5 px-3 text-[#00d4ff] font-semibold">{m.symbol}</td>
                      <td className="py-2.5 px-3"><StatusBadge status={m.status} /></td>
                      <td className="py-2.5 px-3 text-[#10b981] font-bold">{m.auc_score.toFixed(4)}</td>
                      <td className="py-2.5 px-3 text-[#475569]">{m.samples.toLocaleString()}</td>
                      <td className="py-2.5 px-3 text-[#475569] text-xs">{new Date(m.created_at).toLocaleDateString("fa-IR")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
