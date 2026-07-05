import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../utils/api';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';

interface AccountMetrics {
  equity: number;
  balance: number;
  free_margin: number;
  margin_level: number;
  equity_change_pct: number;
}

interface SystemHealth {
  status: string;
  kill_switch_active: boolean;
  redis: boolean;
  mt5: boolean;
}

const DashboardPage: React.FC = () => {
  const [account, setAccount] = useState<AccountMetrics | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [performance, setPerformance] = useState<Record<string, number> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [acc, hlth, perf] = await Promise.allSettled([
        apiClient.get<AccountMetrics>('/metrics/account'),
        apiClient.get<SystemHealth>('/health/ready'),
        apiClient.get<Record<string, number>>('/metrics/performance'),
      ]);
      if (acc.status === 'fulfilled') setAccount(acc.value);
      if (hlth.status === 'fulfilled') setHealth(hlth.value);
      if (perf.status === 'fulfilled') setPerformance(perf.value);
      setError(null);
    } catch (err) {
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    // Poll every 5 seconds
    const interval = setInterval(fetchAll, 5000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  if (loading) return <LoadingSpinner />;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-white">🌌 Galaxy Vast AI Trading</h1>

      {error && <ErrorAlert message={error} />}

      {/* System Status */}
      {health && (
        <div className={`p-4 rounded-lg border ${
          health.kill_switch_active
            ? 'bg-red-900 border-red-500'
            : 'bg-green-900 border-green-500'
        }`}>
          <p className="font-semibold text-white">
            {health.kill_switch_active
              ? '🚨 KILL SWITCH ACTIVE — Trading Halted'
              : '✅ System Online — Trading Active'}
          </p>
          <div className="flex gap-4 mt-2 text-sm">
            <span className={health.redis ? 'text-green-400' : 'text-red-400'}>
              Redis: {health.redis ? '✅' : '❌'}
            </span>
            <span className={health.mt5 ? 'text-green-400' : 'text-red-400'}>
              MT5: {health.mt5 ? '✅' : '❌'}
            </span>
          </div>
        </div>
      )}

      {/* Account Metrics */}
      {account && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {([
            { label: 'Equity', value: `$${account.equity.toLocaleString('en', { minimumFractionDigits: 2 })}`,
              delta: `${account.equity_change_pct >= 0 ? '+' : ''}${account.equity_change_pct.toFixed(2)}%`,
              positive: account.equity_change_pct >= 0 },
            { label: 'Balance', value: `$${account.balance.toLocaleString('en', { minimumFractionDigits: 2 })}` },
            { label: 'Free Margin', value: `$${account.free_margin.toLocaleString('en', { minimumFractionDigits: 2 })}` },
            { label: 'Margin Level', value: `${account.margin_level.toFixed(1)}%` },
          ] as Array<{ label: string; value: string; delta?: string; positive?: boolean }>).map(m => (
            <div key={m.label} className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <p className="text-gray-400 text-sm">{m.label}</p>
              <p className="text-white text-xl font-bold">{m.value}</p>
              {m.delta && (
                <p className={`text-sm ${m.positive ? 'text-green-400' : 'text-red-400'}`}>{m.delta}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Performance KPIs */}
      {performance && (
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <h2 className="text-lg font-semibold text-white mb-3">📊 Performance</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div><p className="text-gray-400 text-sm">Win Rate</p>
              <p className="text-white font-bold">{((performance.win_rate ?? 0) * 100).toFixed(1)}%</p></div>
            <div><p className="text-gray-400 text-sm">Profit Factor</p>
              <p className="text-white font-bold">{(performance.profit_factor ?? 0).toFixed(2)}</p></div>
            <div><p className="text-gray-400 text-sm">Sharpe Ratio</p>
              <p className="text-white font-bold">{(performance.sharpe_ratio ?? 0).toFixed(2)}</p></div>
            <div><p className="text-gray-400 text-sm">Max Drawdown</p>
              <p className="text-red-400 font-bold">{((performance.max_drawdown ?? 0) * 100).toFixed(1)}%</p></div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DashboardPage;
