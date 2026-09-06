import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  createSummaryApiUrlFromWebSocketUrl,
  fetchSessionSummary,
  formatDuration,
  formatSummaryMarkdown,
  resolveSummaryEndpoint,
  type SessionSummary,
} from './session-summary'


const SAMPLE_SUMMARY: SessionSummary = {
  session_id: 'abc-123',
  mode: 'local',
  generated_at: 1786200000,
  duration_seconds: 125,
  segment_count: 42,
  revision_count: 3,
  speaker_count: 2,
  keywords: [
    { term: 'kubernetes', count: 9, examples: ['Kubernetes orchestrates containers'] },
    { term: 'docker', count: 5, examples: [] },
  ],
  bullets: [],
  action_items: [],
}


describe('resolveSummaryEndpoint', () => {
  it('derives endpoint from runtime websocket URL', () => {
    const endpoint = resolveSummaryEndpoint(
      'sess-1',
      '?wsUrl=ws%3A%2F%2F127.0.0.1%3A49321%2Fapi%2Fv1%2Fws%2Ftranslate',
    )
    assert.equal(endpoint, 'http://127.0.0.1:49321/api/v1/sessions/sess-1/summary')
  })

  it('falls back to the default backend host and port', () => {
    const endpoint = resolveSummaryEndpoint('sess-1')
    assert.ok(endpoint.startsWith('http://127.0.0.1:8000/api/v1/sessions/sess-1/summary'))
  })

  it('encodes the session id', () => {
    const endpoint = resolveSummaryEndpoint('a/b c')
    assert.ok(endpoint.includes('/sessions/a%2Fb%20c/summary'))
  })
})


describe('createSummaryApiUrlFromWebSocketUrl', () => {
  it('converts a valid local ws url to http endpoint', () => {
    const url = createSummaryApiUrlFromWebSocketUrl(
      'ws://127.0.0.1:8000/api/v1/ws/translate/sess-1',
      'sess-1',
    )
    assert.equal(url, 'http://127.0.0.1:8000/api/v1/sessions/sess-1/summary')
  })

  it('rejects non-loopback hosts', () => {
    const url = createSummaryApiUrlFromWebSocketUrl(
      'ws://evil.example.com/api/v1/ws/translate/sess-1',
      'sess-1',
    )
    assert.equal(url, null)
  })

  it('rejects non-ws protocols', () => {
    const url = createSummaryApiUrlFromWebSocketUrl(
      'http://127.0.0.1:8000/api/v1/ws/translate/sess-1',
      'sess-1',
    )
    assert.equal(url, null)
  })
})


describe('fetchSessionSummary', () => {
  it('returns null for empty session id', async () => {
    assert.equal(await fetchSessionSummary(''), null)
  })

  it('returns summary on success', async () => {
    const fetcher = async (): Promise<Response> => {
      return new Response(
        JSON.stringify({ success: true, reason: 'ok', summary: SAMPLE_SUMMARY }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )
    }
    const summary = await fetchSessionSummary('abc-123', {
      fetcher: fetcher as typeof globalThis.fetch,
      endpoint: 'http://127.0.0.1:8000/api/v1/sessions/abc-123/summary',
    })
    assert.ok(summary)
    assert.equal(summary.session_id, 'abc-123')
    assert.equal(summary.keywords[0].term, 'kubernetes')
  })

  it('returns null when the payload reports failure', async () => {
    const fetcher = async (): Promise<Response> => {
      return new Response(
        JSON.stringify({ success: false, reason: 'not found', summary: null }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )
    }
    const summary = await fetchSessionSummary('missing', {
      fetcher: fetcher as typeof globalThis.fetch,
      endpoint: 'http://127.0.0.1:8000/api/v1/sessions/missing/summary',
    })
    assert.equal(summary, null)
  })

  it('returns null when the request throws', async () => {
    const fetcher = async (): Promise<Response> => {
      throw new Error('network down')
    }
    const summary = await fetchSessionSummary('abc-123', {
      fetcher: fetcher as typeof globalThis.fetch,
      endpoint: 'http://127.0.0.1:8000/api/v1/sessions/abc-123/summary',
    })
    assert.equal(summary, null)
  })
})


describe('formatSummaryMarkdown', () => {
  it('renders stats and keywords', () => {
    const md = formatSummaryMarkdown(SAMPLE_SUMMARY)
    assert.ok(md.includes('kubernetes'))
    assert.ok(md.includes('42'))
    assert.ok(md.includes('## Keywords'))
  })

  it('renders bullets and action items when present', () => {
    const summary: SessionSummary = {
      ...SAMPLE_SUMMARY,
      mode: 'llm',
      bullets: ['Kubernetes 编排容器'],
      action_items: ['部署生产集群'],
    }
    const md = formatSummaryMarkdown(summary)
    assert.ok(md.includes('- Kubernetes 编排容器'))
    assert.ok(md.includes('- [ ] 部署生产集群'))
    assert.ok(md.includes('## Key points'))
    assert.ok(md.includes('## Action items'))
  })
})


describe('formatDuration', () => {
  it('formats seconds only', () => {
    assert.equal(formatDuration(45), '45s')
  })

  it('formats minutes and seconds', () => {
    assert.equal(formatDuration(125), '2m 5s')
  })

  it('clamps negative values', () => {
    assert.equal(formatDuration(-10), '0s')
  })
})
