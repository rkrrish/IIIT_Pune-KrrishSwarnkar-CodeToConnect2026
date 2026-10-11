/**
 * Centralized API client for the S&P 100 Risk Engine backend.
 * All fetch functions with error handling and base URL configuration.
 */

const API_BASE = import.meta.env.VITE_API_BASE || '';

async function request(url, options = {}) {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.message || body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Dashboard ───────────────────────────────────────────────────
export const fetchSummary = () => request('/api/dashboard/summary');
export const fetchIndex = () => request('/api/dashboard/index');
export const fetchWeightHistory = () => request('/api/dashboard/weight-history');
export const fetchGraph = (ticker) => request(`/api/dashboard/graph?ticker=${encodeURIComponent(ticker)}`);

// ── Ledger ──────────────────────────────────────────────────────
export const fetchLedger = () => request('/api/ledger');
export const fetchLedgerEntry = (id) => request(`/api/ledger/${id}`);

// ── Pipeline control ────────────────────────────────────────────
export const runPipeline = () => request('/api/pipeline/run', { method: 'POST' });
export const runLivePipeline = () => request('/api/pipeline/live/run', { method: 'POST' });
export const nextTimestep = () => request('/api/pipeline/next', { method: 'POST' });
export const resetPipeline = () => request('/api/pipeline/reset', { method: 'POST' });
export const fetchPipelineStatus = () => request('/api/pipeline/status');

// ── SSE Stream ──────────────────────────────────────────────────
export function createLedgerStream(onMessage, onError) {
  const url = `${API_BASE}/api/ledger/stream`;
  const source = new EventSource(url);

  source.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.warn('[SSE] Failed to parse:', e);
    }
  };

  source.onerror = (err) => {
    console.warn('[SSE] Connection error, will retry...', err);
    if (onError) onError(err);
  };

  return source;
}

// ── Module B: Stress Test ────────────────────────────────────────
export const fetchStressTestLatest = () => request('/api/stress-test/latest').catch(() => null);
export const fetchStressTestScenarios = () => request('/api/stress-test/scenarios');
export const runStressTest = (force = true, scenario = null) => {
  const params = new URLSearchParams({ force });
  if (scenario) params.append('scenario', scenario);
  return request(`/api/stress-test/run?${params}`, { method: 'POST' });
};
