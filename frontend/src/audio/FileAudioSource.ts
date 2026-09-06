/**
 * 音频文件输入源。
 *
 * 选择本地音频文件（WAV/MP3 等浏览器可解码格式），离线解码为 16kHz
 * 单声道 PCM 后，按实时节奏（100ms/块）逐块送入翻译管线——让录播课程、
 * 本地音频文件也能像实时流一样逐句翻译（ROADMAP V3.2 AC-V3.4）。
 *
 * 设计要点：
 * - 不修改原始文件；解码在内存中进行。
 * - 采用「拉模式」定时器按真实时间推进，而非全量一次性发送，
 *   保证后端 VAD/ASR 的时序与真实播放一致。
 * - 播放节奏按文件时长映射：文件总时长 = 总采样数 / 目标采样率。
 */

import type { AudioCaptureBackend } from '../types'

/** 后端管线期望的采样率（与 AudioCapture / SystemAudioBridge 对齐）。 */
const PIPELINE_SAMPLE_RATE = 16000

/** 每块时长（ms），与 AudioCapture 的 chunkDurationMs 一致。 */
const CHUNK_DURATION_MS = 100

/** 每块采样数。 */
const CHUNK_SAMPLES = (PIPELINE_SAMPLE_RATE * CHUNK_DURATION_MS) / 1000

export type AudioFileSourceState = 'inactive' | 'active' | 'ended' | 'error'

export interface AudioFileSourceCallbacks {
  onStateChange: (state: AudioFileSourceState) => void
  onAudioChunk: (chunk: ArrayBuffer) => void
  /** 文件加载失败/解码失败时回调错误信息。 */
  onError?: (message: string) => void
  /** 文件播放到末尾时回调。 */
  onEnded?: () => void
}

export interface AudioFileSourceOptions {
  /** 是否在文件播完后自动停止并复位（默认 true）。 */
  loop?: boolean
}

/**
 * 将任意采样率/声道数的 AudioBuffer 重采样为 16kHz 单声道。
 * 采用线性插值，足够实时字幕管线使用。
 */
export function resampleToPipeline(
  buffer: AudioBuffer,
  targetRate = PIPELINE_SAMPLE_RATE,
): Float32Array {
  const channels = buffer.numberOfChannels
  const sourceRate = buffer.sampleRate
  const sourceLength = buffer.length

  if (sourceRate <= 0 || sourceLength === 0) {
    return new Float32Array(0)
  }

  // 多声道下混为单声道。
  let mono: Float32Array
  if (channels === 1) {
    mono = buffer.getChannelData(0)
  } else {
    mono = new Float32Array(sourceLength)
    for (let channel = 0; channel < channels; channel += 1) {
      const data = buffer.getChannelData(channel)
      for (let i = 0; i < sourceLength; i += 1) {
        mono[i] += data[i]
      }
    }
    for (let i = 0; i < sourceLength; i += 1) {
      mono[i] /= channels
    }
  }

  if (sourceRate === targetRate) {
    return mono
  }

  // 线性插值重采样。
  const ratio = sourceRate / targetRate
  const outputLength = Math.max(1, Math.floor(sourceLength / ratio))
  const output = new Float32Array(outputLength)
  for (let index = 0; index < outputLength; index += 1) {
    const position = index * ratio
    const lower = Math.floor(position)
    const upper = Math.min(lower + 1, sourceLength - 1)
    const fraction = position - lower
    output[index] = mono[lower] * (1 - fraction) + mono[upper] * fraction
  }
  return output
}

export class FileAudioSource {
  private _state: AudioFileSourceState = 'inactive'
  private _callbacks: AudioFileSourceCallbacks | null = null
  private _samples: Float32Array | null = null
  private _timer: ReturnType<typeof setInterval> | null = null
  private _offset = 0
  private _fileName = ''
  private _captureBackend: AudioCaptureBackend | null = null
  private readonly _options: AudioFileSourceOptions

  constructor(options: AudioFileSourceOptions = {}) {
    this._options = options
  }

  get state(): AudioFileSourceState {
    return this._state
  }

  get fileName(): string {
    return this._fileName
  }

  /** 已加载音频的 16kHz 采样数（加载前为 0）。 */
  get sampleCount(): number {
    return this._samples?.length ?? 0
  }

  get captureBackend(): AudioCaptureBackend | null {
    return this._captureBackend
  }

  setCallbacks(callbacks: AudioFileSourceCallbacks): void {
    this._callbacks = callbacks
  }

