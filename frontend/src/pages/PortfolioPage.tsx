import { Shield, AlertTriangle, CheckCircle, TrendingUp, TrendingDown } from "lucide-react";

const MOCK_POSITIONS = [
  { symbol:"XAUUSD", direction:"BUY",  risk_percent:1.0, unrealized_pnl: 38.50, correlation:"Gold" },
  { symbol:"EURUSD", direction:"SELL", risk_percent:0.8, unrealized_pnl:-12.30, correlation:"EUR" },
];

const MOCK_CURRENCY_EXPOSURE: Record<string, number> = {
  "XAU": 1.0, "EUR": 0.8, "GBP": 0.0, "USD": 1.8,
};

export default function PortfolioPage() {
  const totalRisk = MOCK_POSITIONS.reduce((s, p) => s + p.risk_percent, 0);
  const maxRisk   = 5.0;
  const riskPct   = (totalRisk / maxRisk) * 100;
  const canOpen   = totalRisk < maxRisk;

  return (
    <div className="space-y-5">

      {/* Overall risk gauge */}
      <div className="gv-card p-5" style={{ borderColor: totalRisk > 4 ? "rgba(239,68,68,0.3)" : totalRisk > 3 ? "rgba(245,158,11,0.3)" : "rgba(16,185,129,0.3)" }}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold" style={{ color: "var(--gv-text-primary)" }}>ریسک کل پرتفولیو</h3>
          <span className={`flex items-center gap-2 text-sm font-medium px-3 py-1.5 rounded-lg ${canOpen ? "badge-buy" : "badge-sell"}`}>
            {canOpen ? <CheckCircle size={14}/> : <AlertTriangle size={14}/>}
            {canOpen ? "امکان معامله جدید" : "بلاک — محدودیت ریسک"}
          </span>
        </div>

        <div className="flex items-end gap-3 mb-3">
          <span className="font-mono text-4xl font-bold" style={{ color: totalRisk > 4 ? "#ef4444" : totalRisk > 3 ? "#f59e0b" : "#10b981" }}>
            {totalRisk.toFixed(1)}%
          </span>
          <span className="text-sm mb-1" style={{ color: "var(--gv-text-muted)" }}>از {maxRisk}% مجاز</span>
        </div>

        {/* Risk bar */}
        <div className="w-full h-4 rounded-full overflow-hidden" style={{ background: "var(--gv-bg-secondary)" }}>
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${Math.min(riskPct, 100)}%`,
              background: totalRisk > 4 ? "linear-gradient(90deg, #ef4444, #b91c1c)" :
                          totalRisk > 3 ? "linear-gradient(90deg, #f59e0b, #d97706)" :
                          "linear-gradient(90deg, #10b981, #059669)",
            }}
          />
        </div>
        <div className="flex justify-between mt-1 text-xs" style={{ color: "var(--gv-text-muted)" }}>
          <span>۰%</span>
          <span>سطح هشدار ۳%</span>
          <span>حداکثر ۵%</span>
        </div>
      </div>

      {/* Open positions */}
      <div className="gv-card p-4">
        <h3 className="font-semibold mb-4" style={{ color: "var(--gv-text-primary)" }}>معاملات باز و ریسک هر پوزیشن</h3>
        <div className="space-y-3">
          {MOCK_POSITIONS.map((pos) => (
            <div key={pos.symbol} className="flex items-center justify-between p-3 rounded-xl"
              style={{ background: "var(--gv-bg-secondary)", border: "1px solid var(--gv-border)" }}
            >
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${pos.direction==="BUY" ? "badge-buy" : "badge-sell"}`}>
                  {pos.direction==="BUY" ? <TrendingUp size={14}/> : <TrendingDown size={14}/>}
                </div>
                <div>
                  <div className="font-mono font-bold text-sm" style={{ color: "var(--gv-text-primary)" }}>{pos.symbol}</div>
                  <div className="text-xs" style={{ color: "var(--gv-text-muted)" }}>{pos.correlation} Group</div>
                </div>
              </div>

              <div className="flex items-center gap-6 text-sm">
                <div className="text-center">
                  <div className="font-mono font-bold" style={{ color: "#f59e0b" }}>{pos.risk_percent}%</div>
                  <div className="text-xs" style={{ color: "var(--gv-text-muted)" }}>ریسک</div>
                </div>
                <div className="text-center">
                  <div className="font-mono font-bold" style={{ color: pos.unrealized_pnl >= 0 ? "#10b981" : "#ef4444" }}>
                    {pos.unrealized_pnl >= 0 ? "+" : ""}${pos.unrealized_pnl.toFixed(2)}
                  </div>
                  <div className="text-xs" style={{ color: "var(--gv-text-muted)" }}>PnL فعلی</div>
                </div>
                {/* Risk bar */}
                <div className="w-24">
                  <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--gv-bg-card)" }}>
                    <div className="h-full rounded-full" style={{ width: `${(pos.risk_percent/2)*100}%`, background: "#f59e0b" }} />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Currency exposure */}
      <div className="gv-card p-4">
        <h3 className="font-semibold mb-4" style={{ color: "var(--gv-text-primary)" }}>مواجهه ارزی</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(MOCK_CURRENCY_EXPOSURE).map(([currency, risk]) => (
            <div key={currency} className="p-3 rounded-xl text-center"
              style={{ background: "var(--gv-bg-secondary)", border: "1px solid var(--gv-border)" }}
            >
              <div className="font-mono text-2xl font-bold" style={{ color: risk > 0 ? "#00d4ff" : "var(--gv-text-muted)" }}>
                {risk.toFixed(1)}%
              </div>
              <div className="text-xs mt-1 font-medium" style={{ color: "var(--gv-text-secondary)" }}>{currency}</div>
              <div className="w-full h-1.5 rounded-full mt-2 overflow-hidden" style={{ background: "var(--gv-bg-card)" }}>
                <div className="h-full rounded-full" style={{ width: `${(risk/3)*100}%`, background: "#00d4ff" }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Daily limits */}
      <div className="gv-card p-4">
        <h3 className="font-semibold mb-4" style={{ color: "var(--gv-text-primary)" }}>محدودیت‌های روزانه</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label:"معاملات امروز", used:2, max:5,   color:"#00d4ff" },
            { label:"ضرر روزانه",   used:0.8, max:3,  color:"#ef4444", suffix:"%" },
            { label:"ضرر هفتگی",   used:1.2, max:7,  color:"#f59e0b", suffix:"%" },
            { label:"Drawdown ماه", used:4.2, max:15, color:"#8b5cf6", suffix:"%" },
          ].map(({ label, used, max, color, suffix="" }) => (
            <div key={label} className="p-3 rounded-xl" style={{ background:"var(--gv-bg-secondary)", border:"1px solid var(--gv-border)" }}>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs" style={{ color:"var(--gv-text-muted)" }}>{label}</span>
                <span className="font-mono text-sm font-bold" style={{ color }}>
                  {used}{suffix} / {max}{suffix}
                </span>
              </div>
              <div className="h-2 rounded-full overflow-hidden" style={{ background:"var(--gv-bg-card)" }}>
                <div className="h-full rounded-full transition-all" style={{ width:`${(used/max)*100}%`, background:color }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
