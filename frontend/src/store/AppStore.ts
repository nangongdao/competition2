import { AudioSourceManager } from '../audio/AudioSourceManager'
import { BackendTtsPlayer } from '../audio/BackendTtsPlayer'
import { splitSentences } from '../audio/sentence'
import { TtsPlayer } from '../audio/TtsPlayer'
import { WsClient } from '../network/WsClient'
import {
  getRuntimeWebSocketUrlFromSearch,
  resolveWebSocketBaseUrl,
} from '../network/ws-url'
import { pushRevisionEvent, revisionEventFromMessage } from '../revision/revision-history'
import { SubtitleRenderer } from '../subtitle/SubtitleRenderer'
import { SubtitleStore } from '../subtitle/SubtitleStore'
import { DEFAULT_SUBTITLE_STYLE, normalizeSubtitleStyle } from '../subtitle/subtitle-style'
import type {
  AppStatus,
  AudioSourceType,
  ClientDiagnostics,
  LanguageConfig,
  RevisionReason,
  RevisionEvent,
  RevisionMessage,
  ServerMessage,
  SessionDiagnostics,
  SourceLanguage,
  SubtitleEntry,
  SubtitleMode,
  SubtitleStyleConfig,
  TargetLanguage,
  TranslationStyle,
  TtsDiagnostics,
  TtsEngine,
  TtsSettings,
} from '../types'


export interface AppState {
  status: AppStatus
  connectionState: string
  subtitleMode: SubtitleMode
  languageConfig: LanguageConfig
  translationRevisionCount: number
  asrRevisionCount: number
  lastRevisionReason: RevisionReason | null
  /** 阶段 4：本次会话的修正历史时间线（最新在前）。 */
  revisionHistory: RevisionEvent[]
  serverDiagnostics: SessionDiagnostics | null
  clientDiagnostics: ClientDiagnostics
  /** 当前音频输入源：mic（麦克风）| tab（标签页）| system（Tauri 系统音频）| file（本地文件）。 */
  audioSource: AudioSourceType
  /** 文件输入源选择中的文件名（仅 file 源可见）。 */
  audioFileName: string | null
  /** 文件输入源是否已播放到末尾。 */
  audioFileEnded: boolean
  ttsSettings: TtsSettings
  ttsDiagnostics: TtsDiagnostics
  /** 当前语音播放引擎（auto/local/backend）。 */
  ttsEngine: TtsEngine
  /** 当前翻译风格预设（阶段 3）：concise/faithful/lecture。 */
  translationStyle: TranslationStyle
  /**
   * 阶段 8：auto 模式下 Whisper 检测到的源语言代码（如 en/ja），
   * 用于控制面板提示用户当前识别出的语言；未检测时为 null。
   */
  detectedSourceLanguage: string | null
  /** 阶段 2：术语热词注入 ASR 是否开启（默认开，降低专名误识别）。 */
  asrHotwordsEnabled: boolean
  subtitleStyle: SubtitleStyleConfig
  diagnosticsText: string
  visibleSubtitles: SubtitleEntry[]
  subtitleHistory: SubtitleEntry[]
}


type StateListener = (state: AppState) => void


const WS_URL = getWebSocketBaseUrl()


const EMPTY_CLIENT_DIAGNOSTICS: ClientDiagnostics = {
  sessionId: '',
  captureBackend: null,
  sentAudioChunks: 0,
  droppedAudioChunks: 0,
  reconnectAttempts: 0,
  connectionOpens: 0,
  lastDisconnectAt: null,
}


const EMPTY_TTS_SETTINGS: TtsSettings = {
  enabled: false,
  volume: 0.8,
  rate: 1,
}

/** 默认引擎：自动（优先后端 MP3，回退本地浏览器语音）。 */
const DEFAULT_TTS_ENGINE: TtsEngine = 'auto'


const DEFAULT_LANGUAGE_CONFIG: LanguageConfig = {
  sourceLanguage: 'en',
  targetLanguage: 'zh-CN',
}

/** 默认翻译风格：简洁（贴近原句长度，去冗余）。 */
const DEFAULT_TRANSLATION_STYLE: TranslationStyle = 'concise'


