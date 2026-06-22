/**
 * frontend/src/utils/config.ts
 * FIX-33: WS_URL export شد — useWebSocket.ts import می‌کرد → build fail
 * FIX-34: API_BASE_URL بدون /api suffix
 */

export const API_BASE_URL =
  (import.meta.env?.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export const WS_URL = API_BASE_URL.replace(/^http/, "ws") + "/ws";

export const CHART_CONFIG = {
  colors: { bullish: "#22c55e", bearish: "#ef4444", neutral: "#94a3b8" },
  themes: { dark: { background: "#0f172a", text: "#f1f5f9", grid: "#1e293b" } },
} as const;

export const SCORING_CONFIG = {
  minEntryScore: 65, strongSignalScore: 80, weakSignalScore: 50,
  smcWeight: 0.35, paWeight: 0.30, timeWeight: 0.15, riskWeight: 0.10, momentumWeight: 0.10,
} as const;

export const DEFAULT_SYMBOLS = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","XAUUSD","BTCUSD"] as const;

export const TIMEFRAMES = [
  { value: "M1",  label: "۱ دقیقه"  },
  { value: "M5",  label: "۵ دقیقه"  },
  { value: "M15", label: "۱۵ دقیقه" },
  { value: "M30", label: "۳۰ دقیقه" },
  { value: "H1",  label: "۱ ساعت"   },
  { value: "H4",  label: "۴ ساعت"   },
  { value: "D1",  label: "روزانه"    },
  { value: "W1",  label: "هفتگی"     },
] as const;

export const KILL_ZONES = [
  { name: "توکیو",   start: 0,  end: 3,  color: "#f59e0b" },
  { name: "لندن",    start: 8,  end: 11, color: "#3b82f6" },
  { name: "نیویورک", start: 13, end: 16, color: "#22c55e" },
  { name: "سیدنی",   start: 22, end: 1,  color: "#8b5cf6" },
] as const;

export const TRADE_STATUS = {
  pending:   { label: "در انتظار", color: "bg-slate-500" },
  open:      { label: "باز",       color: "bg-sky-500"   },
  closed:    { label: "بسته",      color: "bg-slate-700" },
  cancelled: { label: "لغو",       color: "bg-rose-500"  },
} as const;

export const TRADE_DIRECTION = {
  buy:  { label: "خرید",  icon: "↑", color: "text-emerald-500" },
  sell: { label: "فروش", icon: "↓", color: "text-rose-500"    },
} as const;

export const SIGNAL_STATUS = {
  generated: { label: "تولید شده",  color: "bg-slate-500"   },
  sent:      { label: "ارسال شده",  color: "bg-sky-500"     },
  executed:  { label: "اجرا شده",   color: "bg-emerald-500" },
  expired:   { label: "منقضی",      color: "bg-amber-500"   },
  skipped:   { label: "رد شده",     color: "bg-rose-500"    },
} as const;
