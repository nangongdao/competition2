import React, { useEffect, useMemo, useState } from 'react'

import {
  formatLearningNotesMarkdown,
  formatPlainTranscript,
  formatSrtSubtitles,
  formatVttSubtitles,
  hasExportableSubtitles,
} from '../subtitle/subtitle-export'
import type { SubtitleEntry } from '../types'


interface SubtitleHistoryPanelProps {
  entries: SubtitleEntry[]
  isOpen: boolean
  diagnosticsText: string
  onClose: () => void
}


const tapSafeButtonStyle: React.CSSProperties = {
  border: 'none',
  borderRadius: '12px',
  cursor: 'pointer',
  fontWeight: 700,
  WebkitTapHighlightColor: 'transparent',
}


const panelStyle: React.CSSProperties = {
  position: 'fixed',
  right: '16px',
  bottom: '16px',
  zIndex: 100001,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'stretch',
  width: 'min(92vw, 440px)',
  maxHeight: 'min(72vh, 640px)',
  minHeight: 0,
  borderRadius: '22px',
  overflow: 'hidden',
  background: 'linear-gradient(160deg, rgba(8, 14, 23, 0.96), rgba(25, 32, 43, 0.92))',
  border: '1px solid rgba(255,255,255,0.1)',
  boxShadow: '0 28px 72px rgba(0, 0, 0, 0.42)',
  backdropFilter: 'blur(18px)',
}


const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '12px',
  padding: '16px 16px 12px',
  borderBottom: '1px solid rgba(255,255,255,0.08)',
}


const summaryStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
  gap: '8px',
  padding: '12px 14px 0',
}


const listStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'stretch',
  gap: '10px',
  minHeight: 0,
  overflowY: 'auto',
  padding: '14px',
  overscrollBehavior: 'contain',
}


const footerStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: '10px',
  padding: '12px 14px 14px',
  borderTop: '1px solid rgba(255,255,255,0.08)',
}


