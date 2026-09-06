import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  getRuntimeWebSocketUrlFromSearch,
  resolveTerminalWebSocketUrl,
  resolveWebSocketBaseUrl,
} from './ws-url'


describe('WebSocket URL resolution', () => {
  it('prefers runtime desktop URL over build-time configuration', () => {
    const url = resolveWebSocketBaseUrl({
      runtimeUrl: 'ws://127.0.0.1:49321/api/v1/ws/translate',
      configuredUrl: 'ws://127.0.0.1:8000/api/v1/ws/translate',
      hostname: 'localhost',
    })

    assert.equal(url, 'ws://127.0.0.1:49321/api/v1/ws/translate')
  })

  it('uses configured Vite URL when no runtime URL is available', () => {
    const url = resolveWebSocketBaseUrl({
      configuredUrl: 'ws://127.0.0.1:8001/api/v1/ws/translate/',
      hostname: 'localhost',
    })

    assert.equal(url, 'ws://127.0.0.1:8001/api/v1/ws/translate')
  })

  it('falls back to the current hostname and default backend port', () => {
    const url = resolveWebSocketBaseUrl({ hostname: 'demo.local' })

    assert.equal(url, 'ws://demo.local:8000/api/v1/ws/translate')
  })

  it('extracts decoded runtime URL from search params', () => {
    const runtimeUrl = getRuntimeWebSocketUrlFromSearch(
      '?surface=overlay&wsUrl=ws%3A%2F%2F127.0.0.1%3A49152%2Fapi%2Fv1%2Fws%2Ftranslate%2F',
    )

    assert.equal(runtimeUrl, 'ws://127.0.0.1:49152/api/v1/ws/translate')
  })
})

describe('normalizeWebSocketUrl — 安全校验', () => {
  const maliciousUrls = [
    'ws://attacker.example.com/collect',
    'wss://evil.cn/x',
    'http://127.0.0.1:8000/api', // 协议不对
    'javascript:alert(1)',
    'ws://169.254.169.254/', // 云元数据
    'ws://192.168.1.100:8000/', // 内网他机
  ]

  for (const url of maliciousUrls) {
    it(`拒绝 ${url}`, () => {
      assert.equal(
        resolveWebSocketBaseUrl({ runtimeUrl: url }),
        'ws://127.0.0.1:8000/api/v1/ws/translate', // 回落到默认值
      )
    })
  }

  it('接受本机地址', () => {
    assert.equal(
      resolveWebSocketBaseUrl({ runtimeUrl: 'ws://127.0.0.1:8000/api/v1/ws/translate' }),
      'ws://127.0.0.1:8000/api/v1/ws/translate',
    )
  })

  it('接受 localhost 主机', () => {
    assert.equal(
      resolveWebSocketBaseUrl({ runtimeUrl: 'ws://localhost:8000/api/v1/ws/translate' }),
      'ws://localhost:8000/api/v1/ws/translate',
    )
  })

  it('拒绝混合大小写的主机（应归一化后仍匹配白名单）', () => {
    assert.equal(
      resolveWebSocketBaseUrl({ runtimeUrl: 'ws://LOCALHOST:8000/api' }),
      'ws://LOCALHOST:8000/api',
    )
  })
})

describe('resolveTerminalWebSocketUrl', () => {
  it('将翻译 WS 路径替换为终端路径', () => {
    const url = resolveTerminalWebSocketUrl({
      runtimeUrl: 'ws://127.0.0.1:49321/api/v1/ws/translate',
    })

    assert.equal(url, 'ws://127.0.0.1:49321/api/v1/ws/terminal')
  })

  it('无运行时 URL 时回落到默认端口终端地址', () => {
    const url = resolveTerminalWebSocketUrl({ hostname: '127.0.0.1' })

    assert.equal(url, 'ws://127.0.0.1:8000/api/v1/ws/terminal')
  })

  it('带尾斜杠的翻译 URL 也能正确转换', () => {
    const url = resolveTerminalWebSocketUrl({
      runtimeUrl: 'ws://127.0.0.1:8000/api/v1/ws/translate/',
    })

    assert.equal(url, 'ws://127.0.0.1:8000/api/v1/ws/terminal')
  })
})
