// frontend/src/components/LoadingSpinner.tsx
import React from "react";

interface Props { size?: "sm" | "md" | "lg"; text?: string; }

const sizeMap = { sm: "w-4 h-4", md: "w-8 h-8", lg: "w-12 h-12" };

export default function LoadingSpinner({ size = "md", text }: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-8">
      <svg className={`animate-spin ${sizeMap[size]} text-blue-500`} fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      {text && <p className="text-gray-400 text-sm">{text}</p>}
    </div>
  );
}
