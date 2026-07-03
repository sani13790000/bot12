// frontend/src/pages/ReportsPage.tsx
import React from "react";
import { FileText } from "lucide-react";
import { dashboardApi } from "@/utils/api";
import { useApi } from "@/hooks/useApi";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";

export default function ReportsPage() {
  const { data, isLoading, error, refetch } = useApi(dashboardApi.getStats);
  return (
    <div className="p-6 space-y-6">
      <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><FileText size={20} className="text-blue-400" /> گزارش‌ها</h1><p className="text-sm text-gray-400 mt-1">گزارش‌های دوره‌ای</p></div>
      {isLoading && <LoadingSpinner text="در حال بارگذاری..." />}
      {error    && <ErrorAlert message={error} onRetry={refetch} />}
      {data && (<div className="rounded-xl border border-gray-800 bg-gray-900 p-8 text-center"><FileText size={48} className="mx-auto mb-4 text-gray-600" /><p className="text-gray-400 text-sm">گزارش‌ها — در حال توسعه</p></div>)}
    </div>
  );
}
