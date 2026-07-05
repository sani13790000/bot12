// frontend/src/pages/AdminDashboardPage.tsx
// BUG-W2 fix: StatCard import — named import from correct path
// BEFORE: import StatCard from "@/components/StatCard"  (default import, wrong path -> build fail)
// AFTER:  import { StatCard } from "@/components/common/StatCard"  (named export, correct path)
import React, { useState } from "react";
import { Shield, Users, Activity, AlertTriangle, Power, Loader2 } from "lucide-react";
import { adminApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import { StatCard } from "@/components/common/StatCard";
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
          <StatCard title="کل کاربران"   value={stats.total_users}        icon={<Users size={16} />}    color="accent" />
          <StatCard title="کاربران فعال" value={stats.active_users}       icon={<Activity size={16} />} color="green" />
          <StatCard title="معاملات امروز" value={stats.total_trades_today} icon={<Activity size={16} />} color="gold" />
          <StatCard title="سلامت سیستم"  value={stats.system_health} icon={<Shield size={16} />} color={stats.system_health==="healthy"?"green":stats.system_health==="degraded"?"gold":"red"} />
        </div>
      )}
      {security && (
        <div className="rounded-xl border border-[#1e2d3d] bg-[#0d1f2d] p-4">
          <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2"><Shield size={16} className="text-purple-400" /> وضعیت امنیت</h2>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            <StatCard title="تهدیدات شناسایی‌شده" value={security.threats_detected ?? 0} icon={<AlertTriangle size={16} />} color="red" />
            <StatCard title="IP مسدودشده"          value={security.ips_blocked ?? 0}      icon={<Shield size={16} />}        color="purple" />
            <StatCard title="امتیاز امنیتی"         value={security.security_score ?? 0}   icon={<Activity size={16} />}      color="green" />
          </div>
        </div>
      )}
    </div>
  );
}
