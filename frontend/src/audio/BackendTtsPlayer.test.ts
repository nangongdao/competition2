import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'

import { BackendTtsPlayer } from './BackendTtsPlayer'


/**
 * 极简 HTMLAudioElement mock：仅覆盖 BackendTtsPlayer 依赖的字段与方法。
 */
class MockAudioElement {
  src = ''
  volume = 1
  playbackRate = 1
  preload = 'none'
  paused = true
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  playCalls = 0

  async play(): Promise<void> {
    this.playCalls += 1
    this.paused = false
  }

  pause(): void {
    this.paused = true
  }

  finish(): void {
    this.paused = true
    this.onended?.()
  }

  fail(): void {
    this.paused = true
    this.onerror?.()
  }
}


const HAD_ORIGINAL_AUDIO = 'Audio' in globalThis
const ORIGINAL_AUDIO = (globalThis as Record<string, unknown>).Audio
const HAD_ORIGINAL_URL = 'URL' in globalThis
const ORIGINAL_URL = globalThis.URL

let mockInstances: MockAudioElement[] = []
let revokedUrls: string[] = []


function installAudioMock(): void {
  mockInstances = []
  revokedUrls = []
  Object.defineProperty(globalThis, 'Audio', {
    configurable: true,
    value: class {
      constructor() {
        const instance = new MockAudioElement()
        mockInstances.push(instance)
        return instance
      }
    },
  })

  Object.defineProperty(globalThis, 'URL', {
    configurable: true,
    value: {
      createObjectURL: () => 'blob:mock-audio',
      revokeObjectURL: (url: string) => {
        revokedUrls.push(url)
      },
    },
  })
}


function latestAudio(): MockAudioElement {
  const instance = mockInstances[mockInstances.length - 1]
  if (!instance) {
    throw new Error('No Audio instance created yet')
  }
  return instance
}


function restoreAudioMock(): void {
  if (HAD_ORIGINAL_AUDIO) {
    Object.defineProperty(globalThis, 'Audio', { configurable: true, value: ORIGINAL_AUDIO })
  } else {
    delete (globalThis as Record<string, unknown>).Audio
  }
  if (HAD_ORIGINAL_URL) {
    Object.defineProperty(globalThis, 'URL', { configurable: true, value: ORIGINAL_URL })
  } else {
    delete (globalThis as Record<string, unknown>).URL
  }
}


function makePayload(length: number): ArrayBuffer {
  const buffer = new ArrayBuffer(length)
  new Uint8Array(buffer).fill(0x41)
  return buffer
}


