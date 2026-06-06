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
  private _spokenSegmentIds: Set<string> = new Set()
  private _speakingSegmentId: string | null = null

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
      volume: clamp(volume, MIN_VOLUME, MAX_VOLUME),
    }
    this._notifyDiagnostics()
  }

  setRate(rate: number): void {
    this._settings = {
      ...this._settings,
      rate: clamp(rate, MIN_RATE, MAX_RATE),
    }
    this._notifyDiagnostics()
  }

  enqueueFinalTranslation(segmentId: string, text: string): void {
    if (!this._settings.enabled) {
      return
    }

    this._enqueueOrUpdate(segmentId, text, false)
  }

  handleRevisedTranslation(segmentId: string, text: string): void {
    if (!this._settings.enabled) {
      return
    }

    this._enqueueOrUpdate(segmentId, text, true)
  }

  reset(): void {
    this.cancelQueue()
    this._spokenSegmentIds = new Set()
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
    this._speakingSegmentId = null
    this._notifyDiagnostics()
  }

  private _enqueueOrUpdate(segmentId: string, text: string, isRevision: boolean): void {
    const normalizedText = normalizeSpeechText(text)
    if (!normalizedText) {
      this._diagnostics = {
        ...this._diagnostics,
        skippedUtterances: this._diagnostics.skippedUtterances + 1,
      }
      this._notifyDiagnostics()
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

    const queuedItem = this._queue.find((item) => item.segmentId === segmentId)
    if (queuedItem) {
      queuedItem.text = normalizedText
      this._notifyDiagnostics()
      return
    }

    if (this._speakingSegmentId === segmentId || this._spokenSegmentIds.has(segmentId)) {
      if (isRevision) {
        this._diagnostics = {
          ...this._diagnostics,
          skippedUtterances: this._diagnostics.skippedUtterances + 1,
        }
        this._notifyDiagnostics()
      }
      return
    }

    this._queue.push({
      segmentId,
      text: normalizedText,
    })
    this._notifyDiagnostics()
    this._drainQueue()
  }

  private _drainQueue(): void {
    if (!this._settings.enabled || !this._speech || this._speakingSegmentId) {
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

    this._speakingSegmentId = item.segmentId
    this._notifyDiagnostics()

    utterance.onend = () => {
      this._spokenSegmentIds.add(item.segmentId)
      this._speakingSegmentId = null
      this._diagnostics = {
        ...this._diagnostics,
        spokenUtterances: this._diagnostics.spokenUtterances + 1,
        lastError: null,
      }
      this._notifyDiagnostics()
      this._drainQueue()
    }

    utterance.onerror = (event: SpeechSynthesisErrorEvent) => {
      this._speakingSegmentId = null
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

  private _notifyDiagnostics(): void {
    this._diagnostics = {
      ...this._diagnostics,
      isSupported: this._isSupported,
      enabled: this._settings.enabled,
      isSpeaking: this._speakingSegmentId !== null,
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


function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}
