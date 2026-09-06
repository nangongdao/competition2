/**
 * 音频源管理器。
 *
 * 统一四种输入源的创建与生命周期（ROADMAP V3.2）：
 * - `mic`：麦克风（getUserMedia）
 * - `tab`：标签页/窗口音频（getDisplayMedia）
 * - `system`：Tauri 系统音频 loopback
 * - `file`：本地音频文件
 *
 * AppController 通过本管理器获取/切换音频源，避免 if/else 散落在状态层。
 */

import type { AudioSourceType } from '../types'
import { AudioCapture } from './AudioCapture'
import { FileAudioSource } from './FileAudioSource'
import { SystemAudioBridge } from '../desktop/system-audio'

export type { AudioCaptureMode } from './AudioCapture'
export type { AudioFileSourceState } from './FileAudioSource'

/** 统一回调：各源状态变化都归一为字符串状态，供上层展示。 */
export type AudioSourceState = 'inactive' | 'active' | 'ended' | 'error' | 'unavailable'

export interface AudioSourceManagerCallbacks {
  onStateChange?: (source: AudioSourceType, state: AudioSourceState) => void
  onAudioChunk: (chunk: ArrayBuffer) => void
  onError?: (source: AudioSourceType, message: string) => void
  onEnded?: (source: AudioSourceType) => void
}

export class AudioSourceManager {
  private _audioCapture: AudioCapture
  private _systemAudioBridge: SystemAudioBridge
  private _fileSource: FileAudioSource
  private _callbacks: AudioSourceManagerCallbacks | null = null
  private _activeSource: AudioSourceType | null = null

  constructor() {
    this._audioCapture = new AudioCapture()
    this._systemAudioBridge = new SystemAudioBridge()
    this._fileSource = new FileAudioSource()

    this._audioCapture.setCallbacks({
      onStateChange: (state) => {
        this._notifyState('mic', state)
        this._notifyState('tab', state)
      },
      onAudioChunk: (chunk) => this._callbacks?.onAudioChunk(chunk),
    })

    this._systemAudioBridge.setCallbacks({
      onStateChange: (state) => {
        this._notifyState('system', normalizeSystemState(state))
      },
      onAudioChunk: (chunk) => this._callbacks?.onAudioChunk(chunk),
      onError: (message) => this._callbacks?.onError?.('system', message),
    })

    this._fileSource.setCallbacks({
      onStateChange: (state) => this._notifyState('file', state),
      onAudioChunk: (chunk) => this._callbacks?.onAudioChunk(chunk),
      onError: (message) => this._callbacks?.onError?.('file', message),
      onEnded: () => this._callbacks?.onEnded?.('file'),
    })
  }

  get activeSource(): AudioSourceType | null {
    return this._activeSource
  }

  get audioCapture(): AudioCapture {
    return this._audioCapture
  }

  get systemAudioBridge(): SystemAudioBridge {
    return this._systemAudioBridge
  }

  get fileSource(): FileAudioSource {
    return this._fileSource
  }

  setCallbacks(callbacks: AudioSourceManagerCallbacks): void {
    this._callbacks = callbacks
  }

  /** 切换到指定音频源（会先停止当前源）。 */
  async startSource(source: AudioSourceType, file?: File): Promise<boolean> {
    if (source === this._activeSource && this._isActive()) {
      return true
    }

    await this.stopAll()

    try {
      switch (source) {
        case 'mic':
          this._audioCapture.setMode('mic')
          await this._audioCapture.start()
          break
        case 'tab':
          this._audioCapture.setMode('tab')
          await this._audioCapture.start()
          break
        case 'system':
          await this._systemAudioBridge.start()
          break
        case 'file':
          if (!file) {
            this._callbacks?.onError?.('file', 'No audio file provided')
            return false
          }
          return await this._fileSource.start(file)
      }
      this._activeSource = source
      return true
    } catch (error) {
      this._activeSource = null
      const message = error instanceof Error ? error.message : String(error)
      this._callbacks?.onError?.(source, message)
      return false
    }
  }

  /**
   * 停止所有音频源。
   *
   * @param keepFileSample 为 true 时保留已加载文件样本（AppController.stop 时
   *   调用，允许用户不重新选文件直接再点开始）；切换音频源时应传 false 完全释放。
   */
  async stopAll(keepFileSample = false): Promise<void> {
    if (this._audioCapture.state === 'active') {
      this._audioCapture.stop()
    }
    if (this._systemAudioBridge.state === 'capturing') {
      await this._systemAudioBridge.stop()
    }
    if (this._fileSource.state === 'active' || this._fileSource.state === 'ended') {
      if (keepFileSample) {
        this._fileSource.stop()
      } else {
        this._fileSource.reset()
      }
    }
    this._activeSource = null
  }

  /** 当前是否有任一源在活跃采集。 */
  private _isActive(): boolean {
    return (
      this._audioCapture.state === 'active' ||
      this._systemAudioBridge.state === 'capturing' ||
      this._fileSource.state === 'active'
    )
  }

  private _notifyState(source: AudioSourceType, state: AudioSourceState): void {
    this._callbacks?.onStateChange?.(source, state)
  }
}

/** 归一化 SystemAudioBridge 状态到统一状态。 */
function normalizeSystemState(state: 'unavailable' | 'idle' | 'capturing' | 'error'): AudioSourceState {
  switch (state) {
    case 'capturing':
      return 'active'
    case 'unavailable':
      return 'unavailable'
    case 'idle':
      return 'inactive'
    case 'error':
      return 'error'
  }
}
