import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'

import { decodeBase64, downmixToMono, resampleLinear, SystemAudioBridge } from './system-audio'
import type { SystemAudioFrame, SystemAudioCallbacks } from './system-audio'


/** 手动触发事件监听器的 mock。 */
class MockListener {
  listeners: Array<{ event: string; handler: (payload: { payload: SystemAudioFrame }) => void }> = []

  async listen(
    event: string,
    handler: (payload: { payload: SystemAudioFrame }) => void,
  ): Promise<() => void> {
    const entry = { event, handler }
    this.listeners.push(entry)
    return () => {
      const index = this.listeners.indexOf(entry)
      if (index >= 0) {
        this.listeners.splice(index, 1)
      }
    }
  }

  emit<T>(event: string, payload: T): void {
    for (const entry of this.listeners) {
      if (entry.event === event) {
        entry.handler({ payload: payload as SystemAudioFrame })
      }
    }
  }
}


/** 记录 Tauri command 调用的 mock invoke。 */
class MockInvoke {
  calls: string[] = []
  failWith: string | null = null

  async invoke<T>(command: string): Promise<T> {
    this.calls.push(command)
    if (this.failWith) {
      throw new Error(this.failWith)
    }
    return { available: true, capturing: command === 'start_system_audio' } as T
  }
}


function float32ToBase64(samples: number[]): string {
  const buffer = new ArrayBuffer(samples.length * 4)
  const view = new Float32Array(buffer)
  samples.forEach((value, index) => {
    view[index] = value
  })
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index])
  }
  return btoa(binary)
}


const HAD_ORIGINAL_TAURI = '__TAURI_INTERNALS__' in globalThis
const ORIGINAL_TAURI = (globalThis as Record<string, unknown>).__TAURI_INTERNALS__


function installTauriRuntime(): void {
  Object.defineProperty(globalThis, '__TAURI_INTERNALS__', {
    configurable: true,
    value: {},
  })
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: globalThis,
  })
}


function restoreTauriRuntime(): void {
  if (HAD_ORIGINAL_TAURI) {
    Object.defineProperty(globalThis, '__TAURI_INTERNALS__', {
      configurable: true,
      value: ORIGINAL_TAURI,
    })
  } else {
    delete (globalThis as Record<string, unknown>).__TAURI_INTERNALS__
  }
  delete (globalThis as Record<string, unknown>).window
}


function makeCallbacks(chunks: ArrayBuffer[], states: string[]): SystemAudioCallbacks {
  return {
    onStateChange: (state) => states.push(state),
    onAudioChunk: (chunk) => chunks.push(chunk),
  }
}


describe('decodeBase64', () => {
  it('decodes base64 strings to bytes', () => {
    const bytes = decodeBase64(btoa('hello'))
    assert.equal(String.fromCharCode(...bytes), 'hello')
  })

  it('returns empty bytes for empty input', () => {
    const bytes = decodeBase64('')
    assert.equal(bytes.byteLength, 0)
  })
})


