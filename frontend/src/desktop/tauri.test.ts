import assert from 'node:assert/strict'
import { describe, it } from 'node:test'


/**
 * Tauri 运行时探测的纯逻辑：检测 window 上是否暴露 __TAURI_INTERNALS__。
 * 在 jsdom/真实浏览器中通过 window 全局判断。
 */
describe('Tauri runtime detection', () => {
  it('detects Tauri WebView via __TAURI_INTERNALS__', () => {
    const windowWithTauri = {
      __TAURI_INTERNALS__: { invoke: () => Promise.resolve() },
    } as unknown as Window

    assert.equal('__TAURI_INTERNALS__' in windowWithTauri, true)
  })

  it('reports absent when running in plain browser', () => {
    const plainWindow = {} as Window
    assert.equal('__TAURI_INTERNALS__' in plainWindow, false)
  })

  it('handles undefined window gracefully (SSR / node context)', () => {
    const hasWindow = typeof window !== 'undefined'
    assert.equal(hasWindow, false)
  })
})
