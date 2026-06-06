import type { RevisionReason, SubtitleEntry } from '../types'


const DEFAULT_SUBTITLE_DURATION_MS = 2600
const MIN_SUBTITLE_DURATION_MS = 900
const MAX_SUBTITLE_DURATION_MS = 6500
const SUBTITLE_GAP_MS = 80


interface TimedSubtitleEntry {
  entry: SubtitleEntry
  index: number
  startMs: number
  endMs: number
}


export function hasExportableSubtitles(entries: SubtitleEntry[]): boolean {
  return entries.some((entry) => hasSubtitleText(entry))
}


export function formatPlainTranscript(entries: SubtitleEntry[]): string {
  return getExportableEntries(entries)
    .map((entry, index) => {
      const time = formatClockTime(entry.timestamp)
      const revisionLabel = entry.isRevised ? ` [revised:${entry.revisionReason ?? 'unknown'}]` : ''
      return [
        `${index + 1}. ${time}${revisionLabel}`,
        `EN: ${entry.sourceText || '-'}`,
        `ZH: ${entry.translatedText || '-'}`,
      ].join('\n')
    })
    .join('\n\n')
}


export function formatSrtSubtitles(entries: SubtitleEntry[]): string {
  return getTimedEntries(entries)
    .map((timedEntry) => {
      return [
        String(timedEntry.index + 1),
        `${formatSrtTimestamp(timedEntry.startMs)} --> ${formatSrtTimestamp(timedEntry.endMs)}`,
        ...formatSubtitleLines(timedEntry.entry),
      ].join('\n')
    })
    .join('\n\n')
}


export function formatVttSubtitles(entries: SubtitleEntry[]): string {
  const cues = getTimedEntries(entries)
    .map((timedEntry) => {
      return [
        `${formatVttTimestamp(timedEntry.startMs)} --> ${formatVttTimestamp(timedEntry.endMs)}`,
        ...formatSubtitleLines(timedEntry.entry),
      ].join('\n')
    })
    .join('\n\n')

  return cues ? `WEBVTT\n\n${cues}` : 'WEBVTT'
}


export function formatLearningNotesMarkdown(entries: SubtitleEntry[]): string {
  const exportableEntries = getExportableEntries(entries)
  const revisedCount = exportableEntries.filter((entry) => entry.isRevised).length
  const sourceCount = exportableEntries.filter((entry) => entry.sourceText.trim()).length
  const translatedCount = exportableEntries.filter((entry) => entry.translatedText.trim()).length
  const generatedAt = new Date().toLocaleString()
  const lines = [
    '# AI Interpreter Learning Notes',
    '',
    `Generated: ${generatedAt}`,
    `Entries: ${exportableEntries.length}`,
    `Source lines: ${sourceCount}`,
    `Translated lines: ${translatedCount}`,
    `Revised lines: ${revisedCount}`,
    '',
    '## Timeline',
  ]

  if (exportableEntries.length === 0) {
    lines.push('', 'No subtitles were captured.')
    return lines.join('\n')
  }

  exportableEntries.forEach((entry, index) => {
    lines.push(
      '',
      `### ${index + 1}. ${formatClockTime(entry.timestamp)}`,
      '',
      `- Source: ${formatMarkdownInline(entry.sourceText || '-')}`,
      `- Translation: ${formatMarkdownInline(entry.translatedText || '-')}`,
    )

    if (entry.isRevised) {
      lines.push(`- Revision: ${formatRevisionReason(entry.revisionReason)}${formatRevisionTime(entry.revisedAt)}`)
    }
  })

  return lines.join('\n')
}


function getExportableEntries(entries: SubtitleEntry[]): SubtitleEntry[] {
  return entries.filter((entry) => hasSubtitleText(entry))
}


function getTimedEntries(entries: SubtitleEntry[]): TimedSubtitleEntry[] {
  const exportableEntries = getExportableEntries(entries)
  if (exportableEntries.length === 0) {
    return []
  }

  const baseTimestamp = exportableEntries[0].timestamp
  return exportableEntries.map((entry, index) => {
    const startMs = Math.max(0, entry.timestamp - baseTimestamp)
    const nextEntry = exportableEntries[index + 1]
    const suggestedDurationMs = getSuggestedDurationMs(entry)
    const naturalEndMs = startMs + suggestedDurationMs

    if (!nextEntry) {
      return {
        entry,
        index,
        startMs,
        endMs: naturalEndMs,
      }
    }

    const nextStartMs = Math.max(startMs + 1, nextEntry.timestamp - baseTimestamp)
    const latestEndMs = Math.max(startMs + 1, nextStartMs - SUBTITLE_GAP_MS)
    return {
      entry,
      index,
      startMs,
      endMs: Math.min(naturalEndMs, latestEndMs),
    }
  })
}


function hasSubtitleText(entry: SubtitleEntry): boolean {
  return entry.sourceText.trim().length > 0 || entry.translatedText.trim().length > 0
}


function formatSubtitleLines(entry: SubtitleEntry): string[] {
  const lines: string[] = []

  if (entry.sourceText.trim()) {
    lines.push(`EN: ${formatSubtitleText(entry.sourceText)}`)
  }
  if (entry.translatedText.trim()) {
    lines.push(`ZH: ${formatSubtitleText(entry.translatedText)}`)
  }
  if (entry.isRevised) {
    lines.push(`[${formatRevisionReason(entry.revisionReason)}]`)
  }

  return lines
}


function getSuggestedDurationMs(entry: SubtitleEntry): number {
  const textLength = `${entry.sourceText} ${entry.translatedText}`.trim().length
  const durationMs = Math.max(
    MIN_SUBTITLE_DURATION_MS,
    Math.min(MAX_SUBTITLE_DURATION_MS, textLength * 55),
  )
  return Math.max(DEFAULT_SUBTITLE_DURATION_MS, durationMs)
}


function formatSubtitleText(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}


function formatMarkdownInline(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}


function formatRevisionReason(reason: RevisionReason | undefined): string {
  switch (reason) {
    case 'asr_correction':
      return 'ASR revised'
    case 'translation_correction':
      return 'Translation revised'
    default:
      return 'Revised'
  }
}


function formatRevisionTime(revisedAt: number | undefined): string {
  if (!revisedAt) {
    return ''
  }
  return ` at ${formatClockTime(revisedAt)}`
}


function formatClockTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}


function formatSrtTimestamp(timestampMs: number): string {
  return formatDurationTimestamp(timestampMs, ',')
}


function formatVttTimestamp(timestampMs: number): string {
  return formatDurationTimestamp(timestampMs, '.')
}


function formatDurationTimestamp(timestampMs: number, millisecondSeparator: ',' | '.'): string {
  const safeTimestampMs = Math.max(0, Math.floor(timestampMs))
  const milliseconds = safeTimestampMs % 1000
  const totalSeconds = Math.floor(safeTimestampMs / 1000)
  const seconds = totalSeconds % 60
  const totalMinutes = Math.floor(totalSeconds / 60)
  const minutes = totalMinutes % 60
  const hours = Math.floor(totalMinutes / 60)

  return [
    padNumber(hours, 2),
    padNumber(minutes, 2),
    padNumber(seconds, 2),
  ].join(':') + millisecondSeparator + padNumber(milliseconds, 3)
}


function padNumber(value: number, length: number): string {
  return String(value).padStart(length, '0')
}
