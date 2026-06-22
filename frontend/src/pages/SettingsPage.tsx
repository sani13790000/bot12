/**
 * frontend/src/pages/SettingsPage.tsx
 * FIX-27: stub بود — فرم کامل با save/reset + settingsApi
 */
import { useState, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { settingsApi } from "@/utils/api";
import type { SystemSettings } from "@/types";
import { Save, RefreshCw, Settings } from "lucide-react";

const DEFAULT_SETTINGS: SystemSettings = {
  trading_enabled: true, max_daily_trades: 10,
  risk_per_trade: 1.0, max_drawdown_limit: 10.0,
  allowed_symbols: ["XAUUSD", "EURUSD", "GBPUSD"],
};

export default function SettingsPage() {
  const { user } = useAuth();
  const [form,    setForm]    = useState<SystemSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving,  setSaving]  = useState(false);
  const [saved,   setSaved]   = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    settingsApi.get().then(r => { if (r.success && r.data) setForm(r.data); }).finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true); setError(null); setSaved(false);
    const r = await settingsApi.update(form);
    if (r.success) { setSaved(true); setTimeout(() => setSaved(false), 3000); }
    else setError(r.error ?? "خطا در ذخیره");
    setSaving(false);
  };

  if (loading) return <div className="flex justify-center pt-20"><RefreshCw className="w-6 h-6 text-blue-400 animate-spin" /></div>;

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <Settings className="w-6 h-6 text-blue-400" />تنظیمات سیستم
      </h1>
      {user?.role !== "ADMIN" && (
        <div className="p-3 bg-yellow-900/30 border border-yellow-700 rounded-lg text-yellow-300 text-sm">
          فقط ادمین می‌تواند تنظیمات را تغییر دهد.
        </div>
      )}
      {error  && <div className="p-3 bg-red-900/30    border border-red-700    rounded-lg text-red-300    text-sm">{error}</div>}
      {saved  && <div className="p-3 bg-green-900/30  border border-green-700  rounded-lg text-green-300  text-sm">✅ تنظیمات ذخیره شد</div>}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-white font-medium">معاملات فعال</p>
            <p className="text-gray-500 text-sm">فعال یا غیرفعال کردن معاملات خودکار</p>
          </div>
          <button
            onClick={() => setForm(f => ({ ...f, trading_enabled: !f.trading_enabled }))}
            disabled={user?.role !== "ADMIN"}
            className={`relative w-12 h-6 rounded-full transition-colors ${form.trading_enabled ? "bg-blue-600" : "bg-gray-700"} disabled:opacity-50`}>
            <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${form.trading_enabled ? "translate-x-6" : ""}`} />
          </button>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">حداکثر معاملات روزانه</label>
          <input type="number" min={1} max={50} value={form.max_daily_trades}
            onChange={e => setForm(f => ({ ...f, max_daily_trades: Number(e.target.value) }))}
            disabled={user?.role !== "ADMIN"}
            className="w-full px-4 py-2.5 rounded-lg bg-gray-800 border border-gray-700 text-white focus:outline-none focus:border-blue-500 disabled:opacity-50" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">ریسک هر معامله (%) — فعلی: {form.risk_per_trade}%</label>
          <input type="range" min={0.1} max={5} step={0.1} value={form.risk_per_trade}
            onChange={e => setForm(f => ({ ...f, risk_per_trade: Number(e.target.value) }))}
            disabled={user?.role !== "ADMIN"} className="w-full accent-blue-500 disabled:opacity-50" />
          <div className="flex justify-between text-xs text-gray-500 mt-1"><span>0.1%</span><span>5%</span></div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">حداکثر Drawdown (%) — فعلی: {form.max_drawdown_limit}%</label>
          <input type="range" min={1} max={30} step={0.5} value={form.max_drawdown_limit}
            onChange={e => setForm(f => ({ ...f, max_drawdown_limit: Number(e.target.value) }))}
            disabled={user?.role !== "ADMIN"} className="w-full accent-red-500 disabled:opacity-50" />
          <div className="flex justify-between text-xs text-gray-500 mt-1"><span>1%</span><span>30%</span></div>
        </div>
      </div>
      {user?.role === "ADMIN" && (
        <button onClick={save} disabled={saving}
          className="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium transition-colors">
          {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "ذخیره..." : "ذخیره تنظیمات"}
        </button>
      )}
    </div>
  );
}
