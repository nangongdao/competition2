import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  createCostApiUrlFromWebSocketUrl,
  fetchCostOverview,
  resetCostUsage,
  resolveCostEndpoint,
  type CostOverview,
} from './cost-api'


describe('resolveCostEndpoint', () => {
  it('derives endpoint from runtime websocket URL', () => {
    const endpoint = resolveCostEndpoint(
      '/cost',
      '?wsUrl=ws%3A%2F%2F127.0.0.1%3A49321%2Fapi%2Fv1%2Fws%2Ftranslate',
    )
    assert.equal(endpoint, 'http://127.0.0.1:49321/api/v1/cost')
  })

  it('falls back to the default backend host and port', () => {
    const endpoint = resolveCostEndpoint('/cost')
    assert.ok(endpoint.startsWith('http://127.0.0.1:8000/api/v1/cost'))
  })
})

describe('createCostApiUrlFromWebSocketUrl — 安全校验', () => {
  it('rejects non-loopback hosts', () => {
    assert.equal(
      createCostApiUrlFromWebSocketUrl('ws://attacker.example.com/collect', '/cost'),
      null,
    )
  })

  it('rejects http protocol', () => {
    assert.equal(
      createCostApiUrlFromWebSocketUrl('http://127.0.0.1:8000/api', '/cost'),
      null,
    )
  })

  it('accepts loopback hosts', () => {
    assert.ok(
      createCostApiUrlFromWebSocketUrl(
        'ws://127.0.0.1:8000/api/v1/ws/translate',
        '/cost',
      ),
    )
  })
})

describe('cost REST client', () => {
  function jsonResponse(body: unknown, ok = true): Response {
    return {
      ok,
      status: ok ? 200 : 500,
      json: async () => body,
    } as Response
  }

  const overview: CostOverview = {
    success: true,
    reason: 'cost overview loaded',
    total_sessions: 3,
    usage: { nmt_input_tokens: 1000, nmt_output_tokens: 500, asr_seconds: 120, tts_chars: 2000 },
    today: { nmt_input_tokens: 1000, nmt_output_tokens: 500, asr_seconds: 120, tts_chars: 2000 },
    total_cost_usd: 0.0045,
    total_cost_cny: 0.0324,
    today_cost_usd: 0.0045,
    today_cost_cny: 0.0324,
    daily_cost_limit_usd: 2,
    daily_nmt_call_limit: 500,
    suggestions: [],
    prices: { nmt_input_per_m: 0.15, nmt_output_per_m: 0.6, asr_per_minute: 0.006, tts_per_k_chars: 0.015 },
    token_estimate_note: 'note',
  }

  it('fetchCostOverview returns overview on success', async () => {
    const fetcher = async (): Promise<Response> => jsonResponse({ ...overview })
    const result = await fetchCostOverview({ fetcher, endpoint: 'http://127.0.0.1:8000/api/v1/cost' })
    assert.ok(result)
    assert.equal(result?.total_sessions, 3)
    assert.equal(result?.usage.nmt_input_tokens, 1000)
  })

  it('fetchCostOverview returns null on failed response', async () => {
    const fetcher = async (): Promise<Response> => jsonResponse({ success: false }, false)
    const result = await fetchCostOverview({ fetcher, endpoint: 'http://127.0.0.1:8000/api/v1/cost' })
    assert.equal(result, null)
  })

  it('resetCostUsage returns overview on success', async () => {
    const fetcher = async (): Promise<Response> => jsonResponse({ ...overview, total_sessions: 0 })
    const result = await resetCostUsage({ fetcher, endpoint: 'http://127.0.0.1:8000/api/v1/cost/reset' })
    assert.ok(result)
    assert.equal(result?.total_sessions, 0)
  })
})