describe('BackendTtsPlayer', () => {
  afterEach(() => {
    restoreAudioMock()
  })

  it('reports unsupported when Audio element is missing', () => {
    delete (globalThis as Record<string, unknown>).Audio
    const player = new BackendTtsPlayer()
    assert.equal(player.diagnostics.isSupported, false)
  })

  it('ignores audio frames while disabled', () => {
    installAudioMock()
    const player = new BackendTtsPlayer()
    player.handleTtsAudioMeta('seg-1', 1024)
    player.handleTtsAudioBytes(makePayload(1024))
    assert.equal(player.diagnostics.queueLength, 0)
    assert.equal(player.diagnostics.skippedUtterances, 0)
  })

  it('plays one MP3 frame per metadata frame in order', async () => {
    installAudioMock()
    const player = new BackendTtsPlayer()
    player.setEnabled(true)

    player.handleTtsAudioMeta('seg-1', 4)
    player.handleTtsAudioBytes(makePayload(4))
    player.handleTtsAudioMeta('seg-2', 8)
    player.handleTtsAudioBytes(makePayload(8))

    // 等待 play 异步调用落地
    await new Promise((resolve) => setTimeout(resolve, 0))
    const audio = latestAudio()
    assert.equal(audio.playCalls, 1)
    assert.equal(player.diagnostics.isSpeaking, true)
    assert.equal(player.diagnostics.queueLength, 1)

    audio.finish()
    await new Promise((resolve) => setTimeout(resolve, 0))
    assert.equal(player.diagnostics.spokenUtterances, 1)
    assert.equal(player.diagnostics.isSpeaking, true)

    audio.finish()
    await new Promise((resolve) => setTimeout(resolve, 0))
    assert.equal(player.diagnostics.spokenUtterances, 2)
    assert.equal(player.diagnostics.isSpeaking, false)
  })

  it('skips empty-audio metadata frames without queueing', async () => {
    installAudioMock()
    const player = new BackendTtsPlayer()
    player.setEnabled(true)

    player.handleTtsAudioMeta('seg-1', 0)
    assert.equal(player.diagnostics.skippedUtterances, 1)
    assert.equal(player.diagnostics.queueLength, 0)
  })

  it('skips binary frames without pending metadata', async () => {
    installAudioMock()
    const player = new BackendTtsPlayer()
    player.setEnabled(true)

    player.handleTtsAudioBytes(makePayload(4))
    assert.equal(player.diagnostics.queueLength, 0)
  })

  it('cancelQueue clears queued items and revokes object URLs', async () => {
    installAudioMock()
    const player = new BackendTtsPlayer()
    player.setEnabled(true)

    player.handleTtsAudioMeta('seg-1', 4)
    player.handleTtsAudioBytes(makePayload(4))
    await new Promise((resolve) => setTimeout(resolve, 0))
    const audio = latestAudio()

    player.cancelQueue()
    assert.equal(audio.paused, true)
    assert.equal(player.diagnostics.queueLength, 0)
    assert.equal(player.diagnostics.isSpeaking, false)
    assert.equal(revokedUrls.length >= 1, true)
  })

  it('clamps volume and rate, falls back for non-finite values', () => {
    installAudioMock()
    const player = new BackendTtsPlayer()

    player.setVolume(2)
    player.setRate(0.1)
    assert.equal(player.settings.volume, 1)
    assert.equal(player.settings.rate, 0.7)

    player.setVolume(Number.NaN)
    player.setRate(Number.POSITIVE_INFINITY)
    assert.equal(player.settings.volume, 0.8)
    assert.equal(player.settings.rate, 1)
  })

  it('reset preserves enabled/volume/rate but clears counters', () => {
    installAudioMock()
    const player = new BackendTtsPlayer()
    player.setEnabled(true)
    player.setVolume(0.5)
    player.setRate(1.1)

    player.handleTtsAudioMeta('seg-1', 4)
    player.handleTtsAudioBytes(makePayload(4))
    player.reset()

    assert.equal(player.settings.enabled, true)
    assert.equal(player.settings.volume, 0.5)
    assert.equal(player.settings.rate, 1.1)
    assert.equal(player.diagnostics.spokenUtterances, 0)
    assert.equal(player.diagnostics.queueLength, 0)
  })

  it('handleRevisedTranslation removes queued items for the segment', async () => {
    installAudioMock()
    const player = new BackendTtsPlayer()
    player.setEnabled(true)

    // 两个片段入队，第一个开始播放，第二个仍在队列
    player.handleTtsAudioMeta('seg-1', 4)
    player.handleTtsAudioBytes(makePayload(4))
    player.handleTtsAudioMeta('seg-2', 8)
    player.handleTtsAudioBytes(makePayload(8))
    await new Promise((resolve) => setTimeout(resolve, 0))
    assert.equal(player.diagnostics.queueLength, 1)
    const audio = latestAudio()
    assert.equal(audio.playCalls, 1)

    // 修正 seg-2：仍在队列中的旧音频被移除，播放不被打断
    player.handleRevisedTranslation('seg-2', 'corrected text')
    assert.equal(player.diagnostics.queueLength, 0)
    assert.equal(audio.playCalls, 1)

    audio.finish()
    await new Promise((resolve) => setTimeout(resolve, 0))
    assert.equal(player.diagnostics.isSpeaking, false)
  })

  it('handleRevisedTranslation skips when segment already spoken', async () => {
    installAudioMock()
    const player = new BackendTtsPlayer()
    player.setEnabled(true)

    player.handleTtsAudioMeta('seg-1', 4)
    player.handleTtsAudioBytes(makePayload(4))
    await new Promise((resolve) => setTimeout(resolve, 0))
    const audio = latestAudio()
    audio.finish()
    await new Promise((resolve) => setTimeout(resolve, 0))

    const skippedBefore = player.diagnostics.skippedUtterances
    // 已播放完毕，修正太晚 -> 跳过，不打断任何播放
    player.handleRevisedTranslation('seg-1', 'corrected text')
    assert.equal(player.diagnostics.skippedUtterances, skippedBefore + 1)
    assert.equal(player.diagnostics.isSpeaking, false)
  })

  it('handleRevisedTranslation ignores when disabled', () => {
    installAudioMock()
    const player = new BackendTtsPlayer()
    player.handleTtsAudioMeta('seg-1', 4)
    player.handleTtsAudioBytes(makePayload(4))
    const skippedBefore = player.diagnostics.skippedUtterances
    player.handleRevisedTranslation('seg-1', 'corrected text')
    assert.equal(player.diagnostics.skippedUtterances, skippedBefore)
  })
})
