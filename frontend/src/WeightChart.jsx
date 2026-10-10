import React, { useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, ReferenceLine
} from 'recharts';
import useStore from './store';
import './WeightChart.css';

// Curated palette for up to 20 tickers
// Curated institutional palette for up to 20 tickers
const COLORS = [
  '#1e40af', // Navy
  '#0d9488', // Soft Teal
  '#b91c1c', // Restrained Red
  '#d97706', // Restrained Amber
  '#4f46e5', // Indigo
  '#0284c7', // Slate Blue
  '#15803d', // Restrained Green
  '#7c3aed', // Violet
  '#c05621', // Terracotta
  '#0891b2', // Muted Cyan
  '#475569', // Slate
  '#9f1239', // Rose
  '#047857', // Emerald
  '#4338ca', // Cobalt
  '#b45309', // Dark Amber
  '#0369a1', // Ocean Blue
  '#6b21a8', // Deep Purple
  '#334155', // Dark Slate
  '#0e7490', // Teal-Blue
  '#a16207', // Dark Gold
];

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">Step {label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: p.color }} />
          <span className="chart-tooltip-ticker">{p.dataKey}</span>
          <span className="chart-tooltip-value">{(p.value * 100).toFixed(2)}%</span>
        </div>
      ))}
    </div>
  );
}

export default function WeightChart({ selectedTicker }) {
  const weightHistory = useStore((s) => s.weightHistory);
  const { tickers = [], series = {} } = weightHistory;

  // Build unified time-series: each row = { step, NVDA: weight, AAPL: weight, ... }
  const chartData = useMemo(() => {
    if (!tickers.length) return [];

    // Find max steps across all tickers
    let maxSteps = 0;
    const tickerData = {};
    for (const t of tickers) {
      const points = series[t] || [];
      tickerData[t] = points;
      if (points.length > maxSteps) maxSteps = points.length;
    }

    // Build rows by step index per ticker
    // Since different tickers may have different step counts,
    // we'll create one row per unique step across all tickers
    const stepMap = new Map();
    for (const t of tickers) {
      const points = tickerData[t] || [];
      for (const pt of points) {
        if (!stepMap.has(pt.step)) {
          stepMap.set(pt.step, { step: pt.step });
        }
        stepMap.get(pt.step)[t] = pt.weight;
      }
    }

    return Array.from(stepMap.values()).sort((a, b) => a.step - b.step);
  }, [tickers, series]);

  // Determine which tickers to show
  const visibleTickers = selectedTicker
    ? tickers.filter((t) => t === selectedTicker)
    : tickers;

  // Highlight tickers with major weight changes (> 2% from base)
  const majorChangeTickers = useMemo(() => {
    const result = new Set();
    for (const t of tickers) {
      const points = series[t] || [];
      if (points.length >= 2) {
        const first = points[0].weight;
        const last = points[points.length - 1].weight;
        if (Math.abs(last - first) > 0.02) result.add(t);
      }
    }
    return result;
  }, [tickers, series]);

  if (chartData.length === 0) {
    return (
      <div className="chart-container">
        <div className="section-header">
          <span className="material-icons-outlined section-icon">show_chart</span>
          <h2>Weight Evolution Over Time</h2>
        </div>
        <div className="chart-empty">
          <span className="material-icons-outlined">insert_chart_outlined</span>
          <p>Run the pipeline to see weight evolution data</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chart-container">
      <div className="section-header">
        <span className="material-icons-outlined section-icon">show_chart</span>
        <h2>
          {selectedTicker
            ? `Weight History — ${selectedTicker}`
            : 'Portfolio Weight Evolution'}
        </h2>
        {majorChangeTickers.size > 0 && !selectedTicker && (
          <div className="major-change-badges">
            {Array.from(majorChangeTickers).map((t) => (
              <span key={t} className="major-badge">{t}</span>
            ))}
            <span className="major-label">major Δ</span>
          </div>
        )}
      </div>
      <div className="chart-area">
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
            <defs>
              <linearGradient id="chartBg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="rgba(29, 78, 216, 0.04)" />
                <stop offset="100%" stopColor="transparent" />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#e5e1d8"
              vertical={false}
            />
            <XAxis
              dataKey="step"
              tick={{ fill: '#71717a', fontSize: 11 }}
              axisLine={{ stroke: '#d6d0c4' }}
              tickLine={false}
              label={{ value: 'Pipeline Step', position: 'insideBottom', offset: -5, fill: '#71717a', fontSize: 11 }}
            />
            <YAxis
              tick={{ fill: '#71717a', fontSize: 11 }}
              axisLine={{ stroke: '#d6d0c4' }}
              tickLine={false}
              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              domain={['auto', 'auto']}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 11, color: '#52525b', paddingTop: 10 }}
              iconType="circle"
              iconSize={8}
            />
            {visibleTickers.map((ticker, idx) => {
              const colorIndex = tickers.indexOf(ticker);
              const isMajor = majorChangeTickers.has(ticker);
              return (
                <Line
                  key={ticker}
                  type="monotone"
                  dataKey={ticker}
                  stroke={COLORS[colorIndex % COLORS.length]}
                  strokeWidth={isMajor || selectedTicker ? 2.5 : 1.2}
                  dot={false}
                  activeDot={{
                    r: 5,
                    stroke: COLORS[colorIndex % COLORS.length],
                    strokeWidth: 2,
                    fill: '#fcfbf8',
                  }}
                  opacity={selectedTicker ? 1 : isMajor ? 0.95 : 0.65}
                  connectNulls
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
