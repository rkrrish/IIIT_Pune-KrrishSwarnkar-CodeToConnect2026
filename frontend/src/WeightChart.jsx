import React, { useState, useMemo } from 'react';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, ReferenceLine
} from 'recharts';
import useStore from './store';
import './WeightChart.css';

// Curated institutional color palette for 20 tickers
const COLORS = [
  '#1e40af', '#0d9488', '#b91c1c', '#d97706', '#4f46e5',
  '#0284c7', '#15803d', '#7c3aed', '#c05621', '#0891b2',
  '#475569', '#9f1239', '#047857', '#4338ca', '#b45309',
  '#0369a1', '#6b21a8', '#334155', '#0e7490', '#a16207',
];

function GFTooltip({ active, payload, label, baseValue }) {
  if (!active || !payload?.length) return null;
  const currentVal = payload[0].value;
  const diff = currentVal - baseValue;
  const pctChange = baseValue !== 0 ? (diff / baseValue) * 100 : 0;
  const isPos = diff >= 0;

  return (
    <div className="gf-tooltip">
      <div className="gf-tooltip-header">Pipeline Step {label} {label === 0 ? '(Base)' : ''}</div>
      <div className="gf-tooltip-body">
        <span className="gf-tooltip-price">{(currentVal * 100).toFixed(2)}%</span>
        <span className={`gf-tooltip-change ${isPos ? 'pos' : 'neg'}`}>
          {isPos ? '+' : ''}{pctChange.toFixed(2)}%
        </span>
      </div>
    </div>
  );
}

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

  const [chartMode, setChartMode] = useState('line');
  const [internalTickerFilter, setInternalTickerFilter] = useState('ALL');

  const activeTicker = selectedTicker || (internalTickerFilter !== 'ALL' ? internalTickerFilter : null);

  const handleTickerSelect = (t) => {
    setInternalTickerFilter(t);
    if (onSelectTicker) {
      onSelectTicker(t === 'ALL' ? null : t);
    }
  };

  // 1. Data for Top Single Line Index Area Chart
  const { gfChartData, baseIndexValue, latestValue, netChangePct, isPositive } = useMemo(() => {
    if (!tickers.length) {
      return { gfChartData: [], baseIndexValue: 1, latestValue: 1, netChangePct: 0, isPositive: true };
    }

    let maxSteps = 0;
    for (const t of tickers) {
      const points = series[t] || [];
      if (points.length > maxSteps) maxSteps = points.length;
    }

    const data = [];
    for (let s = 0; s < maxSteps; s++) {
      let stepTotalWeight = 0;
      for (const t of tickers) {
        const points = series[t] || [];
        const pt = points.find((p) => p.step === s);
        if (activeTicker) {
          if (t === activeTicker && pt) stepTotalWeight = pt.weight;
        } else {
          if (pt) stepTotalWeight += pt.weight;
        }
      }

      data.push({
        step: s,
        value: stepTotalWeight,
      });
    }

    const first = data[0]?.value || 0;
    const last = data[data.length - 1]?.value || 0;
    const diff = last - first;
    const pct = first !== 0 ? (diff / first) * 100 : 0;

    return {
      gfChartData: data,
      baseIndexValue: first,
      latestValue: last,
      netChangePct: pct,
      isPositive: diff >= 0,
    };
  }, [tickers, series, activeTicker]);

  // 2. Data for Multi-Ticker Line Chart (Reverted to original single-line structure per ticker)[cite: 1]
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

  // 3. Data for Bar Chart
  const barChartData = useMemo(() => {
    if (activeTicker) {
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

    if (constituents.length > 0) {
      return constituents.map((item) => ({
        ticker: item.ticker,
        name: item.name,
        base_weight: item.base_weight,
        current_weight: item.current_weight,
        weight_change: item.weight_change,
      })).sort((a, b) => b.weight_change - a.weight_change);
    }

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
    <div className="charts-wrapper">
      {/* ══════════════════════════════════════════════════════════ */}
      {/* CHART 1: Single-Line Market Graph (Website Theme Matching)  */}
      {/* ══════════════════════════════════════════════════════════ */}
      <div className="gf-chart-container">
        <div className="gf-header">
          <div className="gf-ticker-title">
            <h2>{activeTicker ? `${activeTicker} Market Trajectory` : 'Market Overview'}</h2>
            {activeTicker && (
              <button className="gf-clear-btn" onClick={() => handleTickerSelect('ALL')}>
                Reset View
              </button>
            )}
          </div>

          <div className="gf-metrics">
            <span className="gf-main-price">{(latestValue * 100).toFixed(2)}%</span>
            <span className={`gf-badge ${isPositive ? 'pos' : 'neg'}`}>
              {isPositive ? '↑' : '↓'} {Math.abs(netChangePct).toFixed(2)}%
            </span>
          </div>
        </div>

        <div className="gf-chart-area">
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={gfChartData} margin={{ top: 15, right: 15, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="themeBlueGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2563eb" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#2563eb" stopOpacity={0.0} />
                </linearGradient>
              </defs>

              <CartesianGrid strokeDasharray="3 3" stroke="#e5e1d8" vertical={false} />
              <XAxis
                dataKey="step"
                tick={{ fill: '#71717a', fontSize: 11 }}
                axisLine={{ stroke: '#d6d0c4' }}
                tickLine={false}
                tickFormatter={(v) => (v === 0 ? 'Base' : `Step ${v}`)}
              />
              <YAxis
                tick={{ fill: '#71717a', fontSize: 11 }}
                axisLine={{ stroke: '#d6d0c4' }}
                tickLine={false}
                tickFormatter={(v) => `${(v * 100).toFixed(1)}%`}
                domain={['auto', 'auto']}
              />
              <Tooltip content={<GFTooltip baseValue={baseIndexValue} />} />
              <ReferenceLine
                y={baseIndexValue}
                stroke="#94a3b8"
                strokeDasharray="2 2"
                label={{ value: 'Baseline Benchmark', fill: '#71717a', fontSize: 10, position: 'right' }}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#1d4ed8"
                strokeWidth={2.5}
                fillOpacity={1}
                fill="url(#themeBlueGradient)"
                activeDot={{ r: 5, stroke: '#1d4ed8', strokeWidth: 2, fill: '#ffffff' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════ */}
      {/* CHART 2: Multi-Ticker Line / Bar Section (Original Style)  */}
      {/* ══════════════════════════════════════════════════════════ */}
      <div className="chart-container">
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
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

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

        {/* Quick Filter Pills */}
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

        {/* Chart Area */}
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
              <BarChart data={barChartData} margin={{ top: 15, right: 25, left: 10, bottom: 25 }}>
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
                      return <Cell key={`cell-${index}`} fill={COLORS[tickers.indexOf(activeTicker) % COLORS.length]} />;
                    }
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
    </div>
  );
}