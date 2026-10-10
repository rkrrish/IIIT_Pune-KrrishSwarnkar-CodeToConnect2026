import React, { useState } from 'react';
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

  const sorted = [...constituents].sort((a, b) => {
    const av = a[sortKey] ?? 0;
    const bv = b[sortKey] ?? 0;
    if (typeof av === 'string') return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    return sortDir === 'asc' ? av - bv : bv - av;
  });

  const columns = [
    { key: 'ticker', label: 'Ticker' },
    { key: 'name', label: 'Company' },
    { key: 'sector', label: 'Sector' },
    { key: 'base_weight', label: 'Base Wt', format: (v) => `${(v * 100).toFixed(2)}%` },
    { key: 'current_weight', label: 'Current Wt', format: (v) => `${(v * 100).toFixed(2)}%` },
    { key: 'weight_change', label: 'Change', format: (v) => {
      const pct = (v * 100).toFixed(2);
      const sign = v > 0 ? '+' : '';
      return `${sign}${pct}%`;
    }, colorize: true },
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
                  style={{ animationDelay: `${idx * 25}ms` }}
                  onClick={() => onTickerClick && onTickerClick(item.ticker)}
                >
                  {columns.map((col) => {
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
