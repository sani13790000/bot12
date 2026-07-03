// frontend/src/pages/TradeHistoryPage.tsx
import React, { useState } from "react";
import { History, ChevronLeft, ChevronRight, Search, Filter } from "lucide-react";
import { tradesApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import Badge from "@/components/Badge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

const PAGE_SIZE = 20;

export default function TradeHistoryPage() {
  const [page, setPage]     = useState(1);
  const [search, setSearch] = useState("");
  const [dir, setDir]       = useState<"all" | "buy" | "sell">("all");
  const { data, isLoading, error, refetch } = useApi(() => tradesApi.listClosed(page, PAGE_SIZE));
  if (isLoading) return <LoadingSpinner text="در حال بارگذاری تاریخچه..." />;
  if (error)     return <div className="p-6"><ErrorAlert message={error} onRetry={refetch} /></div>;
  const items = ((data as any)?.items ?? []).filter((t: any) => (!search || t.symbol.toLowerCase().includes(search.toLowerCase())) && (dir === "all" || t.direction === dir));
  const totalPages = Math.ceil(((data as any)?.total ?? 0) / PAGE_SIZE);
  return (
    <div className="p-6 space-y-6">
      <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><History size={20} className="text-gray-400" /> تاریخچه معاملات</h1><p className="text-sm text-gray-400 mt-1">همه معاملات بسته‌شده</p></div>
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1"><Search size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500" /><input value={search} onChange={e => setSearch(e.target.value)} placeholder="جستجو نماد..." className="w-full rounded-lg bg-gray-800 border border-gray-700 pr-9 pl-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500" /></div>
        <div className="flex gap-2 items-center"><Filter size={14} className="text-gray-400" />{(["all", "buy", "sell"] as const).map(d => (<button key={d} onClick={() => setDir(d)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${dir === d ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}>{d === "all" ? "همه" : d === "buy" ? "خرید" : "فروش"}</button>))}</div>
      </div>
      <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-gray-800 text-gray-400 text-xs">{["نماد","جهت","حجم","ورود","خروج","SL","TP","P&L","وضعیت","تاریخ"].map(h => <th key={h} className="text-right px-3 py-3 font-medium">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-gray-800">
            {items.length === 0 ? (<tr><td colSpan={10} className="text-center py-10 text-gray-500">هیچ معامله‌ای یافت نشد</td></tr>) : items.map((t: any) => { const pnl = t.pnl ?? 0; return (<tr key={t.id} className="hover:bg-gray-800/50 transition-colors"><td className="px-3 py-3 font-mono text-white font-medium">{t.symbol}</td><td className="px-3 py-3"><Badge label={t.direction === "buy" ? "خرید" : "فروش"} color={t.direction === "buy" ? "green" : "red"} /></td><td className="px-3 py-3 text-gray-300">{t.lot_size}</td><td className="px-3 py-3 font-mono text-gray-300 text-xs">{t.entry_price?.toFixed(5)}</td><td className="px-3 py-3 font-mono text-gray-300 text-xs">{t.close_price?.toFixed(5) ?? "—"}</td><td className="px-3 py-3 font-mono text-red-400 text-xs">{t.stop_loss?.toFixed(5) ?? "—"}</td><td className="px-3 py-3 font-mono text-green-400 text-xs">{t.take_profit?.toFixed(5) ?? "—"}</td><td className={`px-3 py-3 font-mono font-bold ${pnl >= 0 ? "text-green-400" : "text-red-400"}`}>{pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}</td><td className="px-3 py-3"><Badge label={t.status} color={t.status === "closed" ? "gray" : "blue"} /></td><td className="px-3 py-3 text-xs text-gray-500">{t.closed_at ? new Date(t.closed_at).toLocaleDateString("fa-IR") : "—"}</td></tr>); })}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (<div className="flex items-center justify-between"><p className="text-xs text-gray-400">صفحه {page} از {totalPages}</p><div className="flex gap-2"><button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-white"><ChevronRight size={16} /></button><button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-white"><ChevronLeft size={16} /></button></div></div>)}
    </div>
  );
}