const EMPTY_TTS_DIAGNOSTICS: TtsDiagnostics = {
  isSupported: false,
  enabled: false,
  isSpeaking: false,
  queueLength: 0,
  spokenUtterances: 0,
  skippedUtterances: 0,
  failedUtterances: 0,
  lastError: null,
}


export class AppController {
  private _audioSourceManager: AudioSourceManager
  private _ttsPlayer: TtsPlayer
  private _backendTtsPlayer: BackendTtsPlayer
  private _ttsEngine: TtsEngine = DEFAULT_TTS_ENGINE
  private _ttsEnabled = false
  private _wsClient: WsClient
  private _subtitleStore: SubtitleStore
  private _subtitleRenderer: SubtitleRenderer | null = null
  private _listeners: Set<StateListener> = new Set()
  //: 流式 TTS 的逐段未完成句子缓冲（key: segmentId）
  private _ttsSentenceBuffers: Map<string, string> = new Map()
  //: 已提交给 TTS 的句子计数（key: segmentId），用于句子序号去重
  private _ttsSentenceCounters: Map<string, number> = new Map()
  private _state: AppState = {
    status: 'idle',
    connectionState: 'disconnected',
    subtitleMode: 'bilingual',
    languageConfig: DEFAULT_LANGUAGE_CONFIG,
    translationRevisionCount: 0,
    asrRevisionCount: 0,
    lastRevisionReason: null,
    revisionHistory: [],
    serverDiagnostics: null,
    clientDiagnostics: EMPTY_CLIENT_DIAGNOSTICS,
    audioSource: 'mic',
    audioFileName: null,
    audioFileEnded: false,
    ttsSettings: EMPTY_TTS_SETTINGS,
    ttsDiagnostics: EMPTY_TTS_DIAGNOSTICS,
    ttsEngine: DEFAULT_TTS_ENGINE,
    translationStyle: DEFAULT_TRANSLATION_STYLE,
    detectedSourceLanguage: null,
    asrHotwordsEnabled: true,
    subtitleStyle: { ...DEFAULT_SUBTITLE_STYLE },
    diagnosticsText: formatDiagnosticsText(EMPTY_CLIENT_DIAGNOSTICS, null, EMPTY_TTS_DIAGNOSTICS),
    visibleSubtitles: [],
    subtitleHistory: [],
  }

  constructor() {
    this._audioSourceManager = new AudioSourceManager()
    this._ttsPlayer = new TtsPlayer()
    this._backendTtsPlayer = new BackendTtsPlayer()
    this._wsClient = new WsClient(WS_URL)
    this._subtitleStore = new SubtitleStore()
    // 第二梯队-方向 3：单一数据流 —— 订阅 Store，任何字幕变更自动同步到渲染器与 React 快照。
    this._subtitleStore.subscribe(() => this._syncSubtitles())
    this._state = {
      ...this._state,
      clientDiagnostics: this._getClientDiagnostics(),
      ttsSettings: this._ttsPlayer.settings,
      ttsDiagnostics: this._ttsPlayer.diagnostics,
      diagnosticsText: formatDiagnosticsText(
        this._getClientDiagnostics(),
        null,
        this._ttsPlayer.diagnostics,
      ),
    }

    this._audioSourceManager.setCallbacks({
      onAudioChunk: (chunk: ArrayBuffer) => {
        this._wsClient.sendAudio(chunk)
      },
      onStateChange: () => {
        this._updateClientDiagnostics()
      },
      onError: (_source, _message) => {
        this._updateState({ status: 'error' })
      },
      onEnded: (source) => {
        if (source === 'file') {
          this._updateState({ audioFileEnded: true })
        }
      },
    })

    this._wsClient.setCallbacks({
      onStateChange: (state) => {
        this._updateState({ connectionState: state })
      },
      onMessage: (message: ServerMessage) => {
        this._handleServerMessage(message)
      },
      onError: (error) => {
        console.error('[AppController] websocket error', error)
      },
      onDiagnosticsChange: (diagnostics) => {
        this._updateClientDiagnostics(diagnostics)
      },
      onMessageBytes: (payload) => {
        this._backendTtsPlayer.handleTtsAudioBytes(payload)
      },
    })

    this._ttsPlayer.setCallbacks({
      onDiagnosticsChange: (diagnostics) => {
        this._updateState({
          ttsSettings: this._ttsPlayer.settings,
          ttsDiagnostics: diagnostics,
          diagnosticsText: formatDiagnosticsText(
            this._state.clientDiagnostics,
            this._state.serverDiagnostics,
            diagnostics,
          ),
        })
      },
    })

    this._backendTtsPlayer.setCallbacks({
      onDiagnosticsChange: (diagnostics) => {
        this._updateState({
          ttsSettings: this._backendTtsPlayer.settings,
          ttsDiagnostics: diagnostics,
          diagnosticsText: formatDiagnosticsText(
            this._state.clientDiagnostics,
            this._state.serverDiagnostics,
            diagnostics,
          ),
        })
      },
    })
  }

