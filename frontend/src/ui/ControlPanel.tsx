import React, { useEffect, useState } from 'react'

import type {
  AppStatus,
  ClientDiagnostics,
  RevisionReason,
  SessionDiagnostics,
  SubtitleMode,
} from '../types'


interface ControlPanelProps {
  status: AppStatus
  connectionState: string
  subtitleMode: SubtitleMode
  subtitleHistoryCount: number
  translationRevisionCount: number
  asrRevisionCount: number
  lastRevisionReason: RevisionReason | null
  serverDiagnostics: SessionDiagnostics | null
  clientDiagnostics: ClientDiagnostics
  onStart: () => void
  onStop: () => void
  onManualRevise: () => void
  onOpenHistory: () => void
  onSubtitleModeChange: (mode: SubtitleMode) => void
}


const STATUS_LABELS: Record<AppStatus, string> = {
  idle: 'Ready',
  capturing: 'Capturing audio',
  translating: 'Live translation',
  error: 'Action needed',
}


const STATUS_COLORS: Record<AppStatus, string> = {
  idle: '#8f9aa8',
  capturing: '#58b06a',
  translating: '#4aa3ff',
  error: '#ff6b5e',
}


const MODE_OPTIONS: Array<{ label: string; value: SubtitleMode }> = [
  { label: 'Both', value: 'bilingual' },
  { label: 'Translation', value: 'translation_only' },
  { label: 'Source', value: 'source_only' },
]


const REVISION_LABELS: Record<RevisionReason, string> = {
  asr_correction: 'ASR',
  translation_correction: 'Translation',
}


const tapSafeButtonStyle: React.CSSProperties = {
  WebkitTapHighlightColor: 'transparent',
}


const primaryButtonStyle: React.CSSProperties = {
  ...tapSafeButtonStyle,
  minHeight: '44px',
  border: 'none',
  borderRadius: '12px',
  cursor: 'pointer',
  fontSize: '14px',
  fontWeight: 700,
  color: '#fff',
}


const secondaryButtonStyle: React.CSSProperties = {
  ...tapSafeButtonStyle,
  minHeight: '44px',
  borderRadius: '12px',
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(255,255,255,0.04)',
  color: '#d9e1eb',
  cursor: 'pointer',
  fontSize: '13px',
  fontWeight: 600,
}


const metricStyle: React.CSSProperties = {
  minWidth: 0,
  padding: '8px 10px',
  borderRadius: '12px',
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.06)',
}


const buttonClipStyle: React.CSSProperties = {
  borderRadius: '12px',
  overflow: 'hidden',
}


