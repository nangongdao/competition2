/**
 * 全局快捷键系统（第二梯队-方向 6）。
 *
 * 提供：
 * - 纯函数式快捷键绑定定义与键盘事件匹配（浏览器 / 聚焦的 Tauri 窗口内有效，可单测）。
 * - 可选的 Tauri `global-shortcut` 系统级注册桥（见 `src-tauri`，前端经事件触发同一套回调）。
 *
 * 约定（Web 层）：
 * - Ctrl/Cmd + Space ：开始/停止翻译
 * - Ctrl/Cmd + 1     ：循环切换字幕显示模式（双语 / 仅译文 / 仅原文）
 * - Ctrl/Cmd + H     ：开关字幕历史面板
 */

export type ShortcutAction =
  | 'toggle_translation'
  | 'cycle_subtitle_mode'
  | 'toggle_history'


export interface ShortcutBinding {
  action: ShortcutAction
  key: string
  ctrl: boolean
  shift: boolean
  alt: boolean
}

/** 默认快捷键绑定表（可被 UI 覆盖）。 */
export const DEFAULT_SHORTCUTS: ShortcutBinding[] = [
  { action: 'toggle_translation', key: ' ', ctrl: true, shift: false, alt: false },
  { action: 'cycle_subtitle_mode', key: '1', ctrl: true, shift: false, alt: false },
  { action: 'toggle_history', key: 'h', ctrl: true, shift: false, alt: false },
]

/** 字幕显示模式循环顺序（循环切换用）。 */
export const SUBTITLE_MODE_CYCLE = ['bilingual', 'translation_only', 'source_only'] as const

/** 一次会话内可直接切换的字幕显示模式。 */
export type SubtitleModeCycleItem = (typeof SUBTITLE_MODE_CYCLE)[number]

/**
 * 依据当前修饰键状态匹配一组快捷键绑定，返回命中的动作（最多一个）。
 *
 * @param bindings 快捷键绑定表。
 * @param key 事件中的 `event.key`（已归一化）。
 * @param ctrlShiftAlt 当前按下的修饰键。
 */
export function matchShortcut(
  bindings: ShortcutBinding[],
  key: string,
  ctrlShiftAlt: { ctrl: boolean; shift: boolean; alt: boolean },
): ShortcutAction | null {
  const normalizedKey = normalizeKey(key)
  for (const binding of bindings) {
    if (
      normalizeKey(binding.key) === normalizedKey &&
      binding.ctrl === ctrlShiftAlt.ctrl &&
      binding.shift === ctrlShiftAlt.shift &&
      binding.alt === ctrlShiftAlt.alt
    ) {
      return binding.action
    }
  }
  return null
}

/**
 * 从 DOM KeyboardEvent 提取修饰键状态并匹配。
 * 兼容 Mac 的 meta（Command）视为 ctrl，Windows/Linux 的 ctrlKey 视为 ctrl。
 */
export function matchKeyboardEvent(
  event: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'altKey'>,
  bindings: ShortcutBinding[] = DEFAULT_SHORTCUTS,
): ShortcutAction | null {
  // 纯打字（无修饰键）不应触发快捷键，避免与输入框冲突。
  if (!event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
    return null
  }
  return matchShortcut(bindings, event.key, {
    ctrl: event.ctrlKey || event.metaKey,
    shift: event.shiftKey,
    alt: event.altKey,
  })
}

/** 计算下一个字幕显示模式（循环）。 */
export function nextSubtitleMode(current: string): SubtitleModeCycleItem {
  const index = SUBTITLE_MODE_CYCLE.indexOf(current as SubtitleModeCycleItem)
  const nextIndex = (index === -1 ? 0 : index + 1) % SUBTITLE_MODE_CYCLE.length
  return SUBTITLE_MODE_CYCLE[nextIndex]
}

function normalizeKey(key: string): string {
  return key.trim().toLowerCase()
}
