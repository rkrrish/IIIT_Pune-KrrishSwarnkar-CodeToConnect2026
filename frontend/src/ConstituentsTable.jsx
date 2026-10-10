import React, { useState, useMemo } from 'react';
import useStore from './store';
import './ConstituentsTable.css';

export default function ConstituentsTable({ onTickerClick }) {
  const constituents = useStore((s) => s.constituents);
  const [sortKey, setSortKey] = useState('current_weight');
  const [sortDir, setSortDir] = useState('desc');

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  // Ensure initial_rank, current_rank, and rank_change are computed reliably
  const enrichedConstituents = useMemo(() => {
    if (!constituents.length) return [];

    // Sort by base_weight descending to assign initial ranks
    const sortedBase = [...constituents].sort((a, b) => (b.base_weight ?? 0) - (a.base_weight ?? 0));
    const initRanks = new Map();
    sortedBase.forEach((item, idx) => initRanks.set(item.ticker, idx + 1));

    // Sort by current_weight descending to assign current ranks
    const sortedCurrent = [...constituents].sort((a, b) => (b.current_weight ?? 0) - (a.current_weight ?? 0));
    const currRanks = new Map();
    sortedCurrent.forEach((item, idx) => currRanks.set(item.ticker, idx + 1));

    return constituents.map((item) => {
      const initR = item.initial_rank ?? initRanks.get(item.ticker) ?? 1;
      const currR = item.current_rank ?? currRanks.get(item.ticker) ?? 1;
      const rankChange = item.rank_change ?? (initR - currR);
      return {
        ...item,
        initial_rank: initR,
        current_rank: currR,
        rank_change: rankChange,
      };
    });
  }, [constituents]);

  const sorted = useMemo(() => {
    return [...enrichedConstituents].sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      if (typeof av === 'string') return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortDir === 'asc' ? av - bv : bv - av;
    });
  }, [enrichedConstituents, sortKey, sortDir]);

  const columns = [
    { key: 'ticker', label: 'Ticker' },
    { key: 'name', label: 'Company' },
    { key: 'sector', label: 'Sector' },
    { key: 'base_weight', label: 'Base Wt', format: (v) => `${(v * 100).toFixed(2)}%` },
    { key: 'current_weight', label: 'Current Wt', format: (v) => `${(v * 100).toFixed(2)}%` },
    {
      key: 'weight_change',
      label: 'Change',
      format: (v) => {
        const pct = (v * 100).toFixed(2);
        const sign = v > 0 ? '+' : '';
        return `${sign}${pct}%`;
      },
      colorize: true,
    },
    {
      key: 'rank_change',
      label: 'Index Move',
      customRender: (item) => {
        const change = item.rank_change ?? 0;
        if (change > 0) {
          return (
            <span
              className="rank-movement rank-up"
              title={`Moved UP ${change} position(s) in index (Initial Rank #${item.initial_rank} → Current Rank #${item.current_rank})`}
            >
              <span className="triangle-up">▲</span> +{change}
            </span>
          );
        }
        if (change < 0) {
          return (
            <span
              className="rank-movement rank-down"
              title={`Moved DOWN ${Math.abs(change)} position(s) in index (Initial Rank #${item.initial_rank} → Current Rank #${item.current_rank})`}
            >
              <span className="triangle-down">▼</span> {change}
            </span>
          );
        }
        return (
          <span
            className="rank-movement rank-neutral"
            title={`Index position unchanged (Rank #${item.initial_rank || '—'})`}
          >
            —
          </span>
        );
      },
    },
  ];

  return (
    <div className="constituents-container">
      <div className="section-header">
        <span className="material-icons-outlined section-icon">analytics</span>
        <h2>S&P 100 Index Constituents</h2>
        <span className="badge">{constituents.length} tickers</span>
      </div>
      <div className="table-wrapper">
        <table className="constituents-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className={sortKey === col.key ? 'sorted' : ''}
                >
                  {col.label}
                  {sortKey === col.key && (
                    <span className="sort-arrow">{sortDir === 'asc' ? '↑' : '↓'}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.length > 0 ? (
              sorted.map((item, idx) => (
                <tr
                  key={item.ticker}
                  className="animate-fade-in-up"
                  style={{ animationDelay: `${idx * 20}ms` }}
                  onClick={() => onTickerClick && onTickerClick(item.ticker)}
                >
                  {columns.map((col) => {
                    if (col.customRender) {
                      return <td key={col.key}>{col.customRender(item)}</td>;
                    }
                    const raw = item[col.key];
                    const formatted = col.format ? col.format(raw) : raw;
                    let cls = '';
                    if (col.colorize) {
                      cls = raw > 0 ? 'positive' : raw < 0 ? 'negative' : '';
                    }
                    return (
                      <td key={col.key} className={cls}>
                        {col.key === 'ticker' ? (
                          <span className="ticker-badge">{formatted}</span>
                        ) : (
                          formatted ?? '—'
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns.length} className="empty-state">
                  <span className="material-icons-outlined">info</span>
                  Run the pipeline to see index data with NLP-adjusted weights
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
