import React, { useEffect, useRef, useState } from 'react'

import {
  Check,
  ClipboardCopy,
  Download,
  KeyRound,
  ListChecks,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  Timer,
  Users,
  X,
} from 'lucide-react'

import { formatDuration, formatSummaryMarkdown } from '../summary/session-summary'
import type { SessionSummary } from '../summary/session-summary'
import type { UiText } from '../i18n'


export interface SummaryPanelProps {
  sessionId: string
  isOpen: boolean
  hasSubtitles: boolean
  uiText: UiText
  fetchSummary: (
    sessionId: string,
    options: { useLlm: boolean },
  ) => Promise<SessionSummary | null>
  onClose: () => void
}


type SummaryStatus = 'idle' | 'loading' | 'done' | 'failed'


export const SummaryPanel: React.FC<SummaryPanelProps> = ({
  sessionId,
  isOpen,
  hasSubtitles,
  uiText,
  fetchSummary,
  onClose,
}) => {
  const text = uiText.summary
  const [status, setStatus] = useState<SummaryStatus>('idle')
  const [useLlm, setUseLlm] = useState(false)
  const [summary, setSummary] = useState<SessionSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle')
  const requestIdRef = useRef(0)

  useEffect(() => {
    if (!isOpen) {
      setStatus('idle')
      setSummary(null)
      setError(null)
      setCopyStatus('idle')
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

  const runFetch = async (withLlm: boolean): Promise<void> => {
    if (!sessionId) {
      setError(text.needActiveSession)
      setStatus('failed')
      return
    }
    if (!hasSubtitles) {
      setError(text.needSubtitles)
      setStatus('failed')
      return
    }

    const requestId = ++requestIdRef.current
    setStatus('loading')
    setError(null)
    setSummary(null)
    try {
      const result = await fetchSummary(sessionId, { useLlm: withLlm })
      if (requestId !== requestIdRef.current) {
        return
      }
      if (!result) {
        setStatus('failed')
        setError(text.fetchFailed)
        return
      }
      setSummary(result)
      setStatus('done')
    } catch {
      if (requestId === requestIdRef.current) {
        setStatus('failed')
        setError(text.fetchFailed)
      }
    }
  }

  const handleGenerate = (): void => {
    void runFetch(useLlm)
  }

  const handleCopy = async (): Promise<void> => {
    if (!summary) {
      return
    }
    try {
      await navigator.clipboard.writeText(formatSummaryMarkdown(summary))
      setCopyStatus('copied')
      window.setTimeout(() => setCopyStatus('idle'), 1600)
    } catch {
      setCopyStatus('failed')
      window.setTimeout(() => setCopyStatus('idle'), 1600)
    }
  }

  const handleDownload = (): void => {
    if (!summary) {
      return
    }
    downloadTextFile(
      formatSummaryMarkdown(summary),
      `ai-interpreter-summary-${Date.now()}.md`,
      'text/markdown;charset=utf-8',
    )
  }

  if (!isOpen) {
    return null
  }

  return (
    <section
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="false"
      className="summary-panel"
    >
      <div className="summary-header">
        <div className="summary-title">
          <Sparkles size={18} />
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

      <div className="summary-body">
        <label className="summary-llm-toggle">
          <input
            type="checkbox"
            checked={useLlm}
            onChange={(event) => setUseLlm(event.target.checked)}
          />
          <span>{text.useLlm}</span>
          <span className="summary-toggle-hint">{text.llmHint}</span>
        </label>

        <button
          type="button"
          className="btn-primary summary-generate"
          disabled={status === 'loading' || !hasSubtitles}
          onClick={handleGenerate}
        >
          {status === 'loading' ? <LoaderCircle size={16} className="spin" /> : <RefreshCw size={16} />}
          {status === 'loading' ? text.generating : text.generate}
        </button>

        {error ? (
          <div className="summary-error">{error}</div>
        ) : null}

        {status === 'done' && summary ? (
          <div className="summary-content">
            <div className="summary-metrics">
              <SummaryMetric icon={<Timer size={14} />} label={text.duration} value={formatDuration(summary.duration_seconds)} />
              <SummaryMetric icon={<ListChecks size={14} />} label={text.segments} value={String(summary.segment_count)} />
              <SummaryMetric icon={<RefreshCw size={14} />} label={text.revisions} value={String(summary.revision_count)} />
              <SummaryMetric icon={<Users size={14} />} label={text.speakers} value={String(summary.speaker_count)} />
            </div>

            {summary.bullets.length > 0 ? (
              <div className="summary-section">
                <div className="summary-section-title">
                  <Sparkles size={14} />
                  {text.keyPoints}
                </div>
                <ul className="summary-bullets">
                  {summary.bullets.map((bullet, index) => (
                    <li key={`bullet-${index}`}>{bullet}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {summary.action_items.length > 0 ? (
              <div className="summary-section">
                <div className="summary-section-title">
                  <ListChecks size={14} />
                  {text.actionItems}
                </div>
                <ul className="summary-actions">
                  {summary.action_items.map((item, index) => (
                    <li key={`action-${index}`}>
                      <input type="checkbox" readOnly tabIndex={-1} />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {summary.keywords.length > 0 ? (
              <div className="summary-section">
                <div className="summary-section-title">
                  <KeyRound size={14} />
                  {text.keywords}
                </div>
                <div className="summary-keywords">
                  {summary.keywords.map((keyword) => (
                    <span key={keyword.term} className="summary-keyword">
                      {keyword.term}
                      <em>{keyword.count}</em>
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {status === 'done' && summary ? (
        <div className="summary-footer">
          <button
            type="button"
            className="btn-secondary"
            style={copyStatus === 'copied' ? { color: 'var(--green)', borderColor: 'rgba(52,211,153,0.4)' } : undefined}
            onClick={() => {
              void handleCopy()
            }}
          >
            {copyStatus === 'copied' ? <Check size={15} /> : copyStatus === 'failed' ? <X size={15} /> : <ClipboardCopy size={15} />}
            {copyStatus === 'copied'
              ? text.copied
              : copyStatus === 'failed'
                ? text.copyFailed
                : text.copyMd}
          </button>
          <button type="button" className="btn-secondary" onClick={handleDownload}>
            <Download size={15} />
            {text.downloadMd}
          </button>
        </div>
      ) : null}
    </section>
  )
}


interface SummaryMetricProps {
  icon: React.ReactNode
  label: string
  value: string
}


const SummaryMetric: React.FC<SummaryMetricProps> = ({ icon, label, value }) => (
  <div className="summary-metric">
    <div className="summary-metric-icon">{icon}</div>
    <div className="summary-metric-body">
      <div className="summary-metric-label">{label}</div>
      <div className="summary-metric-value">{value}</div>
    </div>
  </div>
)


function downloadTextFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
