/**
 * کامپوننت نمودار
 *
 * نویسنده: MT5 Trading Team
 */

import React, { useMemo } from 'react';

interface EquityChartProps {
  data: Array<{
    date: string;
    value: number;
  }>;
  height?: number;
  showGrid?: boolean;
}

interface CandlestickChartProps {
  data: Array<{
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
  }>;
  height?: number;
}

interface BarChartProps {
  data: Array<{
    label: string;
    value: number;
    color?: string;
  }>;
  height?: number;
  horizontal?: boolean;
}

// نمودار Equity
export function EquityChart({ data, height = 256, showGrid = true }: EquityChartProps) {
  const { min, max, range, points } = useMemo(() => {
    if (data.length === 0) {
      return { min: 0, max: 100, range: 100, points: '' };
    }

    const values = data.map(d => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;

    const width = 100 / (data.length - 1 || 1);

    const points = data.map((point, i) => {
      const x = i * width;
      const y = 100 - ((point.value - min) / range) * 100;
      return `${x},${y}`;
    }).join(' ');

    return { min, max, range, points };
  }, [data]);

  const startY = useMemo(() => {
    if (data.length === 0) return 0;
    const firstValue = data[0].value;
    return 100 - ((firstValue - min) / range) * 100;
  }, [data, min, range]);

  const endY = useMemo(() => {
    if (data.length === 0) return 0;
    const lastValue = data[data.length - 1].value;
    return 100 - ((lastValue - min) / range) * 100;
  }, [data, min, range]);

  const isUp = data.length > 1 && data[data.length - 1].value >= data[0].value;

  if (data.length === 0) {
    return (
      <div
        className="bg-slate-800/30 rounded-lg flex items-center justify-center"
        style={{ height }}
      >
        <p className="text-slate-500">داده‌ای یافت نشد</p>
      </div>
    );
  }

  return (
    <div className="relative" style={{ height }}>
      <svg
        viewBox={`0 0 100 100`}
        preserveAspectRatio="none"
        className="w-full h-full"
      >
        {/* Grid */}
        {showGrid && (
          <>
            {[0, 25, 50, 75, 100].map((y) => (
              <line
                key={`h-${y}`}
                x1="0"
                y1={y}
                x2="100"
                y2={y}
                stroke="rgb(51, 65, 85)"
                strokeWidth="0.2"
                strokeDasharray="1,1"
              />
            ))}
          </>
        )}

        {/* Area fill */}
        <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
          <stop
            offset="0%"
            stopColor={isUp ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'}
            stopOpacity="0.3"
          />
          <stop
            offset="100%"
            stopColor={isUp ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'}
            stopOpacity="0"
          />
        </linearGradient>

        <polygon
          points={`0,100 ${points} 100,100`}
          fill="url(#equityGradient)"
        />

        {/* Line */}
        <polyline
          points={points}
          fill="none"
          stroke={isUp ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'}
          strokeWidth="0.5"
          vectorEffect="non-scaling-stroke"
        />

        {/* Start point */}
        <circle
          cx="0"
          cy={startY}
          r="1"
          fill={isUp ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'}
        />

        {/* End point */}
        <circle
          cx="100"
          cy={endY}
          r="1.5"
          fill={isUp ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)'}
        />
      </svg>

      {/* Labels */}
      <div className="absolute top-0 left-0 text-xs text-slate-500">
        {max.toLocaleString('fa-IR')}
      </div>
      <div className="absolute bottom-0 left-0 text-xs text-slate-500">
        {min.toLocaleString('fa-IR')}
      </div>

      {/* Start/End values */}
      <div className="absolute top-0 right-0 text-xs text-slate-400">
        {data[0]?.value.toLocaleString('fa-IR')}
      </div>
      <div className={`absolute bottom-0 right-0 text-xs ${isUp ? 'text-emerald-400' : 'text-rose-400'}`}>
        {data[data.length - 1]?.value.toLocaleString('fa-IR')}
      </div>
    </div>
  );
}

// نمودار ستونی
export function BarChart({ data, height = 200, horizontal = false }: BarChartProps) {
  const max = useMemo(() => {
    return Math.max(...data.map(d => Math.abs(d.value)), 1);
  }, [data]);

  if (horizontal) {
    return (
      <div className="space-y-2" style={{ minHeight: height }}>
        {data.map((item, index) => (
          <div key={index} className="flex items-center gap-3">
            <div className="w-24 text-sm text-slate-400 truncate">{item.label}</div>
            <div className="flex-1 h-6 bg-slate-700/30 rounded overflow-hidden relative">
              <div
                className={`absolute top-0 bottom-0 rounded ${
                  item.value >= 0
                    ? item.color ? '' : 'bg-emerald-500/50'
                    : item.color ? '' : 'bg-rose-500/50'
                }`}
                style={{
                  width: `${(Math.abs(item.value) / max) * 100}%`,
                  right: item.value < 0 ? 0 : 'auto',
                  left: item.value >= 0 ? 0 : 'auto',
                  backgroundColor: item.color
                }}
              />
            </div>
            <div className="w-16 text-sm text-right text-slate-300">
              {item.value.toLocaleString('fa-IR')}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-end gap-2" style={{ height }}>
      {data.map((item, index) => (
        <div
          key={index}
          className="flex-1 flex flex-col items-center gap-1"
        >
          <div
            className={`w-full rounded-t ${
              item.value >= 0
                ? item.color ? '' : 'bg-emerald-500/50'
                : item.color ? '' : 'bg-rose-500/50'
            }`}
            style={{
              height: `${(Math.abs(item.value) / max) * 100}%`,
              minHeight: 4,
              backgroundColor: item.color
            }}
          />
          <div className="text-xs text-slate-500 truncate max-w-full">
            {item.label}
          </div>
        </div>
      ))}
    </div>
  );
}

// نمودار دایره‌ای
interface PieChartProps {
  data: Array<{
    label: string;
    value: number;
    color: string;
  }>;
  size?: number;
}

export function PieChart({ data, size = 200 }: PieChartProps) {
  const total = useMemo(() => {
    return data.reduce((sum, item) => sum + item.value, 0);
  }, [data]);

  const segments = useMemo(() => {
    let currentAngle = 0;
    return data.map((item) => {
      const angle = (item.value / total) * 360;
      const startAngle = currentAngle;
      currentAngle += angle;
      return {
        ...item,
        startAngle,
        endAngle: currentAngle,
        percentage: (item.value / total) * 100
      };
    });
  }, [data, total]);

  const createArc = (startAngle: number, endAngle: number) => {
    const start = {
      x: 50 + 40 * Math.cos((startAngle - 90) * (Math.PI / 180)),
      y: 50 + 40 * Math.sin((startAngle - 90) * (Math.PI / 180))
    };
    const end = {
      x: 50 + 40 * Math.cos((endAngle - 90) * (Math.PI / 180)),
      y: 50 + 40 * Math.sin((endAngle - 90) * (Math.PI / 180))
    };

    const largeArc = endAngle - startAngle > 180 ? 1 : 0;

    return `M 50 50 L ${start.x} ${start.y} A 40 40 0 ${largeArc} 1 ${end.x} ${end.y} Z`;
  };

  if (total === 0) {
    return (
      <div
        className="rounded-full bg-slate-800/30 flex items-center justify-center"
        style={{ width: size, height: size }}
      >
        <p className="text-slate-500 text-sm">داده‌ای نیست</p>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-4">
      <svg
        viewBox="0 0 100 100"
        style={{ width: size, height: size }}
      >
        {segments.map((segment, index) => (
          <path
            key={index}
            d={createArc(segment.startAngle, segment.endAngle)}
            fill={segment.color}
          />
        ))}
        <circle cx="50" cy="50" r="25" fill="rgb(15, 23, 42)" />
      </svg>

      <div className="space-y-2">
        {segments.map((segment, index) => (
          <div key={index} className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded"
              style={{ backgroundColor: segment.color }}
            />
            <span className="text-slate-300 text-sm">{segment.label}</span>
            <span className="text-slate-500 text-xs">
              ({segment.percentage.toFixed(1)}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// نمودار Kill Zone
interface KillZoneChartProps {
  sessions: Array<{
    name: string;
    start: number;
    end: number;
    color: string;
    active: boolean;
    profit: number;
  }>;
}

export function KillZoneChart({ sessions }: KillZoneChartProps) {
  return (
    <div className="bg-slate-800/30 rounded-lg p-4">
      <div className="flex items-center gap-1 h-8">
        {Array.from({ length: 24 }).map((_, hour) => {
          const session = sessions.find(
            (s) =>
              (s.start < s.end && hour >= s.start && hour < s.end) ||
              (s.start > s.end && (hour >= s.start || hour < s.end))
          );

          return (
            <div
              key={hour}
              className={`flex-1 h-full ${
                session
                  ? session.active
                    ? 'ring-1 ring-white/30'
                    : ''
                  : ''
              }`}
              style={{
                backgroundColor: session?.color || 'rgb(51, 65, 85)',
                opacity: session ? (session.active ? 1 : 0.5) : 0.3
              }}
              title={`${hour.toString().padStart(2, '0')}:00 UTC`}
            />
          );
        })}
      </div>

      <div className="flex justify-between mt-2 text-xs text-slate-500">
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>24:00</span>
      </div>

      <div className="flex flex-wrap gap-3 mt-4">
        {sessions.map((session) => (
          <div key={session.name} className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded"
              style={{ backgroundColor: session.color }}
            />
            <span className="text-slate-400 text-sm">{session.name}</span>
            {session.active && (
              <span className="text-xs text-emerald-400">(فعال)</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// نمودار کندلی ساده
export function SimpleCandlestickChart({ data, height = 200 }: CandlestickChartProps) {
  const { min, max, range } = useMemo(() => {
    if (data.length === 0) return { min: 0, max: 100, range: 100 };

    const allPrices = data.flatMap(d => [d.high, d.low]);
    const min = Math.min(...allPrices);
    const max = Math.max(...allPrices);
    return { min, max, range: max - min || 1 };
  }, [data]);

  const candleWidth = 100 / (data.length || 1);

  if (data.length === 0) {
    return (
      <div
        className="bg-slate-800/30 rounded-lg flex items-center justify-center"
        style={{ height }}
      >
        <p className="text-slate-500">داده‌ای یافت نشد</p>
      </div>
    );
  }

  return (
    <div style={{ height }}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
        {data.map((candle, index) => {
          const x = index * candleWidth + candleWidth / 2;
          const isBullish = candle.close >= candle.open;

          const openY = 100 - ((candle.open - min) / range) * 100;
          const closeY = 100 - ((candle.close - min) / range) * 100;
          const highY = 100 - ((candle.high - min) / range) * 100;
          const lowY = 100 - ((candle.low - min) / range) * 100;

          const color = isBullish ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)';

          return (
            <g key={index}>
              {/* Wick */}
              <line
                x1={x}
                y1={highY}
                x2={x}
                y2={lowY}
                stroke={color}
                strokeWidth="0.5"
              />

              {/* Body */}
              <rect
                x={x - candleWidth * 0.3}
                y={Math.min(openY, closeY)}
                width={candleWidth * 0.6}
                height={Math.abs(closeY - openY) || 0.5}
                fill={isBullish ? color : color}
                stroke={color}
                strokeWidth="0.2"
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}
