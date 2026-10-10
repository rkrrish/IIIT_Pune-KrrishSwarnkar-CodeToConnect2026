import React, { useState, useMemo } from 'react';
import {
  LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, ReferenceLine
} from 'recharts';
import useStore from './store';
import './WeightChart.css';

// Curated institutional color palette for 20 tickers
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

function LineTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">Pipeline Step {label}</div>
      {payload.map((p) => {
        const valPct = (p.value * 100).toFixed(2);
        return (
          <div key={p.dataKey} className="chart-tooltip-row">
            <span className="chart-tooltip-dot" style={{ background: p.color }} />
            <span className="chart-tooltip-ticker">{p.dataKey}</span>
            <span className="chart-tooltip-value">{valPct}%</span>
          </div>
        );
      })}
    </div>
  );
}

function BarTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload;
  const changePct = (data.weight_change * 100).toFixed(2);
  const sign = data.weight_change > 0 ? '+' : '';

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{data.ticker} — {data.name || data.ticker}</div>
      <div className="chart-tooltip-row">
        <span>Base Weight:</span>
        <span className="chart-tooltip-value">{(data.base_weight * 100).toFixed(2)}%</span>
      </div>
      <div className="chart-tooltip-row">
        <span>Current Weight:</span>
        <span className="chart-tooltip-value">{(data.current_weight * 100).toFixed(2)}%</span>
      </div>
      <div className="chart-tooltip-row">
        <span>Net Change:</span>
        <span className={`chart-tooltip-value ${data.weight_change > 0 ? 'pos' : data.weight_change < 0 ? 'neg' : ''}`}>
          {sign}{changePct}%
        </span>
      </div>
    </div>
  );
}

