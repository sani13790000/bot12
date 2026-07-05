// BUG-R4 FIX: Was stub. Now calls /api/v1/ai/models/{symbol}
import React, { useState } from "react";
import { Cpu, RefreshCw, TrendingUp, Target, BarChart2 } from "lucide-react";
import { useApi } from "@/hooks/useApi";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorAlert from "@/components/ErrorAlert";
import { API_BASE_URL } from "@/utils/api";

interface ModelInfo {
  symbol: string;
  version: number;
  trained_at: string;
  auc_roc: number;
  accuracy: number;
  f1_score: number;
  n_samples: number;
  is_best: boolean;
}

const SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "ALL"];

const fetchModelInfo = (symbol: string) => async (): Promise<ModelInfo> => {
  const res = await fetch(`${API_BASE_URL}/api/v1/ai/models/${symbol}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

const MetricBar = ({ label, value }: { label: string; value: number }) => {
  const pct = Math.min(value * 100, 100);
  const color = pct >= 70 ? "bg-green-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>{label}</span>
        <span className="text-white font-medium">{pct.toFixed(1)}%</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
};

export default function ModelPerformancePage() {
  const [symbol, setSymbol] = useState("XAUUSD");
  const { data, isLoading, error, refetch } = useApi<ModelInfo>(fetchModelInfo(symbol));
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Cpu size={20} className="text-purple-400" /> XGBoost Model Performance
          </h1>
          <p className="text-sm text-gray-400 mt-1">Model accuracy metrics</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={symbol} onChange={e => setSymbol(e.target.value)}
            className="bg-gray-800 text-white text-sm rounded-lg px-3 py-1.5 border border-gray-700">
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <button onClick={refetch} className="text-gray-400 hover:text-white">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>
      {isLoading && <LoadingSpinner text="Loading..." />}
      {error && <ErrorAlert message={error} onRetry={refetch} />}
      {data && (
        <div className="space-y-4">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <div className="flex items-center justify-between mb-4">
              <div><p className="text-xs text-gray-500">Symbol</p><p className="text-white font-bold text-lg">{data.symbol}</p></div>
              <div><p className="text-xs text-gray-500">Version</p><p className="text-white font-bold text-lg">v{data.version}</p></div>
              <div><p className="text-xs text-gray-500">Samples</p><p className="text-white font-bold">{data.n_samples.toLocaleString()}</p></div>
              {data.is_best && <span className="bg-yellow-900 text-yellow-300 text-xs px-2 py-1 rounded-full">Best</span>}
            </div>
            <p className="text-xs text-gray-500">Trained: {new Date(data.trained_at).toLocaleString()}</p>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
            <MetricBar label="AUC-ROC" value={data.auc_roc} />
            <MetricBar label="Accuracy" value={data.accuracy} />
            <MetricBar label="F1 Score" value={data.f1_score} />
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "AUC-ROC", value: data.auc_roc, icon: <TrendingUp size={16} className="text-blue-400" /> },
              { label: "Accuracy", value: data.accuracy, icon: <Target size={16} className="text-green-400" /> },
              { label: "F1 Score", value: data.f1_score, icon: <BarChart2 size={16} className="text-purple-400" /> },
            ].map(({ label, value, icon }) => (
              <div key={label} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
                <div className="flex items-center gap-2 mb-2">{icon}<p className="text-xs text-gray-500">{label}</p></div>
                <p className="text-2xl font-bold text-white">{(value*100).toFixed(1)}<span className="text-xs text-gray-400">%</span></p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
