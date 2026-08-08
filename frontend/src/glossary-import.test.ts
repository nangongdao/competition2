import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { parseGlossaryFile } from './glossary-import'


describe('parseGlossaryFile', () => {
  it('parses JSON array files', () => {
    const items = parseGlossaryFile('terms.json', JSON.stringify([
      { source: 'K8s', target: 'Kubernetes' },
      { source: 'ML', target: '机器学习', keep_original: true },
    ]))

    assert.equal(items.length, 2)
    assert.deepEqual(items[0], { source: 'K8s', target: 'Kubernetes', keep_original: false })
    assert.deepEqual(items[1], { source: 'ML', target: '机器学习', keep_original: true })
  })

  it('parses JSON objects with entries key', () => {
    const items = parseGlossaryFile('t.json', JSON.stringify({
      entries: [{ source: 'A', target: '甲' }],
    }))
    assert.equal(items.length, 1)
  })

  it('ignores invalid JSON items', () => {
    const items = parseGlossaryFile('t.json', JSON.stringify([
      { source: 'A', target: '甲' },
      { source: 123 },
      'bad',
    ]))
    assert.equal(items.length, 1)
  })

  it('returns empty for malformed JSON', () => {
    assert.deepEqual(parseGlossaryFile('t.json', '{broken'), [])
  })

  it('parses CSV with optional keep_original column', () => {
    const items = parseGlossaryFile('t.csv', 'K8s,Kubernetes,true\nML,机器学习\n\n')

    assert.equal(items.length, 2)
    assert.equal(items[0]?.keep_original, true)
    assert.equal(items[1]?.target, '机器学习')
    assert.equal(items[1]?.keep_original, false)
  })

  it('skips comment and blank CSV lines', () => {
    const items = parseGlossaryFile('t.csv', '# comment\nA,甲\n\n , \n')
    assert.equal(items.length, 1)
  })

  it('rejects unsupported file extensions', () => {
    assert.deepEqual(parseGlossaryFile('t.txt', 'A,甲'), [])
  })
})
