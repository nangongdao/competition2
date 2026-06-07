/** WebSocket protocol and frontend view-model types. */

export type ServerMessage =
  | AsrPartialMessage
  | AsrFinalMessage
  | TranslationTokenMessage
  | RevisionMessage
  | SessionDiagnosticsMessage
  | StatusMessage
  | ErrorMessage

export interface AsrPartialMessage {
  type: 'asr_partial'
  text: string
}

export interface AsrFinalMessage {
  type: 'asr_final'
  segment_id: string
  text: string
  confidence: number
  latency_ms?: number
  source_language?: string
  target_language?: string
}

export interface TranslationTokenMessage {
  type: 'translation_token'
  segment_id: string
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
}

export type SubtitleMode = 'bilingual' | 'translation_only' | 'source_only'

export type SourceLanguage = 'auto' | 'en' | 'ja' | 'ko' | 'es' | 'fr' | 'de'

export type TargetLanguage = 'zh-CN'

export type UiLanguage = 'zh-CN' | 'en-US'

export type TranslationEngine = 'openai' | 'claude'

export type DesktopAsrProfile = 'light' | 'cpu' | 'gpu' | 'env'

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
  runtime: {
    asrProfile: DesktopAsrProfile
    sourceLanguage: SourceLanguage
  }
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
  runtime: {
    asrProfile: DesktopAsrProfile
    sourceLanguage: SourceLanguage
  }
}

export interface DesktopSettingsSaveResult {
  success: boolean
  reason: string
  settings?: DesktopSettingsSnapshot
}

export type AudioCaptureBackend = 'audio-worklet' | 'script-processor'

export interface TtsSettings {
  enabled: boolean
  volume: number
  rate: number
}

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
