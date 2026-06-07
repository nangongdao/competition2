import { getDesktopBridge } from './overlay'
import type {
  DesktopAsrProfile,
  DesktopSettingsSaveResult,
  DesktopSettingsSnapshot,
  DesktopSettingsUpdate,
  SourceLanguage,
  TranslationEngine,
  UiLanguage,
} from '../types'


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
    asrProfile: 'light',
    sourceLanguage: 'en',
  },
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
    return createUnavailableDesktopSettings()
  }

  try {
    const settings = await bridge.getSettings()
    return sanitizeDesktopSettingsSnapshot(settings)
  } catch (error) {
    console.warn('[desktop-settings] failed to load settings', error)
    return createUnavailableDesktopSettings()
  }
}


export async function saveDesktopSettings(
  update: DesktopSettingsUpdate,
): Promise<DesktopSettingsSaveResult> {
  const bridge = getDesktopBridge()
  if (!bridge?.saveSettings) {
    return {
      success: false,
      reason: 'desktop settings unavailable',
    }
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
    return {
      success: false,
      reason: 'desktop settings save failed',
    }
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
  return value === 'light' || value === 'cpu' || value === 'gpu' || value === 'env'
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
