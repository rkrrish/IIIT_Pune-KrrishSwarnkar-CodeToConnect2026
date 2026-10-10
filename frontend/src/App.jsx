import React, { useEffect, useState, useCallback } from 'react';
import toast, { Toaster } from 'react-hot-toast';
import useStore from './store';
import { useLedgerStream, usePipelinePoller } from './hooks';
import * as api from './api';
import SummaryCards from './SummaryCards';
import ConstituentsTable from './ConstituentsTable';
import LedgerList from './LedgerList';
import WeightChart from './WeightChart';
import InspectModal from './InspectModal';
import PipelineStatusBadge from './PipelineStatusBadge';
import './App.css';

function App() {
  const refreshAll = useStore((s) => s.refreshAll);
  const clearLedger = useStore((s) => s.clearLedger);
  const fetchPipelineStatus = useStore((s) => s.fetchPipelineStatus);
  const pipelineStatus = useStore((s) => s.pipelineStatus);

  const [selectedEntry, setSelectedEntry] = useState(null);
  const [selectedEntryIndex, setSelectedEntryIndex] = useState(null);
  const [selectedTicker, setSelectedTicker] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);

  // Initialize data on mount
  useEffect(() => {
    refreshAll();
  }, []);

  // SSE streaming & pipeline status polling
  useLedgerStream();
  usePipelinePoller();

  // ── Actions ─────────────────────────────────────────────────

  const handleRunPipeline = useCallback(async () => {
    if (pipelineStatus === 'running') {
      toast.error('Pipeline is already running');
      return;
    }
    setActionLoading('run');
    try {
      await api.runPipeline();
      toast.success('Pipeline started — processing all events');
      fetchPipelineStatus();
      // Poll for completion
      const pollId = setInterval(async () => {
        const status = await api.fetchPipelineStatus();
        if (status.status !== 'running') {
          clearInterval(pollId);
          refreshAll();
          if (status.status === 'error') {
            toast.error(`Pipeline error: ${status.message}`);
          } else {
            toast.success('Pipeline completed successfully');
          }
          setActionLoading(null);
        }
      }, 2000);
    } catch (err) {
      toast.error(`Failed: ${err.message}`);
      setActionLoading(null);
    }
  }, [pipelineStatus]);

  const handleNextTimestep = useCallback(async () => {
    if (pipelineStatus === 'running') {
      toast.error('Pipeline is already running');
      return;
    }
    setActionLoading('next');
    try {
      await api.nextTimestep();
      toast('Processing next timestep…', { icon: '⏭️' });
      fetchPipelineStatus();
      // Poll for completion
      const pollId = setInterval(async () => {
        const status = await api.fetchPipelineStatus();
        if (status.status !== 'running') {
          clearInterval(pollId);
          refreshAll();
          toast.success('Timestep processed');
          setActionLoading(null);
        }
      }, 1500);
    } catch (err) {
      toast.error(`Failed: ${err.message}`);
      setActionLoading(null);
    }
  }, [pipelineStatus]);

  const handleReset = useCallback(async () => {
    setActionLoading('reset');
    try {
      await api.resetPipeline();
      clearLedger();
      refreshAll();
      toast.success('Demo reset — ledger cleared');
    } catch (err) {
      toast.error(`Reset failed: ${err.message}`);
    }
    setActionLoading(null);
  }, []);

  // ── Handlers ────────────────────────────────────────────────

  const handleInspect = (entry, idx) => {
    setSelectedEntry(entry);
    setSelectedEntryIndex(idx);
  };

  const handleCloseInspect = () => {
    setSelectedEntry(null);
    setSelectedEntryIndex(null);
  };

  const handleTickerClick = (ticker) => {
    setSelectedTicker((prev) => (prev === ticker ? null : ticker));
  };

  return (
    <div className="dashboard">
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#fcfbf8',
            color: '#1c1917',
            border: '1px solid #e5e1d8',
            borderRadius: '10px',
            fontSize: '0.85rem',
            fontFamily: 'Inter, sans-serif',
            boxShadow: '0 4px 12px rgba(28, 25, 23, 0.08)',
          },
          success: { iconTheme: { primary: '#15803d', secondary: '#fcfbf8' } },
          error: { iconTheme: { primary: '#b91c1c', secondary: '#fcfbf8' } },
        }}
      />

      {/* ── Header ─────────────────────────────────────────── */}
      <header className="dashboard-header">
        <div className="header-left">
          <div className="logo-mark">
            <span className="material-icons-outlined">analytics</span>
          </div>
          <div className="header-text">
            <h1>S&P 100 NLP Risk Engine</h1>
            <p className="header-subtitle">Tactical Index Rebalancing Dashboard</p>
          </div>
        </div>
        <div className="header-right">
          <PipelineStatusBadge />
          <div className="header-actions">
            <button
              className="btn btn-primary"
              onClick={handleNextTimestep}
              disabled={actionLoading === 'next' || pipelineStatus === 'running'}
            >
              <span className="material-icons-outlined btn-icon">skip_next</span>
              {actionLoading === 'next' ? 'Processing…' : 'Next Timestep'}
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleRunPipeline}
              disabled={actionLoading === 'run' || pipelineStatus === 'running'}
            >
              <span className="material-icons-outlined btn-icon">play_arrow</span>
              {actionLoading === 'run' ? 'Running…' : 'Run Pipeline'}
            </button>
            <button
              className="btn btn-danger"
              onClick={handleReset}
              disabled={actionLoading === 'reset' || pipelineStatus === 'running'}
            >
              <span className="material-icons-outlined btn-icon">restart_alt</span>
              Reset Demo
            </button>
          </div>
        </div>
      </header>

      {/* ── Main Content ──────────────────────────────────── */}
      <main className="dashboard-main">
        {/* KPI Cards */}
        <section className="dashboard-section">
          <SummaryCards />
        </section>

        {/* Constituents Table */}
        <section className="dashboard-section">
          <ConstituentsTable onTickerClick={handleTickerClick} />
        </section>

        {/* Weight Chart */}
        <section className="dashboard-section">
          <WeightChart
            selectedTicker={selectedTicker}
            onSelectTicker={handleTickerClick}
          />
        </section>

        {/* Ledger */}
        <section className="dashboard-section">
          <LedgerList
            onInspect={handleInspect}
            onTickerClick={handleTickerClick}
          />
        </section>
      </main>

      {/* ── Footer ─────────────────────────────────────────── */}
      <footer className="dashboard-footer">
        <p>S&P 100 NLP Risk Engine • Powered by FinBERT + Black-Litterman • Demo Mode</p>
      </footer>

      {/* ── Inspect Modal ──────────────────────────────────── */}
      {selectedEntry && (
        <InspectModal
          entry={selectedEntry}
          entryIndex={selectedEntryIndex}
          onClose={handleCloseInspect}
        />
      )}
    </div>
  );
}

export default App;
