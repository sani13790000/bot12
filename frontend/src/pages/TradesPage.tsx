/**
 * صفحه معاملات
 *
 * نویسنده: MT5 Trading Team
 */

import { useState } from 'react';
import {
  TrendingUp,
  TrendingDown
} from 'lucide-react';
import { ErrorCard, EmptyCard } from '@/components/common/Card';
import { useTrades, useOpenTrades } from '@/hooks/useApi';
import { formatCurrency, formatDate, getDirectionText, getProfitColor } from '@/utils/helpers';

type TradeFilter = 'all' | 'open' | 'closed';
type DirectionFilter = 'all' | 'buy' | 'sell';

interface TradeData {
  trades: Array<{
    id: string;
    symbol: string;
    direction: 'buy' | 'sell';
    status: string;
    volume: number;
    entry_price: number;
    current_price?: number;
    exit_price?: number;
    profit_money: number;
    stop_loss: number;
    take_profit: number;
    opened_at: string;
    closed_at?: string;
  }>;
}

interface Trade {
  id: string;
  symbol: string;
  direction: 'buy' | 'sell';
  status: string;
  volume: number;
  entry_price: number;
  current_price?: number;
  exit_price?: number;
  profit_money: number;
  stop_loss: number;
  take_profit: number;
  opened_at: string;
  closed_at?: string;
}

interface OpenTradesData {
  positions: Array<Trade>;
}

