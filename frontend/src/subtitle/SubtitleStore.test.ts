import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { SubtitleStore } from './SubtitleStore'


describe('SubtitleStore 乱序保护', () => {
  it('按 seq 有序插入历史，而非按到达顺序追加', () => {
    const store = new SubtitleStore()

    // 翻译异步化：长句 seq=0 后完成，短句 seq=1 先到
    store.appendToken('session-abc_1', '你好')
    store.appendToken('session-abc_0', '这是一段')
    store.appendToken('session-abc_0', '较长的话')

    assert.deepEqual(
      store.history.map((entry) => entry.segmentId),
      ['session-abc_0', 'session-abc_1'],
    )
    assert.equal(store.history[0].translatedText, '这是一段较长的话')
    assert.equal(store.history[1].translatedText, '你好')
  })

  it('乱序到达时 asr_final 与翻译 token 合并到同一条目', () => {
    const store = new SubtitleStore()

    store.appendToken('session-abc_1', '早', 1)
    store.appendToken('session-abc_0', '好', 0)
    store.upsertSource('session-abc_0', 'Good morning.', 1000, 0)

    const first = store.getEntry('session-abc_0')
    assert.ok(first)
    assert.equal(first?.sourceText, 'Good morning.')
    assert.equal(first?.translatedText, '好')
  })

  it('无 seq 时回退为解析 segmentId 尾部序号', () => {
    const store = new SubtitleStore()

    store.appendToken('session-abc_2', '第三')
    store.appendToken('session-abc_1', '第二')

    assert.deepEqual(
      store.history.map((entry) => entry.segmentId),
      ['session-abc_1', 'session-abc_2'],
    )
  })

  it('upsertSource 记录说话人标签', () => {
    const store = new SubtitleStore()

    store.upsertSource('session-abc_0', 'Hello', 1000, 0, 'speaker_2')
    store.appendToken('session-abc_0', ' 你好', 0)

    const entry = store.getEntry('session-abc_0')
    assert.equal(entry?.speaker, 'speaker_2')
  })

  it('说话人标签在历史序中保留', () => {
    const store = new SubtitleStore()

    store.upsertSource('session-abc_1', 'One', 1000, 1, 'speaker_1')
    store.upsertSource('session-abc_2', 'Two', 2000, 2, 'speaker_2')

    assert.deepEqual(
      store.history.map((entry) => entry.speaker),
      ['speaker_1', 'speaker_2'],
    )
  })
})
