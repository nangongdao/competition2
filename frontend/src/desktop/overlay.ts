import type {
  DesktopSettingsSaveResult,
  DesktopSettingsSnapshot,
  DesktopSettingsUpdate,
  SubtitleEntry,
  SubtitleMode,
  SubtitleStyleConfig,
} from '../types'
import { DEFAULT_SUBTITLE_STYLE } from '../subtitle/subtitle-style'


export interface DesktopOverlaySnapshot {
  entries: SubtitleEntry[]
  mode: SubtitleMode
  updatedAt: number
  /** 字幕样式配置（V2.3）：浮窗渲染时应用相同 CSS 变量。 */
  style?: SubtitleStyleConfig
}


export interface DesktopOverlayState {
  available: boolean
  visible: boolean
}


export interface DesktopBridge {
  setOverlayVisible: (visible: boolean) => void
  getOverlayState: () => Promise<DesktopOverlayState>
  sendSubtitleSnapshot: (snapshot: DesktopOverlaySnapshot) => void
  onOverlayStateChange: (callback: (state: DesktopOverlayState) => void) => () => void
  onSubtitleSnapshot: (callback: (snapshot: DesktopOverlaySnapshot) => void) => () => void
  getSettings?: () => Promise<DesktopSettingsSnapshot>
  saveSettings?: (update: DesktopSettingsUpdate) => Promise<DesktopSettingsSaveResult>
}


export interface SubtitleDisplayState {
  showSource: boolean
  showTranslated: boolean
  className: string
}


const MAX_OVERLAY_ENTRIES = 6


declare global {
  interface Window {
    aiInterpreterDesktop?: DesktopBridge
  }
}


export function getDesktopBridge(): DesktopBridge | null {
  if (typeof window === 'undefined') {
    return null
  }

  return window.aiInterpreterDesktop ?? null
}


export function createDesktopOverlaySnapshot(
  entries: SubtitleEntry[],
  mode: SubtitleMode,
  updatedAt = Date.now(),
  style: SubtitleStyleConfig = DEFAULT_SUBTITLE_STYLE,
): DesktopOverlaySnapshot {
  return {
    entries: getVisibleOverlayEntries(entries),
    mode,
    updatedAt,
    style: { ...style },
  }
}


export function getVisibleOverlayEntries(entries: SubtitleEntry[]): SubtitleEntry[] {
  return entries
    .filter(hasRenderableSubtitleText)
    .slice(-MAX_OVERLAY_ENTRIES)
    .map(cloneSubtitleEntry)
}


export function getSubtitleDisplayState(
  entry: SubtitleEntry,
  mode: SubtitleMode,
): SubtitleDisplayState {
  const showSource = mode !== 'translation_only' && entry.sourceText.length > 0
  const showTranslated = mode !== 'source_only' && entry.translatedText.length > 0
  const stateClasses = [
    showSource && !showTranslated ? 'only-source' : '',
    showTranslated && !showSource ? 'only-translated' : '',
    entry.isRevised ? 'revised' : '',
  ].filter((value) => value.length > 0)

  return {
    showSource,
    showTranslated,
    className: ['desktop-subtitle-entry', ...stateClasses].join(' '),
  }
}


function hasRenderableSubtitleText(entry: SubtitleEntry): boolean {
  return entry.sourceText.trim().length > 0 || entry.translatedText.trim().length > 0
}


function cloneSubtitleEntry(entry: SubtitleEntry): SubtitleEntry {
  return { ...entry }
}
