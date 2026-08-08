import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'

import { TtsPlayer } from './TtsPlayer'


class MockSpeechSynthesisUtterance extends EventTarget {
  text: string
  lang = ''
  volume = 1
  rate = 1
  voice: SpeechSynthesisVoice | null = null
  onend: ((this: MockSpeechSynthesisUtterance, event: Event) => void) | null = null
  onerror: ((this: MockSpeechSynthesisUtterance, event: Event) => void) | null = null

  constructor(text = '') {
    super()
    this.text = text
  }
}


class MockSpeechSynthesis extends EventTarget {
  readonly spoken: MockSpeechSynthesisUtterance[] = []
  cancelCalls = 0
  paused = false
  speaking = false

  getVoices(): SpeechSynthesisVoice[] {
    return []
  }

  speak(utterance: MockSpeechSynthesisUtterance): void {
    this.spoken.push(utterance)
    this.speaking = true
  }

  cancel(): void {
    this.cancelCalls += 1
    this.speaking = false
  }

  pause(): void {
    this.paused = true
  }

  resume(): void {
    this.paused = false
  }

  finishSpokenAt(index: number): void {
    const utterance = this.spoken[index]
    if (!utterance) {
      throw new Error(`No spoken utterance at index ${index}.`)
    }

    this.speaking = false
    utterance.onend?.call(utterance, new Event('end'))
  }
}


describe('TtsPlayer', () => {
  afterEach(() => {
    restoreSpeechMocks()
  })

  it('reports unsupported speech synthesis without enabling playback', () => {
    const player = new TtsPlayer()

    player.setEnabled(true)
    player.enqueueFinalTranslation('seg-1', 'ni hao')

    assert.equal(player.diagnostics.isSupported, false)
    assert.equal(player.diagnostics.enabled, false)
    assert.equal(player.diagnostics.failedUtterances, 1)
    assert.equal(player.diagnostics.queueLength, 0)
  })

  it('clamps finite settings and falls back for non-finite values', () => {
    installSpeechMocks()
    const player = new TtsPlayer()

    player.setVolume(2)
    player.setRate(0.1)
    assert.equal(player.settings.volume, 1)
    assert.equal(player.settings.rate, 0.7)

    player.setVolume(Number.NaN)
    player.setRate(Number.POSITIVE_INFINITY)
    assert.equal(player.settings.volume, 0.8)
    assert.equal(player.settings.rate, 1)
  })

  it('speaks finalized translations in queue order with normalized Chinese utterances', () => {
    const speech = installSpeechMocks()
    const player = new TtsPlayer()

    player.setEnabled(true)
    player.enqueueFinalTranslation('seg-1', '  ni    hao  ')
    player.enqueueFinalTranslation('seg-2', 'second line')

    assert.equal(speech.spoken.length, 1)
    assert.equal(speech.spoken[0]?.text, 'ni hao')
    assert.equal(speech.spoken[0]?.lang, 'zh-CN')
    assert.equal(player.diagnostics.isSpeaking, true)
    assert.equal(player.diagnostics.queueLength, 1)

    speech.finishSpokenAt(0)

    assert.equal(speech.spoken.length, 2)
    assert.equal(speech.spoken[1]?.text, 'second line')
    assert.equal(player.diagnostics.spokenUtterances, 1)
  })

  it('updates queued revisions and skips revisions after a segment was spoken', () => {
    const speech = installSpeechMocks()
    const player = new TtsPlayer()

    player.setEnabled(true)
    player.enqueueFinalTranslation('seg-1', 'first line')
    player.enqueueFinalTranslation('seg-2', 'second line old')
    player.handleRevisedTranslation('seg-2', 'second line new')

    speech.finishSpokenAt(0)
    assert.equal(speech.spoken[1]?.text, 'second line new')

    speech.finishSpokenAt(1)
    player.handleRevisedTranslation('seg-2', 'second line late')

    assert.equal(speech.spoken.length, 2)
    assert.equal(player.diagnostics.skippedUtterances, 1)
  })

  it('skips blank final text and cancels active speech when disabled', () => {
    const speech = installSpeechMocks()
    const player = new TtsPlayer()

    player.setEnabled(true)
    player.enqueueFinalTranslation('seg-empty', '   ')
    player.enqueueFinalTranslation('seg-1', 'first line')
    player.enqueueFinalTranslation('seg-2', 'second line')
    player.setEnabled(false)

    assert.equal(player.diagnostics.skippedUtterances, 1)
    assert.equal(player.diagnostics.enabled, false)
    assert.equal(player.diagnostics.isSpeaking, false)
    assert.equal(player.diagnostics.queueLength, 0)
    assert.equal(speech.cancelCalls, 1)
  })

  it('speaks streaming sentences per segment without waiting for final', () => {
    const speech = installSpeechMocks()
    const player = new TtsPlayer()

    player.setEnabled(true)
    player.speakStreamSentence('seg-1', '第一句。', 0)
    player.speakStreamSentence('seg-1', '第二句。', 1)

    assert.equal(speech.spoken.length, 1)
    assert.equal(speech.spoken[0]?.text, '第一句。')
    assert.equal(player.diagnostics.queueLength, 1)

    speech.finishSpokenAt(0)
    assert.equal(speech.spoken.length, 2)
    assert.equal(speech.spoken[1]?.text, '第二句。')
    assert.equal(player.diagnostics.spokenUtterances, 1)
  })

  it('skips duplicate streaming sentence with the same index', () => {
    const speech = installSpeechMocks()
    const player = new TtsPlayer()

    player.setEnabled(true)
    player.speakStreamSentence('seg-1', '第一句。', 0)
    player.speakStreamSentence('seg-1', '第一句。', 0)

    assert.equal(speech.spoken.length, 1)
    assert.equal(player.diagnostics.skippedUtterances, 1)
  })

  it('streams sentences from two segments in order', () => {
    const speech = installSpeechMocks()
    const player = new TtsPlayer()

    player.setEnabled(true)
    player.speakStreamSentence('seg-a', '甲。', 0)
    player.speakStreamSentence('seg-b', '乙。', 0)

    assert.equal(speech.spoken.length, 1)
    assert.equal(speech.spoken[0]?.text, '甲。')
    assert.equal(player.diagnostics.queueLength, 1)

    speech.finishSpokenAt(0)
    assert.equal(speech.spoken[1]?.text, '乙。')
  })
})


const HAD_ORIGINAL_WINDOW = 'window' in globalThis
const ORIGINAL_WINDOW = globalThis.window
const HAD_ORIGINAL_UTTERANCE = 'SpeechSynthesisUtterance' in globalThis
const ORIGINAL_UTTERANCE = globalThis.SpeechSynthesisUtterance


function installSpeechMocks(): MockSpeechSynthesis {
  const speech = new MockSpeechSynthesis()
  Object.defineProperty(globalThis, 'SpeechSynthesisUtterance', {
    configurable: true,
    value: MockSpeechSynthesisUtterance,
    writable: true,
  })
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      speechSynthesis: speech,
    },
    writable: true,
  })
  return speech
}


function restoreSpeechMocks(): void {
  if (HAD_ORIGINAL_UTTERANCE) {
    Object.defineProperty(globalThis, 'SpeechSynthesisUtterance', {
      configurable: true,
      value: ORIGINAL_UTTERANCE,
      writable: true,
    })
  } else {
    Reflect.deleteProperty(globalThis, 'SpeechSynthesisUtterance')
  }

  if (HAD_ORIGINAL_WINDOW) {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: ORIGINAL_WINDOW,
      writable: true,
    })
  } else {
    Reflect.deleteProperty(globalThis, 'window')
  }
}
