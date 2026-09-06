/** WebSocket protocol and frontend view-model types. */

export type ServerMessage =
  | AsrPartialMessage
  | AsrFinalMessage
  | TranslationTokenMessage
  | RevisionMessage
  | SessionDiagnosticsMessage
  | StatusMessage
  | ErrorMessage
  | TtsAudioMessage

/**
 * 后端 TTS 音频元信息帧（随后的二进制帧携带 MP3 数据）。
 * 协议见 backend/core/pipeline.py `_emit_tts_audio`。
 */
export interface TtsAudioMessage {
  type: 'tts_audio'
  segment_id: string
  segment_index?: number
  format: 'mp3'
  /** 后续二进制帧的字节长度（便于前端校验/丢弃）。 */
  length: number
}

export interface AsrPartialMessage {
  type: 'asr_partial'
  text: string
}

export interface AsrFinalMessage {
  type: 'asr_final'
  segment_id: string
  /** 单调递增的片段序号，用于前端按序落位（翻译异步化后可能乱序到达）。 */
  segment_index?: number
  text: string
  confidence: number
  latency_ms?: number
  source_language?: string
  target_language?: string
  /** 说话人标识（启用说话人分离时下发，如 "speaker_1"）。 */
  speaker_id?: string
  /**
   * 阶段 8：源语言自动检测模式下，Whisper 检测到的源语言代码
   * （如 en / ja / zh-CN）；非 auto 模式或未检测时为 undefined。
   */
  detected_language?: string
}

export interface TranslationTokenMessage {
  type: 'translation_token'
  segment_id: string
  /** 单调递增的片段序号，用于前端按序落位。 */
  segment_index?: number
  token: string
  is_final: boolean
}

export type RevisionReason = 'asr_correction' | 'translation_correction'

export interface RevisionMessage {
  type: 'revision'
  segment_id: string
  new_text: string
  source_text?: string
  reason: RevisionReason
  old_text?: string
  old_source_text?: string
  correction_source?: string
  trigger?: string
  latency_ms?: number
  confidence?: number
}

/**
 * 修正时间线上的单条事件（前端由 RevisionMessage 累积而成）。
 * 用于阶段 4「修正历史可观测」：用户可回溯本次会话的所有修正记录。
 */
export interface RevisionEvent {
  id: string
  segmentId: string
  /** 片段序号（用于定位对应的字幕条目）。 */
  segmentIndex?: number
  newText: string
  sourceText?: string
  oldText?: string
  oldSourceText?: string
  reason: RevisionReason
  correctionSource?: string
  trigger?: string
  latencyMs?: number
  confidence?: number
  /** 修正发生时的本地时间戳（毫秒）。 */
  timestamp: number
}

export interface LatencySummary {
  count: number
  avg_ms: number
  max_ms: number
}

export interface SessionDiagnostics {
  session_id: string
  status: 'running' | 'closed'
  started_at: number
  duration_ms: number
  audio_chunks_received: number
  audio_bytes_received: number
  audio_chunks_dropped: number
  audio_queue_depth: number
  audio_queue_max_depth: number
  audio_queue_capacity: number
  asr_segments: number
  translation_segments: number
  revision_segments: number
  reconnect_count: number
  latency: Record<string, LatencySummary>
  api_call_counts: Record<string, number>
  revision_counts: Record<string, number>
  revision_sources: Record<string, number>
  revision_triggers: Record<string, number>
}

export interface SessionDiagnosticsMessage {
  type: 'session_diagnostics'
  diagnostics: SessionDiagnostics
}

export interface StatusMessage {
  type: 'status'
  code: string
  message: string
  session_id?: string
  /** 会话重连令牌，客户端重连时通过 ?token= 查询参数回传。 */
  reconnect_token?: string
}

export interface ErrorMessage {
  type: 'error'
  code: string
  message: string
}

export type ClientMessage = AudioChunkMessage | ControlMessage

export interface AudioChunkMessage {
  type: 'audio_chunk'
  data: ArrayBuffer
  timestamp: number
}

export interface ControlMessage {
  type: 'pause' | 'resume' | 'config' | 'manual_revise' | 'request_diagnostics'
  language?: SourceLanguage
  target_language?: TargetLanguage
  style_preset?: TranslationStyle
}

export type SubtitleMode = 'bilingual' | 'translation_only' | 'source_only'

/**
 * 翻译风格预设（阶段 3 字幕风格控制）：
 * - `concise`：简洁 —— 贴近原句长度，去冗余（默认）
 * - `faithful`：忠实 —— 完整保留信息与语气
 * - `lecture`：讲义式 —— 面向学习/复盘，适当展开关键概念
 */
export type TranslationStyle = 'concise' | 'faithful' | 'lecture'

export type SubtitlePosition = 'bottom' | 'middle' | 'top'

