import { getDesktopBridge } from './overlay'
import { getRuntimeWebSocketUrlFromSearch } from '../network/ws-url'
import type {
  DesktopAsrProfile,
  DesktopSettingsSaveResult,
  DesktopSettingsSnapshot,
  DesktopSettingsUpdate,
  SourceLanguage,
  TranslationEngine,
  UiLanguage,
} from '../types'


const LOCAL_SETTINGS_API_PATH = '/api/v1/settings/local'

export const DEFAULT_DESKTOP_SETTINGS: DesktopSettingsSnapshot = {
  available: false,
  uiLanguage: 'zh-CN',
  translation: {
    engine: 'openai',
    model: 'gpt-4o-mini',
    openaiBaseUrl: 'https://api.openai.com/v1',
    hasOpenaiApiKey: false,
    hasAnthropicApiKey: false,
  },
  runtime: {
    asrProfile: 'remote',
    sourceLanguage: 'en',
  },
}


type BrowserSettingsFetcher = (input: string, init?: RequestInit) => Promise<Response>


interface BrowserSettingsRequestOptions {
  endpoint?: string
  fetcher?: BrowserSettingsFetcher
}


export function createUnavailableDesktopSettings(): DesktopSettingsSnapshot {
  return {
    ...DEFAULT_DESKTOP_SETTINGS,
    translation: { ...DEFAULT_DESKTOP_SETTINGS.translation },
    runtime: { ...DEFAULT_DESKTOP_SETTINGS.runtime },
  }
}


export async function loadDesktopSettings(): Promise<DesktopSettingsSnapshot> {
  const bridge = getDesktopBridge()
  if (!bridge?.getSettings) {
    return loadBrowserLocalSettings()
  }

  try {
    const settings = await bridge.getSettings()
    return sanitizeDesktopSettingsSnapshot(settings)
  } catch (error) {
    console.warn('[desktop-settings] failed to load settings', error)
    return loadBrowserLocalSettings()
  }
}


export async function saveDesktopSettings(
  update: DesktopSettingsUpdate,
): Promise<DesktopSettingsSaveResult> {
  const bridge = getDesktopBridge()
  if (!bridge?.saveSettings) {
    return saveBrowserLocalSettings(update)
  }

  try {
    const result = await bridge.saveSettings(update)
    if (result.success && result.settings) {
      return {
        ...result,
        settings: sanitizeDesktopSettingsSnapshot(result.settings),
      }
    }
    return result
  } catch (error) {
    console.warn('[desktop-settings] failed to save settings', error)
    return saveBrowserLocalSettings(update)
  }
}


export async function loadBrowserLocalSettings(
  options: BrowserSettingsRequestOptions = {},
): Promise<DesktopSettingsSnapshot> {
  const fetcher = options.fetcher ?? getDefaultFetcher()
  if (!fetcher) {
    return createUnavailableDesktopSettings()
  }

  try {
    const response = await fetcher(options.endpoint ?? resolveLocalSettingsEndpoint(), {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    })
    if (!response.ok) {
      return createUnavailableDesktopSettings()
    }

    return sanitizeSettingsLoadResult(await response.json())
  } catch (error) {
    console.warn('[browser-settings] failed to load settings', error)
    return createUnavailableDesktopSettings()
  }
}


export async function saveBrowserLocalSettings(
  update: DesktopSettingsUpdate,
  options: BrowserSettingsRequestOptions = {},
): Promise<DesktopSettingsSaveResult> {
  const fetcher = options.fetcher ?? getDefaultFetcher()
  if (!fetcher) {
    return {
      success: false,
      reason: 'browser settings unavailable',
    }
  }

  try {
    const response = await fetcher(options.endpoint ?? resolveLocalSettingsEndpoint(), {
      method: 'PUT',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(update),
    })
    if (!response.ok) {
      return {
        success: false,
        reason: 'browser settings save failed',
      }
    }

    return sanitizeSettingsSaveResult(await response.json())
  } catch (error) {
    console.warn('[browser-settings] failed to save settings', error)
    return {
      success: false,
      reason: 'browser settings save failed',
    }
  }
}


export function resolveLocalSettingsEndpoint(search?: string): string {
  const locationSearch = search ?? (typeof window === 'undefined' ? '' : window.location.search)
  const runtimeWebSocketUrl = getRuntimeWebSocketUrlFromSearch(locationSearch)
  return createSettingsApiUrlFromWebSocketUrl(runtimeWebSocketUrl) ?? LOCAL_SETTINGS_API_PATH
}