export default function WeightChart({ selectedTicker, onSelectTicker }) {
  const weightHistory = useStore((s) => s.weightHistory);
  const constituents = useStore((s) => s.constituents);
  const { tickers = [], series = {} } = weightHistory;

  const [chartMode, setChartMode] = useState('line'); // 'line' | 'bar'
  const [internalTickerFilter, setInternalTickerFilter] = useState('ALL');

  // Combined ticker filter (prop takes precedence if selected via table/ledger, else internal selector)
  const activeTicker = selectedTicker || (internalTickerFilter !== 'ALL' ? internalTickerFilter : null);

  const handleTickerSelect = (t) => {
    setInternalTickerFilter(t);
    if (onSelectTicker) {
      onSelectTicker(t === 'ALL' ? null : t);
    }
  };

  // Build unified time-series for Line Chart: row = { step, NVDA: weight, AAPL: weight, ... }
  const lineChartData = useMemo(() => {
    if (!tickers.length) return [];

    let maxSteps = 0;
    for (const t of tickers) {
      const points = series[t] || [];
      if (points.length > maxSteps) maxSteps = points.length;
    }

    const stepMap = new Map();
    for (let s = 0; s < maxSteps; s++) {
      stepMap.set(s, { step: s });
    }

    for (const t of tickers) {
      const points = series[t] || [];
      for (const pt of points) {
        if (!stepMap.has(pt.step)) {
          stepMap.set(pt.step, { step: pt.step });
        }
        stepMap.get(pt.step)[t] = pt.weight;
      }
    }

    return Array.from(stepMap.values()).sort((a, b) => a.step - b.step);
  }, [tickers, series]);

  // Build data for Bar Chart
  const barChartData = useMemo(() => {
    if (activeTicker) {
      // Bar Chart for a specific ticker across pipeline steps
      const points = series[activeTicker] || [];
      return points.map((pt) => ({
        stepLabel: `Step ${pt.step}`,
        step: pt.step,
        ticker: activeTicker,
        current_weight: pt.weight,
        base_weight: pt.base_weight,
        weight_change: pt.weight_change,
      }));
    }

    // Bar Chart for ALL tickers (showing current vs base change)
    if (constituents.length > 0) {
      return constituents.map((item) => ({
        ticker: item.ticker,
        name: item.name,
        base_weight: item.base_weight,
        current_weight: item.current_weight,
        weight_change: item.weight_change,
      })).sort((a, b) => b.weight_change - a.weight_change);
    }

    // Fallback from weightHistory
    return tickers.map((t) => {
      const points = series[t] || [];
      const latest = points[points.length - 1] || {};
      return {
        ticker: t,
        base_weight: latest.base_weight || 0,
        current_weight: latest.weight || 0,
        weight_change: latest.weight_change || 0,
      };
    }).sort((a, b) => b.weight_change - a.weight_change);
  }, [activeTicker, constituents, tickers, series]);

  const visibleTickers = activeTicker
    ? tickers.filter((t) => t === activeTicker)
    : tickers;

  // Major change tickers (> 1.5% delta)
  const majorChangeTickers = useMemo(() => {
    const result = new Set();
    for (const t of tickers) {
      const points = series[t] || [];
      if (points.length >= 2) {
        const first = points[0].weight;
        const last = points[points.length - 1].weight;
        if (Math.abs(last - first) > 0.015) result.add(t);
      }
    }
    return result;
  }, [tickers, series]);

  if (!tickers.length || lineChartData.length === 0) {
    return (
      <div className="chart-container">
        <div className="section-header">
          <span className="material-icons-outlined section-icon">show_chart</span>
          <h2>Portfolio Weight Evolution & Changes</h2>
        </div>
        <div className="chart-empty">
          <span className="material-icons-outlined">insert_chart_outlined</span>
          <p>Run the pipeline to observe ticker weight changes and trajectories</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chart-container">
      {/* ── Section Header with Controls ────────────────────────────── */}
      <div className="section-header chart-header-responsive">
        <div className="chart-title-group">
          <span className="material-icons-outlined section-icon">
            {chartMode === 'line' ? 'show_chart' : 'bar_chart'}
          </span>
          <h2>
            {activeTicker
              ? `${chartMode === 'line' ? 'Weight Evolution' : 'Weight Allocation'} — ${activeTicker}`
              : chartMode === 'line'
              ? 'Portfolio Weight Evolution'
              : 'Ticker Weight Changes (Relative to Base Index)'}
          </h2>
        </div>

        <div className="chart-controls">
          {/* Ticker Filter Selector */}
          <div className="control-group">
            <label htmlFor="ticker-select" className="control-label">Ticker:</label>
            <select
              id="ticker-select"
              className="ticker-select-dropdown"
              value={activeTicker || 'ALL'}
              onChange={(e) => handleTickerSelect(e.target.value)}
            >
              <option value="ALL">All Tickers (20)</option>
              {tickers.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          {/* Mode Switcher */}
          <div className="mode-toggle-group">
            <button
              className={`mode-btn ${chartMode === 'line' ? 'active' : ''}`}
              onClick={() => setChartMode('line')}
              title="Line Chart: Weight evolution over time steps"
            >
              <span className="material-icons-outlined btn-icon">show_chart</span>
              Line Graph
            </button>
            <button
              className={`mode-btn ${chartMode === 'bar' ? 'active' : ''}`}
              onClick={() => setChartMode('bar')}
              title="Bar Chart: Compare ticker weight changes"
            >
              <span className="material-icons-outlined btn-icon">bar_chart</span>
              Bar Graph
            </button>
          </div>
        </div>
      </div>

      {/* ── Ticker Filter Pills ──────────────────────────────────────── */}
      <div className="ticker-pills-bar">
        <span className="pills-label">Quick Filter:</span>
        <button
          className={`ticker-pill ${!activeTicker ? 'active' : ''}`}
          onClick={() => handleTickerSelect('ALL')}
        >
          All
        </button>
        {tickers.slice(0, 12).map((t, idx) => {
          const color = COLORS[idx % COLORS.length];
          const isSelected = activeTicker === t;
          const isMajor = majorChangeTickers.has(t);
          return (
            <button
              key={t}
              className={`ticker-pill ${isSelected ? 'active' : ''} ${isMajor ? 'major' : ''}`}
              onClick={() => handleTickerSelect(t)}
              style={{
                borderColor: isSelected ? color : undefined,
                color: isSelected ? '#ffffff' : undefined,
                backgroundColor: isSelected ? color : undefined,
              }}
            >
              {t} {isMajor && <span className="pill-dot" />}
            </button>
          );
        })}
        {activeTicker && (
          <button className="clear-pill" onClick={() => handleTickerSelect('ALL')}>
            <span className="material-icons-outlined">close</span> Clear Filter
          </button>
        )}
      </div>

      {/* ── Chart Area ──────────────────────────────────────────────── */}
      <div className="chart-area">
        <ResponsiveContainer width="100%" height={380}>
          {chartMode === 'line' ? (
            <LineChart data={lineChartData} margin={{ top: 15, right: 25, left: 10, bottom: 15 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e1d8" vertical={false} />
              <XAxis
                dataKey="step"
                tick={{ fill: '#71717a', fontSize: 11 }}
                axisLine={{ stroke: '#d6d0c4' }}
                tickLine={false}
                tickFormatter={(v) => (v === 0 ? 'Base' : `Step ${v}`)}
                label={{ value: 'Pipeline Step', position: 'insideBottom', offset: -8, fill: '#71717a', fontSize: 11 }}
              />
              <YAxis
                tick={{ fill: '#71717a', fontSize: 11 }}
                axisLine={{ stroke: '#d6d0c4' }}
                tickLine={false}
                tickFormatter={(v) => `${(v * 100).toFixed(1)}%`}
                domain={['auto', 'auto']}
              />
              <Tooltip content={<LineTooltip />} />
              <Legend
                wrapperStyle={{ fontSize: 11, color: '#52525b', paddingTop: 12 }}
                iconType="circle"
                iconSize={8}
                onClick={(e) => handleTickerSelect(e.dataKey)}
              />
              {visibleTickers.map((ticker) => {
                const colorIndex = tickers.indexOf(ticker);
                const isSelected = activeTicker === ticker;
                const isMajor = majorChangeTickers.has(ticker);
                const strokeColor = COLORS[colorIndex % COLORS.length];

                return (
                  <Line
                    key={ticker}
                    type="monotone"
                    dataKey={ticker}
                    stroke={strokeColor}
                    strokeWidth={isSelected ? 3.5 : isMajor ? 2.5 : 1.5}
                    dot={{ r: isSelected ? 4 : 2, fill: strokeColor }}
                    activeDot={{
                      r: 6,
                      stroke: strokeColor,
                      strokeWidth: 2,
                      fill: '#ffffff',
                    }}
                    opacity={activeTicker ? (isSelected ? 1 : 0.25) : isMajor ? 0.95 : 0.7}
                    connectNulls
                  />
                );
              })}
            </LineChart>
          ) : (
            <BarChart
              data={barChartData}
              margin={{ top: 15, right: 25, left: 10, bottom: 25 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e1d8" vertical={false} />
              <XAxis
                dataKey={activeTicker ? 'stepLabel' : 'ticker'}
                tick={{ fill: '#475569', fontSize: 11, fontWeight: 500 }}
                axisLine={{ stroke: '#d6d0c4' }}
                tickLine={false}
                interval={0}
              />
              <YAxis
                tick={{ fill: '#71717a', fontSize: 11 }}
                axisLine={{ stroke: '#d6d0c4' }}
                tickLine={false}
                tickFormatter={(v) => `${(v * 100).toFixed(1)}%`}
              />
              <Tooltip content={<BarTooltip />} />
              <ReferenceLine y={0} stroke="#94a3b8" />
              <Bar
                dataKey={activeTicker ? 'current_weight' : 'weight_change'}
                name={activeTicker ? `${activeTicker} Weight` : 'Weight Change (%)'}
                radius={[4, 4, 0, 0]}
              >
                {barChartData.map((entry, index) => {
                  if (activeTicker) {
                    // For single ticker steps: color by index palette
                    return <Cell key={`cell-${index}`} fill={COLORS[tickers.indexOf(activeTicker) % COLORS.length]} />;
                  }
                  // For all tickers: Green if positive weight change, Red if negative
                  const val = entry.weight_change;
                  const barColor = val > 0 ? '#15803d' : val < 0 ? '#b91c1c' : '#94a3b8';
                  return <Cell key={`cell-${index}`} fill={barColor} />;
                })}
              </Bar>
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
