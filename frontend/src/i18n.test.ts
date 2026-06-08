import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { getUiText, isUiLanguage, UI_LANGUAGE_OPTIONS } from './i18n'


describe('i18n', () => {
  it('exposes exactly Chinese and English UI language options', () => {
    assert.deepEqual(
      UI_LANGUAGE_OPTIONS.map((option) => option.value),
      ['zh-CN', 'en-US'],
    )
  })

  it('returns localized control labels', () => {
    const zh = getUiText('zh-CN')
    const en = getUiText('en-US')

    assert.equal(zh.control.settingsButton, '设置')
    assert.equal(en.control.settingsButton, 'Settings')
    assert.equal(zh.control.sourceOptions.ja, '日语')
    assert.equal(en.control.sourceOptions.ja, 'Japanese')
  })

  it('narrows supported language values', () => {
    assert.equal(isUiLanguage('zh-CN'), true)
    assert.equal(isUiLanguage('en-US'), true)
    assert.equal(isUiLanguage('fr'), false)
  })
})
