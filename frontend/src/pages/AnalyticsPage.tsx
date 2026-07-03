// frontend/src/pages/AnalyticsPage.tsx
import React from "react";
import { LineChart, TrendingUp, Target, BarChart2, Award } from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { dashboardApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import StatCard from "@/components/StatCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

export default function AnalyticsPage() {
  const { data, isLoading, error, refetch } = useApi(dashboardApi.getStats);

  if (isLoading) return <LoadingSpinner text="در حال بارگذاری آنالیتیکس..." />;
  if (error)     return <div className="p-6"><ErrorAlert message={error} onRetry={refetch} /></div>;

  const monthlyData = [
    { month: "فروردین", profit: 1200, loss: -400, trades: 42 },
    { month: "اردیبهشت", profit: 1800, loss: -600, trades: 58 },
    { month: "خرداد", profit: 900, loss: -300, trades: 35 },
    { month: "تیر", profit: 2100, loss: -500, trades: 67 },
    { month: "مرداد", profit: 1600, loss: -700, trades: 51 },
    { month: "شهریور", profit: 2400, loss: -400, trades: 73 },
  ];

  const winrateData = [
    { session: "آسیا", win: 62, lose: 38 },
    { session: "لندن", win: 71, lose: 29 },
    { session: "نیویورک", win: 68, lose: 32 },
    { session: "اورلپ", win: 74, lose: 26 },
  ];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <LineChart size={20} className="text-blue-400" /> آنالیتیکس
        </h1>
        <p className="text-sm text-gray-400 mt-1">تحلیل آماری عملکرد معاملاتی</p>
      </div>
      {data && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="نرخ موفقیت" value={`${data.win_rate?.toFixed(1) ?? 0}%`} icon={Target} color="green" />
          <StatCard title="Sharpe Ratio" value={data.sharpe_ratio?.toFixed(2) ?? "—"} icon={Award} color="blue" />
          <StatCard title="Profit Factor" value={data.profit_factor?.toFixed(2) ?? "—"} icon={TrendingUp} color="purple" />
          <StatCard title="کل معاملات" value={data.total_trades ?? 0} icon={BarChart2} color="yellow" />
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="text-sm font-semibold text-white mb-4">سود/زیان ماهانه</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={monthlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="month" tick={{ fill: "#9ca3af", fontSize: 11 }} />
              <YAxis tick={{ fill: "#9ca3af", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 8 }} />
              <Legend />
              <Bar dataKey="profit" name="سود" fill="#22c55e" radius={[4, 4, 0, 0]} />
              <Bar dataKey="loss" name="زیان" fill="#ef4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="text-sm font-semibold text-white mb-4">نرخ موفقیت به تفکیک سشن</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={winrateData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis type="number" tick={{ fill: "#9ca3af", fontSize: 11 }} domain={[0, 100]} />
              <YAxis type="category" dataKey="session" tick={{ fill: "#9ca3af", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 8 }} />
              <Bar dataKey="win" name="برد%" fill="#3b82f6" radius={[0, 4, 4, 0]} />
              <Bar dataKey="lose" name="باخت%" fill="#6b7280" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="text-sm font-semibold text-white mb-4">تعداد معاملات ماهانه</h2>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={monthlyData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="month" tick={{ fill: "#9ca3af", fontSize: 11 }} />
            <YAxis tick={{ fill: "#9ca3af", fontSize: 11 }} />
            <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 8 }} />
            <Area type="monotone" dataKey="trades" name="تعداد معاملات" stroke="#8b5cf6" fill="#8b5cf620" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
