import React from 'react';
import useStore from './store';
import './PipelineStatusBadge.css';

const STATUS_CONFIG = {
  idle: { label: 'Idle', color: 'var(--accent-green)', icon: 'check_circle' },
  running: { label: 'Running', color: 'var(--accent-orange)', icon: 'sync', pulse: true },
  error: { label: 'Error', color: 'var(--accent-red)', icon: 'error' },
};

export default function PipelineStatusBadge() {
  const pipelineStatus = useStore((s) => s.pipelineStatus);
  const pipelineMessage = useStore((s) => s.pipelineMessage);
  const config = STATUS_CONFIG[pipelineStatus] || STATUS_CONFIG.idle;

  return (
    <div
      className={`pipeline-badge ${config.pulse ? 'pulse' : ''}`}
      style={{ '--badge-color': config.color }}
      title={pipelineMessage || config.label}
    >
      <span className={`material-icons-outlined badge-icon ${config.pulse ? 'spin' : ''}`}>
        {config.icon}
      </span>
      <span className="badge-label">{config.label}</span>
      {config.pulse && <span className="pulse-ring" />}
    </div>
  );
}