  get state(): AppState {
    return { ...this._state }
  }

  /** 当前会话 ID（WebSocket 连接路径中使用的会话 ID，供摘要端点使用）。 */
  get sessionId(): string {
    return this._wsClient.sessionId
  }

  get subtitleStore(): SubtitleStore {
    return this._subtitleStore
  }

  subscribe(listener: StateListener): () => void {
    this._listeners.add(listener)
    return () => this._listeners.delete(listener)
  }

  setSubtitleRenderer(renderer: SubtitleRenderer): void {
    this._subtitleRenderer = renderer
    this._subtitleRenderer.setMode(this._state.subtitleMode)
    this._subtitleRenderer.setStyle(this._state.subtitleStyle)
    this._syncSubtitles()
  }

  setSubtitleStyle(style: SubtitleStyleConfig): void {
    const subtitleStyle = normalizeSubtitleStyle(style)
    this._subtitleRenderer?.setStyle(subtitleStyle)
    this._updateState({ subtitleStyle })
    this._updateSubtitleSnapshot()
  }

  async start(): Promise<void> {
    try {
      this._updateState({ status: 'capturing' })
      this._wsClient.setLanguageConfig(this._state.languageConfig)
      this._wsClient.connect()
      // file 源：直接重播已加载样本（若有）；未加载过则交由管理器报错。
      const ok = await this._audioSourceManager.startSource(
        this._state.audioSource,
        undefined,
      )
      if (!ok) {
        this._updateState({ status: 'error' })
        return
      }
      this._updateState({ status: 'translating' })
    } catch (error) {
      console.error('[AppController] failed to start', error)
      this._updateState({ status: 'error' })
      throw error
    }
  }

  /**
   * 切换音频输入源。
   * - `mic`：浏览器麦克风采集（getUserMedia）
   * - `tab`：浏览器标签页/窗口音频（getDisplayMedia）
   * - `system`：Tauri 系统音频 loopback（需 `--features system-audio` 构建 + loopback 驱动）
   * - `file`：本地音频文件（需传入 File）
   */
  async setAudioSource(source: AudioSourceType, file?: File): Promise<boolean> {
    if (source === this._state.audioSource && !(source === 'file' && file)) {
      return true
    }

    const wasActive = this._state.status === 'capturing' || this._state.status === 'translating'

    // 先停止当前源（切换源时完全释放已加载文件）。
    await this._audioSourceManager.stopAll(false)

    this._updateState({
      audioSource: source,
      audioFileName: source === 'file' ? (file?.name ?? null) : null,
      audioFileEnded: false,
    })

    if (!wasActive) {
      return true
    }

    // 重启新源。
    try {
      const ok = await this._audioSourceManager.startSource(source, file)
      if (!ok) {
        this._updateState({ status: 'error', audioSource: 'mic' })
        return false
      }
      return true
    } catch (error) {
      console.error('[AppController] failed to switch audio source', error)
      this._updateState({ status: 'error', audioSource: 'mic' })
      return false
    }
  }

