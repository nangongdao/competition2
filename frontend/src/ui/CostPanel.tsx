import React, { useEffect, useState } from 'react'

import {
  AlertTriangle,
  Coins,
  LoaderCircle,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react'

import type { UiText } from '../i18n'
import {
  fetchCostOverview,
  resetCostUsage,
  type CostOverview,
} from '../cost/cost-api'


export interface CostPanelProps {
  isOpen: boolean
  uiText: UiText
  onClose: () => void
}


function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString() : '0'
}


function formatToken(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`
  }
  return String(value)
}


export const CostPanel: React.FC<CostPanelProps> = ({
  isOpen,
  uiText,
  onClose,
}) => {
  const text = uiText.cost
  const [overview, setOverview] = useState<CostOverview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) {
      return
    }
    setError(null)
    void loadOverview()
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

  const loadOverview = async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchCostOverview()
      setOverview(result)
    } catch {
      setError(text.loadFailed)
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async (): Promise<void> => {
    setError(null)
    const updated = await resetCostUsage()
    if (!updated) {
      setError(text.resetFailed)
      return
    }
    setOverview(updated)
  }

  const renderCostRow = (label: string, usd: number, cny: number): React.ReactNode => (
    <div className="cost-row">
      <span className="cost-row-label">{label}</span>
      <span className="cost-row-value">
        {usd.toFixed(4)} {text.usd} · {cny.toFixed(4)} {text.cny}
      </span>
    </div>
  )

  const renderUsageRow = (label: string, value: string): React.ReactNode => (
    <div className="cost-row">
      <span className="cost-row-label">{label}</span>
      <span className="cost-row-value">{value}</span>
    </div>
  )

  return (
    <section
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="false"
      className="sub-panel"
    >
      <div className="sub-header">
        <div className="sub-title">
          <Coins size={18} />
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

      <div className="sub-body">
        {error ? (
          <div className="glossary-error">{error}</div>
        ) : null}

        {loading ? (
          <div className="sub-loading">
            <LoaderCircle size={18} className="spin" />
            {text.loading}
          </div>
        ) : !overview ? (
          <div className="sub-empty">{text.noData}</div>
        ) : (
          <div className="cost-content">
            <div className="cost-cards">
              <div className="cost-card">
                <div className="cost-card-label">{text.totalSessions}</div>
                <div className="cost-card-value">{formatNumber(overview.total_sessions)}</div>
              </div>
              <div className="cost-card">
                <div className="cost-card-label">{text.todayCost}</div>
                <div className="cost-card-value">
                  {overview.today_cost_usd.toFixed(4)}
                  <span className="cost-card-unit">{text.usd}</span>
                </div>
              </div>
              <div className="cost-card">
                <div className="cost-card-label">{text.totalCost}</div>
                <div className="cost-card-value">
                  {overview.total_cost_usd.toFixed(4)}
                  <span className="cost-card-unit">{text.usd}</span>
                </div>
              </div>
            </div>

            <div className="cost-section">
              <div className="cost-section-title">{text.usage}</div>
              <div className="cost-rows">
                {renderCostRow(text.totalCost, overview.total_cost_usd, overview.total_cost_cny)}
                {renderCostRow(text.todayCost, overview.today_cost_usd, overview.today_cost_cny)}
                {renderUsageRow(text.nmtInputTokens, formatToken(overview.usage.nmt_input_tokens))}
                {renderUsageRow(text.nmtOutputTokens, formatToken(overview.usage.nmt_output_tokens))}
                {renderUsageRow(text.asrSeconds, formatNumber(overview.usage.asr_seconds))}
                {renderUsageRow(text.ttsChars, formatNumber(overview.usage.tts_chars))}
              </div>
              <div className="cost-note">{overview.token_estimate_note}</div>
            </div>

            <div className="cost-section">
              <div className="cost-section-title">
                <AlertTriangle size={13} />
                {text.suggestions}
              </div>
              {overview.suggestions.length === 0 ? (
                <div className="cost-ok">{text.noSuggestions}</div>
              ) : (
                <ul className="cost-suggestions">
                  {overview.suggestions.map((suggestion) => (
                    <li key={suggestion}>{suggestion}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="sub-footer">
        <button
          type="button"
          className="btn-secondary"
          disabled={loading}
          onClick={() => {
            void loadOverview()
          }}
        >
          <RefreshCw size={15} />
          {text.refresh}
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={loading}
          onClick={() => {
            void handleReset()
          }}
        >
          <Trash2 size={15} />
          {text.resetUsage}
        </button>
      </div>
    </section>
  )
}
