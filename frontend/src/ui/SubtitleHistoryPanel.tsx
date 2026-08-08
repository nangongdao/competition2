import React, { useEffect, useMemo, useRef, useState } from 'react'

import {
  formatLearningNotesMarkdown,
  formatPlainTranscript,
  formatSrtSubtitles,
  formatVttSubtitles,
  hasExportableSubtitles,
} from '../subtitle/subtitle-export'
import { useVirtualizedSubtitles } from '../subtitle/virtual-scroll'
import { speakerColor } from '../subtitle/speaker'
import type { UiText } from '../i18n'
import type { SubtitleEntry } from '../types'


interface SubtitleHistoryPanelProps {
  entries: SubtitleEntry[]
  isOpen: boolean
  diagnosticsText: string
  uiText: UiText
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
  position: 'relative',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'stretch',
  gap: '10px',
  minHeight: 0,
  overflowY: 'auto',
  padding: '14px',
  overscrollBehavior: 'contain',
}


/** 虚拟滚动用的估算条目高度（px）。 */
const SUBTITLE_ITEM_HEIGHT = 140


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
  uiText,
  onClose,
}) => {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle')
  const text = uiText.history
  const listRef = useRef<HTMLDivElement>(null)
  const [viewportHeight, setViewportHeight] = useState(320)

  // 长会议历史可达数千条：只渲染视口内条目（虚拟滚动），保持主线程流畅
  const reversedEntries = useMemo(() => entries.slice().reverse(), [entries])
  const { visible, offsetY, totalHeight, onScroll } = useVirtualizedSubtitles(
    reversedEntries,
    viewportHeight,
    SUBTITLE_ITEM_HEIGHT,
  )

  useEffect(() => {
    const element = listRef.current
    if (!element) {
      return
    }
    const updateHeight = (): void => {
      setViewportHeight(element.clientHeight || 320)
    }
    updateHeight()
    const observer = new ResizeObserver(updateHeight)
    observer.observe(element)
    return () => observer.disconnect()
  }, [isOpen])

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

  const recentEntries = visible
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
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="false"
      style={panelStyle}
    >
      <div style={headerStyle}>
        <div>
          <div style={{ color: '#ffffff', fontSize: '15px', fontWeight: 800 }}>
            {text.title}
          </div>
          <div style={{ color: '#91a0b3', fontSize: '12px', marginTop: '4px' }}>
            {text.latestSummary(entries.length, entries.length)}
          </div>
        </div>
        <div style={{ borderRadius: '12px', overflow: 'hidden' }}>
          <button
            type="button"
            aria-label={text.closeAriaLabel}
            style={{
              ...tapSafeButtonStyle,
              minHeight: '44px',
              minWidth: '64px',
              background: 'rgba(255,255,255,0.08)',
              color: '#d9e1eb',
            }}
            onClick={onClose}
          >
            {text.close}
          </button>
        </div>
      </div>

      <div style={summaryStyle}>
        <SummaryStat label={text.source} value={stats.source} />
        <SummaryStat label={text.translated} value={stats.translated} />
        <SummaryStat label={text.revised} value={stats.revised} />
      </div>

      <div ref={listRef} style={listStyle} onScroll={onScroll}>
        {/* 顶部占位：撑起滚动条比例 */}
        <div style={{ height: offsetY, flexShrink: 0 }} />
        {recentEntries.length === 0 ? (
          <div
            style={{
              padding: '24px 10px',
              textAlign: 'center',
              color: '#91a0b3',
              fontSize: '13px',
            }}
          >
            {text.empty}
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
              <span style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                {entry.speaker ? (
                  <span style={{ color: speakerColor(entry.speaker), fontWeight: 700 }}>
                    {entry.speaker}
                  </span>
                ) : null}
                {entry.isRevised ? (
                  <span style={{ color: '#f4c84c', fontWeight: 700 }}>
                    {entry.revisionReason === 'asr_correction'
                      ? text.asrRevised
                      : text.translationRevised}
                  </span>
                ) : null}
              </span>
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
        {/* 底部占位：撑起滚动条比例 */}
        <div
          style={{
            height: Math.max(0, totalHeight - offsetY - recentEntries.length * SUBTITLE_ITEM_HEIGHT),
            flexShrink: 0,
          }}
        />
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
            {copyStatus === 'copied'
              ? text.copied
              : copyStatus === 'failed'
                ? text.copyFailed
                : text.copyTxt}
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
            {text.downloadTxt}
          </button>
        </div>
        <ExportButton
          label={text.downloadSrt}
          disabled={!canExport}
          onClick={handleDownloadSrt}
        />
        <ExportButton
          label={text.downloadVtt}
          disabled={!canExport}
          onClick={handleDownloadVtt}
        />
        <ExportButton
          label={text.notesMd}
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
            {text.downloadDiagnostics}
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
