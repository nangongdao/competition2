/** 会话产物导入解析测试。 */

import test from 'node:test'
import assert from 'node:assert/strict'

import {
  parseSessionArtifact,
  parseSrt,
  parseVtt,
  parseJson,
  parsePlainTranscript,
} from './session-import'


test('parseSrt parses numbered timed blocks', () => {
  const srt = [
    '1',
    '00:00:01,000 --> 00:00:04,000',
    'EN: Hello world',
    'ZH: 你好世界',
    '',
    '2',
    '00:00:05,000 --> 00:00:08,000',
    'EN: How are you?',
    'ZH: 你好吗？',
  ].join('\n')

  const result = parseSrt(srt)
  assert.equal(result.skipped, 0)
  assert.equal(result.entries.length, 2)
  assert.equal(result.entries[0].sourceText, 'Hello world')
  assert.equal(result.entries[0].translatedText, '你好世界')
  assert.equal(result.entries[0].timestamp, 1000)
})

test('parseSrt skips blocks without timeline or text', () => {
  const srt = [
    '1',
    '00:00:01,000 --> 00:00:02,000',
    '',
    '2',
    'no timeline',
  ].join('\n')

  const result = parseSrt(srt)
  assert.equal(result.entries.length, 0)
  assert.ok(result.skipped >= 1)
})

test('parseVtt handles WEBVTT header', () => {
  const vtt = [
    'WEBVTT',
    '',
    '00:00:01.000 --> 00:00:04.000',
    'Hello there',
    '你好',
    '',
    '00:00:05.000 --> 00:00:08.000',
    'How are you? / 你好吗？',
  ].join('\n')

  const result = parseVtt(vtt)
  assert.equal(result.entries.length, 2)
  assert.equal(result.entries[0].sourceText, 'Hello there')
  assert.equal(result.entries[0].translatedText, '你好')
  // 斜杠分隔的双语
  assert.equal(result.entries[1].sourceText, 'How are you?')
  assert.equal(result.entries[1].translatedText, '你好吗？')
})

test('parseJson restores full subtitle entries', () => {
  const json = JSON.stringify({
    entries: [
      {
        segmentId: 's1',
        sourceText: 'Hello',
        translatedText: '你好',
        isRevised: true,
        revisionReason: 'translation_correction',
        timestamp: 1234,
        seq: 1,
        speaker: 'speaker_1',
      },
      {
        segmentId: 's2',
        sourceText: 'Bye',
        translatedText: '再见',
        timestamp: 2345,
      },
    ],
  })

  const result = parseJson(json)
  assert.equal(result.entries.length, 2)
  assert.equal(result.entries[0].segmentId, 's1')
  assert.equal(result.entries[0].isRevised, true)
  assert.equal(result.entries[0].revisionReason, 'translation_correction')
  assert.equal(result.entries[0].speaker, 'speaker_1')
  assert.equal(result.entries[0].seq, 1)
})

test('parseJson ignores invalid entries', () => {
  const json = JSON.stringify([
    { segmentId: '', sourceText: 'empty id' },
    'not-an-object',
    { segmentId: 'ok', sourceText: 'Hello', translatedText: '你好' },
  ])

  const result = parseJson(json)
  assert.equal(result.entries.length, 1)
  assert.equal(result.skipped, 2)
})

test('parseJson rejects malformed json', () => {
  const result = parseJson('not json {{{')
  assert.equal(result.entries.length, 0)
})

test('parsePlainTranscript parses EN/ZH lines', () => {
  const txt = [
    '1. 00:00:01,000',
    'EN: Hello world',
    'ZH: 你好世界',
    '',
    '2. 00:00:05,000',
    'EN: Goodbye [revised:translation_correction]',
    'ZH: 再见',
  ].join('\n')

  const result = parsePlainTranscript(txt)
  assert.equal(result.entries.length, 2)
  assert.equal(result.entries[0].sourceText, 'Hello world')
  assert.equal(result.entries[0].translatedText, '你好世界')
  // 修订标记被剥离
  assert.equal(result.entries[1].sourceText, 'Goodbye')
})

test('parseSessionArtifact routes by extension', () => {
  const srtResult = parseSessionArtifact('note.srt', '1\n00:00:01,000 --> 00:00:02,000\nEN: Hi\nZH: 嗨')
  assert.equal(srtResult.entries.length, 1)

  const vttResult = parseSessionArtifact('note.vtt', 'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi / 嗨')
  assert.equal(vttResult.entries.length, 1)

  const jsonResult = parseSessionArtifact('note.json', JSON.stringify([{ segmentId: 'a', sourceText: 'x', translatedText: 'y' }]))
  assert.equal(jsonResult.entries.length, 1)

  const txtResult = parseSessionArtifact('note.txt', '1. 00:00:01,000\nEN: Hi\nZH: 嗨')
  assert.equal(txtResult.entries.length, 1)
})

test('parseSessionArtifact skips empty input', () => {
  const result = parseSessionArtifact('empty.txt', '')
  assert.equal(result.entries.length, 0)
})
