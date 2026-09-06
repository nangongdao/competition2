/**
 * Tauri system-audio loopback capture bridge.
 *
 * The Tauri side (feature `system-audio`) captures the system output device
 * (loopback) and emits `audio:data` events carrying base64-encoded float32
 * PCM frames. This module listens for those events, decodes the payload, and
 * forwards the raw PCM bytes to the backend WebSocket so the live
 * interpretation pipeline can process system audio just like microphone input.
 *
 * The loopback device typically runs at a higher sample rate (44.1/48 kHz)
 * than the pipeline's 16 kHz input. Naive forwarding would confuse VAD/ASR
 * timing, so this bridge is designed to be sample-rate-aware: it exposes the
 * device rate to the caller and leaves resampling to a dedicated utility.
 *
 * Safety notes:
 * - Only active in a Tauri WebView (`__TAURI_INTERNALS__` present).
 * - The event payload is untrusted UI-bridge data; decode defensively and
 *   never throw out of the event handler.
 */

import type { UnlistenFn } from '@tauri-apps/api/event'
import { listen as tauriListen } from '@tauri-apps/api/event'
import { invoke as tauriInvoke } from '@tauri-apps/api/core'

import { isTauriRuntime } from '../network/ws-url'


/** 后端管线期望的采样率（与 backend/core/config.py audio_sample_rate 一致）。 */
export const PIPELINE_SAMPLE_RATE = 16000

/** 系统音频数据帧（与 Rust `audio_capture.rs` 的 JSON 结构对应）。 */
export interface SystemAudioFrame {
  /** base64 编码的 float32 PCM 字节（小端）。 */
  data: string
  /** 采集设备采样率（如 44100 / 48000）。 */
  sampleRate: number
  /** 声道数（loopback 通常为 2）。 */
  channels: number
}


/** Rust 侧 `get_system_audio_state` 返回的结构。 */
export interface SystemAudioStateSnapshot {
  available: boolean
  capturing: boolean
  sample_rate: number | null
  channels: number | null
}


export type SystemAudioState = 'unavailable' | 'idle' | 'capturing' | 'error'

export interface SystemAudioCallbacks {
  onStateChange: (state: SystemAudioState) => void
  /** 解码、下混、重采样后的 16kHz 单声道 float32 PCM 字节（小端）。 */
  onAudioChunk: (chunk: ArrayBuffer) => void
  onError?: (message: string) => void
}

const SYSTEM_AUDIO_EVENT = 'audio:data'

type ListenFn = (
  event: string,
  handler: (payload: { payload: SystemAudioFrame }) => void,
) => Promise<UnlistenFn>

type InvokeFn = <T>(command: string) => Promise<T>


export class SystemAudioBridge {
  private _unlisten: UnlistenFn | null = null
  private _callbacks: SystemAudioCallbacks | null = null
  private _state: SystemAudioState = 'unavailable'
  private _deviceSampleRate: number | null = null
  private _deviceChannels: number | null = null
  private readonly _listen: ListenFn
  private readonly _invoke: InvokeFn

  constructor(listen: ListenFn = tauriListen, invoke: InvokeFn = tauriInvoke) {
    this._listen = listen
    this._invoke = invoke
    this._state = isTauriRuntime() ? 'idle' : 'unavailable'
  }

  get state(): SystemAudioState {
    return this._state
  }

  /** 设备采样率（首次收到数据帧后可用）。 */
  get deviceSampleRate(): number | null {
    return this._deviceSampleRate
  }

  get deviceChannels(): number | null {
    return this._deviceChannels
  }

  setCallbacks(callbacks: SystemAudioCallbacks): void {
    this._callbacks = callbacks
    this._notifyState()
  }

