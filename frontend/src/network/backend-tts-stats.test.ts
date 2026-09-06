import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  EMPTY_BACKEND_TTS_STATS,
  diskCacheHitRatePct,
  fetchBackendTtsStats,
  normalizeBackendTtsStats,
} from './backend-tts-stats'

describe('backend-tts-stats', () => {
  it('normalizes null/undefined to empty stats', () => {
    assert.deepEqual(normalizeBackendTtsStats(null), { ...EMPTY_BACKEND_TTS_STATS })
    assert.deepEqual(normalizeBackendTtsStats(undefined), { ...EMPTY_BACKEND_TTS_STATS })
    assert.deepEqual(normalizeBackendTtsStats('nope'), { ...EMPTY_BACKEND_TTS_STATS })
  })

  it('coerces malformed numeric fields to 0', () => {
    const stats = normalizeBackendTtsStats({
      engine: 'edge',
      enabled: true,
      cacheSize: 'NaN',
      synthesized: null,
      failed: 'x',
      active: 5,
    })
    assert.equal(stats.engine, 'edge')
    assert.equal(stats.enabled, true)
    assert.equal(stats.cacheSize, 0)
    assert.equal(stats.synthesized, 0)
    assert.equal(stats.failed, 0)
    assert.equal(stats.active, 5)
  })

  it('preserves valid numeric fields', () => {
    const stats = normalizeBackendTtsStats({
      engine: 'edge',
      voice: 'zh-CN-XiaoxiaoNeural',
      rate: '+0%',
      cacheSize: 10,
      cacheHits: 3,
      diskHits: 7,
      diskCacheFiles: 12,
      synthesized: 5,
      failed: 1,
      active: 2,
      enabled: true,
    })
    assert.equal(stats.cacheSize, 10)
    assert.equal(stats.cacheHits, 3)
    assert.equal(stats.diskHits, 7)
    assert.equal(stats.diskCacheFiles, 12)
    assert.equal(stats.synthesized, 5)
    assert.equal(stats.failed, 1)
    assert.equal(stats.active, 2)
  })

  it('returns empty stats when the fetch is not available', async () => {
    const result = await fetchBackendTtsStats(undefined as never)
    assert.equal(result.success, false)
    assert.deepEqual(result.stats, { ...EMPTY_BACKEND_TTS_STATS })
  })

  it('returns empty stats on non-ok response', async () => {
    const fetcher = async () =>
      ({ ok: false, json: async () => ({}) }) as Response
    const result = await fetchBackendTtsStats(fetcher)
    assert.equal(result.success, false)
    assert.deepEqual(result.stats, { ...EMPTY_BACKEND_TTS_STATS })
  })

  it('parses a successful stats payload', async () => {
    const fetcher = async () =>
      ({
        ok: true,
        json: async () => ({
          success: true,
          stats: {
            engine: 'edge',
            enabled: true,
            voice: 'zh-CN-XiaoxiaoNeural',
            rate: '+0%',
            cacheSize: 4,
            cacheHits: 2,
            diskHits: 1,
            diskCacheFiles: 9,
            synthesized: 3,
            failed: 0,
            active: 1,
          },
        }),
      }) as Response
    const result = await fetchBackendTtsStats(fetcher)
    assert.equal(result.success, true)
    assert.equal(result.stats.cacheHits, 2)
    assert.equal(result.stats.diskCacheFiles, 9)
    assert.equal(result.stats.synthesized, 3)
  })

  it('computes disk cache hit rate percentage', () => {
    const stats = normalizeBackendTtsStats({
      diskHits: 3,
      synthesized: 7,
    })
    assert.equal(diskCacheHitRatePct(stats), 30)
    assert.equal(diskCacheHitRatePct(EMPTY_BACKEND_TTS_STATS), 0)
  })
})
