import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { DEFAULT_SUBTITLE_STYLE } from './subtitle-style'
import {
  buildSubtitleStyleCssVars,
  isSubtitlePosition,
  normalizeSubtitleStyle,
  parseSubtitleStyleCssVars,
} from './subtitle-style'


describe('subtitle style config helpers', () => {
  it('normalizes arbitrary input to valid config with clamped ranges', () => {
    const normalized = normalizeSubtitleStyle({
      fontSize: 999,
      fontColor: 'not-a-color',
      backgroundColor: '#112233',
      backgroundOpacity: -0.5,
      position: 'top',
    })

    assert.equal(normalized.fontSize, 36)
    assert.equal(normalized.fontColor, DEFAULT_SUBTITLE_STYLE.fontColor)
    assert.equal(normalized.backgroundColor, '#112233')
    assert.equal(normalized.backgroundOpacity, 0)
    assert.equal(normalized.position, 'top')
  })

  it('falls back to defaults for empty / malformed input', () => {
    assert.deepEqual(normalizeSubtitleStyle(null), DEFAULT_SUBTITLE_STYLE)
    assert.deepEqual(normalizeSubtitleStyle('nope'), DEFAULT_SUBTITLE_STYLE)
    assert.deepEqual(normalizeSubtitleStyle({}), DEFAULT_SUBTITLE_STYLE)
  })

  it('keeps valid values untouched', () => {
    const style = {
      fontSize: 24,
      fontColor: '#abcdef',
      backgroundColor: '#010203',
      backgroundOpacity: 0.4,
      position: 'middle' as const,
    }
    assert.deepEqual(normalizeSubtitleStyle(style), style)
  })

  it('builds css vars with rgba background', () => {
    const vars = buildSubtitleStyleCssVars({
      fontSize: 26,
      fontColor: '#ffffff',
      backgroundColor: '#000000',
      backgroundOpacity: 0.5,
      position: 'top',
    })

    assert.match(vars, /--subtitle-font-size: 26px/)
    assert.match(vars, /--subtitle-font-color: #ffffff/)
    assert.match(vars, /--subtitle-background: rgba\(0, 0, 0, 0.50\)/)
    assert.match(vars, /--subtitle-position: top/)
  })

  it('round-trips css vars back to the original style', () => {
    const style = {
      fontSize: 30,
      fontColor: '#f0f0f0',
      backgroundColor: '#0b0f1a',
      backgroundOpacity: 0.82,
      position: 'bottom' as const,
    }

    const vars = buildSubtitleStyleCssVars(style)
    assert.deepEqual(parseSubtitleStyleCssVars(vars), style)
  })

  it('parses only known subtitle positions', () => {
    assert.equal(isSubtitlePosition('bottom'), true)
    assert.equal(isSubtitlePosition('middle'), true)
    assert.equal(isSubtitlePosition('top'), true)
    assert.equal(isSubtitlePosition('left'), false)
    assert.equal(isSubtitlePosition(undefined), false)
  })
})
