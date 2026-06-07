import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  createUnavailableDesktopSettings,
  DEFAULT_DESKTOP_SETTINGS,
  sanitizeDesktopSettingsSnapshot,
} from './settings'


describe('desktop settings helpers', () => {
  it('creates an unavailable fallback without sharing nested references', () => {
    const first = createUnavailableDesktopSettings()
    const second = createUnavailableDesktopSettings()

    first.translation.model = 'changed'

    assert.equal(second.translation.model, DEFAULT_DESKTOP_SETTINGS.translation.model)
    assert.equal(first.available, false)
  })

  it('sanitizes invalid Electron settings snapshots to supported defaults', () => {
    const settings = sanitizeDesktopSettingsSnapshot({
      available: true,
      configPath: 123,
      uiLanguage: 'fr',
      translation: {
        engine: 'invalid',
        model: '',
        openaiBaseUrl: ' https://example.test/v1 ',
        hasOpenaiApiKey: 'yes',
        hasAnthropicApiKey: true,
      },
      runtime: {
        asrProfile: 'huge',
        sourceLanguage: 'prompt',
      },
    })

    assert.equal(settings.available, true)
    assert.equal(settings.configPath, undefined)
    assert.equal(settings.uiLanguage, 'zh-CN')
    assert.equal(settings.translation.engine, 'openai')
    assert.equal(settings.translation.model, 'gpt-4o-mini')
    assert.equal(settings.translation.openaiBaseUrl, 'https://example.test/v1')
    assert.equal(settings.translation.hasOpenaiApiKey, false)
    assert.equal(settings.translation.hasAnthropicApiKey, true)
    assert.equal(settings.runtime.asrProfile, 'light')
    assert.equal(settings.runtime.sourceLanguage, 'en')
  })

  it('keeps valid settings from Electron snapshots', () => {
    const settings = sanitizeDesktopSettingsSnapshot({
      available: true,
      configPath: 'E:\\competition2\\config\\desktop-settings.local.json',
      uiLanguage: 'en-US',
      translation: {
        engine: 'claude',
        model: 'claude-sonnet-4-20250514',
        openaiBaseUrl: 'https://api.openai.com/v1',
        hasOpenaiApiKey: true,
        hasAnthropicApiKey: false,
      },
      runtime: {
        asrProfile: 'env',
        sourceLanguage: 'ja',
      },
    })

    assert.equal(settings.available, true)
    assert.equal(settings.uiLanguage, 'en-US')
    assert.equal(settings.translation.engine, 'claude')
    assert.equal(settings.translation.hasOpenaiApiKey, true)
    assert.equal(settings.runtime.asrProfile, 'env')
    assert.equal(settings.runtime.sourceLanguage, 'ja')
  })
})
