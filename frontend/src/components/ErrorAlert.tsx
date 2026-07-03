// frontend/src/components/ErrorAlert.tsx
import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

interface Props { message: string; onRetry?: () => void; }

export default function ErrorAlert({ message, onRetry }: Props) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
      <AlertCircle size={18} className="mt-0.5 shrink-0" />
      <div className="flex-1">
        <p className="text-sm font-medium">خطا</p>
        <p className="text-xs mt-1 text-red-300">{message}</p>
      </div>
      {onRetry && (
        <button onClick={onRetry} className="shrink-0 p-1 hover:text-red-200 transition-colors">
          <RefreshCw size={16} />
        </button>
      )}
    </div>
  );
}
