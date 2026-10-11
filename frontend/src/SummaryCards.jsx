import React, { useEffect, useState, useRef } from 'react';
import useStore from './store';
import './SummaryCards.css';

const CARDS = [
  {
    key: 'num_active_tickers',
    label: 'Active Tickers',
    icon: 'trending_up',
    gradient: 'var(--gradient-card-blue)',
    accent: 'var(--accent-blue)',
  },
  {
    key: 'changed_weights_latest',
    label: 'Changed Weights',
    icon: 'swap_vert',
    gradient: 'var(--gradient-card-purple)',
    accent: 'var(--accent-purple)',
  },
  {
    key: 'total_events_processed',
    label: 'Events Processed',
    icon: 'bolt',
    gradient: 'var(--gradient-card-cyan)',
    accent: 'var(--accent-cyan)',
  },
  {
    key: 'pos_sentiment_events',
    label: 'Positive Signals',
    icon: 'thumb_up',
    gradient: 'var(--gradient-card-green)',
    accent: 'var(--accent-green)',
  },
  {
    key: 'neg_sentiment_events',
    label: 'Negative Signals',
    icon: 'thumb_down',
    gradient: 'var(--gradient-card-red)',
    accent: 'var(--accent-red)',
  },
  {
    key: 'latest_timestamp',
    label: 'Latest Timestamp',
    icon: 'schedule',
    gradient: 'var(--gradient-card-orange)',
    accent: 'var(--accent-orange)',
    isTimestamp: true,
  },
];

function AnimatedNumber({ value, duration = 800 }) {
  const [display, setDisplay] = useState(0);
  const rafRef = useRef(null);
  const startRef = useRef(null);

  useEffect(() => {
    const target = Number(value) || 0;
    const start = display;
    startRef.current = performance.now();

    function animate(now) {
      const elapsed = now - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out quad
      const eased = 1 - (1 - progress) * (1 - progress);
      setDisplay(Math.round(start + (target - start) * eased));
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      }
    }

    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value]);

  return <span>{display}</span>;
}

function formatTimestamp(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return ts;
  }
}

export default function SummaryCards() {
  const summary = useStore((s) => s.summary);

  return (
    <div className="kpi-grid">
      {CARDS.map((card, i) => {
        const rawValue = summary[card.key];
        const isNumber = !card.isTimestamp && typeof rawValue === 'number';

        return (
          <div
            key={card.key}
            className="kpi-card animate-fade-in-up"
            style={{
              background: card.gradient,
              animationDelay: `${i * 60}ms`,
            }}
          >
            <div className="kpi-icon" style={{ color: card.accent }}>
              <span className="material-icons-outlined">{card.icon}</span>
            </div>
            <div className="kpi-content">
              <span className="kpi-label">{card.label}</span>
              <span
                className={`kpi-value ${card.isTimestamp ? 'kpi-value-timestamp' : ''}`}
                style={{ color: card.accent }}
                title={card.isTimestamp && rawValue ? (formatTimestamp(rawValue) || String(rawValue)) : undefined}
              >
                {isNumber ? (
                  <AnimatedNumber value={rawValue} />
                ) : card.isTimestamp ? (
                  formatTimestamp(rawValue)
                ) : (
                  rawValue ?? '—'
                )}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
