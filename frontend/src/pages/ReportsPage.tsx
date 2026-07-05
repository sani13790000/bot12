// frontend/src/pages/ReportsPage.tsx
import React, { useState } from "react";
import { FileText, Download, Calendar, TrendingUp, BarChart2, DollarSign } from "lucide-react";
import { format, subDays } from "date-fns";
import { dashboardApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import { StatCard } from "@/components/common/StatCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const PERIODS = [
  { label: "امروز",   days: 1  },
  { label: "۷ روز",  days: 7  },
  { label: "۳۰ روز", days: 30 },
  { label: "۹۰ روز", days: 90 },
];

export default function ReportsPage() {
  const [period, setPeriod] = useState(30);
  const [downloading, setDownloading] = useState(false);
  const { data, isLoading, error, refetch } = useApi(dashboardApi.getStats);

  if (isLoading) return <LoadingSpinner text="در حال بارگذاری گزارش‌ها..." />;
  if (error)     return <div className="p-6"><ErrorAlert message={error} onRetry={refetch} /></div>;

  const from = format(subDays(new Date(), period), "yyyy/MM/dd");
  const to   = format(new Date(), "yyyy/MM/dd");

  const handleDownloadPDF = async () => {
    setDownloading(true);
    try {
      const token = localStorage.getItem("access_token") ?? "";
      const res = await fetch(
        `${API_BASE}/reports/performance?period=${period}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `report_${period}d_${format(new Date(), "yyyyMMdd")}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("PDF download failed:", err);
      alert("دانلود ناموفق بود — لطفاً دوباره تلاش کنید");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <FileText size={20} className="text-blue-400" /> گزارش‌ها
          </h1>
          <p className="text-sm text-gray-400 mt-1">گزارش‌های دوره‌ای عملکرد</p>
        </div>
        <button
          onClick={handleDownloadPDF}
          disabled={downloading}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
        >
          <Download size={15} />
          {downloading ? "در حال دانلود..." : "دانلود PDF"}
        </button>
      </div>
      <div className="flex gap-2">
        {PERIODS.map(p => (
          <button key={p.days} onClick={() => setPeriod(p.days)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              period === p.days ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"
            }`}>
            {p.label}
          </button>
        ))}
      </div>
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 text-sm text-gray-400 flex items-center gap-2">
        <Calendar size={15} className="text-blue-400" />
        دوره گزارش: <span className="text-white font-mono">{from}</span> تا <span className="text-white font-mono">{to}</span>
      </div>
      {data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard title="کل معاملات"   value={data.total_trades}                    icon={<BarChart2 size={16}/>} color="accent" />
            <StatCard title="نرخ موفقیت"   value={`${data.win_rate?.toFixed(1)}%`}      icon={<TrendingUp size={16}/>} color="green" />
            <StatCard title="سود خالص"     value={`$${data.daily_pnl?.toFixed(2)}`}    icon={<DollarSign size={16}/>} color="purple" />
            <StatCard title="Profit Factor" value={data.profit_factor?.toFixed(2)}      icon={<TrendingUp size={16}/>} color="gold" />
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-800">
              <h2 className="text-sm font-semibold text-white">خلاصه عملکرد</h2>
            </div>
            <table className="w-full text-sm">
              <tbody className="divide-y divide-gray-800">
                {[
                  ["کل معاملات",   data.total_trades],
                  ["نرخ موفقیت",   `${data.win_rate?.toFixed(2)}%`],
                  ["Profit Factor", data.profit_factor?.toFixed(2)],
                  ["Sharpe Ratio",  data.sharpe_ratio?.toFixed(2)],
                  ["Max Drawdown",  `${data.drawdown?.toFixed(2)}%`],
                  ["موجودی فعلی",  `$${data.equity?.toLocaleString()}`],
                ].map(([label, value]) => (
                  <tr key={String(label)} className="hover:bg-gray-800/30">
                    <td className="px-5 py-3 text-gray-400">{label}</td>
                    <td className="px-5 py-3 text-white font-mono text-right">{String(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
