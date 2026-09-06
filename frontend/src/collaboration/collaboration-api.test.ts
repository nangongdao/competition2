import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  clearCollaborationRevisions,
  createCollaborationApiUrlFromWebSocketUrl,
  createCollaborationRoom,
  destroyCollaborationRoom,
  fetchCollaborationRoom,
  fetchCollaborationRooms,
  joinCollaborationRoom,
  leaveCollaborationRoom,
  resolveCollaborationEndpoint,
  submitCollaborationRevision,
  type CollaborationRoom,
} from './collaboration-api'


describe('resolveCollaborationEndpoint', () => {
  it('derives endpoint from runtime websocket URL', () => {
    const endpoint = resolveCollaborationEndpoint(
      '/collaboration/rooms',
      '?wsUrl=ws%3A%2F%2F127.0.0.1%3A49321%2Fapi%2Fv1%2Fws%2Ftranslate',
    )
    assert.equal(endpoint, 'http://127.0.0.1:49321/api/v1/collaboration/rooms')
  })

  it('falls back to the default backend host and port', () => {
    const endpoint = resolveCollaborationEndpoint('/collaboration/rooms')
    assert.ok(endpoint.startsWith('http://127.0.0.1:8000/api/v1/collaboration/rooms'))
  })

  it('normalizes paths without leading slash', () => {
    const endpoint = resolveCollaborationEndpoint('collaboration/rooms')
    assert.ok(endpoint.endsWith('/api/v1/collaboration/rooms'))
  })
})

describe('createCollaborationApiUrlFromWebSocketUrl — 安全校验', () => {
  const maliciousUrls = [
    'ws://attacker.example.com/collect',
    'ws://169.254.169.254/',
    'http://127.0.0.1:8000/api',
    'javascript:alert(1)',
  ]

  for (const url of maliciousUrls) {
    it(`拒绝 ${url}`, () => {
      assert.equal(createCollaborationApiUrlFromWebSocketUrl(url, '/collaboration/rooms'), null)
    })
  }

  it('accepts loopback hosts', () => {
    assert.ok(
      createCollaborationApiUrlFromWebSocketUrl(
        'ws://127.0.0.1:8000/api/v1/ws/translate',
        '/collaboration/rooms',
      ),
    )
    assert.ok(
      createCollaborationApiUrlFromWebSocketUrl(
        'ws://localhost:8000/api/v1/ws/translate',
        '/collaboration/rooms',
      ),
    )
  })
})

describe('collaboration REST client', () => {
  function jsonResponse(body: unknown, ok = true): Response {
    return {
      ok,
      status: ok ? 200 : 500,
      json: async () => body,
    } as Response
  }

  const room: CollaborationRoom = {
    room_id: 'room-1',
    owner_session_id: 'owner',
    title: '产品评审',
    created_at: 1,
    last_active_at: 1,
    member_count: 1,
    members: [
      {
        session_id: 'owner',
        name: '房主',
        is_owner: true,
        joined_at: 1,
        last_seen_at: 1,
      },
    ],
  }

  it('fetchCollaborationRooms returns rooms on success', async () => {
    const result = await fetchCollaborationRooms({
      fetcher: async () => jsonResponse({ success: true, reason: 'ok', rooms: [room] }),
    })
    assert.deepEqual(result, [room])
  })

  it('fetchCollaborationRooms returns null on failure', async () => {
    const result = await fetchCollaborationRooms({
      fetcher: async () => jsonResponse({ success: false, reason: 'boom' }),
    })
    assert.equal(result, null)
  })

  it('createCollaborationRoom posts owner and title', async () => {
    let sentBody = ''
    const result = await createCollaborationRoom('owner-1', '周三评审', {
      fetcher: async (_input, init) => {
        sentBody = String(init?.body ?? '')
        return jsonResponse({ success: true, reason: 'ok', room })
      },
    })
    assert.deepEqual(result, room)
    assert.ok(sentBody.includes('"ownerSessionId":"owner-1"'))
    assert.ok(sentBody.includes('"title":"周三评审"'))
  })

  it('fetchCollaborationRoom returns room with revisions', async () => {
    const detail = {
      ...room,
      revision_count: 1,
      revisions: [
        {
          room_id: 'room-1',
          revision_id: 1,
          member_session_id: 'owner',
          member_name: '房主',
          segment_id: 'seg_1',
          source_text: '',
          new_text: '修正译文',
          created_at: 2,
        },
      ],
    }
    const result = await fetchCollaborationRoom('room-1', {
      fetcher: async () => jsonResponse({ success: true, reason: 'ok', room: detail }),
    })
    assert.equal(result?.revision_count, 1)
    assert.equal(result?.revisions?.[0].new_text, '修正译文')
  })

  it('joinCollaborationRoom posts session and name', async () => {
    let sentBody = ''
    const result = await joinCollaborationRoom('room-1', 'member-1', '小明', {
      fetcher: async (_input, init) => {
        sentBody = String(init?.body ?? '')
        return jsonResponse({ success: true, reason: 'ok', room })
      },
    })
    assert.ok(result)
    assert.ok(sentBody.includes('"sessionId":"member-1"'))
    assert.ok(sentBody.includes('"name":"小明"'))
  })

  it('leaveCollaborationRoom returns success flag', async () => {
    const result = await leaveCollaborationRoom('room-1', 'member-1', {
      fetcher: async () => jsonResponse({ success: true, reason: 'left' }),
    })
    assert.equal(result, true)
  })

  it('submitCollaborationRevision posts revision payload', async () => {
    let sentBody = ''
    const revision = {
      room_id: 'room-1',
      revision_id: 3,
      member_session_id: 'owner',
      member_name: '房主',
      segment_id: 'seg_2',
      source_text: 'source',
      new_text: '新译文',
      created_at: 3,
    }
    const result = await submitCollaborationRevision('room-1', {
      sessionId: 'owner',
      segmentId: 'seg_2',
      newText: '新译文',
      sourceText: 'source',
    }, {
      fetcher: async (_input, init) => {
        sentBody = String(init?.body ?? '')
        return jsonResponse({ success: true, reason: 'ok', revision })
      },
    })
    assert.deepEqual(result, revision)
    assert.ok(sentBody.includes('"segmentId":"seg_2"'))
    assert.ok(sentBody.includes('"newText":"新译文"'))
  })

  it('clearCollaborationRevisions returns cleared count', async () => {
    const result = await clearCollaborationRevisions('room-1', 'owner', {
      fetcher: async () => jsonResponse({ success: true, reason: 'cleared', cleared: 5 }),
    })
    assert.equal(result, 5)
  })

  it('destroyCollaborationRoom returns success flag', async () => {
    const result = await destroyCollaborationRoom('room-1', 'owner', {
      fetcher: async () => jsonResponse({ success: true, reason: 'destroyed' }),
    })
    assert.equal(result, true)
  })
})
