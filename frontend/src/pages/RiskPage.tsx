// frontend/src/pages/RiskPage.tsx
import React from "react";
import { Shield } from "lucide-react";
import { dashboardApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import StatCard from "@/components/StatCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

export default function RiskPage() {
  const { data, isLoading, error, refetch } = useApi(dashboardApi.getStats);
  return (
    <div className="p-6 space-y-6">
      <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><Shield size={20} className="text-red-400" /> مدیریت ریسک</h1><p className="text-sm text-gray-400 mt-1">تنظیمات و محدودیت‌های ریسک</p></div>
      {isLoading && <LoadingSpinner text="در حال بارگذاری..." />}
      {error    && <ErrorAlert message={error} onRetry={refetch} />}
      {data && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <StatCard title="Drawdown" value={`${data.drawdown.toFixed(2)}%`} icon={Shield} color={data.drawdown<10?"green":data.drawdown<20?"yellow":"red"} />
          <StatCard title="Sharpe Ratio" value={data.sharpe_ratio.toFixed(2)} icon={Shield} color={data.sharpe_ratio>1?"green":data.sharpe_ratio>0?"yellow":"red"} />
          <StatCard title="Profit Factor" value={data.profit_factor.toFixed(2)} icon={Shield} color={data.profit_factor>1.5?"green":data.profit_factor>1?"yellow":"red"} />
        </div>
      )}
    </div>
  );
}
