import { ReactNode } from "react";
import { TrendingUp, TrendingDown } from "lucide-react";

type Color = "accent" | "green" | "red" | "gold" | "purple";

const palette: Record<Color, { text: string; border: string; bg: string; glow: string }> = {
  accent: { text: "text-[#00d4ff]", border: "border-[#00d4ff]/30", bg: "bg-[#00d4ff]/5",  glow: "shadow-[0_0_18px_rgba(0,212,255,0.18)]" },
  green:  { text: "text-[#10b981]", border: "border-[#10b981]/30", bg: "bg-[#10b981]/5",  glow: "shadow-[0_0_18px_rgba(16,185,129,0.15)]" },
  red:    { text: "text-[#ef4444]", border: "border-[#ef4444]/30", bg: "bg-[#ef4444]/5",  glow: "shadow-[0_0_18px_rgba(239,68,68,0.15)]"  },
  gold:   { text: "text-[#f59e0b]", border: "border-[#f59e0b]/30", bg: "bg-[#f59e0b]/5",  glow: "shadow-[0_0_18px_rgba(245,158,11,0.15)]" },
  purple: { text: "text-[#8b5cf6]", border: "border-[#8b5cf6]/30", bg: "bg-[#8b5cf6]/5",  glow: "shadow-[0_0_18px_rgba(139,92,246,0.15)]" },
};

interface Props {
  title: string;
  value: number | string;
  format?: "currency" | "percent" | "ratio" | "number";
  color?: Color;
  icon?: ReactNode;
  trend?: number;
  glow?: boolean;
  subtitle?: string;
}

function fmt(v: number | string, format?: string) {
  if (typeof v === "string") return v;
  switch (format) {
    case "currency": return `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    case "percent":  return `${v.toFixed(2)}%`;
    case "ratio":    return v.toFixed(3);
    default:         return v.toLocaleString();
  }
}

export function StatCard({ title, value, format, color = "accent", icon, trend, glow, subtitle }: Props) {
  const p = palette[color];
  return (
    <div className={`gv-card p-4 border ${p.border} ${p.bg} ${glow ? p.glow : ""} transition-all hover:scale-[1.01]`}>
      <div className="flex items-start justify-between mb-2">
        <span className="text-[#475569] text-xs font-medium tracking-wide uppercase">{title}</span>
        {icon && <span className={p.text}>{icon}</span>}
      </div>
      <div className={`text-2xl font-bold ${p.text} tabular-nums`}>{fmt(value, format)}</div>
      {(trend !== undefined || subtitle) && (
        <div className="mt-1.5 flex items-center gap-1">
          {trend !== undefined && (
            <>
              {trend >= 0
                ? <TrendingUp  size={13} className="text-[#10b981]" />
                : <TrendingDown size={13} className="text-[#ef4444]" />}
              <span className={`text-xs ${trend >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                {trend >= 0 ? "+" : ""}{fmt(trend, "currency")}
              </span>
            </>
          )}
          {subtitle && <span className="text-xs text-[#475569]">{subtitle}</span>}
        </div>
      )}
    </div>
  );
}
