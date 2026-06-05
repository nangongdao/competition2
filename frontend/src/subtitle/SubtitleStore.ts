import type { SubtitleEntry, SubtitleMode } from '../types'


export class SubtitleStore {
  private _subtitles: SubtitleEntry[] = []
  private _maxVisible = 6
  private _listeners: Set<() => void> = new Set()
  private _mode: SubtitleMode = 'bilingual'

  get subtitles(): SubtitleEntry[] {
    return this._subtitles
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
    const existing = this._subtitles.find((entry) => entry.segmentId === segmentId)
    if (existing) {
      existing.sourceText = sourceText
      existing.timestamp = timestamp
    } else {
      this._subtitles.push({
        segmentId,
        sourceText,
        translatedText: '',
        isPartial: true,
        isRevised: false,
        timestamp,
      })
    }

    this._cleanup()
    this._notify()
  }

  appendToken(segmentId: string, token: string): void {
    const existing = this._subtitles.find((entry) => entry.segmentId === segmentId)
    if (!existing) {
      this._subtitles.push({
        segmentId,
        sourceText: '',
        translatedText: token,
        isPartial: true,
        isRevised: false,
        timestamp: Date.now(),
      })
    } else {
      existing.translatedText += token
      existing.isPartial = true
    }

    this._cleanup()
    this._notify()
  }

  finalizeSubtitle(segmentId: string): void {
    const existing = this._subtitles.find((entry) => entry.segmentId === segmentId)
    if (!existing) {
      return
    }

    existing.isPartial = false
    this._notify()
  }

  reviseSubtitle(segmentId: string, newText: string): void {
    const existing = this._subtitles.find((entry) => entry.segmentId === segmentId)
    if (!existing) {
      return
    }

    existing.translatedText = newText
    existing.isRevised = true
    existing.isPartial = false
    this._notify()
  }

  reviseSource(segmentId: string, sourceText: string): void {
    const existing = this._subtitles.find((entry) => entry.segmentId === segmentId)
    if (!existing) {
      return
    }

    existing.sourceText = sourceText
    existing.isRevised = true
    existing.isPartial = false
    this._notify()
  }

  reset(): void {
    this._subtitles = []
    this._notify()
  }

  private _cleanup(): void {
    while (this._subtitles.length > this._maxVisible) {
      this._subtitles.shift()
    }
  }

  private _notify(): void {
    this._listeners.forEach((listener) => listener())
  }
}
