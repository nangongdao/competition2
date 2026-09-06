import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  DEFAULT_SHORTCUTS,
  matchKeyboardEvent,
  matchShortcut,
  nextSubtitleMode,
} from './shortcuts'


describe('shortcuts', () => {
  it('matches Ctrl+Space to toggle_translation', () => {
    const action = matchKeyboardEvent(
      { key: ' ', ctrlKey: true, metaKey: false, shiftKey: false, altKey: false },
      DEFAULT_SHORTCUTS,
    )
    assert.equal(action, 'toggle_translation')
  })

  it('treats Command (meta) as ctrl on macOS', () => {
    const action = matchKeyboardEvent(
      { key: '1', ctrlKey: false, metaKey: true, shiftKey: false, altKey: false },
      DEFAULT_SHORTCUTS,
    )
    assert.equal(action, 'cycle_subtitle_mode')
  })

  it('matches Ctrl+H to toggle_history', () => {
    const action = matchShortcut(
      DEFAULT_SHORTCUTS,
      'h',
      { ctrl: true, shift: false, alt: false },
    )
    assert.equal(action, 'toggle_history')
  })

  it('returns null when no modifier is pressed (plain typing)', () => {
    const action = matchKeyboardEvent(
      { key: 'h', ctrlKey: false, metaKey: false, shiftKey: false, altKey: false },
      DEFAULT_SHORTCUTS,
    )
    assert.equal(action, null)
  })

  it('returns null when modifiers mismatch', () => {
    const action = matchShortcut(
      DEFAULT_SHORTCUTS,
      'h',
      { ctrl: false, shift: false, alt: true },
    )
    assert.equal(action, null)
  })

  it('cycles subtitle modes in order', () => {
    assert.equal(nextSubtitleMode('bilingual'), 'translation_only')
    assert.equal(nextSubtitleMode('translation_only'), 'source_only')
    assert.equal(nextSubtitleMode('source_only'), 'bilingual')
    // 未知模式回退到默认双语。
    assert.equal(nextSubtitleMode('unknown'), 'bilingual')
  })
})
