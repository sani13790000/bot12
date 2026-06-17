/**
 * صفحه تحلیل بازار
 *
 * نویسنده: MT5 Trading Team
 */

import { useState, useCallback } from 'react';
import {
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Target,
  AlertTriangle,
  Clock,
  Activity,
  BarChart2,
  Upload
} from 'lucide-react';
import { usePost } from '@/hooks/useApi';
import { formatNumber, getScoreClass, getActiveKillZone } from '@/utils/helpers';
import { TIMEFRAMES, DEFAULT_SYMBOLS, KILL_ZONES } from '@/utils/config';
import { SimpleCandlestickChart } from '@/components/common/Chart';

interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface SMCResult {
  score: number;
  trend: string;
  liquidity_swept: boolean;
  premium_discount: string;
  details: {
    structure: {
      last_event: { type: string; direction: string; level: number } | null;
      key_levels: { last_swing_high: number; last_swing_low: number };
    };
    liquidity: { score: number; sweep_type: string | null };
    blocks: {
      score: number;
      active_blocks: Array<{ type: string; direction: string; high: number; low: number; score: number }>;
    };
    fvg: {
      score: number;
      active_fvgs: Array<{ type: string; high: number; low: number; fill_percent: number }>;
    };
    session: {
      score: number;
      active_sessions: string[];
      killzone_active: boolean;
      current_session: string | null;
    };
  };
}

interface PAResult {
  score: number;
  direction: string;
  confidence: string;
  patterns: Array<{ name: string; direction: string; score: number }>;
}

interface DecisionResult {
  action: string;
  quality: string;
  confidence: string;
  total_score: number;
  direction: string | null;
  reasons: string[];
  suggested_entry: number | null;
  suggested_sl: number | null;
  suggested_tp: number | null;
  risk_reward: number | null;
}

interface AnalysisResult {
  symbol: string;
  timeframe: string;
  current_price: number;
  candle_count: number;
  smc: SMCResult;
  price_action: PAResult;
  decision: DecisionResult;
}

// ارسال متن CSV با فرمت: time,open,high,low,close
function parseCsvCandles(csv: string): Candle[] | null {
  try {
    const lines = csv.trim().split('\n').filter(l => l.trim() && !l.startsWith('time') && !l.startsWith('Time') && !l.startsWith('DATE'));
    return lines.map(line => {
      const [time, open, high, low, close] = line.split(',').map(s => s.trim());
      return {
        time,
        open: parseFloat(open),
        high: parseFloat(high),
        low: parseFloat(low),
        close: parseFloat(close)
      };
    }).filter(c => !isNaN(c.open) && !isNaN(c.close));
  } catch {
    return null;
  }
}

