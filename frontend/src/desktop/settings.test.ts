import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  createSettingsApiUrlFromWebSocketUrl,
  createUnavailableDesktopSettings,
  DEFAULT_DESKTOP_SETTINGS,
  loadBrowserLocalSettings,
  resolveLocalSettingsEndpoint,
  saveBrowserLocalSettings,
  sanitizeDesktopSettingsSnapshot,
} from './settings'
import type { DesktopSettingsUpdate } from '../types'


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
      asr: {
        model: '',
        openaiBaseUrl: '',
        hasOpenaiApiKey: 'yes',
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
    assert.equal(settings.asr.model, 'whisper-1')
    assert.equal(settings.asr.openaiBaseUrl, 'https://api.openai.com/v1')
    assert.equal(settings.asr.hasOpenaiApiKey, false)
    assert.equal(settings.runtime.asrProfile, 'remote')
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
      asr: {
        model: 'whisper-1',
        openaiBaseUrl: 'https://api.openai.com/v1',
        hasOpenaiApiKey: true,
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
    assert.equal(settings.asr.model, 'whisper-1')
    assert.equal(settings.asr.hasOpenaiApiKey, true)
    assert.equal(settings.runtime.asrProfile, 'env')
    assert.equal(settings.runtime.sourceLanguage, 'ja')
  })

  it('derives the local settings API URL from the runtime WebSocket URL', () => {
    assert.equal(
      createSettingsApiUrlFromWebSocketUrl('ws://127.0.0.1:8123/api/v1/ws/translate'),
      'http://127.0.0.1:8123/api/v1/settings/local',
    )
    assert.equal(
      createSettingsApiUrlFromWebSocketUrl('wss://example.test/api/v1/ws/translate'),
      'https://example.test/api/v1/settings/local',
    )
    assert.equal(createSettingsApiUrlFromWebSocketUrl('https://example.test'), null)
  })

  it('uses the wsUrl query parameter for browser settings requests', () => {
    const endpoint = resolveLocalSettingsEndpoint(
      '?wsUrl=ws%3A%2F%2F127.0.0.1%3A8123%2Fapi%2Fv1%2Fws%2Ftranslate',
    )

    assert.equal(endpoint, 'http://127.0.0.1:8123/api/v1/settings/local')
    assert.equal(resolveLocalSettingsEndpoint(''), '/api/v1/settings/local')
  })

  it('loads browser local settings through fetch when Electron is unavailable', async () => {
    const settings = await loadBrowserLocalSettings({
      endpoint: 'http://127.0.0.1:8123/api/v1/settings/local',
      fetcher: async (input, init) => {
        assert.equal(input, 'http://127.0.0.1:8123/api/v1/settings/local')
        assert.equal(init?.method, 'GET')
        return createJsonResponse({
          success: true,
          reason: 'loaded',
          settings: {
            available: true,
            configPath: 'E:\\competition2\\config\\desktop-settings.local.json',
            uiLanguage: 'en-US',
            translation: {
              engine: 'openai',
              model: 'custom-model',
              openaiBaseUrl: 'https://example.test/v1',
              hasOpenaiApiKey: true,
              hasAnthropicApiKey: false,
              openaiApiKey: 'must-not-be-used',
            },
            asr: {
              model: 'gpt-4o-mini-transcribe',
              openaiBaseUrl: 'https://api.openai.com/v1',
              hasOpenaiApiKey: true,
              openaiApiKey: 'must-not-be-used',
            },
            runtime: {
              asrProfile: 'light',
              sourceLanguage: 'de',
            },
          },
        })
      },
    })

    assert.equal(settings.available, true)
    assert.equal(settings.uiLanguage, 'en-US')
    assert.equal(settings.translation.model, 'custom-model')
    assert.equal(settings.translation.hasOpenaiApiKey, true)
    assert.equal(settings.asr.model, 'gpt-4o-mini-transcribe')
    assert.equal(settings.asr.hasOpenaiApiKey, true)
    assert.equal(settings.runtime.sourceLanguage, 'de')
  })

  it('saves browser local settings through fetch', async () => {
    const update: DesktopSettingsUpdate = {
      uiLanguage: 'zh-CN',
      translation: {
        engine: 'openai',
        model: 'gpt-4o-mini',
        openaiBaseUrl: 'https://api.openai.com/v1',
        openaiApiKey: '',
        anthropicApiKey: '',
        clearOpenaiApiKey: false,
        clearAnthropicApiKey: false,
      },
      asr: {
        model: 'whisper-1',
        openaiBaseUrl: 'https://api.openai.com/v1',
        openaiApiKey: '',
        clearOpenaiApiKey: false,
      },
      runtime: {
        asrProfile: 'light',
        sourceLanguage: 'en',
      },
    }

    const result = await saveBrowserLocalSettings(update, {
      endpoint: 'http://127.0.0.1:8123/api/v1/settings/local',
      fetcher: async (input, init) => {
        assert.equal(input, 'http://127.0.0.1:8123/api/v1/settings/local')
        assert.equal(init?.method, 'PUT')
        assert.equal(init?.headers instanceof Object, true)
        assert.equal(typeof init?.body, 'string')
        return createJsonResponse({
          success: true,
          reason: 'saved',
          settings: {
            available: true,
            uiLanguage: 'zh-CN',
            translation: {
              engine: 'openai',
              model: 'gpt-4o-mini',
              openaiBaseUrl: 'https://api.openai.com/v1',
              hasOpenaiApiKey: false,
              hasAnthropicApiKey: false,
            },
            asr: {
              model: 'whisper-1',
              openaiBaseUrl: 'https://api.openai.com/v1',
              hasOpenaiApiKey: false,
            },
            runtime: {
              asrProfile: 'light',
              sourceLanguage: 'en',
            },
          },
        })
      },
    })

    assert.equal(result.success, true)
    assert.equal(result.reason, 'saved')
    assert.equal(result.settings?.available, true)
  })
})


function createJsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
    },
  })
}
