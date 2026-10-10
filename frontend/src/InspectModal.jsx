import React, { useEffect, useState } from 'react';
import { fetchLedgerEntry } from './api';
import './InspectModal.css';

const TABS = [
  { key: 'overview', label: 'Overview', icon: 'info' },
  { key: 'signals', label: 'Risk Signals', icon: 'sensors' },
  { key: 'raw', label: 'Raw Data', icon: 'code' },
];

export default function InspectModal({ entry, entryIndex, onClose }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [enriched, setEnriched] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (entry == null) return;
    setLoading(true);
    const id = entry._id ?? entryIndex;
    fetchLedgerEntry(id)
      .then((data) => {
        setEnriched(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to fetch entry details:', err);
        setEnriched(null);
        setLoading(false);
      });
  }, [entry, entryIndex]);

  if (!entry) return null;

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  const delta = (entry.new_weight || 0) - (entry.old_weight || 0);
  const deltaStr = `${delta > 0 ? '+' : ''}${(delta * 100).toFixed(3)}%`;
  const tickerSummary = enriched?.ticker_summary || {};
  const signals = enriched?.risk_signals || [];

  return (
    <div className="modal-overlay animate-fade-in" onClick={handleOverlayClick}>
      <div className="modal-glass animate-fade-in-up">
        {/* Header */}
        <div className="modal-header">
          <div className="modal-header-left">
            <span className="modal-ticker">{entry.ticker}</span>
            <span className="modal-subtitle">Ledger Entry #{(entry._id ?? entryIndex) + 1}</span>
          </div>
          <button className="modal-close" onClick={onClose} title="Close">
            <span className="material-icons-outlined">close</span>
          </button>
        </div>

        {/* Tabs */}
        <div className="modal-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              className={`modal-tab ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              <span className="material-icons-outlined tab-icon">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="modal-body">
          {loading ? (
            <div className="modal-loading">
              <span className="material-icons-outlined spin">autorenew</span>
              Loading details...
            </div>
          ) : (
            <>
              {activeTab === 'overview' && (
                <div className="tab-content animate-fade-in">
                  <div className="inspect-grid">
                    <div className="inspect-item">
                      <span className="inspect-label">Timestamp</span>
                      <span className="inspect-value mono">{entry.timestamp || '—'}</span>
                    </div>
                    <div className="inspect-item">
                      <span className="inspect-label">Old Weight</span>
                      <span className="inspect-value mono">{(entry.old_weight * 100).toFixed(3)}%</span>
                    </div>
                    <div className="inspect-item">
                      <span className="inspect-label">New Weight</span>
                      <span className="inspect-value mono">{(entry.new_weight * 100).toFixed(3)}%</span>
                    </div>
                    <div className="inspect-item">
                      <span className="inspect-label">Weight Change</span>
                      <span className={`inspect-value mono ${delta > 0 ? 'positive' : delta < 0 ? 'negative' : ''}`}>
                        {deltaStr}
                      </span>
                    </div>
                    <div className="inspect-item">
                      <span className="inspect-label">Rolling Sentiment</span>
                      <span className={`inspect-value mono ${(entry.rolling_sentiment_avg || 0) > 0 ? 'positive' : 'negative'}`}>
                        {entry.rolling_sentiment_avg?.toFixed(4) ?? '—'}
                      </span>
                    </div>
                    <div className="inspect-item">
                      <span className="inspect-label">Impact Score</span>
                      <span className="inspect-value mono">{entry.impact_score?.toFixed(2) ?? '—'}</span>
                    </div>
                    <div className="inspect-item">
                      <span className="inspect-label">Event ID</span>
                      <span className="inspect-value mono small">{entry.latest_event_id || '—'}</span>
                    </div>
                  </div>

                  {/* Ticker summary from risk engine */}
                  {Object.keys(tickerSummary).length > 0 && (
                    <div className="inspect-section">
                      <h4>
                        <span className="material-icons-outlined">assessment</span>
                        NLP Risk Summary — {entry.ticker}
                      </h4>
                      <div className="inspect-grid">
                        <div className="inspect-item">
                          <span className="inspect-label">Company</span>
                          <span className="inspect-value">{tickerSummary.company_name}</span>
                        </div>
                        <div className="inspect-item">
                          <span className="inspect-label">Total Events</span>
                          <span className="inspect-value mono">{tickerSummary.total_events_observed}</span>
                        </div>
                        <div className="inspect-item">
                          <span className="inspect-label">EWMA Sentiment</span>
                          <span className="inspect-value mono">{tickerSummary.ewma_sentiment?.toFixed(4)}</span>
                        </div>
                        <div className="inspect-item">
                          <span className="inspect-label">Sentiment Momentum</span>
                          <span className="inspect-value mono">{tickerSummary.sentiment_momentum?.toFixed(4)}</span>
                        </div>
                        <div className="inspect-item">
                          <span className="inspect-label">Sentiment Volatility</span>
                          <span className="inspect-value mono">{tickerSummary.sentiment_volatility?.toFixed(4)}</span>
                        </div>
                        <div className="inspect-item">
                          <span className="inspect-label">Avg Impact</span>
                          <span className="inspect-value mono">{tickerSummary.average_impact_score?.toFixed(2)}</span>
                        </div>
                        <div className="inspect-item full-width">
                          <span className="inspect-label">Dominant Events</span>
                          <span className="inspect-value">
                            {(tickerSummary.dominant_event_types || []).map((t) => (
                              <span key={t} className="event-tag">{t}</span>
                            ))}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'signals' && (
                <div className="tab-content animate-fade-in">
                  {signals.length > 0 ? (
                    <div className="signals-list">
                      {signals.map((sig, i) => (
                        <div key={sig.event_id || i} className="signal-card">
                          <div className="signal-header">
                            <span className={`sentiment-badge ${sig.sentiment_label?.toLowerCase()}`}>
                              {sig.sentiment_label}
                            </span>
                            <span className="signal-source">{sig.source}</span>
                            <span className="signal-date">{sig.published_at}</span>
                          </div>
                          <p className="signal-text">{sig.text_snippet}</p>
                          <div className="signal-meta">
                            <span>Score: <strong>{sig.sentiment_score?.toFixed(3)}</strong></span>
                            <span>Impact: <strong>{sig.impact_score?.toFixed(1)}</strong></span>
                            <span>Event: <strong>{sig.event_classification}</strong></span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="modal-empty">
                      <span className="material-icons-outlined">sensors_off</span>
                      <p>No detailed risk signals available for this entry.</p>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'raw' && (
                <div className="tab-content animate-fade-in">
                  <pre className="raw-json">{JSON.stringify(enriched || entry, null, 2)}</pre>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