  /**
   * 加载并开始播放音频文件。
   *
   * @param file 浏览器可解码的音频文件（WAV/MP3/OGG/FLAC 等）。
   *   不传 file 时重播已加载的样本（stop 后再次 start 无需重新选文件）。
   * @returns 成功返回 true；解码失败返回 false 并回调 onError。
   */
  async start(file?: File): Promise<boolean> {
    if (this._state === 'active') {
      return false
    }

    if (file) {
      try {
        const decoded = await decodeAudioFile(file)
        this._samples = resampleToPipeline(decoded)
      } catch (error) {
        this._setState('error')
        const message = error instanceof Error ? error.message : 'Failed to decode audio file'
        this._callbacks?.onError?.(message)
        return false
      }

      if (this._samples.length === 0) {
        this._setState('error')
        this._callbacks?.onError?.('Audio file is empty or unreadable')
        return false
      }

      this._fileName = file.name
    }

    if (!this._samples || this._samples.length === 0) {
      this._setState('error')
      this._callbacks?.onError?.('No audio file loaded')
      return false
    }

    this._offset = 0
    this._captureBackend = 'audio-worklet'
    this._startTimer()
    this._setState('active')
    return true
  }

  /** 停止播放但保留已加载样本，允许再次 start 重播。 */
  stop(): void {
    this._stopTimer()
    this._offset = 0
    this._captureBackend = null
    if (this._state === 'ended') {
      this._setState('inactive')
    } else if (this._state === 'active') {
      this._setState('inactive')
    }
  }

  /**
   * 第二梯队-方向 5：跳转到指定采样位置并继续播放（回看跳转）。
   *
   * 从 `sampleOffset` 处重新开始以实时节奏逐块送入管线，
   * 用于「点击历史字幕 → 跳到对应音频位置回听」的场景。
   *
   * @param sampleOffset 目标采样偏移（0 ~ sampleCount）。越界会被夹紧。
   * @returns 是否成功发起跳转（未加载样本或已停止时返回 false）。
   */
  seekToSample(sampleOffset: number): boolean {
    if (!this._samples || this._samples.length === 0) {
      return false
    }

    const clamped = Math.max(0, Math.min(Math.floor(sampleOffset), this._samples.length - 1))
    this._stopTimer()
    this._offset = clamped
    this._captureBackend = 'audio-worklet'
    this._startTimer()
    if (this._state === 'inactive' || this._state === 'ended') {
      this._setState('active')
    }
    return true
  }

  /** 当前播放位置（16kHz 采样偏移）。未播放时为 0。 */
  get currentSampleOffset(): number {
    return this._offset
  }

  /** 完全释放已加载样本（切换音频源时调用）。 */
  reset(): void {
    this._stopTimer()
    this._offset = 0
    this._samples = null
    this._fileName = ''
    this._captureBackend = null
    this._setState('inactive')
  }

  private _startTimer(): void {
    if (this._timer) {
      return
    }
    this._timer = setInterval(() => {
      this._tick()
    }, CHUNK_DURATION_MS)
  }

  private _stopTimer(): void {
    if (this._timer) {
      clearInterval(this._timer)
      this._timer = null
    }
  }

  private _tick(): void {
    const samples = this._samples
    if (!samples || this._state !== 'active') {
      return
    }

    const remaining = samples.length - this._offset
    if (remaining <= 0) {
      // 文件播放完毕。
      this._stopTimer()
      if (this._options.loop) {
        this._offset = 0
        this._startTimer()
      } else {
        this._setState('ended')
        this._callbacks?.onEnded?.()
      }
      return
    }

    const count = Math.min(CHUNK_SAMPLES, remaining)
    const chunk = new Float32Array(count)
    chunk.set(samples.subarray(this._offset, this._offset + count))
    this._offset += count

    // 每个 100ms 块一个 ArrayBuffer（小端 float32 PCM），与实时采集路径一致。
    this._emitChunk(chunk.buffer as ArrayBuffer)
  }

  private _emitChunk(buffer: ArrayBuffer): void {
    this._callbacks?.onAudioChunk(buffer)
  }

  private _setState(state: AudioFileSourceState): void {
    this._state = state
    this._callbacks?.onStateChange(state)
  }
}

/**
 * 将音频文件解码为 AudioBuffer。
 * 优先使用 OfflineAudioContext.decodeAudioData；兼容旧式 AudioContext.decodeAudioData。
 */
async function decodeAudioFile(file: File): Promise<AudioBuffer> {
  const arrayBuffer = await file.arrayBuffer()
  return decodeAudioData(arrayBuffer)
}

async function decodeAudioData(arrayBuffer: ArrayBuffer): Promise<AudioBuffer> {
  // 优先使用 OfflineAudioContext（无需音频输出设备）；降级到 AudioContext。
  const OfflineCtx = typeof OfflineAudioContext !== 'undefined' ? OfflineAudioContext : undefined
  if (OfflineCtx) {
    const context = new OfflineCtx(1, 1, PIPELINE_SAMPLE_RATE)
    try {
      return await context.decodeAudioData(arrayBuffer)
    } catch (error) {
      throw new Error(`decodeAudioData failed: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const AudioCtx = typeof AudioContext !== 'undefined' ? AudioContext : undefined
  if (!AudioCtx) {
    throw new Error('Web Audio API is unavailable in this browser')
  }
  const context = new AudioCtx()
  try {
    return await context.decodeAudioData(arrayBuffer)
  } finally {
    void context.close()
  }
}
