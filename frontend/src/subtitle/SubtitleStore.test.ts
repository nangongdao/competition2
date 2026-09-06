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

  it('restoreHistory 批量恢复导入的字幕并清空旧历史', () => {
    const store = new SubtitleStore()
    store.appendToken('old_0', '旧字幕')
    store.finalizeSubtitle('old_0')

    store.restoreHistory([
      {
        segmentId: 'import_0',
        sourceText: 'Hello',
        translatedText: '你好',
        isPartial: false,
        isRevised: false,
        timestamp: 1000,
        seq: 0,
      },
      {
        segmentId: 'import_1',
        sourceText: 'Bye',
        translatedText: '再见',
        isPartial: false,
        isRevised: true,
        revisionReason: 'translation_correction',
        timestamp: 2000,
        seq: 1,
        speaker: 'speaker_1',
      },
    ])

    // 旧历史被清空，只保留导入的条目，且按 seq 有序
    assert.deepEqual(
      store.history.map((entry) => entry.segmentId),
      ['import_0', 'import_1'],
    )
    assert.equal(store.history[0].sourceText, 'Hello')
    assert.equal(store.history[1].isRevised, true)
    assert.equal(store.history[1].revisionReason, 'translation_correction')
    assert.equal(store.history[1].speaker, 'speaker_1')
    assert.equal(store.history[1].isPartial, false)
  })
})


describe('SubtitleStore 单一数据流（第二梯队-方向 3）', () => {
  it('getSnapshot 返回不可变可见/历史快照', () => {
    const store = new SubtitleStore()
    store.upsertSource('session-abc_0', 'Hello', 1000, 0)
    store.appendToken('session-abc_0', ' 你好', 0)

    const snapshot = store.getSnapshot()
    assert.equal(snapshot.visible.length, 1)
    assert.equal(snapshot.history.length, 1)
    assert.equal(snapshot.visible[0].sourceText, 'Hello')

    // 返回的是副本，外部修改不影响内部状态。
    snapshot.visible[0].sourceText = 'Mutated'
    assert.equal(store.getSnapshot().visible[0].sourceText, 'Hello')
  })

  it('订阅会在任何数据变更时触发', () => {
    const store = new SubtitleStore()
    let notified = 0
    store.subscribe(() => {
      notified += 1
    })

    store.upsertSource('session-abc_0', 'Hello', 1000, 0)
    assert.equal(notified, 1)

    store.appendToken('session-abc_0', ' 世界', 0)
    assert.ok(notified >= 2)
  })

  it('订阅返回取消函数', () => {
    const store = new SubtitleStore()
    let notified = 0
    const unsubscribe = store.subscribe(() => {
      notified += 1
    })

    store.appendToken('session-abc_0', 'x', 0)
    const afterSubscribe = notified

    unsubscribe()
    store.appendToken('session-abc_0', 'y', 0)
    assert.equal(notified, afterSubscribe)
  })
})
