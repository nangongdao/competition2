import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import type { SubtitleEntry } from '../types'
import { formatSampleClock, subtitleToSeekSample } from './subtitle-seek'


const BASE = Date.UTC(2026, 0, 1, 12, 0, 0)


function entry(timestamp: number, text = 'x'): SubtitleEntry {
  return {
    segmentId: `s_${timestamp}`,
    sourceText: text,
    translatedText: text,
    isPartial: false,
    isRevised: false,
    timestamp,
  }
}


describe('subtitle seek (timeline jump)', () => {
  it('maps first entry to the very beginning of the file', () => {
    const entries = [entry(BASE), entry(BASE + 10000), entry(BASE + 20000)]
    assert.equal(subtitleToSeekSample(entries[0], entries, 16000 * 20), 0)
  })

  it('maps last entry to near the end of the file', () => {
    const entries = [entry(BASE), entry(BASE + 10000), entry(BASE + 20000)]
    const sample = subtitleToSeekSample(entries[2], entries, 16000 * 20)
    assert.equal(sample, 16000 * 20 - 1)
  })

  it('maps middle entry proportionally', () => {
    const entries = [entry(BASE), entry(BASE + 10000), entry(BASE + 20000)]
    // 中间条目在 50% 位置，总采样 16000*20=320000，一半=160000
    const sample = subtitleToSeekSample(entries[1], entries, 320000)
    assert.equal(sample, 160000)
  })

  it('returns null when no audio is loaded', () => {
    const entries = [entry(BASE), entry(BASE + 10000)]
    assert.equal(subtitleToSeekSample(entries[0], entries, 0), null)
  })

  it('returns 0 when timeline cannot be established', () => {
    assert.equal(subtitleToSeekSample(entry(BASE), [entry(BASE)], 100000), 0)
  })

  it('clamps out-of-range entries', () => {
    const entries = [entry(BASE), entry(BASE + 10000)]
    // 早于首条时间戳的字幕 → 夹到开头
    assert.equal(subtitleToSeekSample(entry(BASE - 5000), entries, 160000), 0)
    // 晚于末条 → 夹到末尾
    assert.equal(subtitleToSeekSample(entry(BASE + 50000), entries, 160000), 159999)
  })

  it('formats sample offsets as mm:ss', () => {
    assert.equal(formatSampleClock(0), '00:00')
    assert.equal(formatSampleClock(16000 * 65), '01:05')
    assert.equal(formatSampleClock(16000 * 125), '02:05')
  })
})