export const ControlPanel: React.FC<ControlPanelProps> = ({
  status,
  connectionState,
  subtitleMode,
  subtitleHistoryCount,
  translationRevisionCount,
  asrRevisionCount,
  lastRevisionReason,
  serverDiagnostics,
  clientDiagnostics,
  onStart,
  onStop,
  onManualRevise,
  onOpenHistory,
  onSubtitleModeChange,
}) => {
  const [showDetails, setShowDetails] = useState(false)
  const isActive = status === 'capturing' || status === 'translating'

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.ctrlKey && event.key.toLowerCase() === 'r') {
        event.preventDefault()
        onManualRevise()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onManualRevise])

  return (
    <aside aria-label="Live translation controls" className="live-control-panel">
      <div style={{ display: 'flex', alignItems: 'center', fontSize: '13px', color: '#d9e1eb' }}>
        <span
          aria-hidden="true"
          style={{
            display: 'inline-block',
            width: '8px',
            height: '8px',
            marginRight: '8px',
            borderRadius: '999px',
            background: STATUS_COLORS[status],
          }}
        />
        <span>{STATUS_LABELS[status]}</span>
      </div>

      <div style={{ fontSize: '11px', color: '#91a0b3' }}>
        WebSocket: {connectionState}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '8px',
        }}
      >
        <div style={metricStyle}>
          <div style={{ fontSize: '11px', color: '#91a0b3' }}>Translation fixes</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#ffffff' }}>
            {translationRevisionCount}
          </div>
        </div>
        <div style={metricStyle}>
          <div style={{ fontSize: '11px', color: '#91a0b3' }}>ASR fixes</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#ffffff' }}>
            {asrRevisionCount}
          </div>
        </div>
      </div>

      <div style={{ fontSize: '11px', color: '#91a0b3' }}>
        Last fix: {lastRevisionReason ? REVISION_LABELS[lastRevisionReason] : 'None'}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={buttonClipStyle}>
          <button
            type="button"
            style={{
              ...primaryButtonStyle,
              width: '100%',
              background: isActive ? '#d84b45' : '#29945b',
            }}
            onClick={isActive ? onStop : onStart}
          >
            {isActive ? 'Stop translation' : 'Start translation'}
          </button>
        </div>

        <div style={buttonClipStyle}>
          <button
            type="button"
            style={{
              ...secondaryButtonStyle,
              width: '100%',
            }}
            onClick={onManualRevise}
          >
            Revise now
          </button>
        </div>

        <div style={buttonClipStyle}>
          <button
            type="button"
            style={{
              ...secondaryButtonStyle,
              width: '100%',
            }}
            onClick={onOpenHistory}
          >
            History and export ({subtitleHistoryCount})
          </button>
        </div>
      </div>

      <div className="control-mode-group">
        {MODE_OPTIONS.map((option) => {
          const isSelected = option.value === subtitleMode
          return (
            <div
              key={option.value}
              className="control-mode-option"
            >
              <button
                type="button"
                aria-pressed={isSelected}
                style={{
                  ...secondaryButtonStyle,
                  width: '100%',
                  minHeight: '44px',
                  padding: '0 6px',
                  fontSize: '12px',
                  lineHeight: 1.12,
                  overflowWrap: 'anywhere',
                  background: isSelected ? 'rgba(74,163,255,0.18)' : 'rgba(255,255,255,0.03)',
                  borderColor: isSelected ? 'rgba(74,163,255,0.4)' : 'rgba(255,255,255,0.1)',
                  color: isSelected ? '#ffffff' : '#b9c5d3',
                }}
                onClick={() => onSubtitleModeChange(option.value)}
              >
                {option.label}
              </button>
            </div>
          )
        })}
      </div>

      <div style={buttonClipStyle}>
        <button
          type="button"
          style={{
            ...secondaryButtonStyle,
            width: '100%',
            minHeight: '44px',
            fontSize: '12px',
          }}
          onClick={() => setShowDetails((value) => !value)}
        >
          {showDetails ? 'Hide details' : 'Show details'}
        </button>
      </div>

      {showDetails ? (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'stretch',
            gap: '6px',
            padding: '10px 12px',
            borderRadius: '12px',
            background: 'rgba(255,255,255,0.04)',
            fontSize: '12px',
            lineHeight: 1.42,
            color: '#b9c5d3',
          }}
        >
          <DetailRow label="Session" value={serverDiagnostics?.session_id ?? clientDiagnostics.sessionId} />
          <DetailRow label="Sent chunks" value={clientDiagnostics.sentAudioChunks.toString()} />
          <DetailRow label="Client drops" value={clientDiagnostics.droppedAudioChunks.toString()} />
          <DetailRow label="Server drops" value={(serverDiagnostics?.audio_chunks_dropped ?? 0).toString()} />
          <DetailRow label="Reconnects" value={clientDiagnostics.reconnectAttempts.toString()} />
          <DetailRow
            label="ASR latency"
            value={formatLatency(serverDiagnostics?.latency.capture_to_asr_ms)}
          />
          <DetailRow
            label="First token"
            value={formatLatency(serverDiagnostics?.latency.asr_to_first_token_ms)}
          />
          <DetailRow
            label="Final text"
            value={formatLatency(serverDiagnostics?.latency.asr_to_translation_final_ms)}
          />
          <DetailRow
            label="API calls"
            value={formatCounterMap(serverDiagnostics?.api_call_counts)}
          />
        </div>
      ) : null}
    </aside>
  )
}


interface DetailRowProps {
  label: string
  value: string
}


const DetailRow: React.FC<DetailRowProps> = ({ label, value }) => (
  <div
    style={{
      display: 'grid',
      gridTemplateColumns: 'minmax(86px, 0.8fr) minmax(0, 1.2fr)',
      gap: '8px',
      minWidth: 0,
    }}
  >
    <span style={{ color: '#7f8ea3' }}>{label}</span>
    <span style={{ color: '#d9e1eb', wordBreak: 'break-word' }}>{value || '-'}</span>
  </div>
)


function formatLatency(summary: { count: number; avg_ms: number; max_ms: number } | undefined): string {
  if (!summary || summary.count === 0) {
    return '-'
  }
  return `${summary.avg_ms}ms avg`
}


function formatCounterMap(values: Record<string, number> | undefined): string {
  if (!values) {
    return '-'
  }

  const entries = Object.entries(values)
    .filter(([, value]) => value > 0)
    .map(([key, value]) => `${key}:${value}`)

  return entries.length > 0 ? entries.join(', ') : '-'
}
