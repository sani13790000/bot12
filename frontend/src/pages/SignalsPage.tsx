import { useEffect, useState } from "react";
import { Zap, CheckCircle, XCircle, Clock, TrendingUp, TrendingDown } from "lucide-react";
import { signalsApi } from "../utils/api";
import type { Signal } from "../types";

const MOCK_SIGNALS: Signal[] = [
  { id:"s1", symbol:"XAUUSD", direction:"BUY",  entry_price:2341.50, stop_loss:2334.00, take_profit_1:2352.00, take_profit_2:2362.00, confidence_score:87, risk_level:"LOW",    risk_reward_ratio:2.4, status:"ACTIVE",   created_at:"2024-06-18T10:00:00Z", expires_at:"2024-06-18T12:00:00Z", context_explanation:"BOS صعودی در H4 تأیید شد. OB باکیفیت در ناحیه Discount. Kill Zone لندن.", smc_details:"BOS+OB+FVG", pa_pattern:"Pin Bar", session:"London" },
  { id:"s2", symbol:"EURUSD", direction:"SELL", entry_price:1.0842,  stop_loss:1.0868,  take_profit_1:1.0790, take_profit_2:1.0750, confidence_score:82, risk_level:"MEDIUM", risk_reward_ratio:2.0, status:"ACTIVE",   created_at:"2024-06-18T09:30:00Z", expires_at:"2024-06-18T11:30:00Z", context_explanation:"CHOCH نزولی در H1. نقدینگی جارو شد. ساختار Premium.", smc_details:"CHOCH+LiqSweep", pa_pattern:"Engulfing", session:"London" },
  { id:"s3", symbol:"GBPUSD", direction:"BUY",  entry_price:1.2680,  stop_loss:1.2640,  take_profit_1:1.2740, take_profit_2:1.2800, confidence_score:91, risk_level:"LOW",    risk_reward_ratio:2.8, status:"EXECUTED", created_at:"2024-06-17T13:00:00Z", expires_at:"2024-06-17T15:00:00Z", context_explanation:"OB اجرا شد. FVG پر شد.", smc_details:"OB+FVG", pa_pattern:"Inside Bar", session:"NewYork" },
];

function ConfidenceBar({ score }: { score: number }) {
  const color = score >= 85 ? "#10b981" : score >= 75 ? "#f59e0b" : "#ef4444";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: "var(--gv-bg-secondary)" }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${score}%`, background: color }} />
      </div>
      <span className="text-xs font-mono font-bold w-8" style={{ color }}>{score}%</span>
    </div>
  );
}

export default function SignalsPage() {
  const [signals, setSignals] = useState<Signal[]>([]);

  useEffect(() => {
    signalsApi.list().then((res) => {
      setSignals(res.success && res.data?.length ? res.data : MOCK_SIGNALS);
    });
  }, []);

  const handleExecute = async (id: string) => {
    await signalsApi.execute(id);
    setSignals((prev) => prev.map((s) => s.id === id ? { ...s, status: "EXECUTED" } : s));
  };
  const handleCancel = async (id: string) => {
    await signalsApi.cancel(id);
    setSignals((prev) => prev.map((s) => s.id === id ? { ...s, status: "CANCELLED" } : s));
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "سیگنال‌های فعال", value: signals.filter(s=>s.status==="ACTIVE").length,   color:"#00d4ff" },
          { label: "اجرا شده",        value: signals.filter(s=>s.status==="EXECUTED").length, color:"#10b981" },
          { label: "منقضی/لغو",       value: signals.filter(s=>["EXPIRED","CANCELLED"].includes(s.status)).length, color:"#475569" },
        ].map(({ label, value, color }) => (
          <div key={label} className="gv-card p-4 text-center">
            <div className="metric-value" style={{ color }}>{value}</div>
            <div className="text-xs mt-1" style={{ color: "var(--gv-text-muted)" }}>{label}</div>
          </div>
        ))}
      </div>

      <div className="space-y-3">
        {signals.map((s) => (
          <div key={s.id} className="gv-card p-4 fade-in-up"
            style={{ borderColor: s.status === "ACTIVE" ? "rgba(0,212,255,0.2)" : "var(--gv-border)" }}
          >
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${s.direction==="BUY" ? "badge-buy" : "badge-sell"}`}>
                  {s.direction === "BUY" ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold" style={{ color: "var(--gv-text-primary)" }}>{s.symbol}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${s.direction==="BUY" ? "badge-buy" : "badge-sell"}`}>
                      {s.direction === "BUY" ? "خرید" : "فروش"}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${s.status==="ACTIVE" ? "badge-active" : s.status==="EXECUTED" ? "badge-buy" : "badge-wait"}`}>
                      {s.status === "ACTIVE" ? "فعال" : s.status === "EXECUTED" ? "اجرا شد" : "منقضی"}
                    </span>
                  </div>
                  <div className="text-xs mt-0.5" style={{ color: "var(--gv-text-muted)" }}>
                    {s.session} · {new Date(s.created_at).toLocaleTimeString("fa-IR")}
                  </div>
                </div>
              </div>

              {/* Price grid */}
              <div className="flex gap-4 text-xs">
                {[
                  { label: "ورود", value: s.entry_price, color: "var(--gv-text-primary)" },
                  { label: "SL",   value: s.stop_loss,   color: "#ef4444" },
                  { label: "TP1",  value: s.take_profit_1, color: "#10b981" },
                  { label: "R:R",  value: `1:${s.risk_reward_ratio}`, color: "#00d4ff" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="text-center">
                    <div className="font-mono font-bold" style={{ color }}>{value}</div>
                    <div style={{ color: "var(--gv-text-muted)" }}>{label}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Confidence + context */}
            <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--gv-border)" }}>
              <div className="flex items-center gap-4 mb-2">
                <span className="text-xs" style={{ color: "var(--gv-text-muted)" }}>امتیاز اطمینان:</span>
                <div className="flex-1 max-w-xs"><ConfidenceBar score={s.confidence_score} /></div>
              </div>
              <div className="flex items-center justify-between gap-4">
                <div className="text-xs flex-1" style={{ color: "var(--gv-text-secondary)" }}>
                  <span className="font-medium" style={{ color: "var(--gv-accent)" }}>{s.smc_details}</span>
                  {" · "}
                  <span>{s.pa_pattern}</span>
                  {" · "}
                  <span>{s.context_explanation}</span>
                </div>
                {s.status === "ACTIVE" && (
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => handleExecute(s.id)}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                      style={{ background:"rgba(16,185,129,0.15)", color:"#10b981", border:"1px solid rgba(16,185,129,0.3)" }}
                    >
                      <CheckCircle size={12} /> اجرا
                    </button>
                    <button
                      onClick={() => handleCancel(s.id)}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                      style={{ background:"rgba(239,68,68,0.15)", color:"#ef4444", border:"1px solid rgba(239,68,68,0.3)" }}
                    >
                      <XCircle size={12} /> لغو
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
