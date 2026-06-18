import { ReactNode } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: number;
  icon?: ReactNode;
  color?: "accent" | "green" | "red" | "gold" | "purple";
  format?: "currency" | "percent" | "number" | "ratio";
  glow?: boolean;
}

const colorMap = {
  accent: "text-[#00d4ff]  border-[#00d4ff]/20",
  green:  "text-[#10b981]  border-[#10b981]/20",
  red:    "text-[#ef4444]  border-[#ef4444]/20",
  gold:   "text-[#f59e0b]  border-[#f59e0b]/20",
  purple: "text-[#8b5cf6]  border-[#8b5cf6]/20",
};

function fmt(value: string | number, format?: string) {
  if (typeof value === "string") return value;
  switch (format) {
    case "currency": return `$${value.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    case "percent":  return `${value.toFixed(2)}%`;
    case "ratio":    return value.toFixed(3);
    default:         return value.toLocaleString("en");
  }
}

export function StatCard({ title, value, subtitle, trend, icon, color = "accent", format, glow }: StatCardProps) {
  const colorClass = colorMap[color];
  return (
    <div className={`gv-card p-5 fade-in-up ${glow ? `glow-${color === "accent" ? "accent" : color === "green" ? "green" : "red"}` : ""}`}>
      <div className="flex items-start justify-between mb-3">
        <span className="text-[#94a3b8] text-sm">{title}</span>
        {icon && <div className={`${colorClass.split(" ")[0]} opacity-70`}>{icon}</div>}
      </div>
      <div className={`metric-value ${colorClass.split(" ")[0]} mb-1`}>
        {fmt(value, format)}
      </div>
      <div className="flex items-center gap-2 mt-2">
        {trend !== undefined && (
          <span className={`flex items-center gap-1 text-xs font-medium ${trend > 0 ? "text-[#10b981]" : trend < 0 ? "text-[#ef4444]" : "text-[#94a3b8]"}`}>
            {trend > 0 ? <TrendingUp size={12} /> : trend < 0 ? <TrendingDown size={12} /> : <Minus size={12} />}
            {Math.abs(trend).toFixed(2)}%
          </span>
        )}
        {subtitle && <span className="text-[#475569] text-xs">{subtitle}</span>}
      </div>
    </div>
  );
}