export function createSettingsApiUrlFromWebSocketUrl(value: string | null | undefined): string | null {
  const trimmedValue = value?.trim() ?? ''
  if (!trimmedValue) {
    return null
  }

  try {
    const url = new URL(trimmedValue)
    if (url.protocol !== 'ws:' && url.protocol !== 'wss:') {
      return null
    }

    url.protocol = url.protocol === 'wss:' ? 'https:' : 'http:'
    url.pathname = LOCAL_SETTINGS_API_PATH
    url.search = ''
    url.hash = ''
    return url.toString()
  } catch {
    return null
  }
}


export function sanitizeDesktopSettingsSnapshot(
  value: unknown,
): DesktopSettingsSnapshot {
  if (!isRecord(value)) {
    return createUnavailableDesktopSettings()
  }
  const translation = isRecord(value.translation) ? value.translation : {}
  const runtime = isRecord(value.runtime) ? value.runtime : {}

  return {
    available: value.available === true,
    configPath: typeof value.configPath === 'string' ? value.configPath : undefined,
    uiLanguage: pickUiLanguage(value.uiLanguage, DEFAULT_DESKTOP_SETTINGS.uiLanguage),
    translation: {
      engine: pickTranslationEngine(
        translation.engine,
        DEFAULT_DESKTOP_SETTINGS.translation.engine,
      ),
      model: pickString(translation.model, DEFAULT_DESKTOP_SETTINGS.translation.model),
      openaiBaseUrl: pickString(
        translation.openaiBaseUrl,
        DEFAULT_DESKTOP_SETTINGS.translation.openaiBaseUrl,
      ),
      hasOpenaiApiKey: translation.hasOpenaiApiKey === true,
      hasAnthropicApiKey: translation.hasAnthropicApiKey === true,
    },
    runtime: {
      asrProfile: pickAsrProfile(
        runtime.asrProfile,
        DEFAULT_DESKTOP_SETTINGS.runtime.asrProfile,
      ),
      sourceLanguage: pickSourceLanguage(
        runtime.sourceLanguage,
        DEFAULT_DESKTOP_SETTINGS.runtime.sourceLanguage,
      ),
    },
  }
}


function sanitizeSettingsLoadResult(value: unknown): DesktopSettingsSnapshot {
  if (!isRecord(value) || value.success !== true) {
    return createUnavailableDesktopSettings()
  }

  return sanitizeDesktopSettingsSnapshot(value.settings)
}


function sanitizeSettingsSaveResult(value: unknown): DesktopSettingsSaveResult {
  if (!isRecord(value)) {
    return {
      success: false,
      reason: 'browser settings save failed',
    }
  }

  if (value.success === true) {
    return {
      success: true,
      reason: typeof value.reason === 'string' ? value.reason : 'browser settings saved',
      settings: sanitizeDesktopSettingsSnapshot(value.settings),
    }
  }

  return {
    success: false,
    reason: typeof value.reason === 'string' ? value.reason : 'browser settings save failed',
  }
}


function getDefaultFetcher(): BrowserSettingsFetcher | null {
  if (typeof globalThis.fetch !== 'function') {
    return null
  }

  return globalThis.fetch.bind(globalThis)
}


function pickString(value: unknown, fallback: string): string {
  const trimmedValue = typeof value === 'string' ? value.trim() : ''
  return trimmedValue ? trimmedValue : fallback
}


function pickUiLanguage(value: unknown, fallback: UiLanguage): UiLanguage {
  return value === 'zh-CN' || value === 'en-US' ? value : fallback
}


function pickTranslationEngine(value: unknown, fallback: TranslationEngine): TranslationEngine {
  return value === 'openai' || value === 'claude' ? value : fallback
}


function pickAsrProfile(
  value: unknown,
  fallback: DesktopAsrProfile,
): DesktopAsrProfile {
  return value === 'remote'
    || value === 'light'
    || value === 'cpu'
    || value === 'gpu'
    || value === 'env'
    ? value
    : fallback
}


function pickSourceLanguage(
  value: unknown,
  fallback: SourceLanguage,
): SourceLanguage {
  switch (value) {
    case 'auto':
    case 'en':
    case 'ja':
    case 'ko':
    case 'es':
    case 'fr':
    case 'de':
      return value
    default:
      return fallback
  }
}


function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
