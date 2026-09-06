/**
 * Backend TTS audio playback.
 *
 * The backend synthesizes translated text into MP3 audio and pushes it over
 * the WebSocket as a `tts_audio` metadata frame followed by one binary frame.
 * This player decodes the MP3 and plays it through a plain `<audio>` element,
 * so the app no longer depends on the browser's local `speechSynthesis` for
 * voice output.
 *
 * Design notes:
 * - Playback is ordered: decoded MP3 payloads are queued and played strictly
 *   in arrival order to preserve subtitle-voice alignment.
 * - A `tts_audio` metadata frame with `length === 0` (or a missing binary
 *   payload) is treated as a server-side synthesis failure and skipped
 *   silently, matching the backend's graceful-degradation contract.
 * - The same settings/volume/rate contract is shared with the local
 *   `speechSynthesis` player so the control panel stays uniform.
 */

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

const MIN_VOLUME = 0
const MAX_VOLUME = 1
const MIN_RATE = 0.7
const MAX_RATE = 1.35


interface TtsCallbacks {
  onDiagnosticsChange: (diagnostics: TtsDiagnostics) => void
}


interface QueuedItem {
  key: string
  segmentId: string
  url: string
}


export class BackendTtsPlayer {
  private _audio: HTMLAudioElement | null = null
  private _settings: TtsSettings = DEFAULT_TTS_SETTINGS
  private _diagnostics: TtsDiagnostics = DEFAULT_TTS_DIAGNOSTICS
  private _callbacks: TtsCallbacks | null = null
  /** 等待二进制帧的元信息（服务端先发元信息帧，后发音频帧）。 */
  private _pendingMeta: { key: string; segmentId: string; length: number } | null = null
  private _queue: QueuedItem[] = []
  private _isPlaying = false
  private _currentUrl: string | null = null
  private _playingKey: string | null = null
  private _spokenKeys: Set<string> = new Set()
  private _segmentCounters: Map<string, number> = new Map()

