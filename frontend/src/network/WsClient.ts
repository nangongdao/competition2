import type { ClientDiagnostics, LanguageConfig, ServerMessage, TranslationStyle } from '../types'


export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'


export interface WsClientCallbacks {
  onStateChange: (state: ConnectionState) => void
  onMessage: (message: ServerMessage) => void
  onError: (error: Event) => void
  onDiagnosticsChange?: (diagnostics: ClientDiagnostics) => void
  /** 二进制帧（如后端 TTS MP3 音频），紧随元信息帧之后到达。 */
  onMessageBytes?: (payload: ArrayBuffer) => void
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
  private _languageConfig: LanguageConfig | null = null
  private _reconnectToken: string | null = null
  private _stylePreset: TranslationStyle = 'concise'
  private _asrHotwordsEnabled = true

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

  /** 当前会话 ID（由 createSessionId 生成，随重连保持稳定）。 */
  get sessionId(): string {
    return this._diagnostics.sessionId
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
      this._ws = new WebSocket(this._connectUrl())
      this._ws.binaryType = 'arraybuffer'

      this._ws.onopen = () => {
        this._retryCount = 0
        this._diagnostics.connectionOpens += 1
        this._notifyDiagnostics()
        this._sendLanguageConfigIfOpen()
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

  setLanguageConfig(config: LanguageConfig): void {
    this._languageConfig = { ...config }
    this._sendLanguageConfigIfOpen()
  }

  /** 设置翻译风格预设（阶段 3），连接打开时立即下发。 */
  setStylePreset(style: TranslationStyle): void {
    this._stylePreset = style
    if (!this._languageConfig) {
      this._languageConfig = { sourceLanguage: 'en', targetLanguage: 'zh-CN' }
    }
    this._sendLanguageConfigIfOpen()
  }

  /** 设置 ASR 热词注入开关（阶段 2），连接打开时立即下发。 */
  setAsrHotwordsEnabled(enabled: boolean): void {
    this._asrHotwordsEnabled = enabled
    if (!this._languageConfig) {
      this._languageConfig = { sourceLanguage: 'en', targetLanguage: 'zh-CN' }
    }
    this._sendLanguageConfigIfOpen()
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
    this._reconnectToken = null
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
        this._captureReconnectToken(message)
        this._callbacks?.onMessage(message)
        return
      }

      // 二进制帧：转发给二进制回调（当前用于后端 TTS MP3 音频）。
      if (event.data instanceof ArrayBuffer) {
        this._callbacks?.onMessageBytes?.(event.data)
      }
    } catch (err) {
      console.error('[WsClient] Failed to parse message:', err)
    }
  }

  private _captureReconnectToken(message: ServerMessage): void {
    if (message.type === 'status' && typeof message.reconnect_token === 'string') {
      this._reconnectToken = message.reconnect_token
    }
  }

  private _connectUrl(): string {
    if (!this._reconnectToken) {
      return this._url
    }
    return appendReconnectToken(this._url, this._reconnectToken)
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

  private _sendLanguageConfigIfOpen(): void {
    if (!this._languageConfig || !this._ws || this._ws.readyState !== WebSocket.OPEN) {
      return
    }

    this.sendControl({
      type: 'config',
      language: this._languageConfig.sourceLanguage,
      target_language: this._languageConfig.targetLanguage,
      style_preset: this._stylePreset,
      asr_hotwords_enabled: this._asrHotwordsEnabled,
    })
  }
}


function createSessionId(): string {
  // 使用完整 UUID（122 bit 熵）而非截断 8 字符，避免会话 ID 可被枚举。
  // 截断后的短 ID 会让攻击者暴力枚举出活跃会话并触发接管尝试。
  const webCrypto = (globalThis as typeof globalThis & { crypto?: Crypto }).crypto
  if (webCrypto && typeof webCrypto.randomUUID === 'function') {
    return webCrypto.randomUUID()
  }
  if (webCrypto && typeof webCrypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    webCrypto.getRandomValues(bytes)
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  }
  throw new Error('Web Crypto API unavailable for session id generation')
}


function appendSessionId(baseUrl: string, sessionId: string): string {
  const normalized = baseUrl.endsWith('/') ? baseUrl.slice(0, -1) : baseUrl
  return `${normalized}/${encodeURIComponent(sessionId)}`
}


function appendReconnectToken(sessionUrl: string, token: string): string {
  const separator = sessionUrl.includes('?') ? '&' : '?'
  return `${sessionUrl}${separator}token=${encodeURIComponent(token)}`
}
