import type { SubtitlePosition, SubtitleStyleConfig } from '../types'


/** 字号范围（px） */
export const SUBTITLE_FONT_SIZE_MIN = 12
export const SUBTITLE_FONT_SIZE_MAX = 36
/** 背景透明度范围（0-1） */
export const SUBTITLE_OPACITY_MIN = 0
export const SUBTITLE_OPACITY_MAX = 1


export const DEFAULT_SUBTITLE_STYLE: SubtitleStyleConfig = {
  fontSize: 22,
  fontColor: '#ffffff',
  backgroundColor: '#0a0e16',
  backgroundOpacity: 0.78,
  position: 'bottom',
}


/**
 * 将任意输入规整为合法的字幕样式配置（带边界约束）。
 * 持久化 / 快照 / 外部设置均通过此函数收敛。
 */
export function normalizeSubtitleStyle(value: unknown): SubtitleStyleConfig {
  if (!isRecord(value)) {
    return { ...DEFAULT_SUBTITLE_STYLE }
  }

  const fontSize = pickNumber(value.fontSize, DEFAULT_SUBTITLE_STYLE.fontSize)
  const backgroundOpacity = pickNumber(
    value.backgroundOpacity,
    DEFAULT_SUBTITLE_STYLE.backgroundOpacity,
  )

  return {
    fontSize: clampNumber(fontSize, SUBTITLE_FONT_SIZE_MIN, SUBTITLE_FONT_SIZE_MAX),
    fontColor: pickHexColor(value.fontColor, DEFAULT_SUBTITLE_STYLE.fontColor),
    backgroundColor: pickHexColor(
      value.backgroundColor,
      DEFAULT_SUBTITLE_STYLE.backgroundColor,
    ),
    backgroundOpacity: clampNumber(
      backgroundOpacity,
      SUBTITLE_OPACITY_MIN,
      SUBTITLE_OPACITY_MAX,
    ),
    position: pickPosition(value.position, DEFAULT_SUBTITLE_STYLE.position),
  }
}


export function isSubtitlePosition(value: unknown): value is SubtitlePosition {
  return value === 'bottom' || value === 'middle' || value === 'top'
}


/**
 * 生成应用到 DOM 的 CSS 变量对象（React inline style / element.style.setProperty 通用）。
 */
export function buildSubtitleStyleVarMap(style: SubtitleStyleConfig): Record<string, string> {
  return {
    '--subtitle-font-size': `${style.fontSize}px`,
    '--subtitle-font-color': style.fontColor,
    '--subtitle-background': toRgbaString(style.backgroundColor, style.backgroundOpacity),
    '--subtitle-position': style.position,
  }
}


/**
 * 生成应用到 DOM 的 CSS 变量字符串（用于内联 <style> 注入等场景）。
 * 主界面渲染器与独立悬浮字幕窗共用同一套变量名，一处配置处处生效。
 */
export function buildSubtitleStyleCssVars(style: SubtitleStyleConfig): string {
  return Object.entries(buildSubtitleStyleVarMap(style))
    .map(([key, value]) => `${key}: ${value}`)
    .join(';')
}


/** 解析 CSS 变量中记录的样式（与 buildSubtitleStyleCssVars 对应）。 */
export function parseSubtitleStyleCssVars(
  raw: string,
  fallback: SubtitleStyleConfig = DEFAULT_SUBTITLE_STYLE,
): SubtitleStyleConfig {
  const entries = new Map<string, string>()
  raw.split(';').forEach((pair) => {
    const separatorIndex = pair.indexOf(':')
    if (separatorIndex < 0) {
      return
    }
    const key = pair.slice(0, separatorIndex).trim()
    const value = pair.slice(separatorIndex + 1).trim()
    if (key && value) {
      entries.set(key, value)
    }
  })

  const fontSize = parseFloat(entries.get('--subtitle-font-size') ?? '')
  const background = parseRgba(entries.get('--subtitle-background'))

  return {
    fontSize: Number.isFinite(fontSize)
      ? clampNumber(fontSize, SUBTITLE_FONT_SIZE_MIN, SUBTITLE_FONT_SIZE_MAX)
      : fallback.fontSize,
    fontColor: pickHexColor(entries.get('--subtitle-font-color'), fallback.fontColor),
    backgroundColor: background ? background.color : fallback.backgroundColor,
    backgroundOpacity: background ? background.opacity : fallback.backgroundOpacity,
    position: pickPosition(entries.get('--subtitle-position'), fallback.position),
  }
}


function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}


function pickNumber(value: unknown, fallback: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return fallback
  }
  return value
}


const HEX_COLOR_PATTERN = /^#[0-9a-fA-F]{6}$/


function pickHexColor(value: unknown, fallback: string): string {
  return typeof value === 'string' && HEX_COLOR_PATTERN.test(value.trim())
    ? value.trim()
    : fallback
}


function pickPosition(value: unknown, fallback: SubtitlePosition): SubtitlePosition {
  return isSubtitlePosition(value) ? value : fallback
}


function toRgbaString(hexColor: string, opacity: number): string {
  const normalizedHex = hexColor.replace('#', '')
  const red = parseInt(normalizedHex.slice(0, 2), 16)
  const green = parseInt(normalizedHex.slice(2, 4), 16)
  const blue = parseInt(normalizedHex.slice(4, 6), 16)
  if ([red, green, blue].some((channel) => Number.isNaN(channel))) {
    return 'rgba(10, 14, 22, 0.78)'
  }
  const clampedOpacity = clampNumber(opacity, SUBTITLE_OPACITY_MIN, SUBTITLE_OPACITY_MAX)
  return `rgba(${red}, ${green}, ${blue}, ${clampedOpacity.toFixed(2)})`
}


interface ParsedRgba {
  color: string
  opacity: number
}


const RGBA_PATTERN = /^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)$/


function parseRgba(value: string | undefined): ParsedRgba | null {
  if (!value) {
    return null
  }
  const match = RGBA_PATTERN.exec(value.trim())
  if (!match) {
    return null
  }

  const red = Number(match[1])
  const green = Number(match[2])
  const blue = Number(match[3])
  const opacity = Number(match[4])
  if (
    !Number.isInteger(red) || !Number.isInteger(green) || !Number.isInteger(blue)
    || red < 0 || red > 255 || green < 0 || green > 255 || blue < 0 || blue > 255
    || !Number.isFinite(opacity) || opacity < 0 || opacity > 1
  ) {
    return null
  }

  return {
    color: toHexColor(red, green, blue),
    opacity,
  }
}


function toHexColor(red: number, green: number, blue: number): string {
  return `#${[red, green, blue].map((channel) => channel.toString(16).padStart(2, '0')).join('')}`
}


function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
