import type { TtsDiagnostics, TtsSettings } from '../types'


const DEFAULT_TTS_SETTINGS: TtsSettings = {
  enabled: false,
  volume: 0.8,
  rate: 1,
}

const DEFAULT_TTS_DIAGNOSTICS: TtsDiagnostics = {
  isSupported: false,
  enabled: false,
  isSpeaking: false,
  queueLength: 0,
  spokenUtterances: 0,
  skippedUtterances: 0,
  failedUtterances: 0,
  lastError: null,
}

const TTS_LANGUAGE = 'zh-CN'
const MIN_VOLUME = 0
const MAX_VOLUME = 1
const MIN_RATE = 0.7
const MAX_RATE = 1.35


interface TtsCallbacks {
  onDiagnosticsChange: (diagnostics: TtsDiagnostics) => void
}


interface QueuedUtterance {
  key: string
  segmentId: string
  text: string
}


export class TtsPlayer {
  private readonly _speech: SpeechSynthesis | null
  private readonly _isSupported: boolean
  private _settings: TtsSettings = DEFAULT_TTS_SETTINGS
  private _diagnostics: TtsDiagnostics
  private _callbacks: TtsCallbacks | null = null
  private _queue: QueuedUtterance[] = []
  private _spokenKeys: Set<string> = new Set()
  private _segmentNextIndex: Map<string, number> = new Map()
  private _speakingKey: string | null = null

  constructor() {
    this._speech = getSpeechSynthesis()
    this._isSupported = this._speech !== null && canCreateUtterance()
    this._diagnostics = {
      ...DEFAULT_TTS_DIAGNOSTICS,
      isSupported: this._isSupported,
    }
  }

  get settings(): TtsSettings {
    return { ...this._settings }
  }

  get diagnostics(): TtsDiagnostics {
    return { ...this._diagnostics }
  }

  setCallbacks(callbacks: TtsCallbacks): void {
    this._callbacks = callbacks
    this._notifyDiagnostics()
  }

  setEnabled(enabled: boolean): void {
    if (enabled && !this._isSupported) {
      this._diagnostics = {
        ...this._diagnostics,
        lastError: 'Speech synthesis is not available in this browser.',
        failedUtterances: this._diagnostics.failedUtterances + 1,
      }
      this._notifyDiagnostics()
      return
    }

    this._settings = {
      ...this._settings,
      enabled,
    }

    if (!enabled) {
      this.cancelQueue()
    }

    this._notifyDiagnostics()
    this._drainQueue()
  }

  setVolume(volume: number): void {
    this._settings = {
      ...this._settings,
      volume: clamp(volume, MIN_VOLUME, MAX_VOLUME, DEFAULT_TTS_SETTINGS.volume),
    }
    this._notifyDiagnostics()
  }

  setRate(rate: number): void {
    this._settings = {
      ...this._settings,
      rate: clamp(rate, MIN_RATE, MAX_RATE, DEFAULT_TTS_SETTINGS.rate),
    }
    this._notifyDiagnostics()
  }

  enqueueFinalTranslation(segmentId: string, text: string): void {
    if (!this._settings.enabled) {
      return
    }

    const index = this._segmentNextIndex.get(segmentId) ?? 0
    this._segmentNextIndex.set(segmentId, index + 1)
    this._enqueue(segmentId, `${segmentId}:${index}`, text)
  }

  /**
   * 流式 TTS：翻译 token 到达时，按句末标点切分出的完整句子立即入队合成，
   * 不必等整个 segment 翻译完。
   *
   * @param segmentId 片段 ID。
   * @param text 一句完整的译文。
   * @param index 该 segment 内的句子序号（用于去重）。
   */
  speakStreamSentence(segmentId: string, text: string, index: number): void {
    if (!this._settings.enabled) {
      return
    }
    this._enqueue(segmentId, `${segmentId}:${index}`, text)
  }

  handleRevisedTranslation(segmentId: string, text: string): void {
    if (!this._settings.enabled) {
      return
    }

    const normalizedText = normalizeSpeechText(text)
    if (!normalizedText) {
      this._skip('blank')
      return
    }

    // 更新该 segment 队列中尚未朗读的项
    const queued = this._queue.find((item) => item.segmentId === segmentId)
    if (queued) {
      queued.text = normalizedText
      this._notifyDiagnostics()
      return
    }

    // 该 segment 已朗读过（或正在朗读）：修正太晚，跳过
    if (this._isSegmentSpokenOrSpeaking(segmentId)) {
      this._skip('late-revision')
      return
    }

    const index = this._segmentNextIndex.get(segmentId) ?? 0
    this._segmentNextIndex.set(segmentId, index + 1)
    this._enqueue(segmentId, `${segmentId}:${index}`, text)
  }