/**
 * 字幕样式配置（V2.3）：字体大小 / 字体颜色 / 背景透明度 / 背景色 / 字幕位置。
 * 应用于主界面字幕、悬浮字幕窗（Electron / Tauri / Web 浮窗）并持久化到本地设置。
 */
export interface SubtitleStyleConfig {
  fontSize: number          // 12-36，默认 22
  fontColor: string         // 十六进制颜色，默认 '#ffffff'
  backgroundColor: string   // 十六进制颜色，默认 '#0a0e16'
  backgroundOpacity: number // 0-1，默认 0.78
  position: SubtitlePosition
}

export type SourceLanguage = 'auto' | 'en' | 'zh-CN' | 'ja' | 'ko' | 'es' | 'fr' | 'de'

export type TargetLanguage = 'zh-CN' | 'en' | 'ja' | 'ko' | 'es' | 'fr' | 'de'

export type UiLanguage = 'zh-CN' | 'en-US'

export type TranslationEngine = 'openai' | 'claude'

export type DesktopAsrProfile = 'remote' | 'light' | 'cpu' | 'gpu' | 'env'

export interface LanguageConfig {
  sourceLanguage: SourceLanguage
  targetLanguage: TargetLanguage
}

export interface DesktopSettingsSnapshot {
  available: boolean
  configPath?: string
  uiLanguage: UiLanguage
  translation: {
    engine: TranslationEngine
    model: string
    openaiBaseUrl: string
    hasOpenaiApiKey: boolean
    hasAnthropicApiKey: boolean
  }
  asr: {
    model: string
    openaiBaseUrl: string
    hasOpenaiApiKey: boolean
  }
  runtime: {
    asrProfile: DesktopAsrProfile
    sourceLanguage: SourceLanguage
    targetLanguage: TargetLanguage
  }
  subtitleStyle: SubtitleStyleConfig
}

export interface DesktopSettingsUpdate {
  uiLanguage: UiLanguage
  translation: {
    engine: TranslationEngine
    model: string
    openaiBaseUrl: string
    openaiApiKey: string
    anthropicApiKey: string
    clearOpenaiApiKey: boolean
    clearAnthropicApiKey: boolean
  }
  asr: {
    model: string
    openaiBaseUrl: string
    openaiApiKey: string
    clearOpenaiApiKey: boolean
  }
  runtime: {
    asrProfile: DesktopAsrProfile
    sourceLanguage: SourceLanguage
    targetLanguage: TargetLanguage
  }
  subtitleStyle?: SubtitleStyleConfig
}

export interface DesktopSettingsSaveResult {
  success: boolean
  reason: string
  settings?: DesktopSettingsSnapshot
}

export type AudioCaptureBackend = 'audio-worklet' | 'script-processor'

/**
 * 音频输入源类型：
 * - `mic`：麦克风（getUserMedia，无需共享屏幕）
 * - `tab`：标签页/窗口音频（getDisplayMedia，共享屏幕时勾选分享音频）
 * - `system`：Tauri 系统音频 loopback（需 --features system-audio 构建 + loopback 驱动）
 * - `file`：本地音频文件（WAV/MP3 等，离线解码后按实时节奏送入管线）
 */
export type AudioSourceType = 'mic' | 'tab' | 'system' | 'file'

export interface TtsSettings {
  enabled: boolean
  volume: number
  rate: number
}

/**
 * 语音播放引擎选择：
 * - `auto`：自动——优先使用后端 TTS（MP3），收不到后端音频时回退本地浏览器语音
 * - `local`：本地浏览器 speechSynthesis（流式低延迟，质量取决于系统语音）
 * - `backend`：后端 TTS 合成（edge-tts / OpenAI，需后端 tts_engine 已启用）
 */
export type TtsEngine = 'auto' | 'local' | 'backend'

export interface TtsDiagnostics {
  isSupported: boolean
  enabled: boolean
  isSpeaking: boolean
  queueLength: number
  spokenUtterances: number
  skippedUtterances: number
  failedUtterances: number
  lastError: string | null
}

export interface SubtitleEntry {
  segmentId: string
  sourceText: string
  translatedText: string
  isPartial: boolean
  isRevised: boolean
  revisionReason?: RevisionReason
  revisedAt?: number
  timestamp: number
  /** 单调递增的片段序号，用于乱序结果按序落位。 */
  seq?: number
  /** 说话人标识（说话人分离开启时存在），用于字幕着色。 */
  speaker?: string
}

export type AppStatus = 'idle' | 'capturing' | 'translating' | 'error'

export interface ClientDiagnostics {
  sessionId: string
  captureBackend: AudioCaptureBackend | null
  sentAudioChunks: number
  droppedAudioChunks: number
  reconnectAttempts: number
  connectionOpens: number
  lastDisconnectAt: number | null
}
