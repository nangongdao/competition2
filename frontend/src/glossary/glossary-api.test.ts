import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  addGlossaryEntry,
  clearGlossary,
  clearTranslationMemory,
  createApiUrlFromWebSocketUrl,
  deleteGlossaryEntry,
  fetchGlossary,
  fetchTranslationMemoryEntries,
  fetchTranslationMemoryStats,
  importGlossary,
  resolveApiEndpoint,
} from './glossary-api'


describe('resolveApiEndpoint', () => {
  it('derives endpoint from runtime websocket URL', () => {
    const endpoint = resolveApiEndpoint(
      '/glossary',
      '?wsUrl=ws%3A%2F%2F127.0.0.1%3A49321%2Fapi%2Fv1%2Fws%2Ftranslate',
    )
    assert.equal(endpoint, 'http://127.0.0.1:49321/api/v1/glossary')
  })

  it('falls back to the default backend host and port', () => {
    const endpoint = resolveApiEndpoint('/translation-memory')
    assert.ok(endpoint.startsWith('http://127.0.0.1:8000/api/v1/translation-memory'))
  })

  it('normalizes paths without leading slash', () => {
    const endpoint = resolveApiEndpoint('glossary')
    assert.ok(endpoint.endsWith('/api/v1/glossary'))
  })
})

describe('createApiUrlFromWebSocketUrl — 安全校验', () => {
  const maliciousUrls = [
    'ws://attacker.example.com/collect',
    'ws://169.254.169.254/',
    'http://127.0.0.1:8000/api',
    'javascript:alert(1)',
  ]

  for (const url of maliciousUrls) {
    it(`拒绝 ${url}`, () => {
      assert.equal(createApiUrlFromWebSocketUrl(url, '/glossary'), null)
    })
  }

  it('accepts loopback hosts', () => {
    assert.ok(createApiUrlFromWebSocketUrl('ws://127.0.0.1:8000/api/v1/ws/translate', '/glossary'))
    assert.ok(createApiUrlFromWebSocketUrl('ws://localhost:8000/api/v1/ws/translate', '/glossary'))
  })
})

describe('glossary REST client', () => {
  function jsonResponse(body: unknown, ok = true): Response {
    return {
      ok,
      status: ok ? 200 : 500,
      json: async () => body,
    } as Response
  }

  it('fetchGlossary returns snapshot on success', async () => {
    const snapshot = {
      path: '/tmp/glossary.local.json',
      size: 2,
      entries: [
        { id: 'k8s', source: 'K8s', target: 'Kubernetes', keep_original: false },
        { id: 'llm', source: 'LLM', target: '大语言模型', keep_original: false },
      ],
    }
    const result = await fetchGlossary({
      fetcher: async () => jsonResponse({ success: true, reason: 'ok', glossary: snapshot }),
    })
    assert.deepEqual(result, snapshot)
  })

  it('fetchGlossary returns null on failure', async () => {
    const result = await fetchGlossary({
      fetcher: async () => jsonResponse({ success: false, reason: 'no service' }),
    })
    assert.equal(result, null)
  })

  it('addGlossaryEntry posts the entry', async () => {
    let postedBody = ''
    const entry = { id: 'k8s', source: 'K8s', target: 'Kubernetes', keep_original: false }
    const result = await addGlossaryEntry(
      { source: 'K8s', target: 'Kubernetes' },
      {
        fetcher: async (_input, init) => {
          postedBody = String(init?.body ?? '')
          return jsonResponse({ success: true, reason: 'ok', entry })
        },
      },
    )
    assert.deepEqual(result, entry)
    assert.deepEqual(JSON.parse(postedBody), { source: 'K8s', target: 'Kubernetes' })
  })

  it('deleteGlossaryEntry returns success flag', async () => {
    const ok = await deleteGlossaryEntry('k8s', {
      fetcher: async () => jsonResponse({ success: true, reason: 'deleted' }),
    })
    assert.equal(ok, true)
  })

  it('clearGlossary returns cleared count', async () => {
    const cleared = await clearGlossary({
      fetcher: async () => jsonResponse({ success: true, reason: 'ok', cleared: 5 }),
    })
    assert.equal(cleared, 5)
  })

  it('importGlossary sends CSV for .csv files', async () => {
    let postedBody = ''
    const imported = await importGlossary(
      'terms.csv',
      'ML,机器学习\nLLM,大语言模型',
      {
        fetcher: async (_input, init) => {
          postedBody = String(init?.body ?? '')
          return jsonResponse({ success: true, reason: 'ok', imported: 2 })
        },
      },
    )
    assert.equal(imported, 2)
    const parsed = JSON.parse(postedBody)
    assert.ok(typeof parsed.csv === 'string')
    assert.ok(parsed.csv.includes('ML,机器学习'))
  })

  it('importGlossary sends entries for .json files', async () => {
    let postedBody = ''
    const imported = await importGlossary(
      'terms.json',
      '[{"source":"ML","target":"机器学习"}]',
      {
        fetcher: async (_input, init) => {
          postedBody = String(init?.body ?? '')
          return jsonResponse({ success: true, reason: 'ok', imported: 1 })
        },
      },
    )
    assert.equal(imported, 1)
    const parsed = JSON.parse(postedBody)
    assert.deepEqual(parsed.entries, [{ source: 'ML', target: '机器学习' }])
  })
})

