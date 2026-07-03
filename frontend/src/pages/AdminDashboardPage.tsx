// frontend/src/pages/AdminDashboardPage.tsx
import React, { useState } from "react";
import { Shield, Users, Activity, AlertTriangle, Power, Loader2 } from "lucide-react";
import { adminApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import StatCard from "@/components/StatCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

export default function AdminDashboardPage() {
  const { data: stats, isLoading, error, refetch } = useApi(adminApi.getStats);
  const { data: security } = useApi(adminApi.getSecurityMetrics);
  const [ksLoading, setKsLoading] = useState(false);

  const toggleKillSwitch = async () => {
    if (!confirm(stats?.kill_switch_active ? "غیرفعال کردن Kill Switch؟" : "فعال کردن Kill Switch؟ همه معاملات متوقف می‌شوند!")) return;
    setKsLoading(true);
    try { stats?.kill_switch_active ? await adminApi.deactivateKillSwitch() : await adminApi.activateKillSwitch(); refetch(); }
    catch (e) { alert(e instanceof Error ? e.message : "خطا"); }
    finally { setKsLoading(false); }
  };

  if (isLoading) return <LoadingSpinner text="در حال بارگذاری..." />;
  if (error) return <div className="p-6"><ErrorAlert message={error} onRetry={refetch} /></div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><Shield size={20} className="text-purple-400" /> پنل مدیریت</h1><p className="text-sm text-gray-400 mt-1">کنترل کامل سیستم</p></div>
        <button onClick={toggleKillSwitch} disabled={ksLoading}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${stats?.kill_switch_active ? "bg-green-600 hover:bg-green-500 text-white" : "bg-red-600 hover:bg-red-500 text-white"}`}>
          {ksLoading ? <Loader2 size={16} className="animate-spin" /> : <Power size={16} />}
          {stats?.kill_switch_active ? "غیرفعال Kill Switch" : "فعال کردن Kill Switch"}
        </button>
      </div>
      {stats?.kill_switch_active && (
        <div className="flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          <AlertTriangle size={18} /><p className="text-sm font-medium">Kill Switch فعال است — همه معاملات متوقف شده‌اند</p>
        </div>
      )}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="کل کاربران"   value={stats.total_users}        icon={Users}    color="blue" />
          <StatCard title="کاربران فعال" value={stats.active_users}       icon={Activity} color="green" />
          <StatCard title="معاملات امروز" value={stats.total_trades_today} icon={Activity} color="yellow" />
          <StatCard title="سلامت سیستم"  value={stats.system_health} icon={Shield} color={stats.system_health==="healthy"?"green":stats.system_health==="degraded"?"yellow":"red"} />
        </div>
      )}
      {security && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="text-sm font-semibold text-white mb-4">متریک‌های امنیتی</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            {[{ل:"ورود ناموفق ۲۴h",v:security.failed_logins_24h,d:security.failed_logins_24h>10},{ل:"IP مسدود",v:security.blocked_ips,d:false},{ل:"جلسات فعال",v:security.active_sessions,d:false},{ل:"نقض لایسنس",v:security.license_violations,d:security.license_violations>0}]
              .map(({l,v,d}) => (
                <div key={l} className={`rounded-lg p-3 ${d ? "bg-red-500/10 border border-red-500/20" : "bg-gray-800"}`}>
                  <p className="text-xs text-gray-400">{l}</p><p className={`text-lg font-bold mt-1 ${d ? "text-red-400" : "text-white"}`}>{v}</p>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
