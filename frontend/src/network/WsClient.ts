import type { ClientDiagnostics, ServerMessage } from '../types'


export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'


export interface WsClientCallbacks {
  onStateChange: (state: ConnectionState) => void
  onMessage: (message: ServerMessage) => void
  onError: (error: Event) => void
  onDiagnosticsChange?: (diagnostics: ClientDiagnostics) => void
}


const RECONNECT_CONFIG = {
  maxRetries: 10,
  baseDelayMs: 1000,
  maxDelayMs: 30000,
}


export class WsClient {
  private _ws: WebSocket | null = null
  private _state: ConnectionState = 'disconnected'
  private _callbacks: WsClientCallbacks | null = null
  private _baseUrl: string
  private _url: string
  private _retryCount = 0
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _intentionalClose = false
  private _diagnostics: ClientDiagnostics

  constructor(baseUrl: string) {
    this._baseUrl = baseUrl
    const sessionId = createSessionId()
    this._url = appendSessionId(baseUrl, sessionId)
    this._diagnostics = {
      sessionId,
      captureBackend: null,
      sentAudioChunks: 0,
      droppedAudioChunks: 0,
      reconnectAttempts: 0,
      connectionOpens: 0,
      lastDisconnectAt: null,
    }
  }

  get state(): ConnectionState {
    return this._state
  }

  get diagnostics(): ClientDiagnostics {
    return { ...this._diagnostics }
  }

  setCallbacks(callbacks: WsClientCallbacks): void {
    this._callbacks = callbacks
    this._notifyDiagnostics()
  }

  connect(): void {
    if (
      this._ws &&
      (this._ws.readyState === WebSocket.OPEN || this._ws.readyState === WebSocket.CONNECTING)
    ) {
      return
    }

    this._intentionalClose = false
    this._setState('connecting')

    try {
      this._ws = new WebSocket(this._url)
      this._ws.binaryType = 'arraybuffer'

      this._ws.onopen = () => {
        this._retryCount = 0
        this._diagnostics.connectionOpens += 1
        this._notifyDiagnostics()
        this._setState('connected')
      }

      this._ws.onmessage = (event: MessageEvent) => {
        this._handleMessage(event)
      }

      this._ws.onerror = (event: Event) => {
        this._callbacks?.onError(event)
      }

      this._ws.onclose = () => {
        this._diagnostics.lastDisconnectAt = Date.now()
        this._notifyDiagnostics()
        this._setState('disconnected')
        this._tryReconnect()
      }
    } catch (err) {
      console.error('[WsClient] Connection failed:', err)
      this._setState('error')
      this._tryReconnect()
    }
  }

  sendAudio(data: ArrayBuffer): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(data)
      this._diagnostics.sentAudioChunks += 1
      this._notifyDiagnostics()
      return
    }

    this._diagnostics.droppedAudioChunks += 1
    this._notifyDiagnostics()
  }

  sendControl(message: Record<string, unknown>): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(message))
    }
  }

  disconnect(): void {
    this._intentionalClose = true
    this._clearReconnect()
    if (this._ws) {
      this._ws.close(1000, 'Client disconnect')
      this._ws = null
    }
    this._setState('disconnected')
  }

  resetSession(): void {
    this.disconnect()
    const sessionId = createSessionId()
    this._url = appendSessionId(this._baseUrl, sessionId)
    this._retryCount = 0
    this._diagnostics = {
      sessionId,
      captureBackend: null,
      sentAudioChunks: 0,
      droppedAudioChunks: 0,
      reconnectAttempts: 0,
      connectionOpens: 0,
      lastDisconnectAt: null,
    }
    this._notifyDiagnostics()
  }

  private _handleMessage(event: MessageEvent): void {
    try {
      if (typeof event.data === 'string') {
        const message = JSON.parse(event.data) as ServerMessage
        this._callbacks?.onMessage(message)
      }
    } catch (err) {
      console.error('[WsClient] Failed to parse message:', err)
    }
  }

  private _tryReconnect(): void {
    if (this._intentionalClose) return
    if (this._retryCount >= RECONNECT_CONFIG.maxRetries) {
      console.error('[WsClient] Max reconnection attempts reached')
      this._setState('error')
      return
    }

    const delay = Math.min(
      RECONNECT_CONFIG.baseDelayMs * Math.pow(2, this._retryCount),
      RECONNECT_CONFIG.maxDelayMs,
    )

    this._diagnostics.reconnectAttempts += 1
    this._notifyDiagnostics()

    this._reconnectTimer = setTimeout(() => {
      this._retryCount += 1
      this.connect()
    }, delay)
  }

  private _clearReconnect(): void {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer)
      this._reconnectTimer = null
    }
  }

  private _setState(state: ConnectionState): void {
    this._state = state
    this._callbacks?.onStateChange(state)
  }

  private _notifyDiagnostics(): void {
    this._callbacks?.onDiagnosticsChange?.(this.diagnostics)
  }
}


function createSessionId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID().slice(0, 8)
  }

  return Math.random().toString(36).slice(2, 10)
}


function appendSessionId(baseUrl: string, sessionId: string): string {
  const normalized = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl
  return `${normalized}/${encodeURIComponent(sessionId)}`
}