describe('translation memory client', () => {
  function jsonResponse(body: unknown): Response {
    return {
      ok: true,
      status: 200,
      json: async () => body,
    } as Response
  }

  it('fetchTranslationMemoryStats returns stats', async () => {
    const stats = {
      size: 12,
      hits: 8,
      misses: 4,
      written: 12,
      sessions: ['sess-1'],
      threshold: 0.82,
      store: {
        persisted: true,
        size: 120,
        pairs: 2,
        by_pair: { 'en->zh-CN': 100, 'zh-CN->en': 20 },
      },
    }
    const result = await fetchTranslationMemoryStats({
      fetcher: async () => jsonResponse({ success: true, reason: 'ok', stats }),
    })
    assert.deepEqual(result, stats)
    assert.equal(result?.store?.persisted, true)
    assert.equal(result?.store?.size, 120)
  })

  it('fetchTranslationMemoryStats returns null when disabled', async () => {
    const result = await fetchTranslationMemoryStats({
      fetcher: async () => jsonResponse({ success: true, reason: 'ok', stats: null }),
    })
    assert.equal(result, null)
  })

  it('clearTranslationMemory returns cleared count', async () => {
    const cleared = await clearTranslationMemory({
      fetcher: async () => jsonResponse({ success: true, reason: 'ok', cleared: 2, store_cleared: 5 }),
    })
    assert.equal(cleared, 2)
  })

  it('fetchTranslationMemoryEntries returns persisted pairs', async () => {
    const entries = [
      { source: 'Hello world', translated: '你好，世界', language_pair: 'en->zh-CN', created_at: 123 },
    ]
    const result = await fetchTranslationMemoryEntries({
      fetcher: async () => jsonResponse({ success: true, reason: 'ok', size: 1, entries }),
    })
    assert.deepEqual(result, entries)
  })

  it('fetchTranslationMemoryEntries passes language pair query', async () => {
    let requestedPath = ''
    await fetchTranslationMemoryEntries({
      languagePair: 'en->zh-CN',
      fetcher: async (input) => {
        requestedPath = String(input)
        return jsonResponse({ success: true, reason: 'ok', size: 0, entries: [] })
      },
    })
    assert.ok(requestedPath.includes('language_pair=en-%3Ezh-CN'))
  })

  it('fetchTranslationMemoryEntries returns null when store not initialized', async () => {
    const result = await fetchTranslationMemoryEntries({
      fetcher: async () => jsonResponse({ success: false, reason: 'not initialized' }),
    })
    assert.equal(result, null)
  })
})
