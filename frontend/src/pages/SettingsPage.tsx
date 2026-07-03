// frontend/src/pages/SettingsPage.tsx
import React, { useState } from "react";
import { Settings, Save, Loader2 } from "lucide-react";
import { licenseApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import Badge from "@/components/Badge";
import LoadingSpinner from "@/components/LoadingSpinner";

export default function SettingsPage() {
  const { data: license, isLoading, refetch } = useApi(licenseApi.getStatus);
  const [licKey, setLicKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg]       = useState("");

  const activateLicense = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true); setMsg("");
    try { await licenseApi.activate(licKey); setMsg("لایسنس با موفقیت فعال شد"); refetch(); }
    catch (err) { setMsg(err instanceof Error ? err.message : "خطا"); }
    finally { setSaving(false); }
  };

  return (
    <div className="p-6 space-y-6">
      <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><Settings size={20} /> تنظیمات</h1></div>
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
        <h2 className="text-sm font-semibold text-white">وضعیت لایسنس</h2>
        {isLoading && <LoadingSpinner size="sm" />}
        {license && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div><p className="text-gray-400">وضعیت</p><Badge label={license.is_valid?"معتبر":"نامعتبر"} color={license.is_valid?"green":"red"} /></div>
            <div><p className="text-gray-400">پلن</p><p className="text-white mt-1">{license.plan}</p></div>
            <div><p className="text-gray-400">انقضا</p><p className="text-white mt-1">{new Date(license.expires_at).toLocaleDateString("fa-IR")}</p></div>
            <div><p className="text-gray-400">حساب‌ها</p><p className="text-white mt-1">{license.active_accounts}/{license.max_accounts}</p></div>
          </div>
        )}
        <form onSubmit={activateLicense} className="flex gap-3">
          <input value={licKey} onChange={e => setLicKey(e.target.value)} placeholder="کلید لایسنس جدید..."
            className="flex-1 rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" />
          <button type="submit" disabled={saving||!licKey}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm text-white disabled:opacity-50 transition-colors">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}فعال‌سازی
          </button>
        </form>
        {msg && <p className="text-xs text-blue-400">{msg}</p>}
      </div>
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="text-sm font-semibold text-white mb-3">اطلاعات سیستم</h2>
        <div className="space-y-2 text-xs">
          {[{k:"API URL",v:import.meta.env.VITE_API_URL??"http://localhost:8000"},{k:"WS URL",v:import.meta.env.VITE_WS_URL??"ws://localhost:8000"},{k:"نسخه",v:"3.0.0"}]
            .map(({k,v}) => <div key={k} className="flex justify-between p-2 rounded-lg bg-gray-800"><span className="text-gray-400">{k}</span><span className="text-gray-300 font-mono">{v}</span></div>)}
        </div>
      </div>
    </div>
  );
}
