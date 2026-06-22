/**
 * frontend/src/pages/SettingsPage.tsx
 * FIX-FE17: stub -> real settings form
 */
import { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Settings, Save, RefreshCw } from "lucide-react";

export default function SettingsPage() {
  const { settings, updateSettings } = useAuth();
  const [saving, setSaving] = useState(false);
  const [saved,  setSaved]  = useState(false);
  const [form, setForm] = useState({
    risk_percentage:       settings?.risk_percentage       ?? 1,
    max_trades:            settings?.max_trades            ?? 5,
    trading_mode:          settings?.trading_mode          ?? "AUTO",
    notifications_enabled: settings?.notifications_enabled ?? true,
    telegram_alerts:       settings?.telegram_alerts       ?? true,
  });

  const handleSave = async () => {
    setSaving(true);
    try { await updateSettings(form); setSaved(true); setTimeout(() => setSaved(false), 3000); }
    finally { setSaving(false); }
  };

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <Settings className="w-6 h-6 text-blue-400" /> \u062a\u0646\u0638\u06cc\u0645\u0627\u062a
      </h1>
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 space-y-5">
        <div>
          <label className="block text-sm text-gray-300 mb-2">\u0631\u06cc\u0633\u06a9 \u0647\u0631 \u0645\u0639\u0627\u0645\u0644\u0647 (%)</label>
          <input type="number" min={0.1} max={10} step={0.1} value={form.risk_percentage}
            onChange={e => setForm(f => ({ ...f, risk_percentage: +e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-2">\u062d\u062f\u0627\u06a9\u062b\u0631 \u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0647\u0645\u0632\u0645\u0627\u0646</label>
          <input type="number" min={1} max={20} step={1} value={form.max_trades}
            onChange={e => setForm(f => ({ ...f, max_trades: +e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500" />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-2">\u062d\u0627\u0644\u062a \u0645\u0639\u0627\u0645\u0644\u0627\u062a\u06cc</label>
          <select value={form.trading_mode}
            onChange={e => setForm(f => ({ ...f, trading_mode: e.target.value as "AUTO" | "SEMI_AUTO" | "MANUAL" }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500">
            <option value="AUTO">\u0627\u062a\u0648\u0645\u0627\u062a\u06cc\u06a9</option>
            <option value="SEMI_AUTO">\u0646\u06cc\u0645\u0647\u200c\u0627\u062a\u0648\u0645\u0627\u062a\u06cc\u06a9</option>
            <option value="MANUAL">\u062f\u0633\u062a\u06cc</option>
          </select>
        </div>
        <div className="pt-2 border-t border-gray-800">
          {([{key:"notifications_enabled",label:"\u0627\u0639\u0644\u0627\u0646\u200c\u0647\u0627\u06cc \u062f\u0627\u0634\u0628\u0648\u0631\u062f"},{key:"telegram_alerts",label:"\u0627\u0639\u0644\u0627\u0646\u200c\u0647\u0627\u06cc \u062a\u0644\u06af\u0631\u0627\u0645"}] as {key: keyof typeof form, label: string}[]).map(({key,label})=>(
            <label key={key} className="flex items-center justify-between cursor-pointer mb-3">
              <span className="text-sm text-gray-300">{label}</span>
              <button type="button" onClick={() => setForm(f => ({ ...f, [key]: !f[key] }))}
                className={`relative w-11 h-6 rounded-full transition-colors ${form[key] ? "bg-blue-600" : "bg-gray-700"}`}>
                <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${form[key] ? "translate-x-6" : "translate-x-1"}`} />
              </button>
            </label>
          ))}
        </div>
      </div>
      <button onClick={handleSave} disabled={saving}
        className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors">
        {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
        {saved ? "\u0630\u062e\u06cc\u0631\u0647 \u0634\u062f \u2713" : "\u0630\u062e\u06cc\u0631\u0647 \u062a\u0646\u0638\u06cc\u0645\u0627\u062a"}
      </button>
    </div>
  );
}