  constructor() {
    this._diagnostics = {
      ...DEFAULT_TTS_DIAGNOSTICS,
      isSupported: typeof window !== 'undefined' && ('Audio' in window || 'HTMLAudioElement' in window),
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
    this._settings = {
      ...this._settings,
      enabled,
    }

    if (!enabled) {
      this.cancelQueue()
    }

    this._notifyDiagnostics()
  }

  setVolume(volume: number): void {
    this._settings = {
      ...this._settings,
      volume: clamp(volume, MIN_VOLUME, MAX_VOLUME, DEFAULT_TTS_SETTINGS.volume),
    }
    if (this._audio) {
      this._audio.volume = this._settings.volume
    }
    this._notifyDiagnostics()
  }

  setRate(rate: number): void {
    this._settings = {
      ...this._settings,
      rate: clamp(rate, MIN_RATE, MAX_RATE, DEFAULT_TTS_SETTINGS.rate),
    }
    if (this._audio) {
      this._audio.playbackRate = this._settings.rate
    }
    this._notifyDiagnostics()
  }

  /**
   * 收到 `tts_audio` 元信息帧：记录该片段接下来会收到一段 MP3 二进制帧。
   * 服务端合成失败时下发 length=0 的空元信息帧，直接跳过。
   */
  handleTtsAudioMeta(segmentId: string, length: number): void {
    if (!this._settings.enabled) {
      // 未启用时仍记录元信息，但二进制帧不会入队。
      return
    }

    if (length <= 0) {
      this._skip('empty-audio')
      return
    }

    const index = this._segmentCounters.get(segmentId) ?? 0
    this._segmentCounters.set(segmentId, index + 1)
    this._pendingMeta = { key: `${segmentId}:${index}`, segmentId, length }
  }

  /**
   * 收到二进制帧：关联到最近的元信息帧并入队播放。
   */
  handleTtsAudioBytes(payload: ArrayBuffer): void {
    if (!this._settings.enabled) {
      return
    }

    const meta = this._pendingMeta
    if (!meta) {
      // 无元信息的二进制帧（异常顺序）直接丢弃。
      return
    }
    this._pendingMeta = null

    if (payload.byteLength <= 0) {
      this._skip('empty-audio')
      return
    }

    if (this._spokenKeys.has(meta.key) || this._playingKey === meta.key) {
      this._skip('duplicate')
      return
    }

    const url = URL.createObjectURL(new Blob([payload.slice(0)], { type: 'audio/mpeg' }))
    this._queue.push({ key: meta.key, segmentId: meta.segmentId, url })
    this._notifyDiagnostics()
    void this._playNext()
  }

  /**
   * 修正场景播报策略（阶段 6）：译文被修正时替换队列中尚未朗读的项。
   *
   * - 队列中该片段尚未播放的项：直接替换为修正后文本对应的音频（若已入队），
   *   避免朗读旧译文；
   * - 该片段正在播放或已播放完毕：修正太晚，跳过（不打断当前播放，防止语音倒退）。
   */
  handleRevisedTranslation(segmentId: string, _newText: string): void {
    if (!this._settings.enabled) {
      return
    }

    // 后端 TTS 播放的是整段 MP3（元信息帧 key 为 segmentId:index）。
    // 修正后服务端会重新合成并下发新的 tts_audio 帧（新的 index）。
    // 这里把队列中该片段未播放的旧项移除，避免旧音频与新音频重复播放。
    const before = this._queue.length
    const removedItems = this._queue.filter((item) => item.segmentId === segmentId)
    this._queue = this._queue.filter((item) => item.segmentId !== segmentId)
    const removed = before - this._queue.length

    if (removed > 0) {
      // 回收被移除项的对象 URL，避免内存泄漏
      for (const item of removedItems) {
        if (item.url) {
          URL.revokeObjectURL(item.url)
        }
      }
      this._notifyDiagnostics()
      return
    }

    // 队列中没有该片段的待播项：说明已播放或正在播放，修正太晚跳过。
    this._skip('late-revision')
  }

  reset(): void {
    this.cancelQueue()
    this._pendingMeta = null
    this._spokenKeys = new Set()
    this._segmentCounters = new Map()
    this._diagnostics = {
      ...DEFAULT_TTS_DIAGNOSTICS,
      isSupported: this._diagnostics.isSupported,
      enabled: this._settings.enabled,
    }
    this._notifyDiagnostics()
  }

  cancelQueue(): void {
    this._isPlaying = false
    if (this._audio) {
      this._audio.pause()
      this._audio.src = ''
    }
    if (this._currentUrl) {
      URL.revokeObjectURL(this._currentUrl)
      this._currentUrl = null
    }
    this._queue = []
    this._playingKey = null
    this._notifyDiagnostics()
  }

  private async _playNext(): Promise<void> {
    if (!this._settings.enabled || this._isPlaying) {
      return
    }

    const item = this._queue.shift()
    if (!item) {
      this._notifyDiagnostics()
      return
    }

    const audio = this._ensureAudioElement()
    this._isPlaying = true
    this._playingKey = item.key
    this._currentUrl = item.url
    audio.src = item.url
    audio.volume = this._settings.volume
    audio.playbackRate = this._settings.rate

    const cleanup = (): void => {
      this._isPlaying = false
      this._playingKey = null
      if (this._currentUrl) {
        URL.revokeObjectURL(this._currentUrl)
        this._currentUrl = null
      }
      audio.onended = null
      audio.onerror = null
    }

    audio.onended = () => {
      this._spokenKeys.add(item.key)
      this._diagnostics = {
        ...this._diagnostics,
        spokenUtterances: this._diagnostics.spokenUtterances + 1,
        lastError: null,
      }
      cleanup()
      this._notifyDiagnostics()
      void this._playNext()
    }

    audio.onerror = () => {
      this._diagnostics = {
        ...this._diagnostics,
        failedUtterances: this._diagnostics.failedUtterances + 1,
        lastError: 'Audio playback failed.',
      }
      cleanup()
      this._notifyDiagnostics()
      void this._playNext()
    }

    this._notifyDiagnostics()
    try {
      await audio.play()
    } catch (err) {
      // Autoplay policy may reject playback until the user interacts with the
      // page; keep the item queued and surface the failure in diagnostics
      // instead of silently dropping it.
      console.warn('[BackendTts] playback blocked:', err)
      this._isPlaying = false
      this._playingKey = null
      if (this._currentUrl) {
        URL.revokeObjectURL(this._currentUrl)
        this._currentUrl = null
      }
      this._queue.unshift(item)
      this._diagnostics = {
        ...this._diagnostics,
        failedUtterances: this._diagnostics.failedUtterances + 1,
        lastError: 'Playback blocked by autoplay policy.',
      }
      this._notifyDiagnostics()
    }
  }

  private _ensureAudioElement(): HTMLAudioElement {
    if (!this._audio) {
      this._audio = new Audio()
      this._audio.preload = 'auto'
    }
    return this._audio
  }

  private _skip(reason: 'duplicate' | 'empty-audio' | 'late-revision'): void {
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
      isSupported: this._diagnostics.isSupported,
      enabled: this._settings.enabled,
      isSpeaking: this._isPlaying,
      queueLength: this._queue.length,
    }
    this._callbacks?.onDiagnosticsChange(this.diagnostics)
  }
}


function clamp(value: number, min: number, max: number, fallback: number): number {
  const numericValue = Number.isFinite(value) ? value : fallback
  return Math.min(max, Math.max(min, numericValue))
}
