import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { pushRevisionEvent, REVISION_HISTORY_LIMIT, revisionEventFromMessage } from './revision-history'
import type { RevisionMessage } from '../types'


const ASR_MESSAGE: RevisionMessage = {
  type: 'revision',
  segment_id: 'session-abc_3',
  new_text: 'Machine learning',
  source_text: 'Machine learnin',
  reason: 'asr_correction',
  old_source_text: 'Machine learnin',
  correction_source: 'audio_redecode',
  trigger: 'low_confidence',
  latency_ms: 420,
  confidence: 0.12,
}


const TRANSLATION_MESSAGE: RevisionMessage = {
  type: 'revision',
  segment_id: 'session-abc_4',
  new_text: '机器学习入门',
  old_text: '机器学习',
  reason: 'translation_correction',
  correction_source: 'translation_cache',
  trigger: 'sentence_count',
  latency_ms: 300,
}


describe('revisionEventFromMessage（阶段 4 修正历史）', () => {
  it('将 snake_case 后端字段映射为 camelCase 事件字段', () => {
    const event = revisionEventFromMessage(ASR_MESSAGE, 1700000000000)
    assert.equal(event.segmentId, 'session-abc_3')
    assert.equal(event.segmentIndex, 3)
    assert.equal(event.newText, 'Machine learning')
    assert.equal(event.sourceText, 'Machine learnin')
    assert.equal(event.reason, 'asr_correction')
    assert.equal(event.correctionSource, 'audio_redecode')
    assert.equal(event.trigger, 'low_confidence')
    assert.equal(event.latencyMs, 420)
    assert.equal(event.confidence, 0.12)
    assert.equal(event.timestamp, 1700000000000)
    assert.ok(event.id.length > 0)
  })

  it('翻译修正事件保留 oldText / 无 sourceText', () => {
    const event = revisionEventFromMessage(TRANSLATION_MESSAGE, 1700000000001)
    assert.equal(event.oldText, '机器学习')
    assert.equal(event.sourceText, undefined)
    assert.equal(event.reason, 'translation_correction')
    assert.equal(event.segmentIndex, 4)
  })

  it('segmentId 无法解析序号时为 undefined', () => {
    const event = revisionEventFromMessage(
      { ...TRANSLATION_MESSAGE, segment_id: 'no-separator' },
      1,
    )
    assert.equal(event.segmentIndex, undefined)
  })

  it('缺失可选字段不报错', () => {
    const event = revisionEventFromMessage({
      type: 'revision',
      segment_id: 'session-abc_0',
      new_text: 'x',
      reason: 'translation_correction',
    }, 2)
    assert.equal(event.segmentIndex, 0)
    assert.equal(event.latencyMs, undefined)
    assert.equal(event.trigger, undefined)
  })
})


describe('pushRevisionEvent（阶段 4 修正历史累积）', () => {
  it('新事件插入到最前（最新在前）', () => {
    const first = revisionEventFromMessage(ASR_MESSAGE, 1)
    const second = revisionEventFromMessage(TRANSLATION_MESSAGE, 2)
    const history = pushRevisionEvent([first], second)
    assert.equal(history.length, 2)
    assert.equal(history[0].segmentId, 'session-abc_4')
    assert.equal(history[1].segmentId, 'session-abc_3')
  })

  it('超过上限时裁剪最旧事件', () => {
    let history: ReturnType<typeof pushRevisionEvent> = []
    for (let index = 0; index < REVISION_HISTORY_LIMIT + 20; index += 1) {
      const event = revisionEventFromMessage(
        { ...ASR_MESSAGE, segment_id: `session-abc_${index}` },
        index,
      )
      history = pushRevisionEvent(history, event)
    }
    assert.equal(history.length, REVISION_HISTORY_LIMIT)
    // 最新的在最前
    assert.equal(history[0].segmentIndex, REVISION_HISTORY_LIMIT + 19)
    // 最旧 20 条被裁剪
    assert.ok(!history.some((event) => event.segmentIndex === 0))
  })
})
