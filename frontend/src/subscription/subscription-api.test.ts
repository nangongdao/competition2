import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  createSubscriptionApiUrlFromWebSocketUrl,
  fetchSubscription,
  resetSubscriptionUsage,
  resolveSubscriptionEndpoint,
  updateSubscriptionPlan,
  type SubscriptionSnapshot,
} from './subscription-api'


describe('resolveSubscriptionEndpoint', () => {
  it('derives endpoint from runtime websocket URL', () => {
    const endpoint = resolveSubscriptionEndpoint(
      '/subscription',
      '?wsUrl=ws%3A%2F%2F127.0.0.1%3A49321%2Fapi%2Fv1%2Fws%2Ftranslate',
    )
    assert.equal(endpoint, 'http://127.0.0.1:49321/api/v1/subscription')
  })

  it('falls back to the default backend host and port', () => {
    const endpoint = resolveSubscriptionEndpoint('/subscription')
    assert.ok(endpoint.startsWith('http://127.0.0.1:8000/api/v1/subscription'))
  })
})

describe('createSubscriptionApiUrlFromWebSocketUrl — 安全校验', () => {
  it('rejects non-loopback hosts', () => {
    assert.equal(
      createSubscriptionApiUrlFromWebSocketUrl('ws://attacker.example.com/collect', '/subscription'),
      null,
    )
  })

  it('rejects http protocol', () => {
    assert.equal(
      createSubscriptionApiUrlFromWebSocketUrl('http://127.0.0.1:8000/api', '/subscription'),
      null,
    )
  })

  it('accepts loopback hosts', () => {
    assert.ok(
      createSubscriptionApiUrlFromWebSocketUrl(
        'ws://127.0.0.1:8000/api/v1/ws/translate',
        '/subscription',
      ),
    )
  })
})

describe('subscription REST client', () => {
  function jsonResponse(body: unknown, ok = true): Response {
    return {
      ok,
      status: ok ? 200 : 500,
      json: async () => body,
    } as Response
  }

  const subscription: SubscriptionSnapshot = {
    plan: 'free',
    plan_name: '免费版',
    plan_name_en: 'Free',
    price: '¥0/月',
    features: ['每日 30 分钟'],
    daily_used: 10,
    daily_limit: 200,
    daily_remaining: 190,
    day_key: '2026-08-09',
    updated_at: 1,
  }

  it('fetchSubscription returns subscription and plans', async () => {
    const plans = [
      { key: 'free', name: '免费版', name_en: 'Free', price: '¥0/月', daily_limit: 200, features: [] },
      { key: 'pro', name: '个人版', name_en: 'Pro', price: '¥29/月', daily_limit: 5000, features: [] },
    ]
    const result = await fetchSubscription({
      fetcher: async () => jsonResponse({ success: true, reason: 'ok', subscription, plans }),
    })
    assert.equal(result?.subscription?.plan, 'free')
    assert.equal(result?.plans?.length, 2)
  })

  it('fetchSubscription returns null on failure', async () => {
    const result = await fetchSubscription({
      fetcher: async () => jsonResponse({ success: false, reason: 'boom' }),
    })
    assert.equal(result, null)
  })

  it('updateSubscriptionPlan posts plan key', async () => {
    let sentBody = ''
    const result = await updateSubscriptionPlan('pro', {
      fetcher: async (_input, init) => {
        sentBody = String(init?.body ?? '')
        return jsonResponse({
          success: true,
          reason: 'ok',
          subscription: { ...subscription, plan: 'pro' },
        })
      },
    })
    assert.equal(result?.plan, 'pro')
    assert.ok(sentBody.includes('"plan":"pro"'))
  })

  it('resetSubscriptionUsage returns updated snapshot', async () => {
    const result = await resetSubscriptionUsage({
      fetcher: async () => jsonResponse({
        success: true,
        reason: 'ok',
        subscription: { ...subscription, daily_used: 0, daily_remaining: 200 },
      }),
    })
    assert.equal(result?.daily_used, 0)
    assert.equal(result?.daily_remaining, 200)
  })
})