  /**
   * 第二梯队-方向 5：把文件音频源跳转到指定采样位置（回看跳转）。
   *
   * 仅当当前输入源是 `file` 且已加载音频时有效；其他输入源返回 false。
   */
  seekFileToSample(sampleOffset: number): boolean {
    if (this._state.audioSource !== 'file') {
      return false
    }
    return this._audioSourceManager.fileSource.seekToSample(sampleOffset)
  }

  /** 文件音频源总采样数（用于时间轴映射），非 file 源时为 0。 */
  get fileSampleCount(): number {
    return this._audioSourceManager.fileSource.sampleCount
  }

  stop(): void {
    void this._audioSourceManager.stopAll(true)
    this._wsClient.resetSession()
    this._ttsPlayer.reset()
    this._backendTtsPlayer.reset()
    this._subtitleStore.reset()
    this._subtitleRenderer?.reset()
    this._updateState({
      status: 'idle',
      translationRevisionCount: 0,
      asrRevisionCount: 0,
      lastRevisionReason: null,
      revisionHistory: [],
      serverDiagnostics: null,
      clientDiagnostics: this._getClientDiagnostics(),
      ttsSettings: this._ttsPlayer.settings,
      ttsDiagnostics: this._ttsPlayer.diagnostics,
      diagnosticsText: formatDiagnosticsText(
        this._getClientDiagnostics(),
        null,
        this._ttsPlayer.diagnostics,
      ),
      visibleSubtitles: [],
      subtitleHistory: [],
      audioFileName: null,
      audioFileEnded: false,
    })
  }

  requestManualRevision(): void {
    this._wsClient.sendControl({ type: 'manual_revise' })
  }

  async uploadGlossary(file: File): Promise<boolean> {
    const { parseGlossaryFile } = await import('../glossary-import')
    let entries: Array<{ source: string; target: string; keep_original?: boolean }>
    try {
      const text = await file.text()
      entries = parseGlossaryFile(file.name, text)
    } catch {
      return false
    }

    if (entries.length === 0) {
      return false
    }
    this._wsClient.sendControl({ type: 'set_glossary', entries })
    return true
  }

  setSubtitleMode(mode: SubtitleMode): void {
    this._subtitleStore.setMode(mode)
    this._subtitleRenderer?.setMode(mode)
    this._syncSubtitles()
    this._updateState({ subtitleMode: mode })
  }

  setSourceLanguage(sourceLanguage: SourceLanguage): void {
    const languageConfig = {
      ...this._state.languageConfig,
      sourceLanguage,
    }
    this._wsClient.setLanguageConfig(languageConfig)
    this._updateState({ languageConfig })
  }

  setTargetLanguage(targetLanguage: TargetLanguage): void {
    const languageConfig = {
      ...this._state.languageConfig,
      targetLanguage,
    }
    this._wsClient.setLanguageConfig(languageConfig)
    this._updateState({ languageConfig })
  }

  /** 切换翻译风格预设（阶段 3），立即下发到后端并更新本地状态。 */
  setTranslationStyle(style: TranslationStyle): void {
    this._wsClient.setStylePreset(style)
    this._updateState({ translationStyle: style })
  }

  /** 切换 ASR 热词注入（阶段 2），立即下发到后端并更新本地状态。 */
  setAsrHotwordsEnabled(enabled: boolean): void {
    this._wsClient.setAsrHotwordsEnabled(enabled)
    this._updateState({ asrHotwordsEnabled: enabled })
  }

  setTtsEnabled(enabled: boolean): void {
    this._ttsEnabled = enabled
    this._syncTtsPlayers()
  }

  setTtsEngine(engine: TtsEngine): void {
    this._ttsEngine = engine
    this._syncTtsPlayers()
  }

  setTtsVolume(volume: number): void {
    this._ttsPlayer.setVolume(volume)
    this._backendTtsPlayer.setVolume(volume)
    this._updateState({
      ttsSettings: this._ttsPlayer.settings,
      ttsDiagnostics: this._ttsPlayer.diagnostics,
      diagnosticsText: formatDiagnosticsText(
        this._state.clientDiagnostics,
        this._state.serverDiagnostics,
        this._ttsPlayer.diagnostics,
      ),
    })
  }

