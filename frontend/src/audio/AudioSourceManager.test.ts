import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'

import { AudioSourceManager } from './AudioSourceManager'
import type { AudioSourceType } from '../types'


/** 记录回调调用的辅助。 */
class CallbackRecorder {
  chunks: ArrayBuffer[] = []
  states: Array<{ source: AudioSourceType; state: string }> = []
  errors: Array<{ source: AudioSourceType; message: string }> = []
  ended: AudioSourceType[] = []
}

describe('AudioSourceManager', () => {
  afterEach(() => {
    // 清理所有全局 mock，避免污染后续测试。
    delete (globalThis as Record<string, unknown>).navigator
  })

  it('routes mic chunks through the unified callback', async () => {
    // 模拟 getUserMedia 返回带音频轨的流。
    class MockTrack {
      readonly kind: string
      stopCalls = 0
      constructor(kind: string) {
        this.kind = kind
      }
      addEventListener(): void {}
      removeEventListener(): void {}
      stop(): void {
        this.stopCalls += 1
      }
    }
    const audioTrack = new MockTrack('audio')
    const videoTrack = new MockTrack('video')
    const stream = {
      getAudioTracks: () => [audioTrack],
      getTracks: () => [audioTrack, videoTrack],
    } as unknown as MediaStream

    const originalNavigator = (globalThis as Record<string, unknown>).navigator
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: {
        mediaDevices: {
          getUserMedia: async () => stream,
          getDisplayMedia: async () => stream,
        },
      },
      writable: true,
    })
    // AudioContext mock：最小实现，让 AudioCapture 走 ScriptProcessor 快速路径。
    class MockAudioContext {
      readonly destination = { connect: () => undefined }
      state = 'running'
      audioWorklet = undefined
      createMediaStreamSource() {
        return { connect: () => undefined, disconnect: () => undefined }
      }
      createScriptProcessor() {
        return { onaudioprocess: null, connect: () => undefined, disconnect: () => undefined }
      }
      async close(): Promise<void> {
        this.state = 'closed'
      }
    }
    const originalAudioContext = (globalThis as Record<string, unknown>).AudioContext
    Object.defineProperty(globalThis, 'AudioContext', {
      configurable: true,
      value: MockAudioContext,
      writable: true,
    })

    const manager = new AudioSourceManager()
    const recorder = new CallbackRecorder()
    manager.setCallbacks({
      onAudioChunk: (chunk) => recorder.chunks.push(chunk),
      onStateChange: (source, state) => recorder.states.push({ source, state }),
      onError: (source, message) => recorder.errors.push({ source, message }),
      onEnded: (source) => recorder.ended.push(source),
    })

    const ok = await manager.startSource('mic')
    assert.equal(ok, true)
    assert.equal(manager.activeSource, 'mic')

    await manager.stopAll()
    assert.equal(manager.activeSource, null)
    assert.equal(recorder.errors.length, 0)

    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: originalNavigator,
      writable: true,
    })
    Object.defineProperty(globalThis, 'AudioContext', {
      configurable: true,
      value: originalAudioContext,
      writable: true,
    })
  })

  it('switching to a file source without a file reports an error', async () => {
    const manager = new AudioSourceManager()
    const recorder = new CallbackRecorder()
    manager.setCallbacks({
      onAudioChunk: () => undefined,
      onError: (source, message) => recorder.errors.push({ source, message }),
    })

    const ok = await manager.startSource('file')
    assert.equal(ok, false)
    assert.equal(manager.activeSource, null)
    assert.equal(recorder.errors.length, 1)
    assert.equal(recorder.errors[0]?.source, 'file')
  })

  it('stopAll is safe when nothing is active', async () => {
    const manager = new AudioSourceManager()
    await manager.stopAll()
    assert.equal(manager.activeSource, null)
  })
})
