/**
 * Global state management with Zustand.
 * Handles summary stats, pipeline status, ledger, index constituents.
 */
import { create } from 'zustand';
import * as api from './api';

const useStore = create((set, get) => ({
  // ── Summary / KPI stats ─────────────────────────────────────
  summary: {
    num_active_tickers: 0,
    changed_weights_latest: 0,
    pos_sentiment_events: 0,
    neg_sentiment_events: 0,
    latest_timestamp: null,
    pipeline_status: 'idle',
    total_events_processed: 0,
  },
  fetchSummary: async () => {
    try {
      const data = await api.fetchSummary();
      set({ summary: data });
    } catch (e) {
      console.error('Failed to fetch summary:', e);
    }
  },

  // ── Pipeline status ─────────────────────────────────────────
  pipelineStatus: 'idle',
  pipelineMessage: '',
  fetchPipelineStatus: async () => {
    try {
      const data = await api.fetchPipelineStatus();
      set({ pipelineStatus: data.status, pipelineMessage: data.message || '' });
    } catch (e) {
      console.error('Failed to fetch pipeline status:', e);
    }
  },

  // ── Constituents (index) ────────────────────────────────────
  constituents: [],
  fetchConstituents: async () => {
    try {
      const data = await api.fetchIndex();
      set({ constituents: data });
    } catch (e) {
      console.error('Failed to fetch index:', e);
    }
  },

  // ── Ledger entries ──────────────────────────────────────────
  ledger: [],
  fetchLedger: async () => {
    try {
      const data = await api.fetchLedger();
      set({ ledger: data });
    } catch (e) {
      console.error('Failed to fetch ledger:', e);
    }
  },
  appendLedgerEntry: (entry) => {
    set((state) => ({ ledger: [...state.ledger, entry] }));
  },
  clearLedger: () => set({ ledger: [] }),

  // ── Weight history for charts ──────────────────────────────
  weightHistory: { tickers: [], series: {} },
  fetchWeightHistory: async () => {
    try {
      const data = await api.fetchWeightHistory();
      set({ weightHistory: data });
    } catch (e) {
      console.error('Failed to fetch weight history:', e);
    }
  },

  // ── Refresh all data ───────────────────────────────────────
  refreshAll: async () => {
    const { fetchSummary, fetchConstituents, fetchLedger, fetchPipelineStatus, fetchWeightHistory } = get();
    await Promise.all([
      fetchSummary(),
      fetchConstituents(),
      fetchLedger(),
      fetchPipelineStatus(),
      fetchWeightHistory(),
    ]);
  },
}));

export default useStore;