describe('SystemAudioBridge', () => {
  afterEach(() => {
    restoreTauriRuntime()
  })

  it('reports unavailable outside a Tauri runtime', () => {
    const bridge = new SystemAudioBridge()
    assert.equal(bridge.state, 'unavailable')
  })

  it('listens for audio:data events and forwards decoded PCM bytes', async () => {
    installTauriRuntime()
    const listener = new MockListener()
    const invoke = new MockInvoke()
    const bridge = new SystemAudioBridge(listener.listen.bind(listener), invoke.invoke.bind(invoke))
    const chunks: ArrayBuffer[] = []
    const states: string[] = []

    bridge.setCallbacks(makeCallbacks(chunks, states))

    await bridge.start()
    assert.equal(bridge.state, 'capturing')
    assert.equal(states.includes('capturing'), true)
    assert.deepEqual(invoke.calls, ['start_system_audio'])

    const payload = float32ToBase64([0.1, 0.2, 0.3, 0.4])
    listener.emit<SystemAudioFrame>('audio:data', {
      data: payload,
      sampleRate: 16000, // 与管线采样率一致，仅下混不重采样
      channels: 1,
    })

    assert.equal(chunks.length, 1)
    assert.equal(chunks[0].byteLength, 16)
    const samples = new Float32Array(chunks[0])
    assert.ok(Math.abs(samples[0] - 0.1) < 1e-6, `sample[0] expected ~0.1, got ${samples[0]}`)
    assert.ok(Math.abs(samples[3] - 0.4) < 1e-6, `sample[3] expected ~0.4, got ${samples[3]}`)
    assert.equal(bridge.deviceSampleRate, 16000)
    assert.equal(bridge.deviceChannels, 1)
  })

  it('reports error when Rust capture start fails', async () => {
    installTauriRuntime()
    const listener = new MockListener()
    const invoke = new MockInvoke()
    invoke.failWith = 'loopback device not found'
    const bridge = new SystemAudioBridge(listener.listen.bind(listener), invoke.invoke.bind(invoke))
    const states: string[] = []

    bridge.setCallbacks(makeCallbacks([], states))
    await bridge.start()

    assert.equal(bridge.state, 'error')
    assert.equal(states.includes('error'), true)
  })

  it('downmixes stereo and resamples 48kHz to pipeline rate', async () => {
    installTauriRuntime()
    const listener = new MockListener()
    const invoke = new MockInvoke()
    const bridge = new SystemAudioBridge(listener.listen.bind(listener), invoke.invoke.bind(invoke))
    const chunks: ArrayBuffer[] = []

    bridge.setCallbacks(makeCallbacks(chunks, []))
    await bridge.start()

    // 4 帧立体声（L/R 交替）
    const stereo = [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]
    listener.emit<SystemAudioFrame>('audio:data', {
      data: float32ToBase64(stereo),
      sampleRate: 48000,
      channels: 2,
    })

    assert.equal(chunks.length, 1)
    const samples = new Float32Array(chunks[0])
    // 下混后 4 个样本全为 0.5；48k→16k 输出长度 = floor(4/3) = 1
    assert.equal(samples.length, 1)
    assert.ok(Math.abs(samples[0] - 0.5) < 1e-6, `sample expected ~0.5, got ${samples[0]}`)
    assert.equal(bridge.deviceSampleRate, 48000)
    assert.equal(bridge.deviceChannels, 2)
  })

  it('drops non-float32-aligned frames', async () => {
    installTauriRuntime()
    const listener = new MockListener()
    const invoke = new MockInvoke()
    const bridge = new SystemAudioBridge(listener.listen.bind(listener), invoke.invoke.bind(invoke))
    const chunks: ArrayBuffer[] = []

    bridge.setCallbacks(makeCallbacks(chunks, []))
    await bridge.start()

    listener.emit<SystemAudioFrame>('audio:data', {
      data: btoa('abc'), // 3 字节，非 4 对齐
      sampleRate: 48000,
      channels: 1,
    })

    assert.equal(chunks.length, 0)
  })

  it('stop invokes Rust stop and resets state', async () => {
    installTauriRuntime()
    const listener = new MockListener()
    const invoke = new MockInvoke()
    const bridge = new SystemAudioBridge(listener.listen.bind(listener), invoke.invoke.bind(invoke))
    bridge.setCallbacks(makeCallbacks([], []))
    await bridge.start()
    assert.equal(bridge.state, 'capturing')

    await bridge.stop()
    assert.equal(bridge.state, 'idle')
    assert.equal(bridge.deviceSampleRate, null)
    assert.equal(invoke.calls.includes('stop_system_audio'), true)
  })
})


describe('downmixToMono', () => {
  it('averages stereo channels per frame', () => {
    const stereo = new Float32Array([1, 3, 2, 4])
    const mono = downmixToMono(stereo, 2)
    assert.equal(mono.length, 2)
    assert.equal(mono[0], 2)
    assert.equal(mono[1], 3)
  })

  it('passes through mono input unchanged', () => {
    const mono = new Float32Array([0.1, 0.2])
    assert.equal(downmixToMono(mono, 1), mono)
  })
})


describe('resampleLinear', () => {
  it('resamples 48kHz to 16kHz at 1/3 length', () => {
    const input = new Float32Array([0, 1, 2, 3, 4, 5, 6, 7, 8])
    const output = resampleLinear(input, 48000, 16000)
    assert.equal(output.length, 3)
    assert.ok(Math.abs(output[0]) < 1e-6)
    assert.ok(Math.abs(output[2] - 6) < 1e-6)
  })

  it('passes through when rates match', () => {
    const input = new Float32Array([0.1, 0.2])
    assert.equal(resampleLinear(input, 16000, 16000), input)
  })

  it('returns empty for invalid rates', () => {
    assert.equal(resampleLinear(new Float32Array([1]), 0, 16000).length, 0)
  })
})
