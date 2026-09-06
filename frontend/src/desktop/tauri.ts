import { invoke } from '@tauri-apps/api/core'
import type {
  DesktopSettingsSaveResult,
  DesktopSettingsSnapshot,
  DesktopSettingsUpdate,
} from '../types'
import { isTauriRuntime } from '../network/ws-url'


export interface TauriPlatformInfo {
  tauri: boolean
  os: string
  arch: string
}


/**
 * Tauri 运行时能力探测：返回当前是否运行在 Tauri WebView 中。
 */
export function isTauriRuntimeAvailable(): boolean {
  return isTauriRuntime()
}


/**
 * 读取平台信息（OS / 架构），非 Tauri 环境返回 null。
 */
export async function getTauriPlatform(): Promise<TauriPlatformInfo | null> {
  if (!isTauriRuntime()) {
    return null
  }
  try {
    return await invoke<TauriPlatformInfo>('get_platform')
  } catch (error) {
    console.warn('[tauri] failed to read platform', error)
    return null
  }
}


/**
 * Tauri 侧读取本地设置快照。
 * 返回 null 表示不可用，应回退到浏览器本地设置路径。
 */
export async function readTauriDesktopSettings(): Promise<DesktopSettingsSnapshot | null> {
  if (!isTauriRuntime()) {
    return null
  }
  try {
    return await invoke<DesktopSettingsSnapshot>('read_desktop_settings')
  } catch (error) {
    console.warn('[tauri] failed to read desktop settings', error)
    return null
  }
}


/**
 * Tauri 侧保存本地设置。
 * 返回 null 表示不可用，应回退到浏览器本地设置路径。
 */
export async function saveTauriDesktopSettings(
  update: DesktopSettingsUpdate,
): Promise<DesktopSettingsSaveResult | null> {
  if (!isTauriRuntime()) {
    return null
  }
  try {
    const result = await invoke<DesktopSettingsSaveResult>('save_desktop_settings', {
      update,
    })
    return result
  } catch (error) {
    console.warn('[tauri] failed to save desktop settings', error)
    return null
  }
}


/**
 * 切换悬浮字幕窗可见性（Tauri）。
 * 返回是否成功下发。
 */
export async function setTauriOverlayVisible(visible: boolean): Promise<boolean> {
  if (!isTauriRuntime()) {
    return false
  }
  try {
    await invoke('set_overlay_visible', { visible })
    return true
  } catch (error) {
    console.warn('[tauri] failed to toggle overlay', error)
    return false
  }
}


/**
 * 读取悬浮字幕窗状态（Tauri）。
 * 不可用返回 null。
 */
export async function getTauriOverlayState(): Promise<{ available: boolean; visible: boolean } | null> {
  if (!isTauriRuntime()) {
    return null
  }
  try {
    return await invoke<{ available: boolean; visible: boolean }>('get_overlay_state')
  } catch (error) {
    console.warn('[tauri] failed to read overlay state', error)
    return null
  }
}
