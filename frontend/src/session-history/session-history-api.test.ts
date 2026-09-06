import assert from 'node:assert/strict'
import { describe, it, mock } from 'node:test'

import type { UiText } from '../i18n'
import {
  clearSessionHistory,
  deleteSessionHistory,
  fetchSessionHistory,
  formatSessionDuration,
  formatSessionStartedAt,
  purgeSessionHistory,
} from './session-history-api'


const ZH_TEXT: UiText = {
  appName: '',
  idleTitle: '',
  idleDescription: '',
  idleSettingsButton: '',
  idleStartButton: '',
  idleFeatures: [],
  startError: '',
  control: {} as UiText['control'],
  history: {
    sessionSeconds: '秒',
    sessionMinutes: '分',
  } as UiText['history'],
  sessionHistory: {} as UiText['sessionHistory'],
  revisionTimeline: {} as UiText['revisionTimeline'],
  summary: {} as UiText['summary'],
  glossary: {} as UiText['glossary'],
  translationMemory: {} as UiText['translationMemory'],
  subtitleStyle: {} as UiText['subtitleStyle'],
  collaboration: {} as UiText['collaboration'],
  subscription: {} as UiText['subscription'],
  cost: {} as UiText['cost'],
  settings: {} as UiText['settings'],
}


function installFetchMock(response: unknown): ReturnType<typeof mock.fn> {
  const fetchMock = mock.fn(async () => ({
    ok: true,
    json: async () => response,
  }))
  mock.method(globalThis, 'fetch', fetchMock)
  return fetchMock
}


describe('session-history-api', () => {
  it('fetches session history from the backend endpoint', async () => {
    const fetchMock = installFetchMock({
      success: true,
      sessions: [{ session_id: 'a', segment_count: 3 }],
      stats: { total_sessions: 1, total_segments: 3, retention_seconds: 604800 },
    })

    const response = await fetchSessionHistory(50)
    assert.equal(response.success, true)
    assert.equal(response.sessions?.length, 1)
    assert.equal(response.stats?.total_sessions, 1)

    const url = fetchMock.mock.calls[0]?.arguments[0] as string
    assert.match(url, /\/api\/v1\/session-history\?limit=50$/)
  })

  it('deletes a single session via DELETE', async () => {
    const fetchMock = installFetchMock({ success: true })

    const response = await deleteSessionHistory('session-x')
    assert.equal(response.success, true)

    const [url, init] = fetchMock.mock.calls[0]?.arguments as [string, RequestInit]
    assert.match(url, /\/api\/v1\/session-history\/session-x$/)
    assert.equal(init.method, 'DELETE')
  })

  it('clears all sessions via DELETE', async () => {
    const fetchMock = installFetchMock({ success: true, cleared: 2 })

    const response = await clearSessionHistory()
    assert.equal(response.cleared, 2)

    const [url, init] = fetchMock.mock.calls[0]?.arguments as [string, RequestInit]
    assert.match(url, /\/api\/v1\/session-history$/)
    assert.equal(init.method, 'DELETE')
  })

  it('purges expired sessions via POST', async () => {
    const fetchMock = installFetchMock({ success: true, purged: 1 })

    const response = await purgeSessionHistory()
    assert.equal(response.purged, 1)

    const [url, init] = fetchMock.mock.calls[0]?.arguments as [string, RequestInit]
    assert.match(url, /\/api\/v1\/session-history\/purge$/)
    assert.equal(init.method, 'POST')
  })

  it('rejects non-ok responses with an error', async () => {
    mock.method(globalThis, 'fetch', mock.fn(async () => ({ ok: false, status: 500 })))
    await assert.rejects(() => fetchSessionHistory(), /500/)
  })

  it('formats session duration in zh-CN units', () => {
    assert.equal(formatSessionDuration(45_000, ZH_TEXT), '45秒')
    assert.equal(formatSessionDuration(90_000, ZH_TEXT), '1分 30秒')
    assert.equal(formatSessionDuration(120_000, ZH_TEXT), '2分')
  })

  it('formats started-at timestamp to local date time', () => {
    const timestamp = 1_700_000_000
    const formatted = formatSessionStartedAt(timestamp)
    assert.match(formatted, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
  })
})