  setTtsRate(rate: number): void {
    this._ttsPlayer.setRate(rate)
    this._backendTtsPlayer.setRate(rate)
    this._updateState({
      ttsSettings: this._ttsPlayer.settings,
      ttsDiagnostics: this._ttsPlayer.diagnostics,
      diagnosticsText: formatDiagnosticsText(
        this._state.clientDiagnostics,
        this._state.serverDiagnostics,
        this._ttsPlayer.diagnostics,
      ),
    })
  }

  /**
   * 同步两个播放器的启用状态，保证任一时刻只有一个引擎在播：
   * - `local`：仅本地 speechSynthesis
   * - `backend`：仅服务端 MP3
   * - `auto`：默认本地（流式低延迟），收到服务端音频后切到服务端（见 `tts_audio` 处理）
   */
  private _syncTtsPlayers(): void {
    const enabled = this._ttsEnabled
    const useLocal = enabled && (this._ttsEngine === 'local' || this._ttsEngine === 'auto')
    const useBackend = enabled && (this._ttsEngine === 'backend' || this._ttsEngine === 'auto')

    // auto 模式：本地为主，服务端待命（收到音频帧时才激活）。
    if (this._ttsEngine === 'auto') {
      this._ttsPlayer.setEnabled(useLocal)
      this._backendTtsPlayer.setEnabled(false)
    } else {
      this._ttsPlayer.setEnabled(useLocal)
      this._backendTtsPlayer.setEnabled(useBackend)
    }

    this._updateState({
      ttsSettings: this._ttsPlayer.settings,
      ttsDiagnostics: this._ttsPlayer.diagnostics,
      diagnosticsText: formatDiagnosticsText(
        this._state.clientDiagnostics,
        this._state.serverDiagnostics,
        this._ttsPlayer.diagnostics,
      ),
    })
  }

  private _handleServerMessage(message: ServerMessage): void {
    switch (message.type) {
      case 'tts_audio':
        // 后端音频到达：auto 模式切到后端播放，停止本地流式朗读避免双重播放。
        if (this._ttsEngine === 'auto' && this._ttsEnabled && message.length > 0) {
          this._ttsPlayer.cancelQueue()
          this._ttsPlayer.setEnabled(false)
          this._backendTtsPlayer.setEnabled(true)
        }
        this._backendTtsPlayer.handleTtsAudioMeta(message.segment_id, message.length)
        break

      case 'asr_partial':
        break

      case 'asr_final':
        this._subtitleStore.upsertSource(
          message.segment_id,
          message.text,
          undefined,
          message.segment_index,
          message.speaker_id,
        )
        // 阶段 8：auto 模式下 Whisper 检测到源语言后，控制面板提示用户
        if (message.detected_language && message.detected_language !== this._state.detectedSourceLanguage) {
          this._updateState({ detectedSourceLanguage: message.detected_language })
        }
        break

      case 'translation_token':
        if (message.is_final) {
          this._subtitleStore.finalizeSubtitle(message.segment_id)
          this._flushStreamingTts(message.segment_id)
        } else {
          this._subtitleStore.appendToken(message.segment_id, message.token, message.segment_index)
          this._handleStreamingTts(message.segment_id, message.token)
        }
        break

      case 'revision':
        if (message.reason === 'asr_correction' && message.source_text) {
          this._subtitleStore.reviseSource(
            message.segment_id,
            message.source_text,
            message.reason,
          )
        }
        this._subtitleStore.reviseSubtitle(message.segment_id, message.new_text, message.reason)
        this._subtitleRenderer?.revise(message.segment_id, message.new_text)
        this._ttsPlayer.handleRevisedTranslation(message.segment_id, message.new_text)
        this._backendTtsPlayer.handleRevisedTranslation(message.segment_id, message.new_text)
        this._recordRevisionEvent(message)
        this._updateState({
          translationRevisionCount:
            this._state.translationRevisionCount +
            (message.reason === 'translation_correction' ? 1 : 0),
          asrRevisionCount:
            this._state.asrRevisionCount +
            (message.reason === 'asr_correction' ? 1 : 0),
          lastRevisionReason: message.reason,
        })
        break

      case 'session_diagnostics':
        this._updateState({
          serverDiagnostics: message.diagnostics,
          diagnosticsText: formatDiagnosticsText(
            this._getClientDiagnostics(),
            message.diagnostics,
            this._state.ttsDiagnostics,
          ),
        })
        break

      case 'status':
        console.warn('[AppController] status', message.code, message.message)
        break

      case 'error':
        console.error('[AppController] server error', message.code, message.message)
        this._updateState({ status: 'error' })
        break
    }
  }