  reset(): void {
    this.cancelQueue()
    this._spokenKeys = new Set()
    this._segmentNextIndex = new Map()
    this._diagnostics = {
      ...DEFAULT_TTS_DIAGNOSTICS,
      isSupported: this._isSupported,
      enabled: this._settings.enabled,
    }
    this._notifyDiagnostics()
  }

  cancelQueue(): void {
    if (this._speech) {
      this._speech.cancel()
    }

    this._queue = []
    this._speakingKey = null
    this._notifyDiagnostics()
  }

  private _enqueue(segmentId: string, key: string, text: string): void {
    const normalizedText = normalizeSpeechText(text)
    if (!normalizedText) {
      this._skip('blank')
      return
    }

    if (!this._isSupported || !this._speech) {
      this._diagnostics = {
        ...this._diagnostics,
        failedUtterances: this._diagnostics.failedUtterances + 1,
        lastError: 'Speech synthesis is not available in this browser.',
      }
      this._notifyDiagnostics()
      return
    }

    if (this._spokenKeys.has(key) || this._speakingKey === key) {
      this._skip('duplicate')
      return
    }

    this._queue.push({
      key,
      segmentId,
      text: normalizedText,
    })
    this._notifyDiagnostics()
    this._drainQueue()
  }

  private _drainQueue(): void {
    if (!this._settings.enabled || !this._speech || this._speakingKey) {
      return
    }

    const item = this._queue.shift()
    if (!item) {
      this._notifyDiagnostics()
      return
    }

    const utterance = new SpeechSynthesisUtterance(item.text)
    utterance.lang = TTS_LANGUAGE
    utterance.volume = this._settings.volume
    utterance.rate = this._settings.rate

    const voice = pickChineseVoice(this._speech)
    if (voice) {
      utterance.voice = voice
    }

    this._speakingKey = item.key
    this._notifyDiagnostics()

    utterance.onend = () => {
      this._spokenKeys.add(item.key)
      this._speakingKey = null
      this._diagnostics = {
        ...this._diagnostics,
        spokenUtterances: this._diagnostics.spokenUtterances + 1,
        lastError: null,
      }
      this._notifyDiagnostics()
      this._drainQueue()
    }

    utterance.onerror = (event: SpeechSynthesisErrorEvent) => {
      this._speakingKey = null
      this._diagnostics = {
        ...this._diagnostics,
        failedUtterances: this._diagnostics.failedUtterances + 1,
        lastError: event.error || 'Speech synthesis failed.',
      }
      this._notifyDiagnostics()
      this._drainQueue()
    }

    this._speech.speak(utterance)
  }

  private _isSegmentSpokenOrSpeaking(segmentId: string): boolean {
    if (this._speakingKey?.startsWith(`${segmentId}:`)) {
      return true
    }
    for (const key of this._spokenKeys) {
      if (key.startsWith(`${segmentId}:`)) {
        return true
      }
    }
    return false
  }

  private _skip(reason: 'blank' | 'late-revision' | 'duplicate'): void {
    void reason
    this._diagnostics = {
      ...this._diagnostics,
      skippedUtterances: this._diagnostics.skippedUtterances + 1,
    }
    this._notifyDiagnostics()
  }

  private _notifyDiagnostics(): void {
    this._diagnostics = {
      ...this._diagnostics,
      isSupported: this._isSupported,
      enabled: this._settings.enabled,
      isSpeaking: this._speakingKey !== null,
      queueLength: this._queue.length,
    }
    this._callbacks?.onDiagnosticsChange(this.diagnostics)
  }
}


function getSpeechSynthesis(): SpeechSynthesis | null {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    return null
  }

  return window.speechSynthesis
}


function canCreateUtterance(): boolean {
  return typeof SpeechSynthesisUtterance !== 'undefined'
}


function normalizeSpeechText(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}


function pickChineseVoice(speech: SpeechSynthesis): SpeechSynthesisVoice | null {
  const voices = speech.getVoices()
  return voices.find((voice) => voice.lang.toLowerCase().startsWith('zh')) ?? null
}


function clamp(value: number, min: number, max: number, fallback: number): number {
  const numericValue = Number.isFinite(value) ? value : fallback
  return Math.min(max, Math.max(min, numericValue))
}