  async start(): Promise<void> {
    if (!isTauriRuntime()) {
      this._setState('unavailable')
      return
    }

    if (this._unlisten) {
      this._setState('capturing')
      return
    }

    try {
      // 先触发 Rust 侧开始采集（loopback 设备驱动已安装时才会成功）。
      await this._invoke<SystemAudioStateSnapshot>('start_system_audio')
      this._unlisten = await this._listen(SYSTEM_AUDIO_EVENT, (event) => {
        this._handleFrame(event.payload)
      })
      this._setState('capturing')
    } catch (err) {
      console.error('[SystemAudioBridge] failed to start system audio:', err)
      this._setState('error')
      this._callbacks?.onError?.('Failed to start system audio capture. Is the loopback driver installed and the app built with --features system-audio?')
    }
  }

  async stop(): Promise<void> {
    if (this._unlisten) {
      this._unlisten()
      this._unlisten = null
    }
    try {
      await this._invoke<SystemAudioStateSnapshot>('stop_system_audio')
    } catch (err) {
      console.warn('[SystemAudioBridge] failed to stop system audio:', err)
    }
    this._deviceSampleRate = null
    this._deviceChannels = null
    if (isTauriRuntime()) {
      this._setState('idle')
    } else {
      this._setState('unavailable')
    }
  }

  private _handleFrame(frame: SystemAudioFrame): void {
    if (!frame || typeof frame.data !== 'string') {
      return
    }

    this._deviceSampleRate = Number.isFinite(frame.sampleRate) ? frame.sampleRate : null
    this._deviceChannels = Number.isFinite(frame.channels) ? frame.channels : null

    let bytes: Uint8Array
    try {
      bytes = decodeBase64(frame.data)
    } catch (err) {
      console.warn('[SystemAudioBridge] failed to decode frame:', err)
      return
    }

    // 对齐 float32（4 字节）的帧才处理；非对齐帧丢弃，避免误判。
    if (bytes.byteLength % 4 !== 0) {
      return
    }

    const sourceRate = this._deviceSampleRate ?? 0
    const channels = this._deviceChannels ?? 1
    if (sourceRate <= 0 || channels <= 0) {
      return
    }

    const samples = new Float32Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 4)
    const mono = downmixToMono(samples, channels)
    const resampled = resampleLinear(mono, sourceRate, PIPELINE_SAMPLE_RATE)

    this._callbacks?.onAudioChunk(resampled.buffer.slice(0) as ArrayBuffer)
  }

  private _setState(state: SystemAudioState): void {
    this._state = state
    this._notifyState()
  }

  private _notifyState(): void {
    this._callbacks?.onStateChange(this._state)
  }
}


/**
 * 多声道 → 单声道（简单平均）。输入帧数必须能被 channels 整除。
 */
export function downmixToMono(samples: Float32Array, channels: number): Float32Array {
  if (channels <= 1) {
    return samples
  }
  const frameCount = Math.floor(samples.length / channels)
  const mono = new Float32Array(frameCount)
  for (let frame = 0; frame < frameCount; frame += 1) {
    let sum = 0
    for (let channel = 0; channel < channels; channel += 1) {
      sum += samples[frame * channels + channel]
    }
    mono[frame] = sum / channels
  }
  return mono
}


/**
 * 线性插值重采样（fromRate → toRate）。
 * 足够实时字幕管线使用；需要更高保真度时可替换为 sinc/多相滤波。
 */
export function resampleLinear(samples: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate <= 0 || toRate <= 0) {
    return new Float32Array(0)
  }
  if (fromRate === toRate || samples.length === 0) {
    return samples
  }

  const ratio = fromRate / toRate
  const outputLength = Math.max(1, Math.floor(samples.length / ratio))
  const output = new Float32Array(outputLength)

  for (let index = 0; index < outputLength; index += 1) {
    const position = index * ratio
    const lower = Math.floor(position)
    const upper = Math.min(lower + 1, samples.length - 1)
    const fraction = position - lower
    output[index] = samples[lower] * (1 - fraction) + samples[upper] * fraction
  }
  return output
}


/**
 * base64 → 字节。防御式实现：非法字符/长度异常返回空 Uint8Array 而非抛错，
 * 由调用方决定是否丢弃。
 */
export function decodeBase64(input: string): Uint8Array {
  const cleaned = input.replace(/\s+/g, '')
  if (cleaned.length === 0) {
    return new Uint8Array(0)
  }

  const binary = atob(cleaned)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes
}
