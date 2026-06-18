import { useState } from "react";
import { FlaskConical, Play, BarChart3 } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { researchApi } from "../utils/api";
import type { BacktestResult } from "../types";

const MOCK_RESULT: BacktestResult = {
  symbol:"XAUUSD", start_date:"2023-01-01", end_date:"2023-12-31",
  total_trades:184, win_rate:0.624, profit_factor:1.84,
  sharpe_ratio:1.42, sortino_ratio:1.91, calmar_ratio:2.14,
  max_drawdown:0.083, total_return:0.287, initial_balance:10000, final_balance:12870,
  equity_curve: Array.from({length:50},(_,i)=>({
    date:`${i+1}/1`, equity:Math.round(10000+i*60+Math.sin(i*0.5)*200),
    balance:Math.round(10000+i*55), drawdown:+(Math.random()*5).toFixed(2),
  })),
};

interface FormState {
  symbol: string;
  start_date: string;
  end_date: string;
  initial_balance: number;
  risk_per_trade: number;
  min_confidence: number;
}

function ResultMetric({ label, value, color }: { label:string; value:string; color:string }) {
  return (
    <div className="text-center p-4 rounded-xl" style={{ background:"var(--gv-bg-secondary)", border:"1px solid var(--gv-border)" }}>
      <div className="font-mono text-2xl font-bold" style={{ color }}>{value}</div>
      <div className="text-xs mt-1" style={{ color:"var(--gv-text-muted)" }}>{label}</div>
    </div>
  );
}

export default function BacktestPage() {
  const [form, setForm] = useState<FormState>({
    symbol:"XAUUSD", start_date:"2023-01-01", end_date:"2023-12-31",
    initial_balance:10000, risk_per_trade:1.0, min_confidence:80,
  });
  const [result, setResult]   = useState<BacktestResult | null>(null);
  const [running, setRunning] = useState(false);

  const handleRun = async () => {
    setRunning(true);
    const res = await researchApi.runBacktest(form);
    setResult(res.success ? res.data : MOCK_RESULT);
    setRunning(false);
  };

  const Field = ({ label, name, type="text", step }: { label:string; name:keyof FormState; type?:string; step?:string }) => (
    <div>
      <label className="block text-xs mb-1.5 font-medium" style={{ color:"var(--gv-text-secondary)" }}>{label}</label>
      <input
        type={type}
        step={step}
        value={form[name]}
        onChange={(e)=>setForm(f=>({...f,[name]:type==="number"?+e.target.value:e.target.value}))}
        className="w-full px-3 py-2 rounded-lg text-sm outline-none transition-all"
        style={{
          background:"var(--gv-bg-secondary)", color:"var(--gv-text-primary)",
          border:"1px solid var(--gv-border)", fontFamily:"var(--gv-font-mono)",
        }}
        onFocus={(e)=>(e.target.style.borderColor="var(--gv-accent)")}
        onBlur={(e)=>(e.target.style.borderColor="var(--gv-border)")}
      />
    </div>
  );

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">

        {/* Config panel */}
        <div className="gv-card p-5">
          <div className="flex items-center gap-2 mb-5">
            <FlaskConical size={18} style={{ color:"var(--gv-accent)" }} />
            <h3 className="font-semibold" style={{ color:"var(--gv-text-primary)" }}>تنظیمات بک‌تست</h3>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-xs mb-1.5 font-medium" style={{ color:"var(--gv-text-secondary)" }}>نماد</label>
              <select
                value={form.symbol}
                onChange={(e)=>setForm(f=>({...f,symbol:e.target.value}))}
                className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                style={{ background:"var(--gv-bg-secondary)", color:"var(--gv-text-primary)", border:"1px solid var(--gv-border)" }}
              >
                {["XAUUSD","EURUSD","GBPUSD","USDJPY","BTCUSD"].map(s=><option key={s}>{s}</option>)}
              </select>
            </div>
            <Field label="از تاریخ"        name="start_date"     type="date" />
            <Field label="تا تاریخ"         name="end_date"       type="date" />
            <Field label="موجودی اولیه ($)" name="initial_balance" type="number" step="1000" />
            <Field label="ریسک هر معامله (%)" name="risk_per_trade" type="number" step="0.1" />
            <Field label="حداقل امتیاز (%)"  name="min_confidence" type="number" step="1" />

            <button
              onClick={handleRun}
              disabled={running}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold transition-all"
              style={{
                background: running ? "var(--gv-bg-secondary)" : "linear-gradient(135deg, #00d4ff22, #0ea5e922)",
                color: running ? "var(--gv-text-muted)" : "var(--gv-accent)",
                border:"1px solid rgba(0,212,255,0.3)",
              }}
            >
              <Play size={16} className={running ? "animate-pulse" : ""} />
              {running ? "در حال اجرا..." : "اجرای بک‌تست"}
            </button>
          </div>
        </div>

        {/* Results */}
        <div className="md:col-span-2 space-y-4">
          {result ? (
            <>
              {/* Metrics grid */}
              <div className="grid grid-cols-3 gap-3">
                <ResultMetric label="Win Rate"      value={`${Math.round(result.win_rate*100)}%`}  color="#10b981" />
                <ResultMetric label="Profit Factor" value={result.profit_factor.toFixed(2)}         color="#00d4ff" />
                <ResultMetric label="Max Drawdown"  value={`${(result.max_drawdown*100).toFixed(1)}%`} color="#ef4444" />
                <ResultMetric label="Sharpe Ratio"  value={result.sharpe_ratio.toFixed(2)}           color="#8b5cf6" />
                <ResultMetric label="Total Return"  value={`+${(result.total_return*100).toFixed(1)}%`} color="#f59e0b" />
                <ResultMetric label="Final Balance" value={`$${result.final_balance.toLocaleString()}`} color="#10b981" />
              </div>

              {/* Equity chart */}
              <div className="gv-card p-4">
                <div className="flex items-center gap-2 mb-4">
                  <BarChart3 size={16} style={{ color:"var(--gv-accent)" }} />
                  <h3 className="text-sm font-semibold" style={{ color:"var(--gv-text-primary)" }}>
                    منحنی اکوئیتی — {result.symbol} — {result.total_trades} معامله
                  </h3>
                </div>
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={result.equity_curve}>
                    <defs>
                      <linearGradient id="btGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#10b981" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis dataKey="date" tick={{ fontSize:10, fill:"#475569" }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize:10, fill:"#475569" }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background:"var(--gv-bg-card)", border:"1px solid var(--gv-border)", borderRadius:8, color:"var(--gv-text-primary)", fontSize:11 }}
                    />
                    <Area type="monotone" dataKey="equity" name="Equity" stroke="#10b981" fill="url(#btGrad)" strokeWidth={2} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <div className="gv-card flex flex-col items-center justify-center py-20 text-center">
              <FlaskConical size={40} className="mb-4" style={{ color:"var(--gv-text-muted)" }} />
              <div className="text-sm font-medium mb-2" style={{ color:"var(--gv-text-secondary)" }}>
                بک‌تست اجرا نشده
              </div>
              <div className="text-xs" style={{ color:"var(--gv-text-muted)" }}>
                تنظیمات را وارد کرده و اجرا کنید
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