export const SubtitleHistoryPanel: React.FC<SubtitleHistoryPanelProps> = ({
  entries,
  isOpen,
  diagnosticsText,
  onClose,
}) => {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle')

  const stats = useMemo(() => {
    return entries.reduce(
      (result, entry) => {
        if (entry.isRevised) {
          result.revised += 1
        }
        if (entry.sourceText) {
          result.source += 1
        }
        if (entry.translatedText) {
          result.translated += 1
        }
        return result
      },
      { revised: 0, source: 0, translated: 0 },
    )
  }, [entries])

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

  useEffect(() => {
    if (!isOpen) {
      setCopyStatus('idle')
    }
  }, [isOpen])

  if (!isOpen) {
    return null
  }

  const recentEntries = entries.slice(-30).reverse()
  const canExport = hasExportableSubtitles(entries)
  const canExportDiagnostics = diagnosticsText.trim().length > 0

  const handleCopy = async (): Promise<void> => {
    if (!canExport) {
      return
    }

    const transcriptText = formatPlainTranscript(entries)
    try {
      await navigator.clipboard.writeText(transcriptText)
      setCopyStatus('copied')
      window.setTimeout(() => setCopyStatus('idle'), 1600)
    } catch {
      setCopyStatus('failed')
      window.setTimeout(() => setCopyStatus('idle'), 1600)
    }
  }

  const handleDownloadTranscript = (): void => {
    if (!canExport) {
      return
    }

    downloadTextFile(
      formatPlainTranscript(entries),
      `ai-interpreter-transcript-${Date.now()}.txt`,
      'text/plain;charset=utf-8',
    )
  }

  const handleDownloadSrt = (): void => {
    if (!canExport) {
      return
    }

    downloadTextFile(
      formatSrtSubtitles(entries),
      `ai-interpreter-subtitles-${Date.now()}.srt`,
      'application/x-subrip;charset=utf-8',
    )
  }

  const handleDownloadVtt = (): void => {
    if (!canExport) {
      return
    }

    downloadTextFile(
      formatVttSubtitles(entries),
      `ai-interpreter-subtitles-${Date.now()}.vtt`,
      'text/vtt;charset=utf-8',
    )
  }

  const handleDownloadNotes = (): void => {
    if (!canExport) {
      return
    }

    downloadTextFile(
      formatLearningNotesMarkdown(entries),
      `ai-interpreter-notes-${Date.now()}.md`,
      'text/markdown;charset=utf-8',
    )
  }

  const handleDownloadDiagnostics = (): void => {
    if (!canExportDiagnostics) {
      return
    }

    downloadTextFile(
      diagnosticsText,
      `ai-interpreter-diagnostics-${Date.now()}.txt`,
      'text/plain;charset=utf-8',
    )
  }

  return (
    <section
      aria-label="Subtitle history"
      role="dialog"
      aria-modal="false"
      style={panelStyle}
    >
      <div style={headerStyle}>
        <div>
          <div style={{ color: '#ffffff', fontSize: '15px', fontWeight: 800 }}>
            Subtitle history
          </div>
          <div style={{ color: '#91a0b3', fontSize: '12px', marginTop: '4px' }}>
            Latest {recentEntries.length} of {entries.length} entries
          </div>
        </div>
        <div style={{ borderRadius: '12px', overflow: 'hidden' }}>
          <button
            type="button"
            aria-label="Close subtitle history"
            style={{
              ...tapSafeButtonStyle,
              minHeight: '44px',
              minWidth: '64px',
              background: 'rgba(255,255,255,0.08)',
              color: '#d9e1eb',
            }}
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>

      <div style={summaryStyle}>
        <SummaryStat label="Source" value={stats.source} />
        <SummaryStat label="Translated" value={stats.translated} />
        <SummaryStat label="Revised" value={stats.revised} />
      </div>

      <div style={listStyle}>
        {recentEntries.length === 0 ? (
          <div
            style={{
              padding: '24px 10px',
              textAlign: 'center',
              color: '#91a0b3',
              fontSize: '13px',
            }}
          >
            No subtitles yet.
          </div>
        ) : recentEntries.map((entry) => (
          <article
            key={entry.segmentId}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'stretch',
              gap: '6px',
              minWidth: 0,
              padding: '12px',
              borderRadius: '16px',
              background: entry.isRevised
                ? 'linear-gradient(135deg, rgba(244,200,76,0.14), rgba(255,255,255,0.04))'
                : 'rgba(255,255,255,0.045)',
              border: entry.isRevised
                ? '1px solid rgba(244,200,76,0.34)'
                : '1px solid rgba(255,255,255,0.07)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
                color: '#7f8ea3',
                fontSize: '11px',
              }}
            >
              <span>{formatTime(entry.timestamp)}</span>
              {entry.isRevised ? (
                <span style={{ color: '#f4c84c', fontWeight: 700 }}>
                  {entry.revisionReason === 'asr_correction' ? 'ASR revised' : 'Translation revised'}
                </span>
              ) : null}
            </div>
            {entry.sourceText ? (
              <div style={{ color: '#b9c5d3', fontSize: '13px', lineHeight: 1.42, wordBreak: 'break-word' }}>
                {entry.sourceText}
              </div>
            ) : null}
            {entry.translatedText ? (
              <div style={{ color: '#ffffff', fontSize: '15px', lineHeight: 1.46, fontWeight: 650, wordBreak: 'break-word' }}>
                {entry.translatedText}
              </div>
            ) : null}
          </article>
        ))}
      </div>

      <div style={footerStyle}>
        <div style={{ borderRadius: '12px', overflow: 'hidden' }}>
          <button
            type="button"
            disabled={!canExport}
            style={{
              ...tapSafeButtonStyle,
              width: '100%',
              minHeight: '44px',
              background: canExport ? 'rgba(74,163,255,0.18)' : 'rgba(255,255,255,0.04)',
              color: canExport ? '#ffffff' : '#718093',
              border: '1px solid rgba(74,163,255,0.25)',
              cursor: canExport ? 'pointer' : 'not-allowed',
            }}
            onClick={() => {
              void handleCopy()
            }}
          >
            {copyStatus === 'copied' ? 'Copied' : copyStatus === 'failed' ? 'Copy failed' : 'Copy TXT'}
          </button>
        </div>
        <div style={{ borderRadius: '12px', overflow: 'hidden' }}>
          <button
            type="button"
            disabled={!canExport}
            style={{
              ...tapSafeButtonStyle,
              width: '100%',
              minHeight: '44px',
              background: canExport ? '#f4c84c' : 'rgba(255,255,255,0.04)',
              color: canExport ? '#10141b' : '#718093',
              cursor: canExport ? 'pointer' : 'not-allowed',
            }}
            onClick={handleDownloadTranscript}
          >
            Download TXT
          </button>
        </div>
        <ExportButton
          label="Download SRT"
          disabled={!canExport}
          onClick={handleDownloadSrt}
        />
        <ExportButton
          label="Download VTT"
          disabled={!canExport}
          onClick={handleDownloadVtt}
        />
        <ExportButton
          label="Notes MD"
          disabled={!canExport}
          onClick={handleDownloadNotes}
        />
        <div style={{ gridColumn: '1 / -1', borderRadius: '12px', overflow: 'hidden' }}>
          <button
            type="button"
            disabled={!canExportDiagnostics}
            style={{
              ...tapSafeButtonStyle,
              width: '100%',
              minHeight: '44px',
              background: canExportDiagnostics ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.04)',
              color: canExportDiagnostics ? '#d9e1eb' : '#718093',
              border: '1px solid rgba(255,255,255,0.1)',
              cursor: canExportDiagnostics ? 'pointer' : 'not-allowed',
            }}
            onClick={handleDownloadDiagnostics}
          >
            Download diagnostics
          </button>
        </div>
      </div>
    </section>
  )
}


interface SummaryStatProps {
  label: string
  value: number
}


const SummaryStat: React.FC<SummaryStatProps> = ({ label, value }) => (
  <div
    style={{
      minWidth: 0,
      padding: '8px 10px',
      borderRadius: '12px',
      background: 'rgba(255,255,255,0.04)',
      border: '1px solid rgba(255,255,255,0.06)',
    }}
  >
    <div style={{ color: '#91a0b3', fontSize: '11px' }}>{label}</div>
    <div style={{ color: '#ffffff', fontSize: '18px', fontWeight: 800 }}>{value}</div>
  </div>
)


interface ExportButtonProps {
  label: string
  disabled: boolean
  onClick: () => void
}


const ExportButton: React.FC<ExportButtonProps> = ({ label, disabled, onClick }) => (
  <div style={{ borderRadius: '12px', overflow: 'hidden' }}>
    <button
      type="button"
      disabled={disabled}
      style={{
        ...tapSafeButtonStyle,
        width: '100%',
        minHeight: '44px',
        background: disabled ? 'rgba(255,255,255,0.04)' : 'rgba(255,255,255,0.08)',
        color: disabled ? '#718093' : '#d9e1eb',
        border: '1px solid rgba(255,255,255,0.1)',
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
      onClick={onClick}
    >
      {label}
    </button>
  </div>
)


function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}


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
