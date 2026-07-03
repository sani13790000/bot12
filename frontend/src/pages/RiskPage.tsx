// frontend/src/pages/RiskPage.tsx
import React from "react";
import { Shield, AlertTriangle, TrendingDown, Lock, BarChart2, Target } from "lucide-react";
import { RadialBarChart, RadialBar, ResponsiveContainer, Tooltip } from "recharts";
import { dashboardApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import StatCard from "@/components/StatCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

export default function RiskPage() {
  const { data, isLoading, error, refetch } = useApi(dashboardApi.getStats);

  if (isLoading) return <LoadingSpinner text="در حال بارگذاری مدیریت ریسک..." />;
  if (error)     return <div className="p-6"><ErrorAlert message={error} onRetry={refetch} /></div>;

  const drawdown = data?.drawdown ?? 0;
  const sharpe   = data?.sharpe_ratio ?? 0;
  const pf       = data?.profit_factor ?? 0;
  const winRate  = data?.win_rate ?? 0;

  const ddColor   = drawdown < 10 ? "text-green-400" : drawdown < 20 ? "text-yellow-400" : "text-red-400";
  const riskLevel = drawdown < 10 ? "پایین" : drawdown < 20 ? "متوسط" : "بالا";
  const riskColor = drawdown < 10 ? "green" : drawdown < 20 ? "yellow" : "red";
  const gaugeData = [{ name: "Drawdown", value: Math.min(drawdown, 30), fill: drawdown < 10 ? "#22c55e" : drawdown < 20 ? "#eab308" : "#ef4444" }];

  const rules = [
    { label: "حداکثر Drawdown",    limit: "20%",  current: `${drawdown.toFixed(2)}%`, ok: drawdown < 20 },
    { label: "حداقل Sharpe",        limit: "0.5",  current: sharpe.toFixed(2),         ok: sharpe > 0.5 },
    { label: "حداقل Profit Factor",  limit: "1.0",  current: pf.toFixed(2),             ok: pf > 1.0 },
    { label: "حداقل Win Rate",       limit: "50%",  current: `${winRate.toFixed(1)}%`,  ok: winRate > 50 },
  ];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Shield size={20} className="text-red-400" /> مدیریت ریسک
        </h1>
        <p className="text-sm text-gray-400 mt-1">وضعیت ریسک و محدودیت‌های حساب</p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="سطح ریسک" value={riskLevel} icon={Shield} color={riskColor} />
        <StatCard title="Max Drawdown" value={`${drawdown.toFixed(2)}%`} icon={TrendingDown} color={riskColor} />
        <StatCard title="Sharpe Ratio" value={sharpe.toFixed(2)} icon={Target} color={sharpe > 1 ? "green" : sharpe > 0 ? "yellow" : "red"} />
        <StatCard title="Profit Factor" value={pf.toFixed(2)} icon={BarChart2} color={pf > 1.5 ? "green" : pf > 1 ? "yellow" : "red"} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="text-sm font-semibold text-white mb-1">Drawdown Gauge</h2>
          <p className={`text-2xl font-bold mb-4 ${ddColor}`}>{drawdown.toFixed(2)}%</p>
          <ResponsiveContainer width="100%" height={160}>
            <RadialBarChart cx="50%" cy="80%" innerRadius="60%" outerRadius="90%" startAngle={180} endAngle={0} data={gaugeData}>
              <RadialBar dataKey="value" cornerRadius={8} background={{ fill: "#1f2937" }} />
              <Tooltip formatter={(v: number) => [`${v.toFixed(1)}%`, "Drawdown"]} />
            </RadialBarChart>
          </ResponsiveContainer>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="text-sm font-semibold text-white mb-4">قوانین ریسک</h2>
          <div className="space-y-3">
            {rules.map(r => (
              <div key={r.label} className="flex items-center justify-between p-3 rounded-lg bg-gray-800/50">
                <div className="flex items-center gap-2">
                  {r.ok ? <Shield size={15} className="text-green-400" /> : <AlertTriangle size={15} className="text-red-400" />}
                  <span className="text-sm text-gray-300">{r.label}</span>
                </div>
                <div className="text-right">
                  <div className={`text-sm font-mono font-medium ${r.ok ? "text-green-400" : "text-red-400"}`}>{r.current}</div>
                  <div className="text-xs text-gray-500">حد: {r.limit}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="rounded-xl border border-red-900/40 bg-red-950/20 p-4">
        <div className="flex items-start gap-3">
          <Lock size={16} className="text-red-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-400">Kill Switch</p>
            <p className="text-xs text-gray-400 mt-1">در صورت رسیدن Drawdown به ۲۰٬ سیستم به‌صورت خودکار همه معاملات را می‌بندد.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
