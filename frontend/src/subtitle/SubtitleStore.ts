import type { RevisionReason, SubtitleEntry, SubtitleMode } from '../types'


export class SubtitleStore {
  private _subtitles: SubtitleEntry[] = []
  private _history: SubtitleEntry[] = []
  private _maxVisible = 6
  private _maxHistory = 200
  private _listeners: Set<() => void> = new Set()
  private _mode: SubtitleMode = 'bilingual'

  get subtitles(): SubtitleEntry[] {
    return this._subtitles
  }

  get history(): SubtitleEntry[] {
    return this._history
  }

  get maxVisible(): number {
    return this._maxVisible
  }

  get mode(): SubtitleMode {
    return this._mode
  }

  subscribe(listener: () => void): () => void {
    this._listeners.add(listener)
    return () => this._listeners.delete(listener)
  }

  setMode(mode: SubtitleMode): void {
    if (this._mode === mode) {
      return
    }
    this._mode = mode
    this._notify()
  }

  upsertSource(segmentId: string, sourceText: string, timestamp = Date.now()): void {
    const existing = this._getOrCreateEntry(segmentId, timestamp)
    if (existing.sourceText !== sourceText) {
      existing.sourceText = sourceText
    }
    existing.timestamp = timestamp

    this._cleanup()
    this._notify()
  }

  appendToken(segmentId: string, token: string): void {
    const existing = this._getOrCreateEntry(segmentId)
    existing.translatedText += token
    existing.isPartial = true

    this._cleanup()
    this._notify()
  }

  finalizeSubtitle(segmentId: string): void {
    const existing = this._findEntry(segmentId)
    if (!existing) {
      return
    }

    existing.isPartial = false
    this._notify()
  }

  reviseSubtitle(
    segmentId: string,
    newText: string,
    reason: RevisionReason = 'translation_correction',
  ): void {
    const existing = this._findEntry(segmentId)
    if (!existing) {
      return
    }

    existing.translatedText = newText
    existing.isRevised = true
    existing.isPartial = false
    existing.revisionReason = reason
    existing.revisedAt = Date.now()
    this._notify()
  }

  reviseSource(
    segmentId: string,
    sourceText: string,
    reason: RevisionReason = 'asr_correction',
  ): void {
    const existing = this._findEntry(segmentId)
    if (!existing) {
      return
    }

    existing.sourceText = sourceText
    existing.isRevised = true
    existing.isPartial = false
    existing.revisionReason = reason
    existing.revisedAt = Date.now()
    this._notify()
  }

  reset(): void {
    this._subtitles = []
    this._history = []
    this._notify()
  }

  exportTranscript(): string {
    return this._history
      .filter((entry) => entry.sourceText || entry.translatedText)
      .map((entry, index) => {
        const time = this._formatTimestamp(entry.timestamp)
        const revisionLabel = entry.isRevised ? ` [revised:${entry.revisionReason ?? 'unknown'}]` : ''
        return [
          `${index + 1}. ${time}${revisionLabel}`,
          `EN: ${entry.sourceText || '-'}`,
          `ZH: ${entry.translatedText || '-'}`,
        ].join('\n')
      })
      .join('\n\n')
  }

  private _getOrCreateEntry(segmentId: string, timestamp = Date.now()): SubtitleEntry {
    const existing = this._findEntry(segmentId)
    if (existing) {
      return existing
    }

    const entry: SubtitleEntry = {
      segmentId,
      sourceText: '',
      translatedText: '',
      isPartial: true,
      isRevised: false,
      timestamp,
    }
    this._history.push(entry)
    return entry
  }

  private _findEntry(segmentId: string): SubtitleEntry | undefined {
    return this._history.find((entry) => entry.segmentId === segmentId)
  }

  private _cleanup(): void {
    this._subtitles = this._history.slice(-this._maxVisible)

    while (this._history.length > this._maxHistory) {
      this._history.shift()
    }
    this._subtitles = this._history.slice(-this._maxVisible)
  }

  private _notify(): void {
    this._listeners.forEach((listener) => listener())
  }

  private _formatTimestamp(timestamp: number): string {
    return new Date(timestamp).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }
}
