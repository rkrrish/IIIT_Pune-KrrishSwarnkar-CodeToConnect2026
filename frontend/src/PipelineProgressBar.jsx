import React from 'react';
import useStore from './store';
import './PipelineProgressBar.css';

const STAGES = [
  { id: 'fetching_live_data', label: '1. Ingest Live Feeds', icon: 'cloud_download' },
  { id: 'deduplicating_data', label: '2. De-duplicate Articles', icon: 'filter_alt' },
  { id: 'nlp_risk_engine', label: '3. FinBERT Risk Engine', icon: 'psychology' },
  { id: 'rebalancing_portfolio', label: '4. Black-Litterman Rebalance', icon: 'tune' },
];

function getStageIndex(stageId) {
  if (stageId === 'complete') return 4;
  const idx = STAGES.findIndex((s) => s.id === stageId);
  return idx >= 0 ? idx : 0;
}

export default function PipelineProgressBar({ onRetry }) {
  const pipelineStatus = useStore((s) => s.pipelineStatus);
  const pipelineStage = useStore((s) => s.pipelineStage);
  const pipelineProgress = useStore((s) => s.pipelineProgress);
  const pipelineMessage = useStore((s) => s.pipelineMessage);
  const failedStage = useStore((s) => s.failedStage);
  const errorMessage = useStore((s) => s.errorMessage);
  const activeMode = useStore((s) => s.activeMode);

  if (pipelineStatus === 'idle' && !failedStage) {
    return null;
  }

  const currentStageIndex = getStageIndex(pipelineStage);

  return (
    <div className="pipeline-progress-container">
      {pipelineStatus === 'running' && (
        <div className="pipeline-running-card">
          <div className="progress-card-header">
            <div className="header-badge">
              <span className="material-icons-outlined spin-icon">sync</span>
              <span className="running-title">
                {activeMode === 'live' ? 'Live Mode Pipeline Running' : 'Demo Mode Pipeline Running'}
              </span>
            </div>
            <span className="progress-percentage">{pipelineProgress}%</span>
          </div>

          {/* Progress Bar Track */}
          <div className="progress-bar-track">
            <div
              className="progress-bar-fill"
              style={{ width: `${Math.max(5, Math.min(100, pipelineProgress))}%` }}
            />
          </div>

          <p className="progress-message">{pipelineMessage || 'Processing stage...'}</p>

          {/* Pipeline Stage Steps */}
          <div className="pipeline-steps-grid">
            {STAGES.map((stg, idx) => {
              const isActive = idx === currentStageIndex;
              const isDone = idx < currentStageIndex || pipelineProgress === 100;
              return (
                <div
                  key={stg.id}
                  className={`step-item ${isActive ? 'active' : ''} ${isDone ? 'completed' : ''}`}
                >
                  <div className="step-icon-wrapper">
                    <span className="material-icons-outlined">{stg.icon}</span>
                  </div>
                  <span className="step-label">{stg.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {pipelineStatus === 'error' && (
        <div className="pipeline-error-card">
          <div className="error-card-header">
            <div className="error-badge-title">
              <span className="material-icons-outlined error-icon">error_outline</span>
              <h3>Pipeline Stage Execution Failed</h3>
            </div>
            {onRetry && (
              <button className="btn btn-retry" onClick={onRetry}>
                <span className="material-icons-outlined">refresh</span>
                Retry Execution
              </button>
            )}
          </div>

          <div className="error-details-body">
            <div className="error-field">
              <span className="field-label">Failed Stage:</span>
              <span className="field-value stage-tag">{failedStage || pipelineStage || 'Unknown'}</span>
            </div>
            <div className="error-field">
              <span className="field-label">Error Message:</span>
              <span className="field-value error-text-box">
                {errorMessage || pipelineMessage || 'An unexpected error occurred during execution.'}
              </span>
            </div>
          </div>

          <div className="error-footer-note">
            <span className="material-icons-outlined note-icon">security</span>
            <span>
              Index integrity preserved. Failed execution prevented corrupted rebalancing output.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