export function AnalysisPage() {
  const [symbol, setSymbol] = useState('EURUSD');
  const [timeframe, setTimeframe] = useState('H1');
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [csvInput, setCsvInput] = useState('');
  const [showCsvInput, setShowCsvInput] = useState(false);

  const { post } = usePost<{ success: boolean; data: AnalysisResult }>();

  // پارس CSV وارد شده توسط کاربر
  const handleCsvLoad = useCallback(() => {
    if (!csvInput.trim()) {
      setError('لطفاً داده CSV را وارد کنید');
      return;
    }
    const parsed = parseCsvCandles(csvInput);
    if (!parsed || parsed.length < 10) {
      setError('فرمت CSV نامعتبر است یا تعداد کندل کافی نیست (حداقل ۱۰)');
      return;
    }
    setCandles(parsed);
    setError(null);
    setShowCsvInput(false);
  }, [csvInput]);

  const runAnalysis = async () => {
    if (candles.length < 10) {
      setError('ابتدا داده بازار را از MT5 وارد کنید (حداقل ۱۰ کندل)');
      setShowCsvInput(true);
      return;
    }

    setIsAnalyzing(true);
    setError(null);

    try {
      const payload = {
        symbol,
        timeframe,
        use_multi_tf: true,
        include_price_action: true,
        opens: candles.map(c => c.open),
        highs: candles.map(c => c.high),
        lows: candles.map(c => c.low),
        closes: candles.map(c => c.close),
        timestamps: candles.map(c => Math.floor(new Date(c.time).getTime() / 1000))
      };

      const response = await post('/analysis/full', payload);

      if (response?.success && response.data) {
        setResult(response.data);
      } else {
        setError('سرور پاسخ نامعتبر برگرداند');
      }
    } catch (err: any) {
      setError(err?.message || 'خطا در ارتباط با سرور');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const activeKZ = getActiveKillZone();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">تحلیل بازار</h1>
          <p className="text-slate-500 mt-1">تحلیل SMC و Price Action</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-700/30 rounded-lg">
            <Clock className="w-4 h-4 text-amber-400" />
            <span className="text-sm text-slate-300">{activeKZ}</span>
          </div>

          <button
            onClick={() => setShowCsvInput(v => !v)}
            className="flex items-center gap-2 px-4 py-2 bg-slate-700/50 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors"
          >
            <Upload className="w-4 h-4" />
            <span>داده MT5</span>
          </button>

          <button
            onClick={runAnalysis}
            disabled={isAnalyzing}
            className="flex items-center gap-2 px-4 py-2 bg-sky-500/20 text-sky-400 rounded-lg hover:bg-sky-500/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isAnalyzing ? 'animate-spin' : ''}`} />
            <span>{isAnalyzing ? 'در حال تحلیل...' : 'تحلیل'}</span>
          </button>
        </div>
      </div>

      {/* CSV Input Panel */}
      {showCsvInput && (
        <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4 space-y-3">
          <p className="text-slate-300 text-sm font-medium">
            داده OHLC را از MT5 کپی کنید (فرمت: time,open,high,low,close)
          </p>
          <p className="text-slate-500 text-xs">
            مثال: 2024.01.15 09:00,1.08500,1.08620,1.08440,1.08580
          </p>
          <textarea
            value={csvInput}
            onChange={e => setCsvInput(e.target.value)}
            rows={8}
            placeholder={"time,open,high,low,close\n2024.01.15 09:00,1.08500,1.08620,1.08440,1.08580\n..."}
            className="w-full bg-slate-900/50 border border-slate-600/50 rounded-lg p-3 text-slate-200 text-xs font-mono focus:outline-none focus:border-sky-500/50 resize-y"
          />
          <div className="flex items-center gap-3">
            <button
              onClick={handleCsvLoad}
              className="px-4 py-2 bg-emerald-500/20 text-emerald-400 rounded-lg hover:bg-emerald-500/30 transition-colors text-sm"
            >
              بارگذاری ({csvInput.trim().split('\n').filter(l => l.trim() && !l.startsWith('time')).length} کندل)
            </button>
            {candles.length > 0 && (
              <span className="text-emerald-400 text-sm">✅ {candles.length} کندل بارگذاری شده</span>
            )}
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-slate-500 text-sm">نماد:</span>
            <select
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              className="bg-slate-700/50 border border-slate-600/50 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500/50"
            >
              {DEFAULT_SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-slate-500 text-sm">تایم‌فریم:</span>
            <select
              value={timeframe}
              onChange={e => setTimeframe(e.target.value)}
              className="bg-slate-700/50 border border-slate-600/50 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500/50"
            >
              {TIMEFRAMES.map(tf => <option key={tf.value} value={tf.value}>{tf.label}</option>)}
            </select>
          </div>

          {candles.length > 0 && (
            <span className="text-slate-400 text-sm mr-auto">
              📊 {candles.length} کندل | آخرین: {candles[candles.length - 1]?.close?.toFixed(5)}
            </span>
          )}

          {result && (
            <div className="flex items-center gap-2 mr-auto">
              <span className="text-slate-400">قیمت فعلی:</span>
              <span className="font-mono text-slate-200">{result.current_price.toFixed(5)}</span>
            </div>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-lg p-4 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-rose-400" />
          <span className="text-rose-400">{error}</span>
        </div>
      )}

      {result && (
        <>
          {/* Main Result */}
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                  result.decision.direction === 'bullish'
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : result.decision.direction === 'bearish'
                      ? 'bg-rose-500/20 text-rose-400'
                      : 'bg-slate-700 text-slate-400'
                }`}>
                  {result.decision.direction === 'bullish' ? (
                    <TrendingUp className="w-6 h-6" />
                  ) : result.decision.direction === 'bearish' ? (
                    <TrendingDown className="w-6 h-6" />
                  ) : (
                    <Activity className="w-6 h-6" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-xl text-slate-100">{result.symbol}</span>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      result.decision.action === 'BUY'
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : result.decision.action === 'SELL'
                          ? 'bg-rose-500/20 text-rose-400'
                          : 'bg-slate-700 text-slate-400'
                    }`}>
                      {result.decision.action}
                    </span>
                  </div>
                  <p className="text-slate-500 text-sm">{result.timeframe} — {result.candle_count} کندل</p>
                </div>
              </div>

              <div className="text-left">
                <div className={`text-3xl font-bold ${getScoreClass(result.decision.total_score).split(' ')[0]}`}>
                  {result.decision.total_score}
                </div>
                <p className="text-slate-500 text-sm">امتیاز کل</p>
              </div>
            </div>

            {/* Trading Levels */}
            {result.decision.direction && (
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="p-4 bg-slate-700/30 rounded-lg text-center">
                  <p className="text-slate-500 text-xs mb-1">ورود</p>
                  <p className="text-xl font-mono text-sky-400">
                    {result.decision.suggested_entry?.toFixed(5) || '-'}
                  </p>
                </div>
                <div className="p-4 bg-slate-700/30 rounded-lg text-center">
                  <p className="text-slate-500 text-xs mb-1">حد ضرر</p>
                  <p className="text-xl font-mono text-rose-400">
                    {result.decision.suggested_sl?.toFixed(5) || '-'}
                  </p>
                </div>
                <div className="p-4 bg-slate-700/30 rounded-lg text-center">
                  <p className="text-slate-500 text-xs mb-1">حد سود</p>
                  <p className="text-xl font-mono text-emerald-400">
                    {result.decision.suggested_tp?.toFixed(5) || '-'}
                  </p>
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {result.decision.reasons.map((reason, idx) => (
                <span key={idx} className="px-2 py-1 bg-slate-700/50 rounded text-sm text-slate-300">
                  {reason}
                </span>
              ))}
            </div>
          </div>

          {/* Score Breakdown */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* SMC */}
            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
              <h3 className="text-lg font-semibold text-slate-100 mb-4 flex items-center gap-2">
                <BarChart2 className="w-5 h-5 text-sky-500" />
                Smart Money Concept
              </h3>
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-slate-400">امتیاز SMC</span>
                    <span className={`font-bold text-lg ${getScoreClass(result.smc.score).split(' ')[0]}`}>
                      {result.smc.score}/100
                    </span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div className={`h-full ${getScoreClass(result.smc.score).split(' ')[1]}`} style={{ width: `${result.smc.score}%` }} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 bg-slate-700/30 rounded-lg">
                    <p className="text-slate-500 text-xs">روند</p>
                    <p className={`font-medium ${result.smc.trend === 'bullish' ? 'text-emerald-400' : result.smc.trend === 'bearish' ? 'text-rose-400' : 'text-slate-300'}`}>
                      {result.smc.trend === 'bullish' ? 'صعودی' : result.smc.trend === 'bearish' ? 'نزولی' : 'رنج'}
                    </p>
                  </div>
                  <div className="p-3 bg-slate-700/30 rounded-lg">
                    <p className="text-slate-500 text-xs">ناحیه</p>
                    <p className="font-medium text-slate-300">
                      {result.smc.premium_discount === 'discount' ? 'تخفیف' : result.smc.premium_discount === 'premium' ? 'پرمیوم' : 'تعادل'}
                    </p>
                  </div>
                  <div className="p-3 bg-slate-700/30 rounded-lg">
                    <p className="text-slate-500 text-xs">نقدینگی اسویپ</p>
                    <p className={`font-medium ${result.smc.liquidity_swept ? 'text-emerald-400' : 'text-slate-400'}`}>
                      {result.smc.liquidity_swept ? 'بله' : 'خیر'}
                    </p>
                  </div>
                  <div className="p-3 bg-slate-700/30 rounded-lg">
                    <p className="text-slate-500 text-xs">ساختار</p>
                    <p className="font-medium text-slate-300">{result.smc.details.structure.last_event?.type || '-'}</p>
                  </div>
                </div>
                <div className="space-y-2">
                  <p className="text-slate-500 text-sm">ناحیه‌های فعال</p>
                  {result.smc.details.blocks.active_blocks.length > 0 && (
                    <div className="p-2 bg-slate-700/20 rounded">
                      <p className="text-xs text-slate-400">Order Blocks</p>
                      <p className="text-sm text-slate-300">{result.smc.details.blocks.active_blocks.length} بلاک فعال</p>
                    </div>
                  )}
                  {result.smc.details.fvg.active_fvgs.length > 0 && (
                    <div className="p-2 bg-slate-700/20 rounded">
                      <p className="text-xs text-slate-400">FVG</p>
                      <p className="text-sm text-slate-300">{result.smc.details.fvg.active_fvgs.length} گپ فعال</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Price Action */}
            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
              <h3 className="text-lg font-semibold text-slate-100 mb-4 flex items-center gap-2">
                <Target className="w-5 h-5 text-amber-500" />
                Price Action
              </h3>
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-slate-400">امتیاز PA</span>
                    <span className={`font-bold text-lg ${getScoreClass(result.price_action.score).split(' ')[0]}`}>
                      {result.price_action.score}/100
                    </span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div className={`h-full ${getScoreClass(result.price_action.score).split(' ')[1]}`} style={{ width: `${result.price_action.score}%` }} />
                  </div>
                </div>
                <div>
                  <p className="text-slate-500 text-sm mb-2">الگوهای شناسایی شده</p>
                  <div className="space-y-2">
                    {result.price_action.patterns.map((pattern, idx) => (
                      <div key={idx} className="flex items-center justify-between p-2 bg-slate-700/30 rounded">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${pattern.direction === 'bullish' ? 'bg-emerald-500' : pattern.direction === 'bearish' ? 'bg-rose-500' : 'bg-slate-500'}`} />
                          <span className="text-slate-300 text-sm">{pattern.name}</span>
                        </div>
                        <span className="text-slate-500 text-xs">+{pattern.score}</span>
                      </div>
                    ))}
                    {result.price_action.patterns.length === 0 && (
                      <p className="text-slate-500 text-sm">الگویی شناسایی نشد</p>
                    )}
                  </div>
                </div>
                <div className="p-3 bg-slate-700/30 rounded-lg">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">اعتماد</span>
                    <span className={`font-medium ${result.price_action.confidence === 'strong' ? 'text-emerald-400' : result.price_action.confidence === 'moderate' ? 'text-amber-400' : 'text-slate-400'}`}>
                      {result.price_action.confidence === 'strong' ? 'قوی' : result.price_action.confidence === 'moderate' ? 'متوسط' : 'ضعیف'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Sessions */}
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
            <h3 className="text-lg font-semibold text-slate-100 mb-4">جلسات معاملاتی</h3>
            <div className="grid grid-cols-4 gap-4">
              {KILL_ZONES.map(kz => {
                const isActive = result.smc.details.session.active_sessions.includes(kz.name);
                return (
                  <div key={kz.name} className={`p-4 rounded-lg border ${isActive ? 'bg-sky-500/10 border-sky-500/30' : 'bg-slate-700/30 border-slate-700/50'}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: kz.color }} />
                      <span className="font-medium text-slate-200">{kz.name}</span>
                      {isActive && <span className="text-xs text-sky-400">(فعال)</span>}
                    </div>
                    <p className="text-slate-500 text-xs">{kz.start}:00 - {kz.end}:00 UTC</p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Chart — از داده واقعی */}
          {candles.length > 0 && (
            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
              <h3 className="text-lg font-semibold text-slate-100 mb-4">
                نمودار قیمت — {candles.length} کندل واقعی
              </h3>
              <SimpleCandlestickChart data={candles} height={256} />
            </div>
          )}
        </>
      )}

      {/* Initial State */}
      {!result && !error && (
        <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-12 text-center">
          <Activity className="w-16 h-16 text-slate-600 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-slate-300 mb-2">تحلیل بازار را شروع کنید</h3>
          <p className="text-slate-500 mb-4">
            داده OHLC از MT5 را وارد کنید، نماد و تایم‌فریم انتخاب کنید و تحلیل را اجرا کنید
          </p>
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={() => setShowCsvInput(true)}
              className="px-4 py-2 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 transition-colors"
            >
              📋 وارد کردن داده MT5
            </button>
            <button
              onClick={runAnalysis}
              className="px-6 py-3 bg-sky-500/20 text-sky-400 rounded-lg hover:bg-sky-500/30 transition-colors"
            >
              شروع تحلیل
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
