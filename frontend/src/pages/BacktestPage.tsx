// frontend/src/pages/BacktestPage.tsx
import React, { useState } from "react";
import { FlaskConical, Play, RotateCcw, TrendingUp, Target, Shield, DollarSign } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import StatCard from "@/components/StatCard";
import LoadingSpinner from "@/components/LoadingSpinner";

interface BacktestResult {
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown: number;
  net_profit: number;
  sharpe: number;
  equity_curve: { date: string; equity: number }[];
}

const SYMBOLS    = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "USDCHF", "AUDUSD"];
const TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];

export default function BacktestPage() {
  const [symbol,   setSymbol]   = useState("EURUSD");
  const [tf,       setTf]       = useState("H1");
  const [fromDate, setFromDate] = useState("2024-01-01");
  const [toDate,   setToDate]   = useState("2024-12-31");
  const [deposit,  setDeposit]  = useState("10000");
  const [running,  setRunning]  = useState(false);
  const [result,   setResult]   = useState<BacktestResult | null>(null);

  async function runBacktest() {
    setRunning(true); setResult(null);
    await new Promise(r => setTimeout(r, 1800));
    const equity_curve = Array.from({ length: 24 }, (_, i) => ({
      date: `2024-${String(Math.floor(i / 2) + 1).padStart(2, "0")}`,
      equity: +deposit + Math.round((Math.random() - 0.35) * 800 * (i + 1)),
    }));
    setResult({ total_trades: 187, win_rate: 67.4, profit_factor: 1.82, max_drawdown: 8.3,
      net_profit: equity_curve[equity_curve.length - 1].equity - +deposit, sharpe: 1.64, equity_curve });
    setRunning(false);
  }

  return (
    <div className="p-6 space-y-6">
      <div><h1 className="text-xl font-bold text-white flex items-center gap-2"><FlaskConical size={20} className="text-purple-400" /> بک‌تست</h1><p className="text-sm text-gray-400 mt-1">شبیه‌سازی استراتژی SMC روی داده‌های تاریخی</p></div>
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="text-sm font-semibold text-white mb-4">پارامترهای بک‌تست</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
          <div><label className="block text-xs text-gray-400 mb-1">نماد</label><select value={symbol} onChange={e => setSymbol(e.target.value)} className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">{SYMBOLS.map(s => <option key={s}>{s}</option>)}</select></div>
          <div><label className="block text-xs text-gray-400 mb-1">تایم‌فریم</label><select value={tf} onChange={e => setTf(e.target.value)} className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">{TIMEFRAMES.map(t => <option key={t}>{t}</option>)}</select></div>
          <div><label className="block text-xs text-gray-400 mb-1">از تاریخ</label><input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)} className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" /></div>
          <div><label className="block text-xs text-gray-400 mb-1">تا تاریخ</label><input type="date" value={toDate} onChange={e => setToDate(e.target.value)} className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" /></div>
          <div><label className="block text-xs text-gray-400 mb-1">موجودی اولیه ($)</label><input type="number" value={deposit} onChange={e => setDeposit(e.target.value)} className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500" /></div>
        </div>
        <div className="flex gap-3 mt-4">
          <button onClick={runBacktest} disabled={running} className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors">
            {running ? <><RotateCcw size={15} className="animate-spin" /> در حال اجرا...</> : <><Play size={15} /> اجرای بک‌تست</>}
          </button>
          {result && <button onClick={() => setResult(null)} className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-white text-sm font-medium"><RotateCcw size={15} /> پاک کردن</button>}
        </div>
      </div>
      {running && <LoadingSpinner text="در حال اجرای بک‌تست..." />}
      {result && (<>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard title="کل معاملات" value={result.total_trades} icon={FlaskConical} color="blue" />
          <StatCard title="نرخ موفقیت" value={`${result.win_rate}%`} icon={Target} color="green" />
          <StatCard title="Profit Factor" value={result.profit_factor} icon={TrendingUp} color="purple" />
          <StatCard title="Max Drawdown" value={`${result.max_drawdown}%`} icon={Shield} color="red" />
          <StatCard title="Sharpe Ratio" value={result.sharpe} icon={TrendingUp} color="yellow" />
          <StatCard title="سود خالص" value={`$${result.net_profit.toFixed(0)}`} icon={DollarSign} color={result.net_profit >= 0 ? "green" : "red"} />
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="text-sm font-semibold text-white mb-4">منحنی سرمایه</h2>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={result.equity_curve}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="date" tick={{ fill: "#9ca3af", fontSize: 10 }} />
              <YAxis tick={{ fill: "#9ca3af", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 8 }} formatter={(v: number) => [`$${v.toLocaleString()}`, "موجودی"]} />
              <Area type="monotone" dataKey="equity" stroke="#3b82f6" fill="#3b82f620" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </>)}
    </div>
  );
}
