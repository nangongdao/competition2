import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { filterSubtitlesByQuery, splitHighlightedText } from './subtitle-search'
import type { SubtitleEntry } from '../types'


function makeEntry(overrides: Partial<SubtitleEntry> & { segmentId: string }): SubtitleEntry {
  return {
    sourceText: '',
    translatedText: '',
    isPartial: false,
    isRevised: false,
    timestamp: 0,
    ...overrides,
  }
}


describe('filterSubtitlesByQuery（阶段 5 历史搜索）', () => {
  it('空查询返回全部条目', () => {
    const entries = [makeEntry({ segmentId: 'a' }), makeEntry({ segmentId: 'b' })]
    assert.equal(filterSubtitlesByQuery(entries, '').length, 2)
    assert.equal(filterSubtitlesByQuery(entries, '   ').length, 2)
  })

  it('按译文匹配（大小写不敏感）', () => {
    const entries = [
      makeEntry({ segmentId: 'a', translatedText: '机器学习入门' }),
      makeEntry({ segmentId: 'b', translatedText: '深度学习实践' }),
    ]
    const result = filterSubtitlesByQuery(entries, '学习')
    assert.deepEqual(result.map((entry) => entry.segmentId), ['a', 'b'])
  })

  it('按原文匹配', () => {
    const entries = [
      makeEntry({ segmentId: 'a', sourceText: 'Machine learning basics' }),
      makeEntry({ segmentId: 'b', sourceText: 'Deep learning practice' }),
    ]
    const result = filterSubtitlesByQuery(entries, 'machine')
    assert.deepEqual(result.map((entry) => entry.segmentId), ['a'])
  })

  it('多关键词为 AND 语义：全部命中才保留', () => {
    const entries = [
      makeEntry({ segmentId: 'a', sourceText: 'Hello world', translatedText: '你好世界' }),
      makeEntry({ segmentId: 'b', sourceText: 'Hello there', translatedText: '你好' }),
    ]
    const result = filterSubtitlesByQuery(entries, 'hello world')
    assert.deepEqual(result.map((entry) => entry.segmentId), ['a'])
  })

  it('无命中返回空数组', () => {
    const entries = [makeEntry({ segmentId: 'a', translatedText: '你好' })]
    assert.deepEqual(filterSubtitlesByQuery(entries, '不存在'), [])
  })
})


describe('splitHighlightedText（阶段 5 关键词高亮）', () => {
  it('空查询返回整段未命中', () => {
    assert.deepEqual(splitHighlightedText('hello', ''), [{ text: 'hello', matched: false }])
  })

  it('命中关键词被标记（大小写不敏感）', () => {
    const parts = splitHighlightedText('Machine learning basics', 'machine')
    const matched = parts.filter((part) => part.matched)
    assert.equal(matched.length, 1)
    assert.equal(matched[0].text, 'Machine')
  })

  it('多关键词任一命中即高亮', () => {
    const parts = splitHighlightedText('深度学习与机器学习', '机器 深度')
    const matchedTexts = parts.filter((part) => part.matched).map((part) => part.text)
    assert.ok(matchedTexts.includes('深度'))
    assert.ok(matchedTexts.includes('机器'))
  })

  it('正则特殊字符作为普通文本处理', () => {
    const parts = splitHighlightedText('C++ 与 C# 对比', 'C++')
    const matched = parts.filter((part) => part.matched)
    assert.equal(matched.length, 1)
    assert.equal(matched[0].text, 'C++')
  })

  it('未命中片段保留原文', () => {
    const parts = splitHighlightedText('Hello world', 'world')
    const unmatched = parts.filter((part) => !part.matched).map((part) => part.text).join('')
    assert.equal(unmatched, 'Hello ')
  })
})
