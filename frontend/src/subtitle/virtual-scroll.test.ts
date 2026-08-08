import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { computeVirtualWindow } from './virtual-scroll'


describe('computeVirtualWindow', () => {
  it('handles empty list', () => {
    const window = computeVirtualWindow(0, 0, 300, 100)
    assert.deepEqual(window, { startIndex: 0, endIndex: 0, offsetY: 0, totalHeight: 0 })
  })

  it('handles non-positive item height', () => {
    const window = computeVirtualWindow(10, 0, 300, 0)
    assert.deepEqual(window, { startIndex: 0, endIndex: 0, offsetY: 0, totalHeight: 0 })
  })

  it('renders only the visible window at the top', () => {
    // 1000 条，viewport 300px，item 100px → 视口 3 条 + overscan 8*2
    const window = computeVirtualWindow(1000, 0, 300, 100)
    assert.equal(window.startIndex, 0)
    assert.equal(window.endIndex, 3 + 16)
    assert.equal(window.offsetY, 0)
    assert.equal(window.totalHeight, 1000 * 100)
  })

  it('shifts the window with scrollTop', () => {
    const window = computeVirtualWindow(1000, 2000, 300, 100)
    // scrollTop 2000 → 第 20 条起，减去 overscan 8 → start 12
    assert.equal(window.startIndex, 20 - 8)
    assert.ok(window.endIndex > window.startIndex)
    assert.equal(window.offsetY, window.startIndex * 100)
  })

  it('clamps endIndex to total', () => {
    const window = computeVirtualWindow(10, 900, 300, 100)
    assert.equal(window.endIndex, 10)
    assert.equal(window.totalHeight, 10 * 100)
  })

  it('never renders the full list for large datasets', () => {
    const window = computeVirtualWindow(5000, 0, 400, 120)
    assert.ok(window.endIndex - window.startIndex < 100)
  })
})
