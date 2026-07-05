// frontend/src/pages/PortfolioPage.tsx
// BUG-T5 FIX: was stub showing 'در حال توسعه'
// Now fetches real data from GET /portfolio/summary and renders live positions
import React, { useEffect, useState } from "react";
import { Briefcase, TrendingUp, TrendingDown, RefreshCw, AlertCircle } from "lucide-react";
import { apiFetch } from "@/utils/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

interface PortfolioSummary {
  open_positions: number;
  total_pnl:      number;
  total_exposure: number;
  equity:         number;
  free_margin:    number;
  margin_level:   number;
  risk_level:     string;
  drawdown_pct:   number;
}

interface Position {
  symbol:      string;
  direction:   string;
  volume:      number;
  entry_price: number;
  pnl:         number;
}

export default function PortfolioPage() {
  const [summary,     setSummary]     = useState<PortfolioSummary | null>(null);
  const [positions,   setPositions]   = useState<Position[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>("");

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const [sumRes, posRes] = await Promise.all([
        apiFetch<{ ok: boolean; summary: PortfolioSummary }>("/portfolio/summary"),
        apiFetch<{ ok: boolean; positions: Position[]; count: number }>("/portfolio/positions"),
      ]);
      if (sumRes.ok) setSummary(sumRes.summary);
      if (posRes.ok) setPositions(posRes.positions);
      setLastUpdated(new Date().toLocaleTimeString("fa-IR"));
    } catch (e: any) {
      setError(e.message ?? "خطا در دریافت اطلاعات");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) return <LoadingSpinner text="در حال بارگذاری پورتفولیو..." />;
  if (error)   return <div className="p-6"><ErrorAlert message={error} onRetry={load} /></div>;

  const pnlColor = (v: number) => v >= 0 ? "text-green-400" : "text-red-400";
  const riskColor = summary?.risk_level === "LOW" ? "text-green-400" :
                    summary?.risk_level === "MEDIUM" ? "text-yellow-400" : "text-red-400";

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Briefcase size={20} className="text-blue-400" /> پورتفولیو
          </h1>
          <p className="text-sm text-gray-400 mt-1">مدیریت سبد دارایی‌ها</p>
        </div>
        <button onClick={load} className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition">
          <RefreshCw size={15} /> به‌روزرسانی — {lastUpdated}
        </button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <p className="text-xs text-gray-400">موقعیت‌های باز</p>
            <p className="text-2xl font-bold text-white mt-1">{summary.open_positions}</p>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <p className="text-xs text-gray-400">سود/زیان کل</p>
            <p className={`text-2xl font-bold mt-1 ${pnlColor(summary.total_pnl)}`}>
              {summary.total_pnl >= 0 ? "+" : ""}{summary.total_pnl.toFixed(2)}
            </p>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <p className="text-xs text-gray-400">ارزش حساب</p>
            <p className="text-2xl font-bold text-white mt-1">{summary.equity.toFixed(2)}</p>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <p className="text-xs text-gray-400">سطح ریسک</p>
            <p className={`text-2xl font-bold mt-1 ${riskColor}`}>{summary.risk_level}</p>
          </div>
        </div>
      )}

      {/* Positions Table */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="text-sm font-semibold text-white mb-4">موقعیت‌های باز ({positions.length})</h2>
        {positions.length === 0 ? (
          <div className="text-center py-8">
            <AlertCircle size={32} className="mx-auto mb-2 text-gray-600" />
            <p className="text-gray-400 text-sm">هیچ موقعیت بازی وجود ندارد</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-gray-800">
                  <th className="text-right pb-3 pr-2">نماد</th>
                  <th className="text-right pb-3">جهت</th>
                  <th className="text-right pb-3">حجم</th>
                  <th className="text-right pb-3">قیمت ورود</th>
                  <th className="text-right pb-3">سود/زیان</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => (
                  <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="py-2 pr-2 font-mono text-white">{p.symbol}</td>
                    <td className="py-2">
                      {p.direction === "BUY"
                        ? <span className="flex items-center gap-1 text-green-400"><TrendingUp size={12} /> BUY</span>
                        : <span className="flex items-center gap-1 text-red-400"><TrendingDown size={12} /> SELL</span>}
                    </td>
                    <td className="py-2 text-gray-300">{p.volume}</td>
                    <td className="py-2 font-mono text-gray-300">{p.entry_price}</td>
                    <td className={`py-2 font-mono font-medium ${pnlColor(p.pnl)}`}>
                      {p.pnl >= 0 ? "+" : ""}{p.pnl.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
