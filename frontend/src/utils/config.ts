// frontend/src/utils/config.ts
// FIX-FE3: WS_URL وجود نداشت → useWebSocket.ts crash
// FIX-FE3: API_BASE_URL path اشتباه بود (double /api)

const _BASE = (import.meta.env?.VITE_API_URL as string | undefined) || "http://localhost:8000";

export const API_BASE_URL = _BASE;
export const WS_URL = _BASE.replace(/^http/, "ws") + "/ws";

export const CHART_CONFIG = {
  colors: { bullish: "#22c55e", bearish: "#ef4444", neutral: "#94a3b8" },
  themes: {
    light: { background: "#ffffff", text: "#1e293b",  grid: "#e2e8f0" },
    dark:  { background: "#0f172a", text: "#f1f5f9",  grid: "#1e293b" },
  },
};

export const SCORING_CONFIG = {
  minEntryScore: 65, strongSignalScore: 80, weakSignalScore: 50,
  smcWeight: 0.35, paWeight: 0.30, timeWeight: 0.15, riskWeight: 0.10, momentumWeight: 0.10,
};

export const DEFAULT_SYMBOLS = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","XAUUSD","BTCUSD"];

export const TIMEFRAMES = [
  { value: "M1",  label: "1 دقیقه"  },
  { value: "M5",  label: "5 دقیقه"  },
  { value: "M15", label: "15 دقیقه" },
  { value: "M30", label: "30 دقیقه" },
  { value: "H1",  label: "1 ساعت"   },
  { value: "H4",  label: "4 ساعت"   },
  { value: "D1",  label: "روزانه"   },
  { value: "W1",  label: "هفتگی"    },
];

export const KILL_ZONES = [
  { name: "توکیو",   start: 0,  end: 3,  color: "#f59e0b" },
  { name: "لندن",    start: 8,  end: 11, color: "#3b82f6" },
  { name: "نیویورک", start: 13, end: 16, color: "#22c55e" },
  { name: "سیدنی",   start: 22, end: 1,  color: "#8b5cf6" },
];

export const COLORS = {
  primary: { 50:"#f0f9ff",500:"#0ea5e9",600:"#0284c7",700:"#0369a1" },
  success: { 50:"#f0fdf4",500:"#22c55e",600:"#16a34a" },
  danger:  { 50:"#fef2f2",500:"#ef4444",600:"#dc2626" },
  warning: { 50:"#fffbeb",500:"#f59e0b",600:"#d97706" },
};

export const TRADE_STATUS = {
  pending:   { label: "در انتظار", color: "bg-slate-500" },
  open:      { label: "باز",       color: "bg-sky-500"    },
  closed:    { label: "بسته",      color: "bg-slate-700"  },
  cancelled: { label: "لغو",       color: "bg-rose-500"   },
};

export const TRADE_DIRECTION = {
  buy:  { label: "خرید",  icon: "↑", color: "text-emerald-500" },
  sell: { label: "فروش",  icon: "↓", color: "text-rose-500"    },
};

export const SIGNAL_STATUS = {
  generated: { label: "تولید شده",   color: "bg-slate-500"   },
  sent:      { label: "ارسال شده",   color: "bg-sky-500"     },
  executed:  { label: "اجرا شده",    color: "bg-emerald-500" },
  expired:   { label: "منقضی",       color: "bg-amber-500"   },
  skipped:   { label: "رد شده",      color: "bg-rose-500"    },
};
