import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, it } from 'node:test'

import type { AudioCaptureState } from './AudioCapture'


class MockMediaStreamTrack extends EventTarget {
  readonly kind: string
  addEndedListenerCalls = 0
  removeEndedListenerCalls = 0
  stopCalls = 0

  constructor(kind: string) {
    super()
    this.kind = kind
  }

  override addEventListener(
    type: string,
    callback: EventListenerOrEventListenerObject | null,
    options?: boolean | AddEventListenerOptions,
  ): void {
    if (type === 'ended') {
      this.addEndedListenerCalls += 1
    }
    super.addEventListener(type, callback, options)
  }

  override removeEventListener(
    type: string,
    callback: EventListenerOrEventListenerObject | null,
    options?: boolean | EventListenerOptions,
  ): void {
    if (type === 'ended') {
      this.removeEndedListenerCalls += 1
    }
    super.removeEventListener(type, callback, options)
  }

  stop(): void {
    this.stopCalls += 1
  }
}


class MockMediaStream {
  constructor(
    private readonly audioTracks: MockMediaStreamTrack[],
    private readonly extraTracks: MockMediaStreamTrack[] = [],
  ) {}

  getAudioTracks(): MockMediaStreamTrack[] {
    return [...this.audioTracks]
  }

  getTracks(): MockMediaStreamTrack[] {
    return [...this.audioTracks, ...this.extraTracks]
  }
}


class MockAudioNode {
  connectCalls = 0
  disconnectCalls = 0

  connect(): MockAudioNode {
    this.connectCalls += 1
    return this
  }

  disconnect(): void {
    this.disconnectCalls += 1
  }
}


class MockScriptProcessorNode extends MockAudioNode {
  onaudioprocess: ((event: AudioProcessingEvent) => void) | null = null

  emitAudioProcess(samples: Float32Array): void {
    const event = {
      inputBuffer: {
        getChannelData: () => samples,
      },
    } as unknown as AudioProcessingEvent

    this.onaudioprocess?.(event)
  }
}


class MockAudioWorklet {
  readonly addModuleCalls: string[] = []

  constructor(private readonly shouldRejectModule: boolean) {}

  async addModule(url: string): Promise<void> {
    this.addModuleCalls.push(url)
    if (this.shouldRejectModule) {
      throw new Error('worklet unavailable')
    }
  }
}


class MockAudioContext {
  static instances: MockAudioContext[] = []

  readonly audioWorklet?: MockAudioWorklet
  readonly destination = new MockAudioNode()
  readonly scriptProcessors: MockScriptProcessorNode[] = []
  state: AudioContextState = 'running'
  closeCalls = 0

  constructor() {
    if (audioWorkletMode !== 'missing') {
      this.audioWorklet = new MockAudioWorklet(audioWorkletMode === 'reject')
    }
    MockAudioContext.instances.push(this)
  }

  createMediaStreamSource(_stream: MediaStream): MockAudioNode {
    return new MockAudioNode()
  }

  createScriptProcessor(): MockScriptProcessorNode {
    const processor = new MockScriptProcessorNode()
    this.scriptProcessors.push(processor)
    return processor
  }

  async close(): Promise<void> {
    this.closeCalls += 1
    this.state = 'closed'
  }
}


class MockMessagePort {
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null

  dispatch(data: unknown): void {
    this.onmessage?.(new MessageEvent('message', { data }))
  }
}


class MockAudioWorkletNode extends MockAudioNode {
  static instances: MockAudioWorkletNode[] = []

  readonly port = new MockMessagePort()

  constructor(
    _context: BaseAudioContext,
    readonly processorName: string,
    _options?: AudioWorkletNodeOptions,
  ) {
    super()
    MockAudioWorkletNode.instances.push(this)
  }
}


type AudioWorkletMode = 'available' | 'reject' | 'missing'

let audioWorkletMode: AudioWorkletMode = 'available'

const HAD_ORIGINAL_NAVIGATOR = 'navigator' in globalThis
const ORIGINAL_NAVIGATOR = globalThis.navigator
const HAD_ORIGINAL_WINDOW = 'window' in globalThis
const ORIGINAL_WINDOW = globalThis.window
const HAD_ORIGINAL_AUDIO_CONTEXT = 'AudioContext' in globalThis
const ORIGINAL_AUDIO_CONTEXT = globalThis.AudioContext
const HAD_ORIGINAL_AUDIO_WORKLET_NODE = 'AudioWorkletNode' in globalThis
const ORIGINAL_AUDIO_WORKLET_NODE = globalThis.AudioWorkletNode
const ORIGINAL_CONSOLE_WARN = console.warn
const ORIGINAL_CONSOLE_ERROR = console.error


