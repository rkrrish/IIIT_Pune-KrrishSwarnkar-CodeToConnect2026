/**
 * Custom hook: subscribes to SSE ledger stream and updates store on each message.
 * Falls back to polling if SSE fails.
 */
import { useEffect, useRef } from 'react';
import { createLedgerStream } from './api';
import useStore from './store';

export function useLedgerStream() {
  const appendLedgerEntry = useStore((s) => s.appendLedgerEntry);
  const fetchLedger = useStore((s) => s.fetchLedger);
  const fetchSummary = useStore((s) => s.fetchSummary);
  const fetchWeightHistory = useStore((s) => s.fetchWeightHistory);
  const fetchConstituents = useStore((s) => s.fetchConstituents);
  const sourceRef = useRef(null);
  const fallbackRef = useRef(null);

  useEffect(() => {
    let isMounted = true;

    // Try SSE first
    sourceRef.current = createLedgerStream(
      (entry) => {
        if (!isMounted) return;
        appendLedgerEntry(entry);
        // Refresh summary & weight history when new data arrives
        fetchSummary();
        fetchWeightHistory();
        fetchConstituents();
      },
      () => {
        // SSE failed — fall back to polling every 5s
        if (!fallbackRef.current && isMounted) {
          console.warn('[useLedgerStream] SSE failed, falling back to polling');
          fallbackRef.current = setInterval(() => {
            fetchLedger();
            fetchSummary();
            fetchWeightHistory();
            fetchConstituents();
          }, 5000);
        }
      }
    );

    return () => {
      isMounted = false;
      if (sourceRef.current) {
        sourceRef.current.close();
      }
      if (fallbackRef.current) {
        clearInterval(fallbackRef.current);
      }
    };
  }, []);
}

/**
 * Custom hook: periodic status polling (every 3s) to keep pipeline status up to date.
 */
export function usePipelinePoller() {
  const fetchPipelineStatus = useStore((s) => s.fetchPipelineStatus);
  const fetchSummary = useStore((s) => s.fetchSummary);

  useEffect(() => {
    fetchPipelineStatus();
    const id = setInterval(() => {
      fetchPipelineStatus();
      fetchSummary();
    }, 3000);
    return () => clearInterval(id);
  }, []);
}