export function TradesPage() {
  const [statusFilter, setStatusFilter] = useState<TradeFilter>('all');
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>('all');
  const [symbolFilter, setSymbolFilter] = useState('');

  // دریافت معاملات
  const { data: allTrades, error: allError } = useTrades({
    limit: 50
  }) as unknown as { data: TradeData | null; error: string | null };
  const { data: openTrades } = useOpenTrades() as unknown as { data: OpenTradesData | null };

  // انتخاب داده‌ها بر اساس فیلتر
  const trades: Trade[] = statusFilter === 'open'
    ? openTrades?.positions || []
    : allTrades?.trades || [];

  // فیلتر کردن
  const filteredTrades: Trade[] = trades.filter((trade) => {
    if (directionFilter !== 'all' && trade.direction !== directionFilter) return false;
    if (symbolFilter && !trade.symbol.toLowerCase().includes(symbolFilter.toLowerCase())) return false;
    return true;
  });

  // آمار
  const totalPnL = filteredTrades.reduce((sum, t) => sum + (t.profit_money || 0), 0);
  const wins = filteredTrades.filter(t => (t.profit_money || 0) > 0).length;
  const losses = filteredTrades.filter(t => (t.profit_money || 0) < 0).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">معاملات</h1>
          <p className="text-slate-500 mt-1">مدیریت و مشاهده معاملات</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
          <p className="text-slate-500 text-sm mb-1">تعداد کل</p>
          <p className="text-2xl font-bold text-slate-100">{filteredTrades.length}</p>
        </div>
        <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
          <p className="text-slate-500 text-sm mb-1">برنده</p>
          <p className="text-2xl font-bold text-emerald-500">{wins}</p>
        </div>
        <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
          <p className="text-slate-500 text-sm mb-1">بازنده</p>
          <p className="text-2xl font-bold text-rose-500">{losses}</p>
        </div>
        <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
          <p className="text-slate-500 text-sm mb-1">سود/ضرر</p>
          <p className={`text-2xl font-bold ${getProfitColor(totalPnL)}`}>
            {formatCurrency(totalPnL)}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
        <div className="flex flex-wrap items-center gap-4">
          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <span className="text-slate-500 text-sm">وضعیت:</span>
            <div className="flex bg-slate-700/50 rounded-lg p-1">
              {(['all', 'open', 'closed'] as TradeFilter[]).map((status) => (
                <button
                  key={status}
                  onClick={() => setStatusFilter(status)}
                  className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                    statusFilter === status
                      ? 'bg-sky-500/20 text-sky-400'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {status === 'all' ? 'همه' : status === 'open' ? 'باز' : 'بسته'}
                </button>
              ))}
            </div>
          </div>

          {/* Direction Filter */}
          <div className="flex items-center gap-2">
            <span className="text-slate-500 text-sm">جهت:</span>
            <div className="flex bg-slate-700/50 rounded-lg p-1">
              {(['all', 'buy', 'sell'] as DirectionFilter[]).map((dir) => (
                <button
                  key={dir}
                  onClick={() => setDirectionFilter(dir)}
                  className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                    directionFilter === dir
                      ? dir === 'buy'
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : dir === 'sell'
                          ? 'bg-rose-500/20 text-rose-400'
                          : 'bg-sky-500/20 text-sky-400'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {dir === 'all' ? 'همه' : dir === 'buy' ? 'خرید' : 'فروش'}
                </button>
              ))}
            </div>
          </div>

          {/* Symbol Filter */}
          <div className="flex items-center gap-2 flex-1 min-w-[200px]">
            <input
              type="text"
              placeholder="جستجوی نماد..."
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              className="flex-1 bg-slate-700/50 border border-slate-600/50 rounded-lg px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/50"
            />
          </div>
        </div>
      </div>

      {/* Trades List */}
      {allError ? (
        <ErrorCard message="خطا در دریافت معاملات" />
      ) : filteredTrades.length === 0 ? (
        <EmptyCard message="معامله‌ای یافت نشد" icon={TrendingUp} />
      ) : (
        <div className="space-y-3">
          {filteredTrades.map((trade) => (
            <div
              key={trade.id}
              className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50 hover:border-slate-600/50 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                    trade.direction === 'buy'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-rose-500/20 text-rose-400'
                  }`}>
                    {trade.direction === 'buy' ? (
                      <TrendingUp className="w-5 h-5" />
                    ) : (
                      <TrendingDown className="w-5 h-5" />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-100">{trade.symbol}</span>
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        trade.status === 'open'
                          ? 'bg-sky-500/20 text-sky-400'
                          : trade.status === 'closed'
                            ? 'bg-slate-500/20 text-slate-400'
                            : 'bg-amber-500/20 text-amber-400'
                      }`}>
                        {trade.status === 'open' ? 'باز' : trade.status === 'closed' ? 'بسته' : 'در انتظار'}
                      </span>
                    </div>
                    <p className="text-slate-500 text-sm">
                      {getDirectionText(trade.direction)} • {trade.volume} لات
                    </p>
                  </div>
                </div>

                <div className="text-left">
                  <p className={`font-semibold ${getProfitColor(trade.profit_money)}`}>
                    {formatCurrency(trade.profit_money)}
                  </p>
                  <p className="text-slate-500 text-sm">سود/ضرر</p>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-3 border-t border-slate-700/50">
                <div>
                  <p className="text-slate-500 text-xs mb-1">ورود</p>
                  <p className="text-slate-200">{trade.entry_price}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">حد ضرر</p>
                  <p className="text-rose-400">{trade.stop_loss}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">حد سود</p>
                  <p className="text-emerald-400">{trade.take_profit}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">时间</p>
                  <p className="text-slate-300 text-sm">
                    {formatDate(trade.opened_at, 'short')}
                  </p>
                </div>
              </div>

              {trade.status === 'open' && (
                <div className="flex gap-2 mt-3 pt-3 border-t border-slate-700/50">
                  <button className="flex-1 bg-rose-500/20 text-rose-400 py-2 rounded-lg text-sm font-medium hover:bg-rose-500/30 transition-colors">
                    بستن معامله
                  </button>
                  <button className="flex-1 bg-slate-700/50 text-slate-300 py-2 rounded-lg text-sm font-medium hover:bg-slate-700 transition-colors">
                    ویرایش SL/TP
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
