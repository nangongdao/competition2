import { afterEach, beforeEach, describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  BACKEND_TTS_STORAGE_KEY,
  clearBackendTtsConfig,
  loadBackendTtsConfig,
  saveBackendTtsConfig,
} from './backend-tts-persist'
import { DEFAULT_BACKEND_TTS_CONFIG } from './backend-tts-config'

/** 简易 in-memory localStorage，供 node 测试环境使用。 */
function installLocalStorageMock(): void {
  const store = new Map<string, string>()
  const mock = {
    getItem: (key: string): string | null => store.get(key) ?? null,
    setItem: (key: string, value: string): void => {
      store.set(key, String(value))
    },
    removeItem: (key: string): void => {
      store.delete(key)
    },
    clear: (): void => {
      store.clear()
    },
  }
  Object.defineProperty(globalThis, 'localStorage', {
    value: mock,
    configurable: true,
    writable: true,
  })
}

describe('backend-tts-persist', () => {
  beforeEach(() => {
    installLocalStorageMock()
  })

  afterEach(() => {
    try {
      localStorage.clear()
    } catch {
      // ignore
    }
  })

  it('returns defaults when nothing has been saved', () => {
    assert.deepEqual(loadBackendTtsConfig(), { ...DEFAULT_BACKEND_TTS_CONFIG })
  })

  it('round-trips a valid config', () => {
    saveBackendTtsConfig({ voice: 'zh-CN-YunxiNeural', rate: '+10%', volume: '+25%', delay: 600 })
    assert.deepEqual(loadBackendTtsConfig(), {
      voice: 'zh-CN-YunxiNeural',
      rate: '+10%',
      volume: '+25%',
      delay: 600,
    })
  })

  it('round-trips a zero delay (紧跟字幕)', () => {
    saveBackendTtsConfig({ voice: 'zh-CN-XiaoxiaoNeural', rate: '+0%', volume: '+0%', delay: 0 })
    assert.deepEqual(loadBackendTtsConfig(), { ...DEFAULT_BACKEND_TTS_CONFIG })
  })

  it('normalizes an out-of-range delay on save', () => {
    saveBackendTtsConfig({ voice: 'zh-CN-XiaoxiaoNeural', rate: '+0%', volume: '+0%', delay: 12345 })
    assert.deepEqual(loadBackendTtsConfig(), { ...DEFAULT_BACKEND_TTS_CONFIG })
  })

  it('normalizes a negative delay on load', () => {
    localStorage.setItem(
      BACKEND_TTS_STORAGE_KEY,
      JSON.stringify({ voice: 'zh-CN-YunxiNeural', rate: '+0%', volume: '+0%', delay: -500 }),
    )
    assert.deepEqual(loadBackendTtsConfig(), {
      voice: 'zh-CN-YunxiNeural',
      rate: '+0%',
      volume: '+0%',
      delay: DEFAULT_BACKEND_TTS_CONFIG.delay,
    })
  })

  it('normalizes an out-of-range voice/rate/volume on save', () => {
    saveBackendTtsConfig({ voice: 'not-a-voice', rate: 'not-a-rate', volume: 'not-a-volume', delay: 300 })
    assert.deepEqual(loadBackendTtsConfig(), {
      voice: DEFAULT_BACKEND_TTS_CONFIG.voice,
      rate: DEFAULT_BACKEND_TTS_CONFIG.rate,
      volume: DEFAULT_BACKEND_TTS_CONFIG.volume,
      delay: 300,
    })
  })

  it('normalizes an out-of-range volume on load', () => {
    localStorage.setItem(
      BACKEND_TTS_STORAGE_KEY,
      JSON.stringify({ voice: 'zh-CN-YunxiNeural', rate: '+0%', volume: 'loud' }),
    )
    assert.deepEqual(loadBackendTtsConfig(), {
      voice: 'zh-CN-YunxiNeural',
      rate: '+0%',
      volume: DEFAULT_BACKEND_TTS_CONFIG.volume,
      delay: DEFAULT_BACKEND_TTS_CONFIG.delay,
    })
  })

  it('falls back to defaults when stored JSON is corrupt', () => {
    localStorage.setItem(BACKEND_TTS_STORAGE_KEY, '{ not valid json')
    assert.deepEqual(loadBackendTtsConfig(), { ...DEFAULT_BACKEND_TTS_CONFIG })
  })

  it('falls back to defaults when stored fields are the wrong type', () => {
    localStorage.setItem(BACKEND_TTS_STORAGE_KEY, JSON.stringify({ voice: 123, rate: null }))
    assert.deepEqual(loadBackendTtsConfig(), { ...DEFAULT_BACKEND_TTS_CONFIG })
  })

  it('clear removes the saved config so the next load returns defaults', () => {
    saveBackendTtsConfig({ voice: 'zh-CN-YunxiNeural', rate: '+25%', volume: '+50%', delay: 1000 })
    clearBackendTtsConfig()
    assert.deepEqual(loadBackendTtsConfig(), { ...DEFAULT_BACKEND_TTS_CONFIG })
  })
})
