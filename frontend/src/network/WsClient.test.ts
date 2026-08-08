import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'

import { WsClient } from './WsClient'


class MockWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: MockWebSocket[] = []

  binaryType: BinaryType = 'blob'
  readyState = MockWebSocket.CONNECTING
  readonly sent: Array<string | ArrayBuffer> = []
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  constructor(readonly url: string) {
    MockWebSocket.instances.push(this)
  }

  send(data: string | ArrayBuffer): void {
    this.sent.push(data)
  }

  close(): void {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  }

  open(): void {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }
}


const HAD_ORIGINAL_WEBSOCKET = 'WebSocket' in globalThis
const ORIGINAL_WEBSOCKET = globalThis.WebSocket
const HAD_ORIGINAL_CRYPTO = 'crypto' in globalThis
const ORIGINAL_CRYPTO = globalThis.crypto


describe('WsClient', () => {
  afterEach(() => {
    restoreWebSocketMock()
  })

  it('sends configured language pair when the socket opens', () => {
    installWebSocketMock()
    const client = new WsClient('ws://localhost:8000/api/v1/ws/translate')

    client.setCallbacks({
      onStateChange: () => undefined,
      onMessage: () => undefined,
      onError: () => undefined,
    })
    client.setLanguageConfig({
      sourceLanguage: 'ja',
      targetLanguage: 'zh-CN',
    })
    client.connect()

    const socket = latestSocket()
    socket.open()

    assert.equal(
      socket.url,
      'ws://localhost:8000/api/v1/ws/translate/config-test-0000-0000-0000-000000000000',
    )
    assert.deepEqual(JSON.parse(readSentText(socket, 0)), {
      type: 'config',
      language: 'ja',
      target_language: 'zh-CN',
    })
  })

  it('sends a new config immediately when language changes on an open socket', () => {
    installWebSocketMock()
    const client = new WsClient('ws://localhost:8000/api/v1/ws/translate')

    client.setCallbacks({
      onStateChange: () => undefined,
      onMessage: () => undefined,
      onError: () => undefined,
    })
    client.connect()
    const socket = latestSocket()
    socket.open()

    client.setLanguageConfig({
      sourceLanguage: 'fr',
      targetLanguage: 'zh-CN',
    })

    assert.deepEqual(JSON.parse(readSentText(socket, 0)), {
      type: 'config',
      language: 'fr',
      target_language: 'zh-CN',
    })
  })
})


function installWebSocketMock(): void {
  MockWebSocket.instances = []
  Object.defineProperty(globalThis, 'crypto', {
    configurable: true,
    value: {
      randomUUID: () => 'config-test-0000-0000-0000-000000000000',
    },
    writable: true,
  })
  Object.defineProperty(globalThis, 'WebSocket', {
    configurable: true,
    value: MockWebSocket,
    writable: true,
  })
}


function restoreWebSocketMock(): void {
  if (HAD_ORIGINAL_WEBSOCKET) {
    Object.defineProperty(globalThis, 'WebSocket', {
      configurable: true,
      value: ORIGINAL_WEBSOCKET,
      writable: true,
    })
  } else {
    Reflect.deleteProperty(globalThis, 'WebSocket')
  }

  if (HAD_ORIGINAL_CRYPTO) {
    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: ORIGINAL_CRYPTO,
      writable: true,
    })
  } else {
    Reflect.deleteProperty(globalThis, 'crypto')
  }
}


function latestSocket(): MockWebSocket {
  const socket = MockWebSocket.instances[MockWebSocket.instances.length - 1]
  if (!socket) {
    throw new Error('Expected a WebSocket instance.')
  }
  return socket
}


function readSentText(socket: MockWebSocket, index: number): string {
  const sent = socket.sent[index]
  if (typeof sent !== 'string') {
    throw new Error(`Expected text message at index ${index}.`)
  }
  return sent
}
