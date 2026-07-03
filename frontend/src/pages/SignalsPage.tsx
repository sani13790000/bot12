// frontend/src/pages/SignalsPage.tsx
import React, { useState } from "react";
import { Zap, Check, X, Loader2 } from "lucide-react";
import { signalsApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import Badge from "@/components/Badge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

const STATUS_COLORS: Record<string, "yellow"|"green"|"red"|"blue"|"gray"> = { pending:"yellow", approved:"green", rejected:"red", executed:"blue", expired:"gray" };
const STATUS_LABELS: Record<string, string> = { pending:"در انتظار", approved:"تأیید شده", rejected:"رد شده", executed:"اجرا شده", expired:"منقضی" };

export default function SignalsPage() {
  const [filter, setFilter] = useState("pending");
  const { data, isLoading, error, refetch } = useApi(() => signalsApi.list(filter || undefined), [filter]);

  return (
    <div className="p-6 space-y-6">
      <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><Zap size={20} className="text-yellow-400" /> سیگنال‌ها</h1><p className="text-sm text-gray-400 mt-1">سیگنال‌های تولید شده توسط AI</p></div>
      <div className="flex gap-2 flex-wrap">
        {Object.entries(STATUS_LABELS).map(([val, label]) => (
          <button key={val} onClick={() => setFilter(val)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${filter===val ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}>{label}</button>
        ))}
        <button onClick={() => setFilter("")} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${filter==="" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"}`}>همه</button>
      </div>
      {isLoading && <LoadingSpinner text="در حال بارگذاری سیگنال‌ها..." />}
      {error    && <ErrorAlert message={error} onRetry={refetch} />}
      <div className="space-y-3">
        {(data ?? []).map(signal => {
          const [loading, setLoading] = React.useState<"approve"|"reject"|null>(null);
          const act = async (type: "approve"|"reject") => {
            setLoading(type);
            try { type==="approve" ? await signalsApi.approve(signal.id) : await signalsApi.reject(signal.id); refetch(); }
            catch (e) { alert(e instanceof Error ? e.message : "خطا"); }
            finally { setLoading(null); }
          };
          const rr = signal.take_profit && signal.stop_loss && signal.entry_price
            ? Math.abs(signal.take_profit - signal.entry_price) / Math.abs(signal.entry_price - signal.stop_loss) : null;
          return (
            <div key={signal.id} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-3">
                  <Badge label={signal.direction==="buy" ? "خرید" : "فروش"} color={signal.direction==="buy" ? "green" : "red"} />
                  <span className="font-bold text-white font-mono">{signal.symbol}</span>
                  <Badge label={STATUS_LABELS[signal.status] ?? signal.status} color={STATUS_COLORS[signal.status] ?? "gray"} />
                  <Badge label={`${(signal.confidence*100).toFixed(0)}%`} color={signal.confidence>=0.7?"green":signal.confidence>=0.5?"yellow":"red"} />
                </div>
                {signal.status==="pending" && (
                  <div className="flex gap-2">
                    <button onClick={() => act("approve")} disabled={!!loading} className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-green-600 hover:bg-green-500 text-xs text-white font-medium disabled:opacity-50 transition-colors">
                      {loading==="approve" ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}تأیید
                    </button>
                    <button onClick={() => act("reject")} disabled={!!loading} className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-xs text-white font-medium disabled:opacity-50 transition-colors">
                      {loading==="reject" ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />}رد
                    </button>
                  </div>
                )}
              </div>
              <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mt-4 text-xs">
                {[{ل:"ورود",v:signal.entry_price.toFixed(5)},{ل:"SL",v:signal.stop_loss.toFixed(5),c:"text-red-400"},{ل:"TP",v:signal.take_profit.toFixed(5),c:"text-green-400"},{l:"R:R",v:rr?`1:${rr.toFixed(2)}`:"—"},{ل:"حجم",v:signal.lot_size},{ل:"منبع",v:signal.source}]
                  .map((item, i) => <div key={i}><p className="text-gray-500">{(item as Record<string,unknown>)['ل'] as string ?? (item as Record<string,unknown>)['l'] as string}</p><p className={`font-mono font-medium mt-0.5 ${(item as Record<string,unknown>)['c'] as string ?? "text-gray-300"}`}>{(item as Record<string,unknown>)['v'] as string}</p></div>)}
              </div>
              {signal.reasoning && <p className="mt-3 text-xs text-gray-400 border-t border-gray-800 pt-3">{signal.reasoning}</p>}
            </div>
          );
        })}
        {data?.length===0 && !isLoading && <div className="text-center py-12 text-gray-500 text-sm">سیگنالی یافت نشد</div>}
      </div>
    </div>
  );
}
