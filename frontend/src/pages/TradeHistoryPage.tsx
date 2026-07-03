// frontend/src/pages/TradeHistoryPage.tsx
import React from "react";
import { History } from "lucide-react";
import { tradesApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import Badge from "@/components/Badge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

export default function TradeHistoryPage() {
  const { data, isLoading, error, refetch } = useApi(() => tradesApi.listClosed(1, 100).then(r => r.items));
  return (
    <div className="p-6 space-y-6">
      <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><History size={20} className="text-gray-400" /> تاریخچه معاملات</h1><p className="text-sm text-gray-400 mt-1">همه معاملات بسته شده</p></div>
      {isLoading && <LoadingSpinner text="در حال بارگذاری..." />}
      {error    && <ErrorAlert message={error} onRetry={refetch} />}
      {data && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-gray-800 text-gray-400 text-xs">{["نماد","جهت","حجم","ورود","خروج","P&L","وضعیت"].map(h=><th key={h} className="text-right px-4 py-3 font-medium">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-gray-800">
              {data.map(t => {
                const pnl = t.pnl ?? 0;
                return (<tr key={t.id} className="hover:bg-gray-800/50 transition-colors">
                  <td className="px-4 py-3 font-mono text-white">{t.symbol}</td>
                  <td className="px-4 py-3"><Badge label={t.direction==="buy"?"خرید":"فروش"} color={t.direction==="buy"?"green":"red"} /></td>
                  <td className="px-4 py-3 text-gray-300">{t.lot_size}</td>
                  <td className="px-4 py-3 font-mono text-gray-300">{t.entry_price.toFixed(5)}</td>
                  <td className="px-4 py-3 font-mono text-gray-300">{t.close_price?.toFixed(5)??"—"}</td>
                  <td className={`px-4 py-3 font-mono font-medium ${pnl>=0?"text-green-400":"text-red-400"}`}>{pnl>=0?"+":""}{pnl.toFixed(2)}</td>
                  <td className="px-4 py-3"><Badge label="بسته" color="gray" /></td>
                </tr>);
              })}
            </tbody>
          </table>
          {data.length===0 && <div className="text-center py-10 text-gray-500 text-sm">تاریخچه‌ای یافت نشد</div>}
        </div>
      )}
    </div>
  );
}
