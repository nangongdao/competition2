import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import type { SubtitleEntry } from '../types'
import {
  formatLearningNotesMarkdown,
  formatPlainTranscript,
  formatSrtSubtitles,
  formatVttSubtitles,
  hasExportableSubtitles,
} from './subtitle-export'


const BASE_TIMESTAMP = Date.UTC(2026, 0, 1, 12, 0, 0)


describe('subtitle export formatting', () => {
  it('detects exportable subtitle entries', () => {
    assert.equal(hasExportableSubtitles([
      createEntry({ sourceText: ' ', translatedText: '' }),
    ]), false)

    assert.equal(hasExportableSubtitles([
      createEntry({ sourceText: '', translatedText: 'Ni hao' }),
    ]), true)
  })

  it('formats plain transcript with revision labels', () => {
    const transcript = formatPlainTranscript([
      createEntry({
        sourceText: 'Hello',
        translatedText: 'Ni hao',
        isRevised: true,
        revisionReason: 'translation_correction',
      }),
    ])

    assert.match(transcript, /1\./)
    assert.match(transcript, /\[revised:translation_correction\]/)
    assert.match(transcript, /EN: Hello/)
    assert.match(transcript, /ZH: Ni hao/)
  })

  it('formats SRT cues with non-overlapping relative timings', () => {
    const srt = formatSrtSubtitles([
      createEntry({
        segmentId: 'seg-1',
        sourceText: 'Hello   world',
        translatedText: 'Ni hao world',
      }),
      createEntry({
        segmentId: 'seg-2',
        sourceText: '',
        translatedText: 'Second line',
        isRevised: true,
        revisionReason: 'asr_correction',
        timestamp: BASE_TIMESTAMP + 1000,
      }),
    ])

    assert.equal(srt, [
      '1',
      '00:00:00,000 --> 00:00:00,920',
      'EN: Hello world',
      'ZH: Ni hao world',
      '',
      '2',
      '00:00:01,000 --> 00:00:03,600',
      'ZH: Second line',
      '[ASR revised]',
    ].join('\n'))
  })

  it('formats VTT cues with header and millisecond separators', () => {
    const vtt = formatVttSubtitles([
      createEntry({
        sourceText: 'Hello',
        translatedText: 'Ni hao',
      }),
    ])

    assert.equal(vtt, [
      'WEBVTT',
      '',
      '00:00:00.000 --> 00:00:02.600',
      'EN: Hello',
      'ZH: Ni hao',
    ].join('\n'))
    assert.equal(formatVttSubtitles([]), 'WEBVTT')
  })

  it('formats learning notes with counts and revision metadata', () => {
    const markdown = formatLearningNotesMarkdown([
      createEntry({
        sourceText: 'Hello',
        translatedText: 'Ni hao',
      }),
      createEntry({
        segmentId: 'seg-2',
        sourceText: '',
        translatedText: 'Second line',
        isRevised: true,
        revisionReason: 'translation_correction',
        revisedAt: BASE_TIMESTAMP + 1300,
      }),
    ])

    assert.match(markdown, /# AI Interpreter Learning Notes/)
    assert.match(markdown, /Entries: 2/)
    assert.match(markdown, /Source lines: 1/)
    assert.match(markdown, /Translated lines: 2/)
    assert.match(markdown, /Revised lines: 1/)
    assert.match(markdown, /- Source: Hello/)
    assert.match(markdown, /- Translation: Second line/)
    assert.match(markdown, /- Revision: Translation revised at/)
  })
})


function createEntry(overrides: Partial<SubtitleEntry> = {}): SubtitleEntry {
  return {
    segmentId: 'seg-1',
    sourceText: 'Hello',
    translatedText: 'Ni hao',
    isPartial: false,
    isRevised: false,
    timestamp: BASE_TIMESTAMP,
    ...overrides,
  }
}
