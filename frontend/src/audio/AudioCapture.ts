/**
 * 音频捕获模块
 *
 * 使用浏览器 Web Audio API 捕获系统音频（getDisplayMedia），
 * 将音频流转换为 16kHz/mono/float32 的 PCM 格式，
 * 通过 WebSocket 发送到后端。
 */

/** 音频捕获配置 */
const AUDIO_CONFIG = {
  sampleRate: 16000,
  channelCount: 1,
  chunkDurationMs: 100, // 每 100ms 发送一个音频块
  bufferSize: 2048,
} as const

export type AudioCaptureState = 'inactive' | 'active' | 'error'

export interface AudioCaptureCallbacks {
  onStateChange: (state: AudioCaptureState) => void
  onAudioChunk: (chunk: ArrayBuffer) => void
}

/**
 * 系统音频捕获器
 *
 * 流程：
 * 1. getDisplayMedia 获取系统/标签页音频
 * 2. AudioContext.createMediaStreamSource 创建音频源
 * 3. ScriptProcessorNode 处理音频（重采样到 16kHz mono）
 * 4. 编码为 PCM Float32 并通过回调输出
 */
export class AudioCapture {
  private _stream: MediaStream | null = null
  private _audioContext: AudioContext | null = null
  private _processor: ScriptProcessorNode | null = null
  private _source: MediaStreamAudioSourceNode | null = null
  private _state: AudioCaptureState = 'inactive'
  private _callbacks: AudioCaptureCallbacks | null = null
  private _chunkTimer: ReturnType<typeof setInterval> | null = null
  private _chunkBuffer: Float32Array[] = []

  /** 获取当前状态 */
  get state(): AudioCaptureState {
    return this._state
  }

  /** 注册回调 */
  setCallbacks(callbacks: AudioCaptureCallbacks): void {
    this._callbacks = callbacks
  }

  /** 开始捕获系统音频 */
  async start(): Promise<void> {
    try {
      // 1. 获取显示媒体（含系统音频）
      this._stream = await navigator.mediaDevices.getDisplayMedia({
        video: true, // 必须包含 video 才能使用 getDisplayMedia
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      })

      // 获取音频轨道
      const audioTrack = this._stream.getAudioTracks()[0]
      if (!audioTrack) {
        throw new Error('No audio track available. Please enable "Share audio".')
      }

      // 2. 创建 AudioContext
      this._audioContext = new AudioContext({
        sampleRate: AUDIO_CONFIG.sampleRate,
      })

      // 3. 创建音频源
      this._source = this._audioContext.createMediaStreamSource(this._stream)

      // 4. 创建处理器（重采样 + 缓冲）
      this._processor = this._audioContext.createScriptProcessor(
        AUDIO_CONFIG.bufferSize,
        AUDIO_CONFIG.channelCount,
        AUDIO_CONFIG.channelCount,
      )

      this._processor.onaudioprocess = (event) => {
        const inputData = event.inputBuffer.getChannelData(0)
        // 复制数据（因为 inputData 会被复用）
        const chunk = new Float32Array(inputData.length)
        chunk.set(inputData)
        this._chunkBuffer.push(chunk)
      }

      // 5. 连接音频图
      this._source.connect(this._processor)
      this._processor.connect(this._audioContext.destination)

      // 6. 定期发送音频块
      this._chunkTimer = setInterval(() => {
        this._flushBuffer()
      }, AUDIO_CONFIG.chunkDurationMs)

      this._state = 'active'
      this._callbacks?.onStateChange(this._state)

      console.log('[AudioCapture] Started successfully')
    } catch (err) {
      this._state = 'error'
      this._callbacks?.onStateChange(this._state)
      console.error('[AudioCapture] Failed to start:', err)
      throw err
    }
  }

  /** 停止捕获 */
  stop(): void {
    // 停止定时器
    if (this._chunkTimer) {
      clearInterval(this._chunkTimer)
      this._chunkTimer = null
    }

    // 断开音频图
    if (this._processor) {
      this._processor.disconnect()
      this._processor = null
    }
    if (this._source) {
      this._source.disconnect()
      this._source = null
    }

    // 关闭 AudioContext
    if (this._audioContext && this._audioContext.state !== 'closed') {
      this._audioContext.close()
      this._audioContext = null
    }

    // 停止媒体流
    if (this._stream) {
      this._stream.getTracks().forEach((track) => track.stop())
      this._stream = null
    }

    // 清空缓冲区
    this._chunkBuffer = []

    this._state = 'inactive'
    this._callbacks?.onStateChange(this._state)

    console.log('[AudioCapture] Stopped')
  }

  /** 将缓冲区中的数据打包发送 */
  private _flushBuffer(): void {
    if (this._chunkBuffer.length === 0) return

    // 合并所有缓冲区块
    const totalLength = this._chunkBuffer.reduce((sum, c) => sum + c.length, 0)
    const combined = new Float32Array(totalLength)
    let offset = 0
    for (const chunk of this._chunkBuffer) {
      combined.set(chunk, offset)
      offset += chunk.length
    }

    // 清空缓冲区
    this._chunkBuffer = []

    // 发送
    this._callbacks?.onAudioChunk(combined.buffer)
  }
}