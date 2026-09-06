import React, { useEffect, useState } from 'react'

import {
  BookMarked,
  Database,
  LoaderCircle,
  RefreshCw,
  Repeat,
  Search,
  Trash2,
  X,
} from 'lucide-react'

import type { UiText } from '../i18n'
import {
  clearTranslationMemory,
  fetchTranslationMemoryStats,
  type TranslationMemoryStats,
} from '../glossary/glossary-api'


export interface TranslationMemoryPanelProps {
  isOpen: boolean
  uiText: UiText
  onClose: () => void
}


export const TranslationMemoryPanel: React.FC<TranslationMemoryPanelProps> = ({
  isOpen,
  uiText,
  onClose,
}) => {
  const text = uiText.translationMemory
  const [stats, setStats] = useState<TranslationMemoryStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)

  useEffect(() => {
    if (!isOpen) {
      return
    }
    setError(null)
    setConfirmClear(false)
    void loadStats()
  }, [isOpen])

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

  if (!isOpen) {
    return null
  }

  const loadStats = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchTranslationMemoryStats()
      setStats(result)
    } catch {
      setError(text.loadFailed)
    } finally {
      setLoading(false)
    }
  }

  const handleClear = async (): Promise<void> => {
    setError(null)
    if (!confirmClear) {
      setConfirmClear(true)
      window.setTimeout(() => setConfirmClear(false), 3000)
      return
    }
    const cleared = await clearTranslationMemory()
    if (cleared === 0) {
      setError(text.noActiveSession)
    }
    setConfirmClear(false)
    await loadStats()
  }

  const hitRate = stats && stats.misses + stats.hits > 0
    ? Math.round((stats.hits / (stats.hits + stats.misses)) * 100)
    : 0

  return (
    <section
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="false"
      className="tm-panel"
    >
      <div className="tm-header">
        <div className="tm-title">
          <BookMarked size={18} />
          <h3>{text.title}</h3>
        </div>
        <button
          type="button"
          className="btn-secondary"
          style={{ width: 'auto', minHeight: '38px', padding: '0 14px' }}
          onClick={onClose}
        >
          <X size={14} />
          {text.close}
        </button>
      </div>

      <div className="tm-body">
        <div className="tm-description">{text.description}</div>

        {error ? (
          <div className="glossary-error">{error}</div>
        ) : null}

        {loading ? (
          <div className="tm-loading">
            <LoaderCircle size={18} className="spin" />
            {text.loading}
          </div>
        ) : !stats ? (
          <div className="tm-empty">{text.noData}</div>
        ) : (
          <div className="tm-metrics">
            <TMMetric icon={<Database size={16} />} label={text.entries} value={String(stats.size)} />
            <TMMetric icon={<Repeat size={16} />} label={text.hits} value={String(stats.hits)} />
            <TMMetric icon={<Search size={16} />} label={text.misses} value={String(stats.misses)} />
            <TMMetric icon={<RefreshCw size={16} />} label={text.written} value={String(stats.written)} />
            <TMMetric icon={<BookMarked size={16} />} label={text.hitRate} value={`${hitRate}%`} />
            <TMMetric icon={<Search size={16} />} label={text.threshold} value={(stats.threshold * 100).toFixed(0)} />
          </div>
        )}

        {stats && stats.store && stats.store.persisted ? (
          <div className="tm-metrics tm-metrics-persisted">
            <TMMetric icon={<Database size={16} />} label={text.persisted} value={text.persistedPairs} />
            <TMMetric icon={<Repeat size={16} />} label={text.persistedPairs} value={String(stats.store.size)} />
            <TMMetric icon={<Search size={16} />} label={text.persistedLanguages} value={String(stats.store.pairs)} />
          </div>
        ) : null}

        {stats && stats.sessions.length > 0 ? (
          <div className="tm-sessions">
            <div className="tm-session-label">{text.activeSessions}</div>
            <div className="tm-session-list">
              {stats.sessions.map((sessionId) => (
                <span key={sessionId} className="tm-session-chip">{shortSessionId(sessionId)}</span>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className="tm-footer">
        <button
          type="button"
          className="btn-secondary"
          disabled={loading}
          onClick={() => {
            void loadStats()
          }}
        >
          <RefreshCw size={15} />
          {text.refresh}
        </button>
        <button
          type="button"
          className="btn-secondary"
          style={confirmClear ? { color: '#ff6b5e', borderColor: 'rgba(255,107,94,0.45)' } : undefined}
          onClick={() => {
            void handleClear()
          }}
        >
          <Trash2 size={15} />
          {confirmClear ? text.confirmClear : text.clearAll}
        </button>
      </div>
    </section>
  )
}


interface TMMetricProps {
  icon: React.ReactNode
  label: string
  value: string
}


const TMMetric: React.FC<TMMetricProps> = ({ icon, label, value }) => (
  <div className="tm-metric">
    <div className="tm-metric-icon">{icon}</div>
    <div className="tm-metric-body">
      <div className="tm-metric-label">{label}</div>
      <div className="tm-metric-value">{value}</div>
    </div>
  </div>
)


function shortSessionId(sessionId: string): string {
  if (sessionId.length <= 12) {
    return sessionId
  }
  return `${sessionId.slice(0, 6)}...${sessionId.slice(-4)}`
}
