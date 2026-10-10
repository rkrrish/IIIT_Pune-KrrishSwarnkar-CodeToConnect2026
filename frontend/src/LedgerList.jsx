import React, { useRef, useEffect, useState } from 'react';
import useStore from './store';
import './LedgerList.css';

export default function LedgerList({ onInspect, onTickerClick }) {
  const ledger = useStore((s) => s.ledger);
  const containerRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const prevCountRef = useRef(0);

  // Auto-scroll to bottom when new entries arrive (if user is at bottom)
  useEffect(() => {
    if (autoScroll && containerRef.current && ledger.length > prevCountRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
    prevCountRef.current = ledger.length;
  }, [ledger.length, autoScroll]);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 50);
  };

  const formatWeight = (w) => (w != null ? `${(w * 100).toFixed(2)}%` : '—');
  const formatSentiment = (s) => (s != null ? s.toFixed(3) : '—');
  const formatImpact = (i) => (i != null ? i.toFixed(1) : '—');

  return (
    <div className="ledger-container">
      <div className="section-header">
        <span className="material-icons-outlined section-icon">receipt_long</span>
        <h2>Rebalance Ledger</h2>
        <span className="badge">{ledger.length} entries</span>
      </div>
      <div className="ledger-scroll" ref={containerRef} onScroll={handleScroll}>
        <table className="ledger-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Timestamp</th>
              <th>Ticker</th>
              <th>Old Wt</th>
              <th>New Wt</th>
              <th>Δ Weight</th>
              <th>Sentiment</th>
              <th>Impact</th>
              <th>Inspect</th>
            </tr>
          </thead>
          <tbody>
            {ledger.length > 0 ? (
              ledger.map((entry, idx) => {
                const isNew = idx >= prevCountRef.current - 1 && idx === ledger.length - 1;
                const delta = (entry.new_weight || 0) - (entry.old_weight || 0);
                const deltaClass = delta > 0.001 ? 'positive' : delta < -0.001 ? 'negative' : '';

                return (
                  <tr
                    key={entry._id ?? idx}
                    className={`ledger-row ${isNew ? 'ledger-row-new' : ''}`}
                    style={{ animationDelay: `${(idx % 20) * 20}ms` }}
                  >
                    <td className="row-num">{idx + 1}</td>
                    <td className="mono-cell">{entry.timestamp || '—'}</td>
                    <td>
                      <button
                        className="ticker-link"
                        onClick={() => onTickerClick && onTickerClick(entry.ticker)}
                      >
                        {entry.ticker}
                      </button>
                    </td>
                    <td className="mono-cell">{formatWeight(entry.old_weight)}</td>
                    <td className="mono-cell">{formatWeight(entry.new_weight)}</td>
                    <td className={`mono-cell ${deltaClass}`}>
                      {delta > 0 ? '+' : ''}{(delta * 100).toFixed(2)}%
                    </td>
                    <td className={`mono-cell ${(entry.rolling_sentiment_avg || 0) > 0 ? 'positive' : (entry.rolling_sentiment_avg || 0) < 0 ? 'negative' : ''}`}>
                      {formatSentiment(entry.rolling_sentiment_avg)}
                    </td>
                    <td className="mono-cell">{formatImpact(entry.impact_score)}</td>
                    <td>
                      <button
                        className="inspect-btn"
                        onClick={() => onInspect(entry, idx)}
                        title="Inspect entry details"
                      >
                        <span className="material-icons-outlined">search</span>
                      </button>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={9} className="empty-state">
                  <span className="material-icons-outlined">inbox</span>
                  No ledger entries yet. Click "Next Timestep" or "Run Pipeline" to begin.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
