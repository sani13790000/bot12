// frontend/src/pages/TradesPage.tsx
import React, { useState } from "react";
import { Plus, X, Loader2 } from "lucide-react";
import { tradesApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import Badge from "@/components/Badge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

export default function TradesPage() {
  const { data, isLoading, error, refetch } = useApi(() => tradesApi.listClosed(1, 50).then(r => r.items));
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-xl font-bold text-white">معاملات</h1><p className="text-sm text-gray-400 mt-1">تاریخچه همه معاملات</p></div>
        <button onClick={() => setShowForm(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium text-white transition-colors">
          <Plus size={16} /> معامله جدید
        </button>
      </div>
      {showForm && (
        <div className="rounded-xl border border-gray-700 bg-gray-900 p-5">
          <h2 className="text-sm font-semibold text-white mb-4">باز کردن معامله جدید</h2>
          <NewTradeForm onClose={() => setShowForm(false)} onSuccess={refetch} />
        </div>
      )}
      {isLoading && <LoadingSpinner text="در حال بارگذاری معاملات..." />}
      {error    && <ErrorAlert message={error} onRetry={refetch} />}
      {data && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-gray-800 text-gray-400 text-xs">
              {["نماد","جهت","حجم","ورود","خروج","SL","TP","P&L","وضعیت"].map(h => <th key={h} className="text-right px-4 py-3 font-medium">{h}</th>)}
            </tr></thead>
            <tbody className="divide-y divide-gray-800">
              {data.map(trade => {
                const pnl = trade.pnl ?? 0;
                const [closing, setClosing] = React.useState(false);
                const handleClose = async () => {
                  if (!confirm("آیا از بستن این معامله مطمئن هستید?")) return;
                  setClosing(true);
                  try { await tradesApi.close(trade.id); refetch(); }
                  catch (e) { alert(e instanceof Error ? e.message : "خطا"); }
                  finally { setClosing(false); }
                };
                return (
                  <tr key={trade.id} className="hover:bg-gray-800/50 transition-colors">
                    <td className="px-4 py-3 font-mono text-white">{trade.symbol}</td>
                    <td className="px-4 py-3"><Badge label={trade.direction === "buy" ? "خرید" : "فروش"} color={trade.direction === "buy" ? "green" : "red"} /></td>
                    <td className="px-4 py-3 text-gray-300">{trade.lot_size}</td>
                    <td className="px-4 py-3 font-mono text-gray-300">{trade.entry_price.toFixed(5)}</td>
                    <td className="px-4 py-3 font-mono text-gray-300">{trade.close_price?.toFixed(5) ?? "—"}</td>
                    <td className="px-4 py-3 font-mono text-red-400">{trade.stop_loss.toFixed(5)}</td>
                    <td className="px-4 py-3 font-mono text-green-400">{trade.take_profit.toFixed(5)}</td>
                    <td className={`px-4 py-3 font-mono font-medium ${pnl >= 0 ? "text-green-400" : "text-red-400"}`}>{pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Badge label={trade.status === "open" ? "باز" : trade.status === "closed" ? "بسته" : trade.status} color={trade.status === "open" ? "green" : trade.status === "closed" ? "gray" : "yellow"} />
                        {trade.status === "open" && (
                          <button onClick={handleClose} disabled={closing} className="p-1 rounded hover:bg-red-500/10 text-gray-400 hover:text-red-400 transition-colors">
                            {closing ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {data.length === 0 && <div className="text-center py-12 text-gray-500 text-sm">معامله‌ای یافت نشد</div>}
        </div>
      )}
    </div>
  );
}

function NewTradeForm({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({ symbol: "EURUSD", direction: "buy", lot_size: 0.01, stop_loss: 0, take_profit: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState("");
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(p => ({ ...p, [k]: ["lot_size","stop_loss","take_profit"].includes(k) ? parseFloat(e.target.value) : e.target.value }));
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(""); setLoading(true);
    try { await tradesApi.open(form as Parameters<typeof tradesApi.open>[0]); onSuccess(); onClose(); }
    catch (err) { setError(err instanceof Error ? err.message : "خطا"); }
    finally { setLoading(false); }
  };
  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-2 md:grid-cols-3 gap-4">
      {[{k:"symbol",l:"نماد",t:"text",p:"EURUSD"},{k:"stop_loss",l:"Stop Loss",t:"number",p:"1.09000"},{k:"take_profit",l:"Take Profit",t:"number",p:"1.11000"},{k:"lot_size",l:"حجم (Lot)",t:"number",p:"0.01"}].map(({k,l,t,p}) => (
        <div key={k}><label className="block text-xs text-gray-400 mb-1">{l}</label>
          <input type={t} value={(form as Record<string,unknown>)[k] as string} onChange={set(k)} placeholder={p} step="any" required
            className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" /></div>
      ))}
      <div><label className="block text-xs text-gray-400 mb-1">جهت</label>
        <select value={form.direction} onChange={set("direction")} className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">
          <option value="buy">خرید (Buy)</option><option value="sell">فروش (Sell)</option>
        </select></div>
      {error && <div className="col-span-full text-xs text-red-400 bg-red-500/10 rounded-lg px-3 py-2">{error}</div>}
      <div className="col-span-full flex gap-3">
        <button type="submit" disabled={loading} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium text-white disabled:opacity-50 transition-colors">
          {loading ? <Loader2 size={14} className="animate-spin" /> : null}باز کردن معامله
        </button>
        <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg border border-gray-700 text-sm text-gray-400 hover:text-white hover:border-gray-500 transition-colors">لغو</button>
      </div>
    </form>
  );
}
