// frontend/src/pages/EquityCurvePage.tsx
import React from "react";
import { TrendingUp } from "lucide-react";
import { dashboardApi } from "@/utils/api";
import { usePoll } from "@/hooks/useApi";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { format } from "date-fns";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

export default function EquityCurvePage() {
  const { data, isLoading, error, refetch } = usePoll(() => dashboardApi.getEquity(90), 60_000);
  return (
    <div className="p-6 space-y-6">
      <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><TrendingUp size={20} className="text-green-400" /> منحنی سرمایه</h1><p className="text-sm text-gray-400 mt-1">نمودار رشد سرمایه ۹۰ روز</p></div>
      {isLoading && <LoadingSpinner text="در حال بارگذاری..." />}
      {error    && <ErrorAlert message={error} onRetry={refetch} />}
      {data && data.length>0 && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={data}>
              <defs><linearGradient id="eg2" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#22c55e" stopOpacity={0.3}/><stop offset="95%" stopColor="#22c55e" stopOpacity={0}/></linearGradient></defs>
              <XAxis dataKey="timestamp" tickFormatter={v=>format(new Date(v),"dd/MM")} tick={{fill:"#6b7280",fontSize:11}} axisLine={false} tickLine={false}/>
              <YAxis tick={{fill:"#6b7280",fontSize:11}} axisLine={false} tickLine={false} tickFormatter={v=>`$${v.toLocaleString()}`}/>
              <Tooltip contentStyle={{background:"#111827",border:"1px solid #374151",borderRadius:8}} formatter={(v:number)=>[`$${v.toLocaleString()}`,"سرمایه"]} labelFormatter={v=>format(new Date(v as string),"yyyy/MM/dd")}/>
              <Area type="monotone" dataKey="equity" stroke="#22c55e" strokeWidth={2} fill="url(#eg2)"/>
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
