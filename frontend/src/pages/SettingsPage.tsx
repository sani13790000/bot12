import { useState, useEffect } from "react";
import { Save, RefreshCw } from "lucide-react";
import { settingsApi } from "../utils/api";
import type { SystemSettings } from "../types";

const MODES = [
  { value: "SIGNAL_ONLY", label: "فقط سیگنال", desc: "سیگنال تولید می‌شود اما معامله نمی‌شود" },
  { value: "SEMI_AUTO",   label: "نیمه خودکار", desc: "تأیید تلگرام قبل از معامله" },
  { value: "FULL_AUTO",   label: "تمام خودکار", desc: "معامله خودکار بدون نیاز به تأیید" },
];

export default function SettingsPage() {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [saving, setSaving]     = useState(false);
  const [saved, setSaved]       = useState(false);

  useEffect(() => {
    settingsApi.get().then(r => { if (r.success) setSettings(r.data); });
  }, []);

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    await settingsApi.update(settings);
    setSaving(false); setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  if (!settings) return <div className="flex justify-center py-20"><div className="w-8 h-8 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="space-y-5 max-w-2xl">
      <div className="flex items-center justify-between">
        <div><h1 className="text-[#f0f6ff] text-2xl font-bold">تنظیمات</h1><p className="text-[#475569] text-sm mt-1">Galaxy Vast AI Trading Platform</p></div>
        <button onClick={handleSave} disabled={saving}
          className={`px-5 py-2 rounded-xl text-sm font-bold transition-all flex items-center gap-2 ${saved ? "bg-[#10b981] text-white" : "bg-[#00d4ff] text-[#070b12] hover:bg-[#0ea5e9]"} disabled:opacity-50`}>
          {saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
          {saved ? "ذخیره شد ✓" : "ذخیره"}
        </button>
      </div>

      {/* Trading Mode */}
      <div className="gv-card p-5">
        <h2 className="text-[#f0f6ff] font-semibold mb-4">حالت معاملاتی</h2>
        <div className="space-y-3">
          {MODES.map(m => (
            <label key={m.value} className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all ${settings.trading_mode === m.value ? "border-[#00d4ff]/40 bg-[#00d4ff]/5" : "border-[#1e2d40] hover:border-[#2a3f58]"}`}>
              <input type="radio" name="mode" value={m.value} checked={settings.trading_mode === m.value as SystemSettings["trading_mode"]}
                onChange={() => setSettings(s => s ? { ...s, trading_mode: m.value as SystemSettings["trading_mode"] } : s)}
                className="mt-1 accent-[#00d4ff]" />
              <div>
                <div className="text-[#f0f6ff] font-medium">{m.label}</div>
                <div className="text-[#475569] text-sm">{m.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Risk Settings */}
      <div className="gv-card p-5">
        <h2 className="text-[#f0f6ff] font-semibold mb-4">تنظیمات ریسک</h2>
        <div className="grid grid-cols-2 gap-4">
          {[
            { key: "risk_per_trade_percent",       label: "ریسک هر معامله (%)",     min: 0.1, max: 5,   step: 0.1 },
            { key: "max_portfolio_risk_percent",   label: "حداکثر ریسک پرتفولیو (%)", min: 1, max: 10,   step: 0.5 },
            { key: "max_daily_trades",             label: "حداکثر معاملات روزانه",  min: 1,  max: 20,   step: 1   },
            { key: "max_daily_loss_percent",       label: "حداکثر ضرر روزانه (%)", min: 0.5, max: 10,  step: 0.5 },
            { key: "max_weekly_loss_percent",      label: "حداکثر ضرر هفتگی (%)", min: 1,   max: 20,   step: 0.5 },
            { key: "min_confidence_score",         label: "حداقل امتیاز اطمینان", min: 50, max: 95,    step: 5   },
          ].map(f => (
            <div key={f.key}>
              <label className="text-[#94a3b8] text-xs block mb-1">{f.label}</label>
              <div className="flex items-center gap-2">
                <input type="range" min={f.min} max={f.max} step={f.step}
                  value={(settings as Record<string, unknown>)[f.key] as number}
                  onChange={e => setSettings(s => s ? { ...s, [f.key]: parseFloat(e.target.value) } : s)}
                  className="flex-1 accent-[#00d4ff]" />
                <span className="font-mono text-[#00d4ff] text-sm w-10 text-right">
                  {((settings as Record<string, unknown>)[f.key] as number).toFixed(f.step < 1 ? 1 : 0)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Module Toggles */}
      <div className="gv-card p-5">
        <h2 className="text-[#f0f6ff] font-semibold mb-4">ماژول‌ها</h2>
        <div className="space-y-3">
          {[
            { key: "enable_smc_engine",   label: "موتور SMC",          desc: "BOS + CHOCH + OB + FVG" },
            { key: "enable_pa_engine",    label: "موتور Price Action",  desc: "الگوهای کندل" },
            { key: "enable_ml_learning",  label: "یادگیری ماشین",      desc: "XGBoost Auto-Retrain" },
            { key: "enable_news_filter",  label: "فیلتر اخبار",        desc: "NFP + FOMC + CPI" },
          ].map(m => (
            <div key={m.key} className="flex items-center justify-between p-3 bg-[#111827] rounded-xl border border-[#1e2d40]">
              <div>
                <div className="text-[#f0f6ff] text-sm font-medium">{m.label}</div>
                <div className="text-[#475569] text-xs">{m.desc}</div>
              </div>
              <button onClick={() => setSettings(s => s ? { ...s, [m.key]: !(s as Record<string,unknown>)[m.key] } : s)}
                className={`relative w-12 h-6 rounded-full transition-all ${(settings as Record<string,unknown>)[m.key] ? "bg-[#00d4ff]" : "bg-[#1e2d40]"}`}>
                <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all ${(settings as Record<string,unknown>)[m.key] ? "right-0.5" : "left-0.5"}`} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
