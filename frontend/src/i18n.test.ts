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
    // 多语种目标语言文案
    assert.equal(zh.control.targetOptions['zh-CN'], '简体中文')
    assert.equal(zh.control.targetOptions.en, '英语')
    assert.equal(en.control.targetOptions.en, 'English')
    assert.equal(en.control.targetOptions['zh-CN'], 'Simplified Chinese')
    // 语音引擎与音频输入文案
    assert.equal(zh.control.voiceEngine, '语音引擎')
    assert.deepEqual(
      zh.control.voiceEngineOptions.map((option) => option.value),
      ['auto', 'local', 'backend'],
    )
    assert.equal(en.control.voiceEngine, 'Voice engine')
    assert.equal(zh.control.audioSource, '音频输入')
    assert.deepEqual(
      zh.control.audioSourceOptions.map((option) => option.value),
      ['mic', 'tab', 'system', 'file'],
    )
    assert.equal(en.control.audioSource, 'Audio input')
    assert.deepEqual(
      en.control.audioSourceOptions.map((option) => option.value),
      ['mic', 'tab', 'system', 'file'],
    )
    assert.equal(zh.control.audioFilePick, '选择音频文件')
    assert.equal(en.control.audioFilePick, 'Pick an audio file')
  })

  it('narrows supported language values', () => {
    assert.equal(isUiLanguage('zh-CN'), true)
    assert.equal(isUiLanguage('en-US'), true)
    assert.equal(isUiLanguage('fr'), false)
  })

  it('localizes glossary and translation memory panels', () => {
    const zh = getUiText('zh-CN')
    const en = getUiText('en-US')

    assert.equal(zh.control.openGlossary, '术语库')
    assert.equal(en.control.openGlossary, 'Glossary')
    assert.equal(zh.control.openTranslationMemory, '翻译记忆库')
    assert.equal(en.control.openTranslationMemory, 'Translation Memory')

    assert.equal(zh.glossary.title, '术语库')
    assert.equal(en.glossary.title, 'Glossary')
    assert.equal(zh.glossary.keepOriginalBadge, '保持原文')
    assert.equal(en.glossary.keepOriginalBadge, 'Keep original')
    assert.ok(zh.glossary.deleteEntry('K8s').includes('K8s'))
    assert.ok(en.glossary.deleteEntry('K8s').includes('K8s'))

    assert.equal(zh.translationMemory.title, '翻译记忆库')
    assert.equal(en.translationMemory.title, 'Translation Memory')
    assert.equal(zh.translationMemory.hitRate, '命中率')
    assert.equal(en.translationMemory.hitRate, 'Hit rate')
  })

  it('localizes revision timeline and history search (阶段 4/5)', () => {
    const zh = getUiText('zh-CN')
    const en = getUiText('en-US')

    assert.equal(zh.control.openRevisionTimeline, '修正历史')
    assert.equal(en.control.openRevisionTimeline, 'Revision history')
    assert.equal(zh.revisionTimeline.title, '修正历史')
    assert.equal(en.revisionTimeline.title, 'Revision history')
    assert.equal(zh.revisionTimeline.reasonLabels.asr_correction, '识别')
    assert.equal(en.revisionTimeline.reasonLabels.translation_correction, 'Translation')
    assert.equal(zh.revisionTimeline.sourceLabels.audio_redecode, '音频重解码')
    assert.equal(en.revisionTimeline.sourceLabels.llm_post_edit, 'LLM post-edit')
    assert.equal(zh.revisionTimeline.triggerLabels.low_confidence, '低置信度')
    assert.equal(en.revisionTimeline.triggerLabels.sentence_count, 'Sentence count')
    assert.equal(zh.revisionTimeline.ago(1), '1 分钟前')
    assert.equal(en.revisionTimeline.ago(1), '1 min ago')

    assert.equal(zh.history.searchPlaceholder, '搜索原文或译文…')
    assert.equal(en.history.searchPlaceholder, 'Search source or translation…')
    assert.equal(zh.history.searchMatchLabel(3), '找到 3 条匹配')
    assert.equal(en.history.searchMatchLabel(1), '1 match found')
    assert.equal(en.history.searchMatchLabel(2), '2 matches found')
    assert.equal(zh.history.searchNoMatch, '没有匹配的字幕。')
    assert.equal(en.history.searchNoMatch, 'No matching subtitles.')
  })
})