describe('AudioCapture', () => {
  beforeEach(() => {
    audioWorkletMode = 'available'
    MockAudioContext.instances = []
    MockAudioWorkletNode.instances = []

    Object.defineProperty(console, 'warn', {
      configurable: true,
      value: () => undefined,
      writable: true,
    })
    Object.defineProperty(console, 'error', {
      configurable: true,
      value: () => undefined,
      writable: true,
    })
  })

  afterEach(() => {
    restoreBrowserMocks()
  })

  it('starts with AudioWorklet and flushes validated Float32 chunks', async () => {
    const audioTrack = new MockMediaStreamTrack('audio')
    installBrowserMocks(new MockMediaStream([audioTrack]), 'available')
    const { AudioCapture } = await import('./AudioCapture')
    const capture = new AudioCapture()
    const states: AudioCaptureState[] = []
    const chunks: ArrayBuffer[] = []

    capture.setCallbacks({
      onStateChange: (state) => states.push(state),
      onAudioChunk: (chunk) => chunks.push(chunk),
    })

    await capture.start()
    assert.equal(capture.state, 'active')
    assert.equal(capture.captureBackend, 'audio-worklet')
    assert.deepEqual(states, ['active'])
    assert.equal(audioTrack.addEndedListenerCalls, 1)

    const workletNode = latestWorkletNode()
    workletNode.port.dispatch({ type: 'not-audio', samples: new Float32Array([9]) })
    workletNode.port.dispatch({ type: 'audio-chunk', samples: [1, 2, 3] })
    workletNode.port.dispatch({
      type: 'audio-chunk',
      samples: new Float32Array([0.25, -0.5]),
    })

    await waitFor(() => chunks.length === 1)
    assert.deepEqual(Array.from(new Float32Array(readFirstChunk(chunks))), [0.25, -0.5])

    capture.stop()
    assert.equal(capture.state, 'inactive')
    assert.equal(capture.captureBackend, null)
    assert.equal(audioTrack.removeEndedListenerCalls, 1)
    assert.equal(audioTrack.stopCalls, 1)
  })

  it('falls back to ScriptProcessor when worklet module loading fails', async () => {
    installBrowserMocks(new MockMediaStream([new MockMediaStreamTrack('audio')]), 'reject')
    const { AudioCapture } = await import('./AudioCapture')
    const capture = new AudioCapture()
    const chunks: ArrayBuffer[] = []

    capture.setCallbacks({
      onStateChange: () => undefined,
      onAudioChunk: (chunk) => chunks.push(chunk),
    })

    await capture.start()
    assert.equal(capture.captureBackend, 'script-processor')
    assert.equal(MockAudioWorkletNode.instances.length, 0)

    latestAudioContext().scriptProcessors[0]?.emitAudioProcess(new Float32Array([1, 2]))

    await waitFor(() => chunks.length === 1)
    assert.deepEqual(Array.from(new Float32Array(readFirstChunk(chunks))), [1, 2])

    capture.stop()
  })

  it('reports an error and stops shared tracks when no audio track is available', async () => {
    const videoTrack = new MockMediaStreamTrack('video')
    installBrowserMocks(new MockMediaStream([], [videoTrack]), 'available')
    const { AudioCapture } = await import('./AudioCapture')
    const capture = new AudioCapture()
    const states: AudioCaptureState[] = []

    capture.setCallbacks({
      onStateChange: (state) => states.push(state),
      onAudioChunk: () => undefined,
    })

    await assert.rejects(
      () => capture.start(),
      /Share audio/,
    )

    assert.equal(capture.state, 'error')
    assert.equal(capture.captureBackend, null)
    assert.deepEqual(states, ['error'])
    assert.equal(videoTrack.stopCalls, 1)
  })
})


function installBrowserMocks(stream: MockMediaStream, workletMode: AudioWorkletMode): void {
  audioWorkletMode = workletMode

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      location: {
        href: 'http://localhost/app/',
      },
    },
    writable: true,
  })
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      mediaDevices: {
        getDisplayMedia: async () => stream as unknown as MediaStream,
      },
    },
    writable: true,
  })
  Object.defineProperty(globalThis, 'AudioContext', {
    configurable: true,
    value: MockAudioContext,
    writable: true,
  })
  Object.defineProperty(globalThis, 'AudioWorkletNode', {
    configurable: true,
    value: MockAudioWorkletNode,
    writable: true,
  })
}


function restoreBrowserMocks(): void {
  restoreGlobalProperty('navigator', HAD_ORIGINAL_NAVIGATOR, ORIGINAL_NAVIGATOR)
  restoreGlobalProperty('window', HAD_ORIGINAL_WINDOW, ORIGINAL_WINDOW)
  restoreGlobalProperty('AudioContext', HAD_ORIGINAL_AUDIO_CONTEXT, ORIGINAL_AUDIO_CONTEXT)
  restoreGlobalProperty(
    'AudioWorkletNode',
    HAD_ORIGINAL_AUDIO_WORKLET_NODE,
    ORIGINAL_AUDIO_WORKLET_NODE,
  )

  Object.defineProperty(console, 'warn', {
    configurable: true,
    value: ORIGINAL_CONSOLE_WARN,
    writable: true,
  })
  Object.defineProperty(console, 'error', {
    configurable: true,
    value: ORIGINAL_CONSOLE_ERROR,
    writable: true,
  })
}


function restoreGlobalProperty(
  propertyName: string,
  hadOriginal: boolean,
  originalValue: unknown,
): void {
  if (hadOriginal) {
    Object.defineProperty(globalThis, propertyName, {
      configurable: true,
      value: originalValue,
      writable: true,
    })
    return
  }

  Reflect.deleteProperty(globalThis, propertyName)
}


function latestWorkletNode(): MockAudioWorkletNode {
  const node = MockAudioWorkletNode.instances[MockAudioWorkletNode.instances.length - 1]
  if (!node) {
    throw new Error('Expected an AudioWorkletNode instance.')
  }
  return node
}


function latestAudioContext(): MockAudioContext {
  const context = MockAudioContext.instances[MockAudioContext.instances.length - 1]
  if (!context) {
    throw new Error('Expected an AudioContext instance.')
  }
  return context
}


async function waitFor(predicate: () => boolean): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) {
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 20))
  }

  throw new Error('Timed out waiting for condition.')
}


function readFirstChunk(chunks: ArrayBuffer[]): ArrayBuffer {
  const chunk = chunks[0]
  if (!chunk) {
    throw new Error('Expected an audio chunk.')
  }
  return chunk
}
