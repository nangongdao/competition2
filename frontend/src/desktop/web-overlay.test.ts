import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { createDesktopOverlaySnapshot } from './overlay'
import {
  createWebOverlaySnapshotMessage,
  createWebOverlayUrl,
  isWebOverlaySnapshotMessage,
  isWebOverlaySurface,
} from './web-overlay'


describe('web floating subtitle overlay helpers', () => {
  it('creates an overlay route URL without dropping existing runtime parameters', () => {
    const url = createWebOverlayUrl(
      'http://127.0.0.1:5173/?wsUrl=ws%3A%2F%2F127.0.0.1%3A8000%2Fws',
    )
    const parsed = new URL(url)

    assert.equal(parsed.searchParams.get('surface'), 'overlay')
    assert.equal(parsed.searchParams.get('transport'), 'web')
    assert.equal(parsed.searchParams.get('wsUrl'), 'ws://127.0.0.1:8000/ws')
  })

  it('detects web overlay surfaces explicitly', () => {
    assert.equal(isWebOverlaySurface('?surface=overlay&transport=web'), true)
    assert.equal(isWebOverlaySurface('?surface=overlay'), false)
    assert.equal(isWebOverlaySurface('?surface=app&transport=web'), false)
  })

  it('validates snapshot broadcast messages', () => {
    const snapshot = createDesktopOverlaySnapshot(
      [
        {
          segmentId: 'segment-1',
          sourceText: 'hello',
          translatedText: '你好',
          isPartial: false,
          isRevised: false,
          timestamp: 1000,
        },
      ],
      'bilingual',
      123,
    )
    const message = createWebOverlaySnapshotMessage(snapshot)

    assert.equal(isWebOverlaySnapshotMessage(message), true)
    assert.equal(isWebOverlaySnapshotMessage({ type: 'web-subtitle-snapshot' }), false)
    assert.equal(
      isWebOverlaySnapshotMessage({
        type: 'web-subtitle-snapshot',
        snapshot: { entries: [], mode: 'invalid', updatedAt: 123 },
      }),
      false,
    )
  })
})
