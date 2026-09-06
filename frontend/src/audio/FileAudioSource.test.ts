import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'

import { FileAudioSource, resampleToPipeline } from './FileAudioSource'


/** 最小 AudioBuffer mock（提供 getChannelData / sampleRate / length / numberOfChannels）。 */
class MockAudioBuffer {
  readonly sampleRate: number
  readonly numberOfChannels: number
  readonly length: number
  private readonly _data: Float32Array[]

  constructor(channels: Float32Array[], sampleRate: number) {
    this._data = channels
    this.numberOfChannels = channels.length
    this.length = channels[0]?.length ?? 0
    this.sampleRate = sampleRate
  }

  getChannelData(channel: number): Float32Array {
    return this._data[channel] ?? new Float32Array(0)
  }
}


function installDecodeMock(channels: Float32Array[], sampleRate: number, shouldFail = false): void {
  class MockOfflineAudioContext {
    readonly state = 'running'
    readonly destination = {}
    constructor(
      public readonly numberOfChannels: number,
      public readonly length: number,
      public readonly sampleRate: number,
    ) {}

    async decodeAudioData(_arrayBuffer: ArrayBuffer): Promise<MockAudioBuffer> {
      if (shouldFail) {
        throw new Error('decode failed')
      }
      return new MockAudioBuffer(channels, sampleRate)
    }
  }
  Object.defineProperty(globalThis, 'OfflineAudioContext', {
    configurable: true,
    value: MockOfflineAudioContext,
    writable: true,
  })
}

function makeWavFile(name: string): File {
  // 构造一个 1 字节的假音频文件（decode mock 不真正解析内容）。
  return new File([new Uint8Array([1, 2, 3, 4])], name, { type: 'audio/wav' })
}

/** 伪造定时器，手动推进时钟。 */
function installFakeTimers(): { advance: (ms: number) => void; restore: () => void } {
  const originalSetInterval = globalThis.setInterval
  const originalClearInterval = globalThis.clearInterval
  const timers: Array<{ id: number; fn: () => void; ms: number }> = []
  let nextId = 1

  Object.defineProperty(globalThis, 'setInterval', {
    configurable: true,
    value: (fn: () => void, ms: number): number => {
      const id = nextId
      nextId += 1
      timers.push({ id, fn, ms })
      return id
    },
    writable: true,
  })
  Object.defineProperty(globalThis, 'clearInterval', {
    configurable: true,
    value: (id: number): void => {
      const index = timers.findIndex((timer) => timer.id === id)
      if (index >= 0) {
        timers.splice(index, 1)
      }
    },
    writable: true,
  })

  return {
    advance: (ms: number) => {
      // 简单近似：每 100ms 触发一次对应回调。
      const ticks = Math.floor(ms / 100)
      for (let i = 0; i < ticks; i += 1) {
        for (const timer of [...timers]) {
          timer.fn()
        }
      }
    },
    restore: () => {
      Object.defineProperty(globalThis, 'setInterval', {
        configurable: true,
        value: originalSetInterval,
        writable: true,
      })
      Object.defineProperty(globalThis, 'clearInterval', {
        configurable: true,
        value: originalClearInterval,
        writable: true,
      })
    },
  }
}

