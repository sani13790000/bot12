import React, { useEffect, useState } from 'react';
import { apiClient } from '../utils/api';
import { useWebSocket } from '../hooks/useWebSocket';
import LoadingSpinner from '../components/LoadingSpinner';

interface Position {
  ticket: number;
  symbol: string;
  type: string;
  volume: number;
  open_price: number;
  current_price: number;
  sl: number;
  tp: number;
  profit: number;
  open_time: string;
}

interface Signal {
  id: string;
  symbol: string;
  direction: string;
  confidence: number;
  created_at: string;
}

const LiveTradesPage: React.FC = () => {
  const [positions, setPositions] = useState<Position[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [killActive, setKillActive] = useState(false);
  const [loading, setLoading] = useState(true);

  // WebSocket for real-time positions
  const { lastMessage } = useWebSocket('/ws/positions');

  useEffect(() => {
    if (lastMessage) {
      try {
        const data = JSON.parse(lastMessage);
        if (data.type === 'positions') {
          setPositions(data.positions ?? []);
          setKillActive(data.kill_switch_active ?? false);
        }
      } catch { /* ignore parse errors */ }
    }
  }, [lastMessage]);

  // REST fallback for initial load + signals
  useEffect(() => {
    const fetchInitial = async () => {
      try {
        const [pos, sigs] = await Promise.allSettled([
          apiClient.get<Position[]>('/trades/positions'),
          apiClient.get<Signal[]>('/signals/recent?limit=20'),
        ]);
        if (pos.status === 'fulfilled') setPositions(pos.value ?? []);
        if (sigs.status === 'fulfilled') setSignals(sigs.value ?? []);
      } finally {
        setLoading(false);
      }
    };
    fetchInitial();
    const interval = setInterval(async () => {
      const sigs = await apiClient.get<Signal[]>('/signals/recent?limit=20').catch(() => null);
      if (sigs) setSignals(sigs);
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingSpinner />;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-white">💹 Live Trades</h1>

      {killActive && (
        <div className="bg-red-900 border border-red-500 rounded-lg p-4">
          <p className="text-white font-bold">🚨 KILL SWITCH ACTIVE — No new trades</p>
        </div>
      )}

      {/* Open Positions */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold text-white mb-3">📌 Open Positions ({positions.length})</h2>
        {positions.length === 0 ? (
          <p className="text-gray-400">No open positions</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-gray-700">
                  {['Ticket','Symbol','Type','Volume','Open','Current','SL','TP','P&L'].map(h => (
                    <th key={h} className="text-left py-2 pr-4">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map(p => (
                  <tr key={p.ticket} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                    <td className="py-2 pr-4 text-gray-300">{p.ticket}</td>
                    <td className="py-2 pr-4 text-white font-medium">{p.symbol}</td>
                    <td className={`py-2 pr-4 font-medium ${
                      p.type === 'BUY' ? 'text-green-400' : 'text-red-400'
                    }`}>{p.type}</td>
                    <td className="py-2 pr-4 text-gray-300">{p.volume.toFixed(2)}</td>
                    <td className="py-2 pr-4 text-gray-300">{p.open_price.toFixed(5)}</td>
                    <td className="py-2 pr-4 text-gray-300">{p.current_price.toFixed(5)}</td>
                    <td className="py-2 pr-4 text-gray-300">{p.sl.toFixed(5)}</td>
                    <td className="py-2 pr-4 text-gray-300">{p.tp.toFixed(5)}</td>
                    <td className={`py-2 pr-4 font-bold ${
                      p.profit >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>${p.profit.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Recent Signals */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <h2 className="text-lg font-semibold text-white mb-3">📡 Recent Signals</h2>
        {signals.length === 0 ? (
          <p className="text-gray-400">No signals yet</p>
        ) : (
          <div className="space-y-2">
            {signals.map(s => (
              <div key={s.id} className="flex items-center justify-between bg-gray-700/50 rounded p-3">
                <span className="text-white font-medium">{s.symbol}</span>
                <span className={`font-bold ${
                  s.direction === 'BUY' ? 'text-green-400' : 'text-red-400'
                }`}>{s.direction}</span>
                <span className="text-gray-300">{(s.confidence * 100).toFixed(1)}%</span>
                <span className="text-gray-500 text-xs">{new Date(s.created_at).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default LiveTradesPage;
