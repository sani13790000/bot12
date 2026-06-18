import { useState } from "react";
import { Settings, Save, ToggleLeft, ToggleRight } from "lucide-react";
import { settingsApi } from "../utils/api";
import type { SystemSettings, TradingMode } from "../types";

const DEFAULT_SETTINGS: SystemSettings = {
  trading_mode:"FULL_AUTO",
  risk_per_trade_percent:1.0,
  max_portfolio_risk_percent:5.0,
  max_daily_trades:5,
  max_daily_loss_percent:3.0,
  max_weekly_loss_percent:7.0,
  max_monthly_drawdown_percent:15.0,
  min_confidence_score:80.0,
  max_spread_points:30,
  enable_smc_engine:true,
  enable_pa_engine:true,
  enable_ml_learning:true,
  enable_news_filter:false,
  allowed_sessions:["London","NewYork"],
  allowed_symbols:["XAUUSD","EURUSD","GBPUSD"],
};

function Toggle({ value, onChange }: { value:boolean; onChange:(v:boolean)=>void }) {
  return (
    <button onClick={()=>onChange(!value)} className="flex items-center gap-2 text-sm transition-colors"
      style={{ color: value ? "#10b981" : "var(--gv-text-muted)" }}
    >
      {value ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
      <span className="text-xs">{value ? "فعال" : "غیرفعال"}</span>
    </button>
  );
}

function NumberInput({ label, value, onChange, min, max, step, suffix }:
  { label:string; value:number; onChange:(v:number)=>void; min?:number; max?:number; step?:number; suffix?:string }) {
  return (
    <div className="flex items-center justify-between p-3 rounded-xl"
      style={{ background:"var(--gv-bg-secondary)", border:"1px solid var(--gv-border)" }}
    >
      <span className="text-sm" style={{ color:"var(--gv-text-secondary)" }}>{label}</span>
      <div className="flex items-center gap-2">
        <input
          type="number" min={min} max={max} step={step} value={value}
          onChange={(e)=>onChange(+e.target.value)}
          className="w-20 px-2 py-1 rounded-lg text-sm text-center outline-none font-mono"
          style={{ background:"var(--gv-bg-card)", color:"var(--gv-accent)", border:"1px solid var(--gv-border)" }}
        />
        {suffix && <span className="text-xs" style={{ color:"var(--gv-text-muted)" }}>{suffix}</span>}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<SystemSettings>(DEFAULT_SETTINGS);
  const [saved, setSaved]       = useState(false);

  const update = <K extends keyof SystemSettings>(key:K, value:SystemSettings[K]) => {
    setSettings(s=>({...s,[key]:value}));
    setSaved(false);
  };

  const handleSave = async () => {
    await settingsApi.update(settings);
    setSaved(true);
    setTimeout(()=>setSaved(false), 3000);
  };

  const MODES: { value:TradingMode; label:string; desc:string }[] = [
    { value:"SIGNAL_ONLY", label:"فقط سیگنال",  desc:"فقط تحلیل و سیگنال — بدون اجرا" },
    { value:"SEMI_AUTO",   label:"نیمه خودکار", desc:"نیاز به تأیید کاربر قبل از اجرا" },
    { value:"FULL_AUTO",   label:"تمام خودکار", desc:"اجرای کامل بدون دخالت" },
  ];

  return (
    <div className="space-y-5 max-w-3xl">

      {/* Trading mode */}
      <div className="gv-card p-5">
        <h3 className="font-semibold mb-4 flex items-center gap-2" style={{ color:"var(--gv-text-primary)" }}>
          <Settings size={16} style={{ color:"var(--gv-accent)" }} />
          حالت معاملاتی
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={()=>update("trading_mode",m.value)}
              className="p-4 rounded-xl text-right transition-all"
              style={{
                background: settings.trading_mode===m.value ? "rgba(0,212,255,0.1)" : "var(--gv-bg-secondary)",
                border:`1px solid ${settings.trading_mode===m.value ? "rgba(0,212,255,0.4)" : "var(--gv-border)"}`,
              }}
            >
              <div className="font-semibold text-sm mb-1" style={{ color: settings.trading_mode===m.value ? "var(--gv-accent)" : "var(--gv-text-primary)" }}>
                {m.label}
              </div>
              <div className="text-xs" style={{ color:"var(--gv-text-muted)" }}>{m.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Risk settings */}
      <div className="gv-card p-5">
        <h3 className="font-semibold mb-4" style={{ color:"var(--gv-text-primary)" }}>تنظیمات ریسک</h3>
        <div className="space-y-3">
          <NumberInput label="ریسک هر معامله"        value={settings.risk_per_trade_percent}      onChange={v=>update("risk_per_trade_percent",v)}      min={0.1} max={5}   step={0.1} suffix="%" />
          <NumberInput label="حداکثر ریسک پرتفولیو"  value={settings.max_portfolio_risk_percent}   onChange={v=>update("max_portfolio_risk_percent",v)}  min={1}   max={20}  step={0.5} suffix="%" />
          <NumberInput label="حداکثر معاملات روزانه" value={settings.max_daily_trades}            onChange={v=>update("max_daily_trades",v)}            min={1}   max={20}  step={1} suffix="معامله" />
          <NumberInput label="حداکثر ضرر روزانه"     value={settings.max_daily_loss_percent}      onChange={v=>update("max_daily_loss_percent",v)}      min={0.5} max={10}  step={0.5} suffix="%" />
          <NumberInput label="حداکثر ضرر هفتگی"      value={settings.max_weekly_loss_percent}     onChange={v=>update("max_weekly_loss_percent",v)}     min={1}   max={20}  step={0.5} suffix="%" />
          <NumberInput label="حداکثر Drawdown ماهانه" value={settings.max_monthly_drawdown_percent} onChange={v=>update("max_monthly_drawdown_percent",v)} min={2} max={30} step={1} suffix="%" />
          <NumberInput label="حداقل امتیاز سیگنال"  value={settings.min_confidence_score}        onChange={v=>update("min_confidence_score",v)}        min={50}  max={99}  step={1} suffix="%" />
          <NumberInput label="حداکثر اسپرد"          value={settings.max_spread_points}           onChange={v=>update("max_spread_points",v)}           min={5}   max={100} step={5} suffix="پیپ" />
        </div>
      </div>

      {/* Module toggles */}
      <div className="gv-card p-5">
        <h3 className="font-semibold mb-4" style={{ color:"var(--gv-text-primary)" }}>ماژول‌های فعال</h3>
        <div className="space-y-3">
          {[
            { key:"enable_smc_engine",  label:"موتور SMC (Smart Money Concepts)" },
            { key:"enable_pa_engine",   label:"موتور Price Action" },
            { key:"enable_ml_learning", label:"سیستم یادگیری ML" },
            { key:"enable_news_filter", label:"فیلتر اخبار (News Filter)" },
          ].map(({ key, label }) => (
            <div key={key} className="flex items-center justify-between p-3 rounded-xl"
              style={{ background:"var(--gv-bg-secondary)", border:"1px solid var(--gv-border)" }}
            >
              <span className="text-sm" style={{ color:"var(--gv-text-secondary)" }}>{label}</span>
              <Toggle value={(settings as any)[key]} onChange={(v)=>update(key as any, v)} />
            </div>
          ))}
        </div>
      </div>

      {/* Save button */}
      <button
        onClick={handleSave}
        className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold transition-all"
        style={{
          background: saved ? "rgba(16,185,129,0.2)" : "rgba(0,212,255,0.15)",
          color: saved ? "#10b981" : "var(--gv-accent)",
          border:`1px solid ${saved ? "rgba(16,185,129,0.4)" : "rgba(0,212,255,0.3)"}`,
        }}
      >
        <Save size={16} />
        {saved ? "✅ تنظیمات ذخیره شد" : "ذخیره تنظیمات"}
      </button>
    </div>
  );
}