  private _handleStreamingTts(segmentId: string, token: string): void {
    if (!token) {
      return
    }

    const buffer = (this._ttsSentenceBuffers.get(segmentId) ?? '') + token
    const sentences = splitSentences(buffer)
    if (sentences.length <= 1) {
      this._ttsSentenceBuffers.set(segmentId, buffer)
      return
    }

    // 前面的都是完整句子，立即送去合成，不等整个 segment 翻译完
    const counter = this._ttsSentenceCounters.get(segmentId) ?? 0
    for (let index = 0; index < sentences.length - 1; index += 1) {
      this._ttsPlayer.speakStreamSentence(segmentId, sentences[index], counter + index)
    }
    this._ttsSentenceCounters.set(segmentId, counter + sentences.length - 1)
    this._ttsSentenceBuffers.set(segmentId, sentences[sentences.length - 1])
  }

  private _flushStreamingTts(segmentId: string): void {
    const remaining = this._ttsSentenceBuffers.get(segmentId)
    if (remaining && remaining.trim()) {
      const counter = this._ttsSentenceCounters.get(segmentId) ?? 0
      this._ttsPlayer.speakStreamSentence(segmentId, remaining, counter)
      this._ttsSentenceCounters.set(segmentId, counter + 1)
    }
    this._ttsSentenceBuffers.delete(segmentId)
    this._ttsSentenceCounters.delete(segmentId)
  }

  private _syncSubtitles(): void {
    if (this._subtitleRenderer) {
      // 单一数据流：由渲染器从 Store 做 DOM 对账（仅更新变化条目）。
      this._subtitleRenderer.syncFromStore(this._subtitleStore)
    }
    this._updateSubtitleSnapshot()
  }

  /**
   * 阶段 4：把一条修正消息累积进修正历史时间线（最新在前，上限 200 条）。
   */
  private _recordRevisionEvent(message: RevisionMessage): void {
    const event = revisionEventFromMessage(message)
    const revisionHistory = pushRevisionEvent(this._state.revisionHistory, event)
    this._updateState({ revisionHistory })
  }

  private _updateSubtitleSnapshot(): void {
    this._updateState({
      visibleSubtitles: [...this._subtitleStore.subtitles],
      subtitleHistory: [...this._subtitleStore.history],
    })
  }

  private _getClientDiagnostics(diagnostics = this._wsClient.diagnostics): ClientDiagnostics {
    return {
      ...diagnostics,
      captureBackend: this._audioSourceManager.audioCapture.captureBackend,
    }
  }

  private _updateClientDiagnostics(diagnostics = this._wsClient.diagnostics): void {
    const clientDiagnostics = this._getClientDiagnostics(diagnostics)
    this._updateState({
      clientDiagnostics,
      diagnosticsText: formatDiagnosticsText(
        clientDiagnostics,
        this._state.serverDiagnostics,
        this._state.ttsDiagnostics,
      ),
    })
  }

  private _updateState(partial: Partial<AppState>): void {
    this._state = { ...this._state, ...partial }
    this._listeners.forEach((listener) => listener(this._state))
  }
}


