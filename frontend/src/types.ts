/** WebSocket protocol and frontend view-model types. */

export type ServerMessage =
  | AsrPartialMessage
  | AsrFinalMessage
  | TranslationTokenMessage
  | RevisionMessage
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
}

export interface StatusMessage {
  type: 'status'
  code: string
  message: string
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
  type: 'pause' | 'resume' | 'config' | 'manual_revise'
  language?: string
  target_language?: string
}

export type SubtitleMode = 'bilingual' | 'translation_only' | 'source_only'

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