describe('FileAudioSource', () => {
  afterEach(() => {
    delete (globalThis as Record<string, unknown>).OfflineAudioContext
    delete (globalThis as Record<string, unknown>).AudioContext
  })

  it('decodes a file and streams 100ms chunks at real-time pace', async () => {
    // 1 秒 @ 16kHz 单声道正弦波。
    const seconds = 1
    const rate = 16000
    const data = new Float32Array(rate * seconds)
    for (let i = 0; i < data.length; i += 1) {
      data[i] = Math.sin((2 * Math.PI * 440 * i) / rate) * 0.5
    }
    installDecodeMock([data], rate)

    const fakeTimers = installFakeTimers()
    const source = new FileAudioSource()
    const chunks: ArrayBuffer[] = []
    let states: string[] = []
    let ended = 0

    source.setCallbacks({
      onAudioChunk: (chunk) => chunks.push(chunk),
      onStateChange: (state) => states.push(state),
      onEnded: () => {
        ended += 1
      },
    })

    const ok = await source.start(makeWavFile('sample.wav'))
    assert.equal(ok, true)
    assert.equal(source.state, 'active')
    assert.equal(source.fileName, 'sample.wav')
    assert.equal(source.sampleCount, rate * seconds)
    assert.equal(chunks.length, 0)

    // 推进 500ms → 应产生 5 块。
    fakeTimers.advance(500)
    assert.equal(chunks.length, 5)

    // 每块 1600 采样。
    for (const chunk of chunks) {
      const samples = new Float32Array(chunk)
      assert.equal(samples.length, 1600)
    }

    // 推进到结束：再 500ms 恰好播完 1 秒（第 10 块）。
    fakeTimers.advance(500)
    assert.equal(chunks.length, 10)
    assert.equal(source.state, 'active')

    // 下一次 tick 检测到无剩余采样 → 结束。
    fakeTimers.advance(100)
    assert.equal(source.state, 'ended')
    assert.equal(ended, 1)

    fakeTimers.restore()
  })

  it('returns false and reports error on decode failure', async () => {
    installDecodeMock([new Float32Array(0)], 16000, true)
    const source = new FileAudioSource()
    let errorMessage = ''
    source.setCallbacks({
      onAudioChunk: () => undefined,
      onStateChange: () => undefined,
      onError: (message) => {
        errorMessage = message
      },
    })

    const ok = await source.start(makeWavFile('bad.wav'))
    assert.equal(ok, false)
    assert.equal(source.state, 'error')
    assert.ok(errorMessage.length > 0)
  })

  it('replays the loaded sample after stop without re-selecting the file', async () => {
    const rate = 16000
    const data = new Float32Array(rate) // 1 秒
    installDecodeMock([data], rate)

    const fakeTimers = installFakeTimers()
    const source = new FileAudioSource()
    let chunks = 0
    source.setCallbacks({
      onAudioChunk: () => {
        chunks += 1
      },
      onStateChange: () => undefined,
    })

    const ok = await source.start(makeWavFile('replay.wav'))
    assert.equal(ok, true)
    assert.equal(source.fileName, 'replay.wav')

    // 播放 300ms → 3 块。
    fakeTimers.advance(300)
    assert.equal(chunks, 3)

    // 停止（保留样本）。
    source.stop()
    assert.equal(source.state, 'inactive')
    assert.equal(source.fileName, 'replay.wav')

    // 不传文件直接重播。
    const replayOk = await source.start()
    assert.equal(replayOk, true)
    assert.equal(source.state, 'active')

    fakeTimers.advance(200)
    assert.equal(chunks, 5)

    // 彻底释放。
    source.reset()
    assert.equal(source.fileName, '')
    assert.equal(source.state, 'inactive')

    const afterReset = await source.start()
    assert.equal(afterReset, false)
    assert.equal(source.state, 'error')

    fakeTimers.restore()
  })

  it('reset clears samples and start without file fails cleanly', async () => {
    installDecodeMock([new Float32Array(16000)], 16000)
    const source = new FileAudioSource()
    source.setCallbacks({
      onAudioChunk: () => undefined,
      onStateChange: () => undefined,
    })
    await source.start(makeWavFile('x.wav'))
    source.reset()

    const ok = await source.start()
    assert.equal(ok, false)
    assert.equal(source.state, 'error')
  })

  it('resampleToPipeline downmixes stereo and resamples to 16k', () => {
    const left = new Float32Array([1, 2, 3, 4])
    const right = new Float32Array([0, 0, 0, 0])
    const buffer = new MockAudioBuffer([left, right], 8000)

    const mono = resampleToPipeline(buffer as unknown as AudioBuffer, 16000)
    // 8000→16000 上采样：长度翻倍。
    assert.equal(mono.length, 8)
    // 首采样 = (1+0)/2 = 0.5。
    assert.ok(Math.abs(mono[0]! - 0.5) < 1e-6)
  })

  it('seekToSample jumps to an offset and resumes streaming from there', async () => {
    // 2 秒 @ 16kHz，便于在中间位置跳转。
    const rate = 16000
    const data = new Float32Array(rate * 2)
    installDecodeMock([data], rate)

    const fakeTimers = installFakeTimers()
    const source = new FileAudioSource()
    const chunks: ArrayBuffer[] = []
    source.setCallbacks({
      onAudioChunk: (chunk) => chunks.push(chunk),
      onStateChange: () => undefined,
    })

    await source.start(makeWavFile('sample.wav'))
    assert.equal(source.sampleCount, rate * 2)
    fakeTimers.advance(300) // 播放 3 块
    assert.equal(chunks.length, 3)

    // 跳到 1 秒处（采样偏移 16000）。
    const ok = source.seekToSample(rate * 1)
    assert.equal(ok, true)
    assert.equal(source.currentSampleOffset, rate * 1)
    assert.equal(source.state, 'active')

    // 清空已发送块，推进 300ms 应再次产生 3 块。
    chunks.length = 0
    fakeTimers.advance(300)
    assert.equal(chunks.length, 3)

    // 越界偏移被夹紧到末尾。
    source.seekToSample(rate * 1000)
    assert.equal(source.currentSampleOffset, rate * 2 - 1)

    fakeTimers.restore()
  })
})
