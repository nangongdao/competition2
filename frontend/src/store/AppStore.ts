import { AudioCapture } from '../audio/AudioCapture'
import { WsClient } from '../network/WsClient'
import { SubtitleRenderer } from '../subtitle/SubtitleRenderer'
import { SubtitleStore } from '../subtitle/SubtitleStore'
import type {
  AppStatus,
  RevisionReason,
  ServerMessage,
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
  subtitleHistory: SubtitleEntry[]
  transcriptText: string
}


type StateListener = (state: AppState) => void


const WS_URL = `ws://${window.location.hostname}:8000/api/v1/ws/translate`


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
    subtitleHistory: [],
    transcriptText: '',
  }

  constructor() {
    this._audioCapture = new AudioCapture()
    this._wsClient = new WsClient(WS_URL)
    this._subtitleStore = new SubtitleStore()

    this._audioCapture.setCallbacks({
      onStateChange: (state) => {
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
    this._wsClient.disconnect()
    this._subtitleStore.reset()
    this._subtitleRenderer?.reset()
    this._updateState({
      status: 'idle',
      translationRevisionCount: 0,
      asrRevisionCount: 0,
      lastRevisionReason: null,
      subtitleHistory: [],
      transcriptText: '',
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
      transcriptText: this._subtitleStore.exportTranscript(),
    })
  }

  private _updateState(partial: Partial<AppState>): void {
    this._state = { ...this._state, ...partial }
    this._listeners.forEach((listener) => listener(this._state))
  }
}