function formatDiagnosticsText(
  client: ClientDiagnostics,
  server: SessionDiagnostics | null,
  tts: TtsDiagnostics,
): string {
  const lines = [
    'AI Interpreter Session Diagnostics',
    '',
    `Session: ${server?.session_id || client.sessionId || '-'}`,
    `Status: ${server?.status ?? '-'}`,
    `Duration: ${server ? formatDuration(server.duration_ms) : '-'}`,
    '',
    'Client',
    `Capture backend: ${formatCaptureBackend(client.captureBackend)}`,
    `Sent audio chunks: ${client.sentAudioChunks}`,
    `Dropped audio chunks: ${client.droppedAudioChunks}`,
    `Reconnect attempts: ${client.reconnectAttempts}`,
    `Connection opens: ${client.connectionOpens}`,
    `Last disconnect: ${client.lastDisconnectAt ? new Date(client.lastDisconnectAt).toLocaleString() : '-'}`,
    '',
    'Voice',
    `Supported: ${tts.isSupported ? 'yes' : 'no'}`,
    `Enabled: ${tts.enabled ? 'yes' : 'no'}`,
    `Speaking: ${tts.isSpeaking ? 'yes' : 'no'}`,
    `Queue length: ${tts.queueLength}`,
    `Spoken utterances: ${tts.spokenUtterances}`,
    `Skipped utterances: ${tts.skippedUtterances}`,
    `Failed utterances: ${tts.failedUtterances}`,
    `Last voice error: ${tts.lastError ?? '-'}`,
  ]

  if (!server) {
    return lines.join('\n')
  }

  lines.push(
    '',
    'Backend',
    `Received audio chunks: ${server.audio_chunks_received}`,
    `Dropped audio chunks: ${server.audio_chunks_dropped}`,
    `Received audio bytes: ${server.audio_bytes_received}`,
    `Audio queue depth: ${server.audio_queue_depth}/${server.audio_queue_capacity}`,
    `Audio queue max depth: ${server.audio_queue_max_depth}`,
    `ASR segments: ${server.asr_segments}`,
    `Translation segments: ${server.translation_segments}`,
    `Revision segments: ${server.revision_segments}`,
    `Reconnect count: ${server.reconnect_count}`,
    '',
    'Latency',
    `Audio queue wait: ${formatLatency(server.latency.audio_queue_wait_ms)}`,
    `Capture to ASR: ${formatLatency(server.latency.capture_to_asr_ms)}`,
    `ASR to first token: ${formatLatency(server.latency.asr_to_first_token_ms)}`,
    `ASR to translation final: ${formatLatency(server.latency.asr_to_translation_final_ms)}`,
    `Revision final: ${formatLatency(server.latency.revision_final_ms)}`,
    '',
    'Counters',
    `API calls: ${formatCounterMap(server.api_call_counts)}`,
    `Revision reasons: ${formatCounterMap(server.revision_counts)}`,
    `Revision sources: ${formatCounterMap(server.revision_sources)}`,
    `Revision triggers: ${formatCounterMap(server.revision_triggers)}`,
  )

  return lines.join('\n')
}


function getWebSocketBaseUrl(): string {
  const hasWindow = typeof window !== 'undefined'
  return resolveWebSocketBaseUrl({
    runtimeUrl: hasWindow ? getRuntimeWebSocketUrlFromSearch(window.location.search) : null,
    configuredUrl: import.meta.env.VITE_WS_URL,
    hostname: hasWindow ? window.location.hostname : null,
  })
}


function formatDuration(durationMs: number): string {
  if (durationMs < 1000) {
    return `${durationMs}ms`
  }
  return `${(durationMs / 1000).toFixed(1)}s`
}


function formatCaptureBackend(backend: ClientDiagnostics['captureBackend']): string {
  switch (backend) {
    case 'audio-worklet':
      return 'AudioWorklet'
    case 'script-processor':
      return 'ScriptProcessor fallback'
    default:
      return '-'
  }
}


function formatLatency(summary: { count: number; avg_ms: number; max_ms: number } | undefined): string {
  if (!summary || summary.count === 0) {
    return '-'
  }
  return `${summary.avg_ms}ms avg / ${summary.max_ms}ms max (${summary.count})`
}


function formatCounterMap(values: Record<string, number>): string {
  const entries = Object.entries(values)
    .filter(([, value]) => value > 0)
    .map(([key, value]) => `${key}:${value}`)

  return entries.length > 0 ? entries.join(', ') : '-'
}
