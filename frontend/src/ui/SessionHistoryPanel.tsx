import React, { useEffect, useMemo, useState } from 'react'

import {
  AlertTriangle,
  Database,
  Eraser,
  LoaderCircle,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react'

import type { SessionHistoryPanelText, UiText } from '../i18n'
import {
  clearSessionHistory,
  deleteSessionHistory,
  fetchSessionHistory,
  formatSessionDuration,
  formatSessionStartedAt,
  purgeSessionHistory,
  type SessionHistoryRecord,
  type SessionHistoryStats,
  type SessionQualityMetrics,
} from '../session-history/session-history-api'


interface SessionHistoryPanelProps {
  isOpen: boolean
  uiText: UiText
  onClose: () => void
}


export const SessionHistoryPanel: React.FC<SessionHistoryPanelProps> = ({
  isOpen,
  uiText,
  onClose,
}) => {
  const text = uiText.sessionHistory
  const [sessions, setSessions] = useState<SessionHistoryRecord[]>([])
  const [stats, setStats] = useState<SessionHistoryStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetchSessionHistory()
      if (response.success) {
        setSessions(response.sessions ?? [])
        setStats(response.stats ?? null)
      } else {
        setError(response.reason ?? 'Failed to load session history')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load session history')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      void load()
    }
  }, [isOpen])

  const handleDelete = async (sessionId: string): Promise<void> => {
    setBusy(true)
    try {
      await deleteSessionHistory(sessionId)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const handleClear = async (): Promise<void> => {
    if (!confirmClear) {
      setConfirmClear(true)
      return
    }
    setBusy(true)
    try {
      await clearSessionHistory()
      setConfirmClear(false)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Clear failed')
    } finally {
      setBusy(false)
    }
  }

  const handlePurge = async (): Promise<void> => {
    setBusy(true)
    try {
      await purgeSessionHistory()
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Purge failed')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (!isOpen) {
      return
    }
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isOpen, onClose])

  const sortedSessions = useMemo(
    () => sessions.slice().sort((a, b) => b.started_at - a.started_at),
    [sessions],
  )

  if (!isOpen) {
    return null
  }

  return (
    <section
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="false"
      className="sub-panel session-history-panel"
    >
      <div className="sub-header">
        <div className="sub-title">
          <Database size={18} />
          <h3>{text.title}</h3>
        </div>
        <button
          type="button"
          className="btn-secondary"
          style={{ width: 'auto', minHeight: '38px', padding: '0 14px' }}
          onClick={onClose}
        >
          <X size={14} />
          {text.closeAriaLabel}
        </button>
      </div>

      <div className="session-history-toolbar">
        <button
          type="button"
          className="btn-secondary"
          style={{ minHeight: '34px', padding: '0 12px', width: 'auto', fontSize: '12px' }}
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw size={13} />
          {text.refresh}
        </button>
        <button
          type="button"
          className="btn-secondary"
          style={{ minHeight: '34px', padding: '0 12px', width: 'auto', fontSize: '12px' }}
          onClick={() => void handlePurge()}
          disabled={busy}
        >
          <Eraser size={13} />
          {text.purge}
        </button>
        <button
          type="button"
          className="btn-secondary danger"
          style={{ minHeight: '34px', padding: '0 12px', width: 'auto', fontSize: '12px' }}
          onClick={() => void handleClear()}
          disabled={busy}
        >
          <Trash2 size={13} />
          {confirmClear ? text.confirmClear : text.clearAll}
        </button>
      </div>

      {stats && (
        <div className="session-history-stats">
          <span>
            {text.statSessions}: <strong>{stats.total_sessions}</strong>
          </span>
          <span>
            {text.statSegments}: <strong>{stats.total_segments}</strong>
          </span>
          <span>
            {text.statRetention}: <strong>{Math.round(stats.retention_seconds / 3600)}h</strong>
          </span>
        </div>
      )}

      {error && (
        <div className="glossary-error">
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      <div className="session-history-list">
        {loading && (
          <div className="session-history-empty">
            <LoaderCircle size={18} className="spin" />
          </div>
        )}
        {!loading && sortedSessions.length === 0 && (
          <div className="session-history-empty">{text.empty}</div>
        )}
        {!loading &&
          sortedSessions.map((session) => (
            <div key={session.session_id} className="session-history-item">
              <div className="session-history-item-main">
                <div className="session-history-item-title">
                  {formatSessionStartedAt(session.started_at)}
                </div>
                <div className="session-history-item-meta">
                  <span>{text.metaSegments}: {session.segment_count}</span>
                  <span>{text.metaDuration}: {formatSessionDuration(session.duration_ms, uiText)}</span>
                </div>
                {session.quality ? (
                  <SessionQuality quality={session.quality} text={text} />
                ) : (
                  <div className="session-quality-empty">{text.noQuality}</div>
                )}
                <code className="session-history-item-id">{session.session_id}</code>
              </div>
              <button
                type="button"
                className="icon-button danger"
                aria-label={text.deleteAriaLabel}
                onClick={() => void handleDelete(session.session_id)}
                disabled={busy}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
      </div>

      <p className="session-history-note">{text.privacyNote}</p>
    </section>
  )
}


interface SessionQualityProps {
  quality: SessionQualityMetrics
  text: SessionHistoryPanelText
}


/** 会话质量指标概览（阶段 10 可观测性补全）。 */
const SessionQuality: React.FC<SessionQualityProps> = ({ quality, text }) => {
  const dropRatio = quality.audio_chunks_received > 0
    ? Math.round((quality.audio_chunks_dropped / quality.audio_chunks_received) * 100)
    : 0
  const avgLatencyMs = pickAvgLatency(quality.latency)

  return (
    <div className="session-quality">
      <div className="session-quality-title">{text.qualityTitle}</div>
      <div className="session-quality-grid">
        <SessionQualityItem label={text.qualityAsr} value={String(quality.asr_segments)} />
        <SessionQualityItem label={text.qualityTranslation} value={String(quality.translation_segments)} />
        <SessionQualityItem label={text.qualityRevision} value={String(quality.revision_segments)} />
        <SessionQualityItem label={text.qualityDropped} value={dropRatio > 0 ? `${dropRatio}%` : '0'} />
        <SessionQualityItem label={text.qualityQueue} value={`${quality.audio_queue_max_depth}/${quality.audio_queue_capacity}`} />
        <SessionQualityItem label={text.qualityReconnect} value={String(quality.reconnect_count)} />
        <SessionQualityItem label={text.qualityLatency} value={avgLatencyMs > 0 ? `${avgLatencyMs}ms` : '-'} />
      </div>
    </div>
  )
}


interface SessionQualityItemProps {
  label: string
  value: string
}


const SessionQualityItem: React.FC<SessionQualityItemProps> = ({ label, value }) => (
  <div className="session-quality-item">
    <span className="session-quality-label">{label}</span>
    <span className="session-quality-value">{value}</span>
  </div>
)


/** 取主要延迟指标的平均值（ASR 到翻译完成优先）。 */
function pickAvgLatency(
  latency: Record<string, { count: number; avg_ms: number; max_ms: number }>,
): number {
  const priority = [
    'asr_to_translation_final_ms',
    'capture_to_asr_ms',
    'audio_queue_wait_ms',
    'revision_final_ms',
  ]
  for (const name of priority) {
    const stats = latency[name]
    if (stats && stats.avg_ms > 0) {
      return stats.avg_ms
    }
  }
  return 0
}
