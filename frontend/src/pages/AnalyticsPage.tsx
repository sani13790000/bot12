import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../utils/api';
import LoadingSpinner from '../components/LoadingSpinner';

interface PerformanceKPIs {
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  max_drawdown: number;
  total_trades: number;
  avg_rr: number;
  total_pnl: number;
  avg_holding_minutes: number;
}

interface EquityPoint {
  timestamp: string;
  equity: number;
}

const AnalyticsPage: React.FC = () => {
  const [kpis, setKpis] = useState<PerformanceKPIs | null>(null);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [k, eq] = await Promise.allSettled([
        apiClient.get<PerformanceKPIs>('/metrics/performance'),
        apiClient.get<{ curve: EquityPoint[] }>('/metrics/equity?days=30'),
      ]);
      if (k.status === 'fulfilled') setKpis(k.value);
      if (eq.status === 'fulfilled' && eq.value?.curve) setEquity(eq.value.curve);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) return <LoadingSpinner />;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-white">📈 Analytics</h1>

      {kpis ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Win Rate', value: `${(kpis.win_rate * 100).toFixed(1)}%`, good: kpis.win_rate > 0.5 },
            { label: 'Profit Factor', value: kpis.profit_factor.toFixed(2), good: kpis.profit_factor > 1.5 },
            { label: 'Sharpe Ratio', value: kpis.sharpe_ratio.toFixed(2), good: kpis.sharpe_ratio > 1 },
            { label: 'Max Drawdown', value: `${(kpis.max_drawdown * 100).toFixed(1)}%`, good: kpis.max_drawdown < 0.15 },
            { label: 'Total Trades', value: String(kpis.total_trades), good: true },
            { label: 'Avg R:R', value: kpis.avg_rr.toFixed(2), good: kpis.avg_rr > 1.5 },
            { label: 'Total PnL', value: `$${kpis.total_pnl.toLocaleString('en', { minimumFractionDigits: 2 })}`, good: kpis.total_pnl > 0 },
            { label: 'Avg Hold (min)', value: kpis.avg_holding_minutes.toFixed(0), good: true },
          ].map(m => (
            <div key={m.label} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">{m.label}</p>
              <p className={`text-xl font-bold ${m.good ? 'text-green-400' : 'text-red-400'}`}>{m.value}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-gray-400">No performance data yet — complete some trades first.</p>
      )}

      {equity.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h2 className="text-lg font-semibold text-white mb-3">📊 Equity Curve (30 days)</h2>
          <div className="space-y-1">
            {equity.slice(-10).map((pt, i) => (
              <div key={i} className="flex justify-between text-sm">
                <span className="text-gray-400">{new Date(pt.timestamp).toLocaleDateString()}</span>
                <span className="text-white font-mono">${pt.equity.toLocaleString('en', { minimumFractionDigits: 2 })}</span>
              </div>
            ))}
          </div>
          <p className="text-gray-500 text-xs mt-2">Showing last 10 data points. Full chart in Streamlit dashboard.</p>
        </div>
      )}
    </div>
  );
};

export default AnalyticsPage;
