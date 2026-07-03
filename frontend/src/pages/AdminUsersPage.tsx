// frontend/src/pages/AdminUsersPage.tsx
import React, { useState } from "react";
import { Users, Search, Loader2 } from "lucide-react";
import { adminApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import Badge from "@/components/Badge";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

export default function AdminUsersPage() {
  const { data, isLoading, error, refetch } = useApi(() => adminApi.listUsers(1));
  const [search, setSearch] = useState("");
  const filtered = (data?.items ?? []).filter(u => u.email.includes(search) || u.full_name.includes(search));

  return (
    <div className="p-6 space-y-6">
      <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><Users size={20} className="text-blue-400" /> مدیریت کاربران</h1><p className="text-sm text-gray-400 mt-1">{data?.total ?? 0} کاربر کل</p></div>
      <div className="relative"><Search size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="جستجو با ایمیل یا نام..."
          className="w-full rounded-lg bg-gray-800 border border-gray-700 pr-9 pl-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500" />
      </div>
      {isLoading && <LoadingSpinner text="در حال بارگذاری..." />}
      {error    && <ErrorAlert message={error} onRetry={refetch} />}
      {data && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-gray-800 text-gray-400 text-xs">{["نام","ایمیل","نقش","وضعیت","عملیات"].map(h => <th key={h} className="text-right px-4 py-3 font-medium">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-gray-800">
              {filtered.map(user => {
                const [loading, setLoading] = React.useState(false);
                const toggleActive = async () => {
                  setLoading(true);
                  try { await adminApi.updateUser(user.id, { is_active: !user.is_active }); refetch(); }
                  catch (e) { alert(e instanceof Error ? e.message : "خطا"); }
                  finally { setLoading(false); }
                };
                const changeRole = async (role: string) => {
                  setLoading(true);
                  try { await adminApi.updateUser(user.id, { role }); refetch(); }
                  catch (e) { alert(e instanceof Error ? e.message : "خطا"); }
                  finally { setLoading(false); }
                };
                return (
                  <tr key={user.id} className="hover:bg-gray-800/50 transition-colors">
                    <td className="px-4 py-3 text-white font-medium">{user.full_name}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{user.email}</td>
                    <td className="px-4 py-3"><select value={user.role} onChange={e => changeRole(e.target.value)} disabled={loading}
                      className="rounded-lg bg-gray-800 border border-gray-700 px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50">
                      {["USER","ADMIN","VIEWER"].map(r => <option key={r}>{r}</option>)}
                    </select></td>
                    <td className="px-4 py-3"><Badge label={user.is_active?"فعال":"غیرفعال"} color={user.is_active?"green":"red"} /></td>
                    <td className="px-4 py-3">
                      <button onClick={toggleActive} disabled={loading}
                        className={`flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-medium transition-colors ${user.is_active?"bg-red-500/10 text-red-400 hover:bg-red-500/20":"bg-green-500/10 text-green-400 hover:bg-green-500/20"}`}>
                        {loading ? <Loader2 size={12} className="animate-spin" /> : null}
                        {user.is_active?"غیرفعال":"فعال کردن"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length===0 && <div className="text-center py-10 text-gray-500 text-sm">کاربری یافت نشد</div>}
        </div>
      )}
    </div>
  );
}
