import React, { useEffect, useMemo, useRef, useState } from 'react'

import {
  Archive,
  BookMarked,
  Check,
  ClipboardCopy,
  FileCode2,
  FileText,
  History,
  ScrollText,
  Search,
  SkipForward,
  StickyNote,
  X,
} from 'lucide-react'

import {
  formatLearningNotesMarkdown,
  formatPlainTranscript,
  formatSrtSubtitles,
  formatVttSubtitles,
  hasExportableSubtitles,
} from '../subtitle/subtitle-export'
import { buildSessionBundle, bundleTimestamp } from '../export/session-bundle'
import { filterSubtitlesByQuery, splitHighlightedText } from '../subtitle/subtitle-search'
import { subtitleToSeekSample } from '../subtitle/subtitle-seek'
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
  /** 第二梯队-方向 5：文件音频源总采样数（非 file 源为 0）。 */
  fileSampleCount: number
  /** 第二梯队-方向 5：跳转到指定采样位置（返回是否成功）。 */
  onSeekToSample?: (sampleOffset: number) => boolean
}


/** 虚拟滚动用的估算条目高度（px）。 */
const SUBTITLE_ITEM_HEIGHT = 140


export const SubtitleHistoryPanel: React.FC<SubtitleHistoryPanelProps> = ({
  entries,
  isOpen,
  diagnosticsText,
  uiText,
  onClose,
  fileSampleCount,
  onSeekToSample,
}) => {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle')
  const [bundleStatus, setBundleStatus] = useState<'idle' | 'exported'>('idle')
  const [seekError, setSeekError] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const text = uiText.history
  const listRef = useRef<HTMLDivElement>(null)
  const [viewportHeight, setViewportHeight] = useState(320)

  // 阶段 5：历史搜索 —— 按原文/译文大小写不敏感过滤（空格分割的关键词全部命中）。
  const filteredEntries = useMemo(
    () => filterSubtitlesByQuery(entries, searchQuery),
    [entries, searchQuery],
  )

  // 长会议历史可达数千条：只渲染视口内条目（虚拟滚动），保持主线程流畅
  const reversedEntries = useMemo(() => filteredEntries.slice().reverse(), [filteredEntries])
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
        setSearchQuery('')
        onClose()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isOpen, onClose])

  useEffect(() => {
    if (!isOpen) {
      setSearchQuery('')
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) {
      setCopyStatus('idle')
    }
  }, [isOpen])

  if (!isOpen) {
    return null
  }

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

  const handleDownloadBundle = (): void => {
    if (!canExport) {
      return
    }

    const { blob } = buildSessionBundle({
      entries,
      diagnosticsText,
      summaryMarkdown: undefined,
      sessionLabel: `session-${bundleTimestamp()}`,
    })
    downloadBlobFile(blob, `ai-interpreter-bundle-${bundleTimestamp()}.zip`)
    setBundleStatus('exported')
    window.setTimeout(() => setBundleStatus('idle'), 1600)
  }

  const handleSeekToEntry = (entry: SubtitleEntry): void => {
    if (!onSeekToSample || fileSampleCount <= 0) {
      setSeekError(true)
      window.setTimeout(() => setSeekError(false), 1600)
      return
    }
    const sampleOffset = subtitleToSeekSample(entry, entries, fileSampleCount)
    if (sampleOffset === null) {
      setSeekError(true)
      window.setTimeout(() => setSeekError(false), 1600)
      return
    }
    const ok = onSeekToSample(sampleOffset)
    if (!ok) {
      setSeekError(true)
      window.setTimeout(() => setSeekError(false), 1600)
    }
  }

  return (
    <section
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="false"
      className="history-panel"
    >
      <div className="history-header">
        <div className="history-title">
          <History size={18} />
          <h3>{text.title}</h3>
        </div>
        <button type="button" className="btn-secondary" style={{ width: 'auto', minHeight: '38px', padding: '0 14px' }} onClick={onClose}>
          <X size={14} />
          {text.close}
        </button>
      </div>

      <div className="history-summary">
        <SummaryStat label={text.source} value={stats.source} />
        <SummaryStat label={text.translated} value={stats.translated} />
        <SummaryStat label={text.revised} value={stats.revised} />
      </div>

      <div className="history-search">
        <Search size={14} />
        <input
          type="search"
          value={searchQuery}
          aria-label={text.searchPlaceholder}
          placeholder={text.searchPlaceholder}
          onChange={(event) => setSearchQuery(event.currentTarget.value)}
        />
        {searchQuery ? (
          <button
            type="button"
            aria-label={text.searchClear}
            onClick={() => setSearchQuery('')}
          >
            <X size={13} />
          </button>
        ) : null}
        {searchQuery.trim() ? (
          <span className="history-search-count">
            {filteredEntries.length > 0
              ? text.searchMatchLabel(filteredEntries.length)
              : text.searchNoMatch}
          </span>
        ) : null}
        {seekError ? (
          <span className="history-seek-error">{text.seekUnavailable}</span>
        ) : null}
      </div>

      <div ref={listRef} className="history-list" onScroll={onScroll}>
        {/* 顶部占位：撑起滚动条比例 */}
        <div style={{ height: offsetY, flexShrink: 0 }} />
        {visible.length === 0 ? (
          <div
            style={{
              padding: '28px 10px',
              textAlign: 'center',
              color: 'var(--text-3)',
              fontSize: '13px',
            }}
          >
            {searchQuery.trim() ? text.searchNoMatch : text.empty}
          </div>
        ) : visible.map((entry) => (
          <article
            key={entry.segmentId}
            className={`history-entry ${entry.isRevised ? 'revised' : ''}`}
          >
            <div className="history-entry-meta">
              <span style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <span>{formatTime(entry.timestamp)}</span>
                {onSeekToSample && fileSampleCount > 0 ? (
                  <button
                    type="button"
                    className="history-seek-btn"
                    aria-label={text.jumpToEntry}
                    title={text.jumpToEntry}
                    onClick={() => handleSeekToEntry(entry)}
                  >
                    <SkipForward size={13} />
                    {text.jumpToEntry}
                  </button>
                ) : null}
              </span>
              <span style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                {entry.speaker ? (
                  <span className="history-badge speaker" style={{ color: speakerColor(entry.speaker) }}>
                    <MicDot />
                    {entry.speaker}
                  </span>
                ) : null}
                {entry.isRevised ? (
                  <span className="history-badge revised">
                    <RefreshDot />
                    {entry.revisionReason === 'asr_correction'
                      ? text.asrRevised
                      : text.translationRevised}
                  </span>
                ) : null}
              </span>
            </div>
            {entry.sourceText ? (
              <div style={{ color: 'var(--text-1)', fontSize: '13px', lineHeight: 1.45, wordBreak: 'break-word' }}>
                <HighlightedText text={entry.sourceText} query={searchQuery} />
              </div>
            ) : null}
            {entry.translatedText ? (
              <div style={{ color: 'var(--text-0)', fontSize: '15px', lineHeight: 1.5, fontWeight: 650, wordBreak: 'break-word' }}>
                <HighlightedText text={entry.translatedText} query={searchQuery} />
              </div>
            ) : null}
          </article>
        ))}
        {/* 底部占位：撑起滚动条比例 */}
        <div
          style={{
            height: Math.max(0, totalHeight - offsetY - visible.length * SUBTITLE_ITEM_HEIGHT),
            flexShrink: 0,
          }}
        />
      </div>

      <div className="history-footer">
        <button
          type="button"
          className="btn-secondary"
          disabled={!canExport}
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
              : text.copyTxt}
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={!canExport}
          style={canExport ? { background: 'linear-gradient(120deg, rgba(244,200,76,0.2), rgba(249,168,212,0.16))', color: '#fff', borderColor: 'rgba(244,200,76,0.4)' } : undefined}
          onClick={handleDownloadTranscript}
        >
          <FileText size={15} />
          {text.downloadTxt}
        </button>
        <ExportButton label={text.downloadSrt} disabled={!canExport} onClick={handleDownloadSrt} icon={<FileCode2 size={15} />} />
        <ExportButton label={text.downloadVtt} disabled={!canExport} onClick={handleDownloadVtt} icon={<ScrollText size={15} />} />
        <ExportButton label={text.notesMd} disabled={!canExport} onClick={handleDownloadNotes} icon={<StickyNote size={15} />} />
        <button
          type="button"
          className="btn-secondary"
          disabled={!canExport}
          style={{
            gridColumn: '1 / -1',
            ...(canExport
              ? { background: 'linear-gradient(120deg, rgba(99,102,241,0.25), rgba(56,189,248,0.18))', color: '#fff', borderColor: 'rgba(99,102,241,0.45)' }
              : undefined),
          }}
          onClick={handleDownloadBundle}
        >
          <Archive size={15} />
          {bundleStatus === 'exported' ? text.bundleDownloaded : text.downloadBundle}
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={!canExportDiagnostics}
          style={{ gridColumn: '1 / -1' }}
          onClick={handleDownloadDiagnostics}
        >
          <BookMarked size={15} />
          {text.downloadDiagnostics}
        </button>
      </div>
    </section>
  )
}


