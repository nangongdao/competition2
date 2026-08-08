import type { RevisionReason, SubtitleEntry, SubtitleMode } from '../types'
import { formatPlainTranscript } from './subtitle-export'


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

  upsertSource(
    segmentId: string,
    sourceText: string,
    timestamp = Date.now(),
    seq?: number,
    speaker?: string,
  ): void {
    const existing = this._getOrCreateEntry(segmentId, timestamp, seq)
    if (existing.sourceText !== sourceText) {
      existing.sourceText = sourceText
    }
    existing.timestamp = timestamp
    if (speaker) {
      existing.speaker = speaker
    }

    this._cleanup()
    this._notify()
  }

  appendToken(segmentId: string, token: string, seq?: number): void {
    const existing = this._getOrCreateEntry(segmentId, Date.now(), seq)
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

  getEntry(segmentId: string): SubtitleEntry | undefined {
    return this._findEntry(segmentId)
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
    return formatPlainTranscript(this._history)
  }

  private _getOrCreateEntry(segmentId: string, timestamp = Date.now(), seq?: number): SubtitleEntry {
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
      seq,
    }
    this._insertOrdered(entry)
    return entry
  }

  /**
   * 按片段序号有序插入字幕条目。
   *
   * 翻译异步化后结果可能乱序到达，必须按序号定位而非追加，
   * 否则短句会插到长句前面。序号缺失时回退为按 segmentId 解析，
   * 仍无法解析则追加到末尾。
   */
  private _insertOrdered(entry: SubtitleEntry): void {
    const entrySeq = entry.seq ?? seqOf(entry.segmentId)
    if (entrySeq === null) {
      this._history.push(entry)
      return
    }

    const index = this._history.findIndex((item) => {
      const itemSeq = item.seq ?? seqOf(item.segmentId)
      return itemSeq !== null && itemSeq > entrySeq
    })
    if (index === -1) {
      this._history.push(entry)
    } else {
      this._history.splice(index, 0, entry)
    }
  }

  private _findEntry(segmentId: string): SubtitleEntry | undefined {
    return this._history.find((entry) => entry.segmentId === segmentId)
  }  private _cleanup(): void {
    this._subtitles = this._history.slice(-this._maxVisible)

    while (this._history.length > this._maxHistory) {
      this._history.shift()
    }
    this._subtitles = this._history.slice(-this._maxVisible)
  }

  private _notify(): void {
    this._listeners.forEach((listener) => listener())
  }

}


/**
 * 从 segmentId 解析单调递增的片段序号。
 *
 * segmentId 形如 "{session_id}_{index}"，序号恒为末段。
 * 解析失败返回 null，调用方回退为追加。
 */
function seqOf(segmentId: string): number | null {
  const index = segmentId.lastIndexOf('_')
  if (index === -1) {
    return null
  }
  const parsed = Number(segmentId.slice(index + 1))
  return Number.isFinite(parsed) ? parsed : null
}
