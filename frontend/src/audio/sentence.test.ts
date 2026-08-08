import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { splitSentences } from './sentence'


describe('splitSentences', () => {
  it('splits on Chinese punctuation', () => {
    const sentences = splitSentences('你好世界。这是第二句！第三句？')
    assert.deepEqual(sentences, ['你好世界。', '这是第二句！', '第三句？'])
  })

  it('splits on English punctuation', () => {
    const sentences = splitSentences('Hello world. This is two; keep together.')
    assert.deepEqual(sentences, ['Hello world.', 'This is two; keep together.'])
  })

  it('keeps an incomplete trailing fragment', () => {
    const sentences = splitSentences('第一句。第二句还没有标点')
    assert.deepEqual(sentences, ['第一句。', '第二句还没有标点'])
  })

  it('handles multiple punctuation characters', () => {
    const sentences = splitSentences('真的吗？？？。')
    assert.deepEqual(sentences, ['真的吗？？？。'])
  })

  it('returns empty for blank input', () => {
    assert.deepEqual(splitSentences(''), [])
    assert.deepEqual(splitSentences('   '), [])
  })
})
