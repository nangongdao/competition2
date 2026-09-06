import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import type { SubtitleEntry } from '../types'
import {
  buildSessionBundle,
  bundleTimestamp,
  type SessionBundleManifest,
} from './session-bundle'
import { buildZip, computeCrc32 } from './zip-writer'


const BASE_TIMESTAMP = Date.UTC(2026, 0, 1, 12, 0, 0)


function createEntry(overrides: Partial<SubtitleEntry> = {}): SubtitleEntry {
  return {
    segmentId: 'sess_1',
    sourceText: '',
    translatedText: '',
    isPartial: false,
    isRevised: false,
    timestamp: BASE_TIMESTAMP,
    ...overrides,
  }
}


describe('zip-writer (store method)', () => {
  it('produces a zip with EOCD signature and file count', () => {
    const bytes = buildZip([
      { name: 'a.txt', content: 'hello' },
      { name: 'b.txt', content: 'world' },
    ])
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)

    // EOCD 位于文件末尾（22 字节），签名 0x06054b50
    const eocdOffset = bytes.length - 22
    assert.equal(view.getUint32(eocdOffset, true), 0x06054b50)
    assert.equal(view.getUint16(eocdOffset + 8, true), 2) // 文件总数
    assert.equal(view.getUint16(eocdOffset + 10, true), 2)

    // 前两个本地文件头签名
    assert.equal(view.getUint32(0, true), 0x04034b50)
  })

  it('stores file content verbatim (no compression)', () => {
    const content = '你好，世界'
    const bytes = buildZip([{ name: 'f.txt', content }])
    const nameBytes = new TextEncoder().encode('f.txt')
    const localHeaderEnd = 30 + nameBytes.length
    const contentBytes = new TextEncoder().encode(content)
    const stored = bytes.subarray(localHeaderEnd, localHeaderEnd + contentBytes.length)
    assert.equal(new TextDecoder().decode(stored), content)
  })

  it('computes CRC-32 correctly against a known value', () => {
    // "123456789" 的标准 CRC-32 = 0xCBF43926
    const crc = computeCrc32(new TextEncoder().encode('123456789'))
    assert.equal(crc, 0xcbf43926)
  })

  it('embeds UTF-8 filenames with the UTF-8 flag set', () => {
    const bytes = buildZip([{ name: '字幕.srt', content: 'x' }])
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
    // 本地文件头 flag（offset 6, u16）应含 0x0800
    const flags = view.getUint16(6, true)
    assert.equal((flags & 0x0800) !== 0, true)
  })
})


describe('session bundle', () => {
  it('packages srt/vtt/txt/md and manifest for a real session', () => {
    const entries = [
      createEntry({ sourceText: 'Hello', translatedText: '你好', timestamp: BASE_TIMESTAMP }),
      createEntry({
        sourceText: 'World',
        translatedText: '世界',
        isRevised: true,
        timestamp: BASE_TIMESTAMP + 3000,
      }),
    ]
    const { blob, manifest } = buildSessionBundle({
      entries,
      diagnosticsText: 'session: ok\nlatency: 50ms',
      summaryMarkdown: '# 摘要',
      sessionLabel: 'demo',
    })

    assert.ok(blob.size > 0)
    assert.ok(manifest.subtitleCount >= 2)
    assert.ok(manifest.files.includes('subtitles.srt'))
    assert.ok(manifest.files.includes('subtitles.vtt'))
    assert.ok(manifest.files.includes('transcript.txt'))
    assert.ok(manifest.files.includes('notes.md'))
    assert.ok(manifest.files.includes('diagnostics.txt'))
    assert.ok(manifest.files.includes('summary.md'))
    assert.ok(manifest.files.includes('manifest.json'))
    assert.equal(manifest.hasDiagnostics, true)
    assert.equal(manifest.hasSummary, true)
    assert.equal(manifest.sessionLabel, 'demo')
  })

  it('omits optional diagnostics/summary when absent', () => {
    const { manifest } = buildSessionBundle({ entries: [createEntry()] })
    assert.equal(manifest.hasDiagnostics, false)
    assert.equal(manifest.hasSummary, false)
    assert.equal(manifest.files.includes('diagnostics.txt'), false)
    assert.equal(manifest.files.includes('summary.md'), false)
  })

  it('bundleTimestamp is filename-safe and zero-padded', () => {
    const date = new Date(2026, 0, 5, 9, 7, 3)
    assert.equal(bundleTimestamp(date), '20260105-090703')
  })

  it('manifest shape is complete', () => {
    const manifest: SessionBundleManifest = {
      generatedAt: '2026-01-01T00:00:00.000Z',
      subtitleCount: 1,
      sourceCount: 1,
      translatedCount: 1,
      revisedCount: 0,
      hasDiagnostics: false,
      hasSummary: false,
      sessionLabel: '',
      files: [],
    }
    assert.equal(manifest.files.length, 0)
  })
})
