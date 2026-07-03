// frontend/src/components/Badge.tsx
import React from "react";

type Color = "green" | "red" | "yellow" | "blue" | "gray" | "purple";

const colorMap: Record<Color, string> = {
  green:  "bg-green-500/10  text-green-400  border-green-500/20",
  red:    "bg-red-500/10    text-red-400    border-red-500/20",
  yellow: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  blue:   "bg-blue-500/10   text-blue-400   border-blue-500/20",
  gray:   "bg-gray-500/10   text-gray-400   border-gray-500/20",
  purple: "bg-purple-500/10 text-purple-400 border-purple-500/20",
};

interface Props { label: string; color?: Color; }

export default function Badge({ label, color = "gray" }: Props) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${colorMap[color]}`}>
      {label}
    </span>
  );
}
