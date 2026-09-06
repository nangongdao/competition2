import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  BACKEND_TTS_DELAY_PRESETS,
  BACKEND_TTS_RATE_PRESETS,
  BACKEND_TTS_VOICES,
  BACKEND_TTS_VOLUME_PRESETS,
  backendTtsVolumeToPlayback,
  DEFAULT_BACKEND_TTS_CONFIG,
  normalizeBackendTtsDelay,
  normalizeBackendTtsRate,
  normalizeBackendTtsVoice,
  normalizeBackendTtsVolume,
} from './backend-tts-config'


describe('backend-tts-config', () => {
  it('exposes a non-empty Chinese voice list with unique values', () => {
    assert.ok(BACKEND_TTS_VOICES.length > 0)
    const values = new Set(BACKEND_TTS_VOICES.map((entry) => entry.value))
    assert.equal(values.size, BACKEND_TTS_VOICES.length)
  })

  it('exposes rate presets covering slow, normal and fast', () => {
    const values = BACKEND_TTS_RATE_PRESETS.map((preset) => preset.value)
    assert.ok(values.includes('+0%'))
    assert.ok(values.includes('-10%'))
    assert.ok(values.includes('+10%'))
  })

  it('keeps a known voice unchanged', () => {
    assert.equal(
      normalizeBackendTtsVoice('zh-CN-YunxiNeural'),
      'zh-CN-YunxiNeural',
    )
  })

  it('falls back to default voice for unknown values', () => {
    assert.equal(
      normalizeBackendTtsVoice('xx-YY-UnknownNeural'),
      DEFAULT_BACKEND_TTS_CONFIG.voice,
    )
  })

  it('keeps a known rate unchanged', () => {
    assert.equal(normalizeBackendTtsRate('+10%'), '+10%')
  })

  it('falls back to default rate for unknown values', () => {
    assert.equal(
      normalizeBackendTtsRate('+3%'),
      DEFAULT_BACKEND_TTS_CONFIG.rate,
    )
  })

  it('exposes volume presets covering quiet, normal and loud', () => {
    const values = BACKEND_TTS_VOLUME_PRESETS.map((preset) => preset.value)
    assert.ok(values.includes('+0%'))
    assert.ok(values.includes('-25%'))
    assert.ok(values.includes('+25%'))
  })

  it('keeps a known volume unchanged', () => {
    assert.equal(normalizeBackendTtsVolume('+25%'), '+25%')
  })

  it('falls back to default volume for unknown values', () => {
    assert.equal(
      normalizeBackendTtsVolume('loud'),
      DEFAULT_BACKEND_TTS_CONFIG.volume,
    )
  })

  it('maps +0% volume to a playback factor of 1.0', () => {
    assert.equal(backendTtsVolumeToPlayback('+0%'), 1)
  })

  it('maps a negative volume to a quieter playback factor', () => {
    assert.ok(backendTtsVolumeToPlayback('-50%') < 1)
    assert.equal(backendTtsVolumeToPlayback('-50%'), 0.5)
  })

  it('clamps a loud volume to the 0.0-1.0 playback range', () => {
    assert.ok(backendTtsVolumeToPlayback('+50%') <= 1)
  })

  it('maps a quiet volume to at least 0.2 to avoid silence', () => {
    assert.ok(backendTtsVolumeToPlayback('-100%') >= 0.2)
  })

  it('falls back to 1.0 for unparseable volume strings', () => {
    assert.equal(backendTtsVolumeToPlayback('nonsense'), 1)
    assert.equal(backendTtsVolumeToPlayback(''), 1)
  })

  it('exposes delay presets covering immediate and paced options', () => {
    assert.ok(BACKEND_TTS_DELAY_PRESETS.length >= 3)
    assert.ok(BACKEND_TTS_DELAY_PRESETS.some((p) => p.value === 0), 'immediate playback must be offered')
    assert.ok(
      BACKEND_TTS_DELAY_PRESETS.every((p) => Number.isFinite(p.value) && p.value >= 0),
      'all delay presets must be non-negative finite numbers',
    )
    const values = new Set(BACKEND_TTS_DELAY_PRESETS.map((p) => p.value))
    assert.equal(values.size, BACKEND_TTS_DELAY_PRESETS.length)
  })

  it('keeps a known delay unchanged', () => {
    assert.equal(normalizeBackendTtsDelay(600), 600)
    assert.equal(normalizeBackendTtsDelay(0), 0)
  })

  it('falls back to default delay for unknown values', () => {
    assert.equal(normalizeBackendTtsDelay(12345), DEFAULT_BACKEND_TTS_CONFIG.delay)
    assert.equal(normalizeBackendTtsDelay(-500), DEFAULT_BACKEND_TTS_CONFIG.delay)
    assert.equal(normalizeBackendTtsDelay(Number.NaN), DEFAULT_BACKEND_TTS_CONFIG.delay)
  })

  it('default config includes zero delay (紧跟字幕)', () => {
    assert.equal(DEFAULT_BACKEND_TTS_CONFIG.delay, 0)
  })
})
