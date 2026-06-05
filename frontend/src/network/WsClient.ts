/**
 * WebSocket 客户端
 *
 * 管理与后端的 WebSocket 连接：
 * - 自动重连（指数退避）
 * - 消息序列化/分派
 * - 连接状态通知
 */

import type { ServerMessage } from '../types'

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'

export interface WsClientCallbacks {
  onStateChange: (state: ConnectionState) => void
  onMessage: (message: ServerMessage) => void
  onError: (error: Event) => void
}

const RECONNECT_CONFIG = {
  maxRetries: 10,
  baseDelayMs: 1000,
  maxDelayMs: 30000,
}

/**
 * WebSocket 客户端
 */
export class WsClient {
  private _ws: WebSocket | null = null
  private _state: ConnectionState = 'disconnected'
  private _callbacks: WsClientCallbacks | null = null
  private _url: string
  private _retryCount = 0
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _intentionalClose = false

  constructor(url: string) {
    this._url = url
  }

  get state(): ConnectionState {
    return this._state
  }

  setCallbacks(callbacks: WsClientCallbacks): void {
    this._callbacks = callbacks
  }

  /** 建立连接 */
  connect(): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) return

    this._intentionalClose = false
    this._setState('connecting')

    try {
      this._ws = new WebSocket(this._url)
      this._ws.binaryType = 'arraybuffer'

      this._ws.onopen = () => {
        console.log('[WsClient] Connected')
        this._retryCount = 0
        this._setState('connected')
      }

      this._ws.onmessage = (event: MessageEvent) => {
        this._handleMessage(event)
      }

      this._ws.onerror = (event: Event) => {
        console.error('[WsClient] Error:', event)
        this._callbacks?.onError(event)
      }

      this._ws.onclose = (event: CloseEvent) => {
        console.log(`[WsClient] Closed: ${event.code} ${event.reason}`)
        this._setState('disconnected')
        this._tryReconnect()
      }
    } catch (err) {
      console.error('[WsClient] Connection failed:', err)
      this._setState('error')
      this._tryReconnect()
    }
  }

  /** 发送音频数据 */
  sendAudio(data: ArrayBuffer): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(data)
    }
  }

  /** 发送控制消息 */
  sendControl(message: Record<string, unknown>): void {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(message))
    }
  }

  /** 断开连接 */
  disconnect(): void {
    this._intentionalClose = true
    this._clearReconnect()
    if (this._ws) {
      this._ws.close(1000, 'Client disconnect')
      this._ws = null
    }
    this._setState('disconnected')
  }

  /** 处理收到的消息 */
  private _handleMessage(event: MessageEvent): void {
    try {
      if (typeof event.data === 'string') {
        const message: ServerMessage = JSON.parse(event.data)
        this._callbacks?.onMessage(message)
      }
      // 二进制消息暂不处理（服务端目前都发 JSON）
    } catch (err) {
      console.error('[WsClient] Failed to parse message:', err)
    }
  }

  /** 尝试重连（指数退避） */
  private _tryReconnect(): void {
    if (this._intentionalClose) return
    if (this._retryCount >= RECONNECT_CONFIG.maxRetries) {
      console.error('[WsClient] Max reconnection attempts reached')
      this._setState('error')
      return
    }

    const delay = Math.min(
      RECONNECT_CONFIG.baseDelayMs * Math.pow(2, this._retryCount),
      RECONNECT_CONFIG.maxDelayMs
    )

    console.log(`[WsClient] Reconnecting in ${delay}ms (attempt ${this._retryCount + 1})`)

    this._reconnectTimer = setTimeout(() => {
      this._retryCount++
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
}