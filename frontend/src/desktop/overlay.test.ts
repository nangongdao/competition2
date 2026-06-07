import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import type { SubtitleEntry } from '../types'
import {
  createDesktopOverlaySnapshot,
  getSubtitleDisplayState,
  getVisibleOverlayEntries,
} from './overlay'


describe('desktop subtitle overlay helpers', () => {
  it('filters empty subtitle entries and keeps the latest visible window', () => {
    const entries = [
      createEntry({ segmentId: 'empty', sourceText: ' ', translatedText: '' }),
      ...Array.from({ length: 8 }, (_, index) =>
        createEntry({
          segmentId: `segment-${index}`,
          sourceText: `source ${index}`,
          translatedText: `translation ${index}`,
        }),
      ),
    ]

    const visibleEntries = getVisibleOverlayEntries(entries)

    assert.equal(visibleEntries.length, 6)
    assert.deepEqual(
      visibleEntries.map((entry) => entry.segmentId),
      ['segment-2', 'segment-3', 'segment-4', 'segment-5', 'segment-6', 'segment-7'],
    )
  })

  it('creates cloneable snapshots without mutating source entries', () => {
    const entries = [createEntry({ segmentId: 'a', translatedText: '你好' })]
    const snapshot = createDesktopOverlaySnapshot(entries, 'translation_only', 123)

    assert.equal(snapshot.updatedAt, 123)
    assert.equal(snapshot.mode, 'translation_only')
    assert.notEqual(snapshot.entries[0], entries[0])

    entries[0].translatedText = 'changed'
    assert.equal(snapshot.entries[0]?.translatedText, '你好')
  })

  it('derives display state from subtitle mode and revision metadata', () => {
    const entry = createEntry({
      sourceText: 'hello',
      translatedText: '你好',
      isRevised: true,
    })

    const translationOnly = getSubtitleDisplayState(entry, 'translation_only')
    const sourceOnly = getSubtitleDisplayState(entry, 'source_only')

    assert.equal(translationOnly.showSource, false)
    assert.equal(translationOnly.showTranslated, true)
    assert.match(translationOnly.className, /only-translated/)
    assert.match(translationOnly.className, /revised/)

    assert.equal(sourceOnly.showSource, true)
    assert.equal(sourceOnly.showTranslated, false)
    assert.match(sourceOnly.className, /only-source/)
  })
})


function createEntry(overrides: Partial<SubtitleEntry> = {}): SubtitleEntry {
  return {
    segmentId: 'segment',
    sourceText: 'hello',
    translatedText: '你好',
    isPartial: false,
    isRevised: false,
    timestamp: 1000,
    ...overrides,
  }
}

