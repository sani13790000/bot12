// BUG-S3 FIX: /api/v1/self-learning/stats endpoint now exists (added in self_learning.py)
// Previously called /stats which returned 404 — now matches real endpoint
import React from "react";
import { BookOpen, RefreshCw, CheckCircle, AlertCircle } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";
import { API_BASE_URL } from "@/utils/api";

interface LearningStats {
  total_retraining_cycles: number;
  last_retrain_at: string | null;
  last_retrain_status: string | null;
  next_retrain_in_seconds: number | null;
  model_version: number | null;
  current_auc: number | null;
  current_accuracy: number | null;
  improvement_pct: number | null;
  training_samples: number | null;
  is_running: boolean;
}

const fetchLearningStats = async (): Promise<LearningStats> => {
  // BUG-S3 FIX: was /self-learning/stats (404) — endpoint added in self_learning.py
  const res = await fetch(`${API_BASE_URL}/api/v1/self-learning/stats`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

const StatusBadge = ({ status }: { status: string | null }) => {
  if (!status) return <span className="text-gray-500 text-xs">-</span>;
  const ok = status === "success" || status === "completed";
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${
      ok ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"
    }`}>
      {ok ? <CheckCircle size={12} /> : <AlertCircle size={12} />}
      {status}
    </span>
  );
};

export default function LearningPage() {
  const { data, isLoading, error, refetch } = useApi<LearningStats>(fetchLearningStats);
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <BookOpen size={20} className="text-yellow-400" />
            Learning (AI Model)
          </h1>
          <p className="text-sm text-gray-400 mt-1">XGBoost retraining history</p>
        </div>
        <button onClick={refetch} className="text-gray-400 hover:text-white">
          <RefreshCw size={16} />
        </button>
      </div>
      {isLoading && <LoadingSpinner text="Loading..." />}
      {error && <ErrorAlert message={error} onRetry={refetch} />}
      {data && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 col-span-full flex justify-between">
            <div>
              <p className="text-xs text-gray-500 mb-1">Status</p>
              {data.is_running
                ? <span className="text-yellow-400 text-sm flex items-center gap-1"><RefreshCw size={14} className="animate-spin" /> Retraining...</span>
                : <span className="text-green-400 text-sm">Ready</span>}
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-500">Last retrain</p>
              <StatusBadge status={data.last_retrain_status} />
            </div>
          </div>
          {([
            { label: "Retraining Cycles",  value: data.total_retraining_cycles },
            { label: "Current AUC",        value: data.current_auc       != null ? `${(data.current_auc*100).toFixed(1)}%`       : "-" },
            { label: "Accuracy",           value: data.current_accuracy  != null ? `${(data.current_accuracy*100).toFixed(1)}%`  : "-" },
            { label: "Training Samples",   value: data.training_samples?.toLocaleString() ?? "-" },
            { label: "Model Version",      value: data.model_version  ?? "-" },
            { label: "Improvement",        value: data.improvement_pct != null ? `${data.improvement_pct > 0 ? "+" : ""}${data.improvement_pct.toFixed(1)}%` : "-" },
          ] as {label:string; value:string|number}[]).map(({ label, value }) => (
            <div key={label} className="rounded-xl border border-gray-800 bg-gray-900 p-5">
              <p className="text-xs text-gray-500 mb-2">{label}</p>
              <p className="text-2xl font-bold text-white">{value}</p>
            </div>
          ))}
          {data.last_retrain_at && (
            <div className="col-span-full rounded-xl border border-gray-800 bg-gray-900 p-5">
              <p className="text-xs text-gray-500 mb-1">Last retrained at</p>
              <p className="text-sm text-white">{new Date(data.last_retrain_at).toLocaleString()}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