interface SummaryStatProps {
  label: string
  value: number
}


const SummaryStat: React.FC<SummaryStatProps> = ({ label, value }) => (
  <div className="metric-card">
    <div className="metric-label">{label}</div>
    <div className="metric-value" style={{ fontSize: '19px' }}>{value}</div>
  </div>
)


interface ExportButtonProps {
  label: string
  disabled: boolean
  icon?: React.ReactNode
  onClick: () => void
}


const ExportButton: React.FC<ExportButtonProps> = ({ label, disabled, icon, onClick }) => (
  <button
    type="button"
    className="btn-secondary"
    disabled={disabled}
    onClick={onClick}
  >
    {icon}
    {label}
  </button>
)


const MicDot: React.FC = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" width={11} height={11}>
    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" x2="12" y1="19" y2="22" />
  </svg>
)

const RefreshDot: React.FC = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" width={11} height={11}>
    <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
    <path d="M21 3v5h-5" />
    <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
    <path d="M3 21v-5h5" />
  </svg>
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
  downloadBlobFile(blob, filename)
}

function downloadBlobFile(blob: Blob, filename: string): void {
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


interface HighlightedTextProps {
  text: string
  query: string
}

/**
 * 阶段 5：在历史条目文本中高亮搜索关键词（大小写不敏感、支持空格分隔多词）。
 * 无查询时原样返回文本，避免无谓的 DOM 拆分。
 */
const HighlightedText: React.FC<HighlightedTextProps> = ({ text, query }) => {
  const parts = splitHighlightedText(text, query)
  return (
    <>
      {parts.map((part, index) =>
        part.matched ? (
          <mark key={index} className="history-search-highlight">
            {part.text}
          </mark>
        ) : (
          <React.Fragment key={index}>{part.text}</React.Fragment>
        ),
      )}
    </>
  )
}
