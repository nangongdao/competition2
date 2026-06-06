/**
 * Browser audio capture for the live interpretation pipeline.
 *
 * The primary path uses AudioWorklet so capture work stays off the main UI
 * thread. Browsers that do not support AudioWorklet automatically fall back to
 * ScriptProcessorNode to keep the current demo flow usable.
 */

const AUDIO_CONFIG = {
  sampleRate: 16000,
  channelCount: 1,
  chunkDurationMs: 100,
  bufferSize: 2048,
  workletModuleUrl: new URL(
    `${import.meta.env.BASE_URL}audio-capture-worklet.js`,
    window.location.href,
  ).toString(),
} as const

const WORKLET_PROCESSOR_NAME = 'audio-capture-processor'
const WORKLET_MESSAGE_TYPE = 'audio-chunk'

type CaptureBackend = 'audio-worklet' | 'script-processor'

export type AudioCaptureState = 'inactive' | 'active' | 'error'

export interface AudioCaptureCallbacks {
  onStateChange: (state: AudioCaptureState) => void
  onAudioChunk: (chunk: ArrayBuffer) => void
}

interface AudioWorkletChunkMessage {
  type: typeof WORKLET_MESSAGE_TYPE
  samples: Float32Array
}

export class AudioCapture {
  private _stream: MediaStream | null = null
  private _audioContext: AudioContext | null = null
  private _workletNode: AudioWorkletNode | null = null
  private _scriptProcessor: ScriptProcessorNode | null = null
  private _source: MediaStreamAudioSourceNode | null = null
  private _state: AudioCaptureState = 'inactive'
  private _callbacks: AudioCaptureCallbacks | null = null
  private _chunkTimer: ReturnType<typeof setInterval> | null = null
  private _chunkBuffer: Float32Array[] = []
  private _captureBackend: CaptureBackend | null = null

  private readonly _handleAudioTrackEnded = (): void => {
    if (this._state === 'active') {
      this.stop()
    }
  }

  get state(): AudioCaptureState {
    return this._state
  }

  get captureBackend(): CaptureBackend | null {
    return this._captureBackend
  }

  setCallbacks(callbacks: AudioCaptureCallbacks): void {
    this._callbacks = callbacks
  }

  async start(): Promise<void> {
    if (this._state === 'active') {
      return
    }

    try {
      this._stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      })

      const audioTrack = this._stream.getAudioTracks()[0]
      if (!audioTrack) {
        throw new Error('No audio track available. Please enable "Share audio".')
      }
      audioTrack.addEventListener('ended', this._handleAudioTrackEnded)

      this._audioContext = new AudioContext({
        sampleRate: AUDIO_CONFIG.sampleRate,
      })
      this._source = this._audioContext.createMediaStreamSource(this._stream)

      const isWorkletStarted = await this._tryStartAudioWorklet()
      if (!isWorkletStarted) {
        this._startScriptProcessor()
      }

      this._chunkTimer = setInterval(() => {
        this._flushBuffer()
      }, AUDIO_CONFIG.chunkDurationMs)

      this._setState('active')
    } catch (error) {
      this._cleanupResources()
      this._setState('error')
      console.error('[AudioCapture] Failed to start:', error)
      throw error
    }
  }

  stop(): void {
    this._cleanupResources()
    this._setState('inactive')
  }

  private async _tryStartAudioWorklet(): Promise<boolean> {
    const audioContext = this._audioContext
    const source = this._source

    if (
      !audioContext ||
      !source ||
      !audioContext.audioWorklet ||
      typeof AudioWorkletNode === 'undefined'
    ) {
      return false
    }

    try {
      await audioContext.audioWorklet.addModule(AUDIO_CONFIG.workletModuleUrl)
      const workletNode = new AudioWorkletNode(audioContext, WORKLET_PROCESSOR_NAME, {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [AUDIO_CONFIG.channelCount],
      })

      workletNode.port.onmessage = (event: MessageEvent<unknown>) => {
        const message = parseAudioWorkletChunkMessage(event.data)
        if (!message) {
          return
        }
        this._chunkBuffer.push(message.samples)
      }

      source.connect(workletNode)
      workletNode.connect(audioContext.destination)

      this._workletNode = workletNode
      this._captureBackend = 'audio-worklet'
      return true
    } catch (error) {
      this._disconnectWorklet()
      console.warn(
        '[AudioCapture] AudioWorklet unavailable; falling back to ScriptProcessorNode',
        error,
      )
      return false
    }
  }

  private _startScriptProcessor(): void {
    const audioContext = this._audioContext
    const source = this._source

    if (!audioContext || !source) {
      throw new Error('Audio graph is not ready.')
    }

    const processor = audioContext.createScriptProcessor(
      AUDIO_CONFIG.bufferSize,
      AUDIO_CONFIG.channelCount,
      AUDIO_CONFIG.channelCount,
    )

    processor.onaudioprocess = (event) => {
      const inputData = event.inputBuffer.getChannelData(0)
      const chunk = new Float32Array(inputData.length)
      chunk.set(inputData)
      this._chunkBuffer.push(chunk)
    }

    source.connect(processor)
    processor.connect(audioContext.destination)

    this._scriptProcessor = processor
    this._captureBackend = 'script-processor'
  }

  private _flushBuffer(): void {
    if (this._chunkBuffer.length === 0) {
      return
    }

    const totalLength = this._chunkBuffer.reduce((sum, chunk) => sum + chunk.length, 0)
    const combined = new Float32Array(totalLength)
    let offset = 0

    for (const chunk of this._chunkBuffer) {
      combined.set(chunk, offset)
      offset += chunk.length
    }

    this._chunkBuffer = []
    this._callbacks?.onAudioChunk(combined.buffer)
  }

  private _cleanupResources(): void {
    if (this._chunkTimer) {
      clearInterval(this._chunkTimer)
      this._chunkTimer = null
    }

    this._disconnectWorklet()
    this._disconnectScriptProcessor()

    if (this._source) {
      this._source.disconnect()
      this._source = null
    }

    if (this._audioContext && this._audioContext.state !== 'closed') {
      void this._audioContext.close()
    }
    this._audioContext = null

    if (this._stream) {
      for (const track of this._stream.getAudioTracks()) {
        track.removeEventListener('ended', this._handleAudioTrackEnded)
      }
      for (const track of this._stream.getTracks()) {
        track.stop()
      }
      this._stream = null
    }

    this._chunkBuffer = []
    this._captureBackend = null
  }

  private _disconnectWorklet(): void {
    if (!this._workletNode) {
      return
    }

    this._workletNode.port.onmessage = null
    this._workletNode.disconnect()
    this._workletNode = null
  }

  private _disconnectScriptProcessor(): void {
    if (!this._scriptProcessor) {
      return
    }

    this._scriptProcessor.onaudioprocess = null
    this._scriptProcessor.disconnect()
    this._scriptProcessor = null
  }

  private _setState(state: AudioCaptureState): void {
    this._state = state
    this._callbacks?.onStateChange(this._state)
  }
}

function parseAudioWorkletChunkMessage(data: unknown): AudioWorkletChunkMessage | null {
  if (typeof data !== 'object' || data === null) {
    return null
  }

  const message = data as { type?: unknown; samples?: unknown }
  if (
    message.type !== WORKLET_MESSAGE_TYPE ||
    !(message.samples instanceof Float32Array)
  ) {
    return null
  }

  return {
    type: WORKLET_MESSAGE_TYPE,
    samples: message.samples,
  }
}
