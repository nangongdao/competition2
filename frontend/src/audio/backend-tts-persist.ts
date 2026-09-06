/**
 * 后端 TTS 语音/语速选择的本地持久化。
 *
 * 用户在控制面板选中的「服务端语音」与「语速」经 WebSocket config 实时下发到
 * 后端合成，但此配置此前仅保存在前端内存里——刷新页面即丢。本模块把选择
 * 持久化到 localStorage，下次打开应用自动恢复上次的语音与语速，无需重复选择。
 */

import {
  DEFAULT_BACKEND_TTS_CONFIG,
  normalizeBackendTtsDelay,
  normalizeBackendTtsRate,
  normalizeBackendTtsVoice,
  normalizeBackendTtsVolume,
  type BackendTtsConfig,
} from './backend-tts-config'

/** localStorage 存储键。 */
export const BACKEND_TTS_STORAGE_KEY = 'ai-interpreter:backend-tts-config'

/**
 * 从 localStorage 读取已保存的后端 TTS 配置。
 *
 * 任何异常（缺失、JSON 损坏、字段非法）都会回退到默认配置，绝不让脏数据
 * 污染后端合成设置。
 */
export function loadBackendTtsConfig(): BackendTtsConfig {
  try {
    const raw = localStorage.getItem(BACKEND_TTS_STORAGE_KEY)
    if (!raw) {
      return { ...DEFAULT_BACKEND_TTS_CONFIG }
    }
    const parsed = JSON.parse(raw) as Partial<BackendTtsConfig>
    const voice =
      typeof parsed.voice === 'string' ? normalizeBackendTtsVoice(parsed.voice) : DEFAULT_BACKEND_TTS_CONFIG.voice
    const rate =
      typeof parsed.rate === 'string' ? normalizeBackendTtsRate(parsed.rate) : DEFAULT_BACKEND_TTS_CONFIG.rate
    const volume =
      typeof parsed.volume === 'string'
        ? normalizeBackendTtsVolume(parsed.volume)
        : DEFAULT_BACKEND_TTS_CONFIG.volume
    const delay =
      typeof parsed.delay === 'number' ? normalizeBackendTtsDelay(parsed.delay) : DEFAULT_BACKEND_TTS_CONFIG.delay
    return { voice, rate, volume, delay }
  } catch (error) {
    console.warn('[backend-tts-persist] failed to load persisted config', error)
    return { ...DEFAULT_BACKEND_TTS_CONFIG }
  }
}

/**
 * 把用户选中的后端 TTS 语音/语速持久化到 localStorage。
 *
 * 写入前会做合法值归一化，仅保存合法配置，避免把非法值固化导致下次启动异常。
 */
export function saveBackendTtsConfig(config: BackendTtsConfig): void {
  try {
    const normalized: BackendTtsConfig = {
      voice: normalizeBackendTtsVoice(config.voice),
      rate: normalizeBackendTtsRate(config.rate),
      volume: normalizeBackendTtsVolume(config.volume),
      delay: normalizeBackendTtsDelay(config.delay),
    }
    localStorage.setItem(BACKEND_TTS_STORAGE_KEY, JSON.stringify(normalized))
  } catch (error) {
    console.warn('[backend-tts-persist] failed to persist config', error)
  }
}

/** 清除已保存的后端 TTS 配置（恢复默认）。 */
export function clearBackendTtsConfig(): void {
  try {
    localStorage.removeItem(BACKEND_TTS_STORAGE_KEY)
  } catch (error) {
    console.warn('[backend-tts-persist] failed to clear config', error)
  }
}
