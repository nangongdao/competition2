import { AudioCapture } from '../audio/AudioCapture'
import { WsClient } from '../network/WsClient'
import { SubtitleRenderer } from '../subtitle/SubtitleRenderer'
import { SubtitleStore } from '../subtitle/SubtitleStore'
import type {
  AppStatus,
  ClientDiagnostics,
  RevisionReason,
  ServerMessage,
  SessionDiagnostics,
  SubtitleEntry,
  SubtitleMode,
} from '../types'


export interface AppState {
  status: AppStatus
  connectionState: string
  subtitleMode: SubtitleMode
  translationRevisionCount: number
  asrRevisionCount: number
  lastRevisionReason: RevisionReason | null
  serverDiagnostics: SessionDiagnostics | null
  clientDiagnostics: ClientDiagnostics
  diagnosticsText: string
  subtitleHistory: SubtitleEntry[]
}


type StateListener = (state: AppState) => void


const DEFAULT_BACKEND_HOST = '127.0.0.1'
const DEFAULT_BACKEND_PORT = 8000


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


export class AppController {
  private _audioCapture: AudioCapture
  private _wsClient: WsClient
  private _subtitleStore: SubtitleStore
  private _subtitleRenderer: SubtitleRenderer | null = null
  private _listeners: Set<StateListener> = new Set()
  private _state: AppState = {
    status: 'idle',
    connectionState: 'disconnected',
    subtitleMode: 'bilingual',
    translationRevisionCount: 0,
    asrRevisionCount: 0,
    lastRevisionReason: null,
    serverDiagnostics: null,
    clientDiagnostics: EMPTY_CLIENT_DIAGNOSTICS,
    diagnosticsText: formatDiagnosticsText(EMPTY_CLIENT_DIAGNOSTICS, null),
    subtitleHistory: [],
  }

  constructor() {
    this._audioCapture = new AudioCapture()
    this._wsClient = new WsClient(WS_URL)
    this._subtitleStore = new SubtitleStore()
    this._state = {
      ...this._state,
      clientDiagnostics: this._getClientDiagnostics(),
      diagnosticsText: formatDiagnosticsText(this._getClientDiagnostics(), null),
    }

    this._audioCapture.setCallbacks({
      onStateChange: (state) => {
        this._updateClientDiagnostics()
        if (state === 'error') {
          this._updateState({ status: 'error' })
        }
      },
      onAudioChunk: (chunk: ArrayBuffer) => {
        this._wsClient.sendAudio(chunk)
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
    })
  }

  get state(): AppState {
    return { ...this._state }
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
    this._syncSubtitles()
  }

  async start(): Promise<void> {
    try {
      this._updateState({ status: 'capturing' })
      this._wsClient.connect()
      await this._audioCapture.start()
      this._updateState({ status: 'translating' })
    } catch (error) {
      console.error('[AppController] failed to start', error)
      this._updateState({ status: 'error' })
      throw error
    }
  }

  stop(): void {
    this._audioCapture.stop()
    this._wsClient.resetSession()
    this._subtitleStore.reset()
    this._subtitleRenderer?.reset()
    this._updateState({
      status: 'idle',
      translationRevisionCount: 0,
      asrRevisionCount: 0,
      lastRevisionReason: null,
      serverDiagnostics: null,
      clientDiagnostics: this._getClientDiagnostics(),
      diagnosticsText: formatDiagnosticsText(this._getClientDiagnostics(), null),
      subtitleHistory: [],
    })
  }

  requestManualRevision(): void {
    this._wsClient.sendControl({ type: 'manual_revise' })
  }

  setSubtitleMode(mode: SubtitleMode): void {
    this._subtitleStore.setMode(mode)
    this._subtitleRenderer?.setMode(mode)
    this._syncSubtitles()
    this._updateState({ subtitleMode: mode })
  }

  private _handleServerMessage(message: ServerMessage): void {
    switch (message.type) {
      case 'asr_partial':
        break

      case 'asr_final':
        this._subtitleStore.upsertSource(
          message.segment_id,
          message.text,
        )
        this._syncSubtitles()
        break

      case 'translation_token':
        if (message.is_final) {
          this._subtitleStore.finalizeSubtitle(message.segment_id)
        } else {
          this._subtitleStore.appendToken(message.segment_id, message.token)
        }
        this._syncSubtitles()
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
        this._updateState({
          translationRevisionCount:
            this._state.translationRevisionCount +
            (message.reason === 'translation_correction' ? 1 : 0),
          asrRevisionCount:
            this._state.asrRevisionCount +
            (message.reason === 'asr_correction' ? 1 : 0),
          lastRevisionReason: message.reason,
        })
        this._syncSubtitles()
        break

      case 'session_diagnostics':
        this._updateState({
          serverDiagnostics: message.diagnostics,
          diagnosticsText: formatDiagnosticsText(
            this._getClientDiagnostics(),
            message.diagnostics,
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

  private _syncSubtitles(): void {
    if (this._subtitleRenderer) {
      for (const entry of this._subtitleStore.subtitles) {
        this._subtitleRenderer.render(entry)
      }
    }
    this._updateSubtitleSnapshot()
  }

  private _updateSubtitleSnapshot(): void {
    this._updateState({
      subtitleHistory: [...this._subtitleStore.history],
    })
  }

  private _getClientDiagnostics(diagnostics = this._wsClient.diagnostics): ClientDiagnostics {
    return {
      ...diagnostics,
      captureBackend: this._audioCapture.captureBackend,
    }
  }

  private _updateClientDiagnostics(diagnostics = this._wsClient.diagnostics): void {
    const clientDiagnostics = this._getClientDiagnostics(diagnostics)
    this._updateState({
      clientDiagnostics,
      diagnosticsText: formatDiagnosticsText(clientDiagnostics, this._state.serverDiagnostics),
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
    `ASR segments: ${server.asr_segments}`,
    `Translation segments: ${server.translation_segments}`,
    `Revision segments: ${server.revision_segments}`,
    `Reconnect count: ${server.reconnect_count}`,
    '',
    'Latency',
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
  const configuredUrl = import.meta.env.VITE_WS_URL
  if (configuredUrl) {
    return configuredUrl.replace(/\/$/, '')
  }

  const hostname = window.location.hostname || DEFAULT_BACKEND_HOST
  return `ws://${hostname}:${DEFAULT_BACKEND_PORT}/api/v1/ws/translate`
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
