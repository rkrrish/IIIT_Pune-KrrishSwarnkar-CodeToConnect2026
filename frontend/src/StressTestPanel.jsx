import React, { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import * as api from './api';
import './StressTestPanel.css';

// ── Helpers ──────────────────────────────────────────────────────────────────

const fmt = (n, decimals = 1) =>
  n == null ? '—' : Number(n).toFixed(decimals);

const fmtPct = (n) =>
  n == null ? '—' : `${n >= 0 ? '+' : ''}${Number(n).toFixed(2)}%`;

const fmtMM = (n) =>
  n == null ? '—' : `$${Math.abs(Number(n)).toFixed(1)}M`;

function sentimentColor(label) {
  if (!label) return 'var(--text-secondary)';
  const l = label.toLowerCase();
  if (l === 'negative') return 'var(--accent-red)';
  if (l === 'positive') return 'var(--accent-green)';
  return 'var(--text-muted)';
}

function shockColor(pct) {
  if (pct == null) return '#52525b';
  if (pct < 0) return '#b91c1c';   // loss
  if (pct > 0) return '#15803d';   // gain (flight-to-quality)
  return '#52525b';
}

function assetClassIcon(cls) {
  switch (cls) {
    case 'Corporate Term Loan':  return 'account_balance';
    case 'Corporate Bond':       return 'receipt_long';
    case 'Interest Rate Swap':   return 'swap_horiz';
    case 'Credit Default Swap':  return 'shield';
    case 'Sovereign Bond':       return 'flag';
    default:                     return 'inventory_2';
  }
}

// ── Sub-components ───────────────────────────────────────────────────────────

function TriggerBadge({ result }) {
  if (!result) return null;
  const triggered = result.triggered;
  return (
    <span className={`st-trigger-badge ${triggered ? 'triggered' : 'idle'}`}>
      <span className="material-icons-outlined">
        {triggered ? 'warning' : 'check_circle'}
      </span>
      {triggered ? `TRIGGERED — ${result.scenario_name}` : 'NO TRIGGER DETECTED'}
    </span>
  );
}

function SummaryKPI({ label, value, sub, highlight }) {
  return (
    <div className={`st-kpi ${highlight || ''}`}>
      <div className="st-kpi-value">{value}</div>
      <div className="st-kpi-label">{label}</div>
      {sub && <div className="st-kpi-sub">{sub}</div>}
    </div>
  );
}

function AnchorPrices({ anchors }) {
  if (!anchors) return null;
  const entries = Object.entries(anchors).filter(([, v]) => v != null);
  if (!entries.length) return (
    <span className="st-anchor-na">Live anchor prices unavailable (yfinance offline).</span>
  );
  return (
    <div className="st-anchors">
      {entries.map(([ticker, price]) => (
        <span key={ticker} className="st-anchor-chip">
          <strong>{ticker}</strong> ${Number(price).toFixed(2)}
        </span>
      ))}
    </div>
  );
}

function PortfolioComparisonBar({ before, after }) {
  if (!before || !after) return null;
  const loss = before - after;
  const pct = before > 0 ? (loss / before) * 100 : 0;
  const afterPct = (after / before) * 100;

  return (
    <div className="st-portfolio-bar-wrap">
      <div className="st-portfolio-bar-labels">
        <span className="st-pbl-before">Before: {fmtMM(before)}</span>
        <span className="st-pbl-after">After: {fmtMM(after)}</span>
      </div>
      <div className="st-portfolio-bar">
        <div
          className="st-portfolio-bar-after"
          style={{ width: `${Math.max(afterPct, 0)}%` }}
        />
        <div
          className="st-portfolio-bar-loss"
          style={{ width: `${Math.min(100 - afterPct, 100)}%` }}
        />
      </div>
      <div className="st-portfolio-bar-loss-label">
        Loss: <strong>{fmtMM(loss)}</strong> ({fmt(Math.abs(pct), 2)}%)
      </div>
    </div>
  );
}

function PositionRow({ pos, maxLoss }) {
  const isGain = pos.shock_pct > 0;
  const isLoss = pos.shock_pct < 0;
  const barWidth = maxLoss > 0 ? Math.min((Math.abs(pos.loss_mm) / maxLoss) * 100, 100) : 0;

  return (
    <div className={`st-pos-row ${isGain ? 'gain' : isLoss ? 'loss' : 'neutral'}`}>
      <div className="st-pos-left">
        <span className="material-icons-outlined st-pos-icon">
          {assetClassIcon(pos.asset_class)}
        </span>
        <div className="st-pos-info">
          <div className="st-pos-id">{pos.id}</div>
          <div className="st-pos-name">{pos.counterparty}</div>
          <div className="st-pos-meta">
            <span className="st-pos-class">{pos.asset_class}</span>
            <span className="st-pos-rating">{pos.rating}</span>
            <span className="st-pos-sector">{pos.sector}</span>
            <span className="st-pos-tenor">{pos.tenor_years}Y</span>
            {pos.market_price_anchor && (
              <span className="st-pos-anchor">{pos.anchor_ticker}: ${pos.market_price_anchor}</span>
            )}
          </div>
        </div>
      </div>
      <div className="st-pos-right">
        <div className="st-pos-values">
          <span className="st-pos-before">{fmtMM(pos.dollar_value_mm)}</span>
          <span className="material-icons-outlined st-pos-arrow">arrow_forward</span>
          <span className="st-pos-after" style={{ color: isLoss ? '#b91c1c' : isGain ? '#15803d' : 'inherit' }}>
            {fmtMM(pos.stressed_value_mm)}
          </span>
        </div>
        <div className="st-pos-shock" style={{ color: shockColor(pos.shock_pct) }}>
          {fmtPct(pos.shock_pct)}
          {isLoss && <> &nbsp;Loss: <strong>{fmtMM(pos.loss_mm)}</strong></>}
          {isGain && <> &nbsp;Gain: <strong>{fmtMM(Math.abs(pos.loss_mm))}</strong></>}
        </div>
        {barWidth > 0 && (
          <div className="st-pos-bar-wrap">
            <div
              className={`st-pos-bar ${isGain ? 'bar-gain' : 'bar-loss'}`}
              style={{ width: `${barWidth}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Panel ────────────────────────────────────────────────────────────────

export default function StressTestPanel() {
  const [result, setResult]             = useState(null);
  const [scenarios, setScenarios]       = useState([]);
  const [selectedScenario, setSelected] = useState('');
  const [loading, setLoading]           = useState(false);
  const [loadingInit, setLoadingInit]   = useState(true);

  // Load scenarios catalog + latest persisted result on mount
  useEffect(() => {
    let mounted = true;
    const init = async () => {
      try {
        const [sc, latest] = await Promise.all([
          api.fetchStressTestScenarios(),
          api.fetchStressTestLatest(),
        ]);
        if (!mounted) return;
        if (sc) setScenarios(sc);
        if (latest) setResult(latest);
      } catch {
        // non-fatal
      } finally {
        if (mounted) setLoadingInit(false);
      }
    };
    init();
    return () => { mounted = false; };
  }, []);

  const handleRun = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.runStressTest(true, selectedScenario || null);
      setResult(res);
      if (res.triggered) {
        toast.success(`Stress test complete — Scenario: ${res.scenario_name}`);
      } else {
        toast(`No high-impact trigger found. Showing baseline.`, { icon: 'ℹ️' });
      }
    } catch (err) {
      toast.error(`Stress test failed: ${err.message}`);
    }
    setLoading(false);
  }, [selectedScenario]);

  const handleAutoDetect = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.runStressTest(false, null);
      setResult(res);
      if (res.triggered) {
        toast.success(`Auto-trigger fired! Scenario: ${res.scenario_name} (Impact ${res.trigger_impact_score})`);
      } else {
        toast(`No qualifying high-impact event found in current signals.`, { icon: 'ℹ️' });
      }
    } catch (err) {
      toast.error(`Auto-detect failed: ${err.message}`);
    }
    setLoading(false);
  }, []);

  // Asset class composition (baseline) for mini donut labels
  const totalBaseline = BASELINE_PORTFOLIO_TOTALS.total;

  // Max loss across positions for bar scaling
  const maxLoss = result?.positions
    ? Math.max(...result.positions.map((p) => Math.abs(p.loss_mm || 0)), 1)
    : 1;

  return (
    <div className="stress-test-panel card">
      {/* ── Panel Header ─────────────────────────────────────────── */}
      <div className="section-header">
        <span className="material-icons-outlined section-icon">crisis_alert</span>
        <h2>Module B — Strategic Portfolio Stress Testing</h2>
        {result && <TriggerBadge result={result} />}
      </div>

      <div className="st-body">
        {/* ── Controls ─────────────────────────────────────────────── */}
        <div className="st-controls">
          <div className="st-control-group">
            <label className="st-label">Shock Scenario Override</label>
            <select
              className="st-select"
              value={selectedScenario}
              onChange={(e) => setSelected(e.target.value)}
              disabled={loading}
            >
              <option value="">— Auto-detect from NLP Signals —</option>
              {scenarios.map((s) => (
                <option key={s.name} value={s.name} title={s.description}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="st-action-group">
            <button
              className="btn btn-primary st-btn"
              onClick={handleRun}
              disabled={loading}
              title="Force-apply the selected (or default) stress scenario immediately"
            >
              <span className="material-icons-outlined btn-icon">bolt</span>
              {loading ? 'Running…' : 'Run Stress Test'}
            </button>
            <button
              className="btn btn-secondary st-btn"
              onClick={handleAutoDetect}
              disabled={loading}
              title="Auto-detect from current NLP Risk Engine signals (trigger only if Impact Score > 7)"
            >
              <span className="material-icons-outlined btn-icon">sensors</span>
              Auto-Detect Trigger
            </button>
          </div>
        </div>

        {/* ── Scenario Description ───────────────────────────────── */}
        {selectedScenario && (() => {
          const sc = scenarios.find((s) => s.name === selectedScenario);
          return sc ? (
            <div className="st-scenario-desc">
              <span className="material-icons-outlined">info</span>
              <em>{sc.description}</em>
            </div>
          ) : null;
        })()}

        {loadingInit && !result && (
          <div className="st-placeholder">
            <span className="material-icons-outlined st-ph-icon spin">sync</span>
            <p>Loading stress test data…</p>
          </div>
        )}

        {!loadingInit && !result && (
          <div className="st-placeholder">
            <span className="material-icons-outlined st-ph-icon">crisis_alert</span>
            <p>No stress test has been run yet.</p>
            <p className="st-ph-sub">
              Run the NLP Risk Engine pipeline first, then click <strong>Run Stress Test</strong> or
              <strong> Auto-Detect Trigger</strong>.
            </p>
          </div>
        )}

        {result && (
          <>
            {/* ── Trigger Info Strip ──────────────────────────────── */}
            {result.triggered && (
              <div className="st-trigger-strip">
                <div className="st-ts-item">
                  <span className="st-ts-label">Trigger Ticker</span>
                  <span className="st-ts-value ticker-chip">{result.trigger_ticker}</span>
                </div>
                <div className="st-ts-item">
                  <span className="st-ts-label">Event Type</span>
                  <span className="st-ts-value">{result.trigger_event_type}</span>
                </div>
                <div className="st-ts-item">
                  <span className="st-ts-label">Impact Score</span>
                  <span className="st-ts-value impact-high">{result.trigger_impact_score} / 10</span>
                </div>
                <div className="st-ts-item">
                  <span className="st-ts-label">Sentiment</span>
                  <span
                    className="st-ts-value"
                    style={{ color: sentimentColor(result.trigger_sentiment) }}
                  >
                    {result.trigger_sentiment}
                  </span>
                </div>
                <div className="st-ts-item">
                  <span className="st-ts-label">Scenario</span>
                  <span className="st-ts-value scenario-label">{result.scenario_name}</span>
                </div>
              </div>
            )}

            {/* ── KPI Row ─────────────────────────────────────────── */}
            <div className="st-kpi-row">
              <SummaryKPI
                label="Portfolio Before"
                value={fmtMM(result.total_portfolio_value_before_mm)}
                sub="Gross book value"
              />
              <SummaryKPI
                label="Portfolio After"
                value={fmtMM(result.total_portfolio_value_after_mm)}
                sub="Post-stress MTM"
                highlight={result.triggered ? 'kpi-loss' : ''}
              />
              <SummaryKPI
                label="Total P&amp;L Loss"
                value={result.triggered ? `-${fmtMM(result.total_loss_mm)}` : '$0.0M'}
                sub={result.triggered ? `${fmt(Math.abs(result.total_loss_pct), 2)}% of portfolio` : 'No shock applied'}
                highlight={result.triggered ? 'kpi-danger' : 'kpi-safe'}
              />
              <SummaryKPI
                label="Positions Stressed"
                value={result.positions?.length ?? '—'}
                sub={`${result.positions?.filter((p) => p.shock_pct < 0).length ?? 0} losses / ${result.positions?.filter((p) => p.shock_pct > 0).length ?? 0} gains`}
              />
            </div>

            {/* ── Visual Portfolio Bar ─────────────────────────────── */}
            {result.triggered && (
              <PortfolioComparisonBar
                before={result.total_portfolio_value_before_mm}
                after={result.total_portfolio_value_after_mm}
              />
            )}

            {/* ── Market Anchor Prices ─────────────────────────────── */}
            <div className="st-anchors-row">
              <span className="st-anchors-label">
                <span className="material-icons-outlined">show_chart</span>
                Live Market Anchors (yfinance):
              </span>
              <AnchorPrices anchors={result.market_anchors_snapshot} />
            </div>

            {/* ── Position Breakdown ───────────────────────────────── */}
            <div className="st-positions">
              <div className="st-pos-header">
                <span className="material-icons-outlined">table_rows</span>
                Asset-Level Stress Impact
                <span className="st-pos-legend">
                  <span className="st-legend-chip loss">Loss</span>
                  <span className="st-legend-chip gain">Flight-to-Quality Gain</span>
                </span>
              </div>
              <div className="st-pos-list">
                {result.positions?.map((pos) => (
                  <PositionRow key={pos.id} pos={pos} maxLoss={maxLoss} />
                ))}
              </div>
            </div>

            {/* ── Notes / Metadata ────────────────────────────────── */}
            {result.notes && (
              <div className="st-notes">
                <span className="material-icons-outlined">info</span>
                {result.notes}
              </div>
            )}
            <div className="st-generated-at">
              Generated at: {result.generated_at ? new Date(result.generated_at).toLocaleString() : '—'}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// Baseline totals for reference (mirrors module_b_stress_test.py)
const BASELINE_PORTFOLIO_TOTALS = { total: 2560 };
