// frontend/src/pages/LiveTradesPage.tsx
import React, { useEffect, useState } from "react";
import { Activity, TrendingUp, TrendingDown, X, Loader2 } from "lucide-react";
import { tradesApi } from "@/utils/api";
import { usePoll } from "@/hooks/useApi";
import { useWebSocket } from "@/contexts/WebSocketContext";
import Badge from "@/components/Badge";
import LoadingSpinner from "@/components/LoadingSpinner";

export default function LiveTradesPage() {
  const { data, isLoading, refetch } = usePoll(tradesApi.listOpen, 5_000);
  const { subscribe, isConnected }   = useWebSocket();
  useEffect(() => subscribe("trade_update", refetch), [subscribe, refetch]);
  const totalPnl = (data ?? []).reduce((s, t) => s + (t.pnl ?? 0), 0);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2"><Activity size={20} className="text-green-400 animate-pulse" />معاملات زنده</h1>
          <p className="text-sm text-gray-400 mt-1">{data?.length ?? 0} معامله باز · {isConnected ? "به‌روزرسانی زنده" : "آفلاین"}</p>
        </div>
        <div className={`text-lg font-bold ${totalPnl >= 0 ? "text-green-400" : "text-red-400"}`}>{totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(2)} $</div>
      </div>
      {isLoading && !data && <LoadingSpinner text="در حال بارگذاری..." />}
      <div className="space-y-3">
        {(data ?? []).map(trade => {
          const pnl = trade.pnl ?? 0;
          const isProfit = pnl >= 0;
          const [closing, setClosing] = React.useState(false);
          const handleClose = async () => {
            if (!confirm("بستن این معامله؟")) return;
            setClosing(true);
            try { await tradesApi.close(trade.id); refetch(); }
            catch (e) { alert(e instanceof Error ? e.message : "خطا"); }
            finally { setClosing(false); }
          };
          return (
            <div key={trade.id} className={`rounded-xl border p-4 flex items-center gap-4 ${isProfit ? "border-green-500/20 bg-green-500/5" : "border-red-500/20 bg-red-500/5"}`}>
              <div className={`p-2 rounded-lg ${isProfit ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                {isProfit ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
              </div>
              <div className="flex-1 grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                <div><p className="text-xs text-gray-400">نماد</p><p className="font-bold text-white font-mono">{trade.symbol}</p></div>
                <div><p className="text-xs text-gray-400">جهت</p><Badge label={trade.direction === "buy" ? "خرید" : "فروش"} color={trade.direction === "buy" ? "green" : "red"} /></div>
                <div><p className="text-xs text-gray-400">ورود</p><p className="font-mono text-gray-300">{trade.entry_price.toFixed(5)}</p></div>
                <div><p className="text-xs text-gray-400">حجم</p><p className="text-gray-300">{trade.lot_size}</p></div>
                <div><p className="text-xs text-gray-400">سود/زیان</p><p className={`font-bold font-mono ${isProfit ? "text-green-400" : "text-red-400"}`}>{isProfit ? "+" : ""}{pnl.toFixed(2)}$</p></div>
              </div>
              <button onClick={handleClose} disabled={closing}
                className="p-2 rounded-lg border border-gray-700 text-gray-400 hover:border-red-500/50 hover:text-red-400 hover:bg-red-500/10 transition-colors">
                {closing ? <Loader2 size={16} className="animate-spin" /> : <X size={16} />}
              </button>
            </div>
          );
        })}
        {data?.length === 0 && (
          <div className="text-center py-16 text-gray-500"><Activity size={40} className="mx-auto mb-3 opacity-30" /><p>هیچ معامله بازی وجود ندارد</p></div>
        )}
      </div>
    </div>
  );
}
