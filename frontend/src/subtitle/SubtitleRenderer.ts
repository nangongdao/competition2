import type { SubtitleEntry, SubtitleMode, SubtitleStyleConfig } from '../types'
import { speakerColor } from './speaker'
import { DEFAULT_SUBTITLE_STYLE } from './subtitle-style'
import type { SubtitleStore } from './SubtitleStore'


export interface SubtitleRendererConfig {
  container: HTMLElement
  maxLines?: number
  bottomOffset?: string
  style?: SubtitleStyleConfig
}


export class SubtitleRenderer {
  private _overlay: HTMLDivElement
  private _maxLines: number
  private _entries: Map<string, HTMLDivElement> = new Map()
  /** 已渲染内容的签名，用于跳过未变化的条目（第二梯队-方向 3）。 */
  private _renderedContent: Map<string, string> = new Map()
  private _mode: SubtitleMode = 'bilingual'
  private _style: SubtitleStyleConfig = { ...DEFAULT_SUBTITLE_STYLE }
  private static _styleInjected = false

  constructor(config: SubtitleRendererConfig) {
    this._maxLines = config.maxLines ?? 6
    this._style = config.style ? { ...config.style } : { ...DEFAULT_SUBTITLE_STYLE }

    if (!SubtitleRenderer._styleInjected) {
      SubtitleRenderer._injectStyles()
      SubtitleRenderer._styleInjected = true
    }

    this._overlay = document.createElement('div')
    this._overlay.id = 'subtitle-overlay'
    this._overlay.style.cssText = `
      position: fixed;
      left: 50%;
      bottom: ${config.bottomOffset ?? '12%'};
      transform: translateX(-50%);
      width: min(92vw, 960px);
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 8px;
      z-index: 99999;
      pointer-events: none;
      font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    `

    this._applyStyle()
    config.container.appendChild(this._overlay)
  }

  setMode(mode: SubtitleMode): void {
    this._mode = mode
  }

  setStyle(style: SubtitleStyleConfig): void {
    this._style = { ...style }
    this._applyStyle()
  }

  private _applyStyle(): void {
    this._overlay.style.setProperty('--subtitle-font-size', `${this._style.fontSize}px`)
    this._overlay.style.setProperty('--subtitle-font-color', this._style.fontColor)
    this._overlay.style.setProperty(
      '--subtitle-background',
      toRgba(this._style.backgroundColor, this._style.backgroundOpacity),
    )
    this._overlay.style.setProperty('--subtitle-position', this._style.position)

    const positionMap = { bottom: '12%', middle: '45%', top: '10%' } as const
    this._overlay.style.bottom = positionMap[this._style.position]
    this._overlay.style.top = this._style.position === 'top' ? positionMap.top : 'auto'
  }

  render(entry: SubtitleEntry): void {
    const signature = contentSignature(entry, this._mode)
    const existing = this._entries.get(entry.segmentId)
    if (!existing) {
      const element = this._createSubtitleElement(entry)
      this._overlay.appendChild(element)
      this._entries.set(entry.segmentId, element)
      this._renderedContent.set(entry.segmentId, signature)
    } else if (this._renderedContent.get(entry.segmentId) !== signature) {
      this._updateText(existing, entry)
      this._renderedContent.set(entry.segmentId, signature)
    }

    this._trim()
  }

  /**
   * 第二梯队-方向 3：单一数据流入口。
   *
   * 从字幕 Store 的可见快照一次性做 DOM 对账（新增/更新/移除），
   * 避免调用方在每次消息到达时全量重绘所有字幕。仅更新内容发生变化的条目。
   */
  syncFromStore(store: SubtitleStore): void {
    const { visible } = store.getSnapshot()
    const visibleIds = new Set<string>()

    for (const entry of visible) {
      visibleIds.add(entry.segmentId)
      this.render(entry)
    }

    // 移除已不在可见列表中的 DOM 条目（滚出/被清理）。
    const staleIds = Array.from(this._entries.keys()).filter((id) => !visibleIds.has(id))
    for (const id of staleIds) {
      const element = this._entries.get(id)
      if (element) {
        element.remove()
      }
      this._entries.delete(id)
      this._renderedContent.delete(id)
    }
  }

  revise(segmentId: string, newText: string): void {
    const element = this._entries.get(segmentId)
    if (!element) {
      return
    }

    element.style.transition = 'opacity 120ms ease'
    element.style.opacity = '0.35'

    window.setTimeout(() => {
      const target = element.querySelector('.subtitle-translated')
      if (target instanceof HTMLDivElement) {
        target.textContent = newText
      }

      element.style.opacity = '1'
      element.classList.add('revised')
      window.setTimeout(() => element.classList.remove('revised'), 1800)
    }, 120)
  }

  reset(): void {
    this._entries.clear()
    this._renderedContent.clear()
    this._overlay.innerHTML = ''
  }

  destroy(): void {
    this.reset()
    this._overlay.remove()
  }

  private _createSubtitleElement(entry: SubtitleEntry): HTMLDivElement {
    const wrapper = document.createElement('div')
    wrapper.className = 'subtitle-entry'
    wrapper.dataset.segmentId = entry.segmentId

    const speaker = document.createElement('div')
    speaker.className = 'subtitle-speaker'

    const source = document.createElement('div')
    source.className = 'subtitle-source'

    const translated = document.createElement('div')
    translated.className = 'subtitle-translated'

    const cursor = document.createElement('span')
    cursor.className = 'subtitle-cursor'
    cursor.textContent = '|'

    wrapper.appendChild(speaker)
    wrapper.appendChild(source)
    wrapper.appendChild(translated)
    wrapper.appendChild(cursor)

    this._applyEntryState(wrapper, speaker, source, translated, cursor, entry)
    return wrapper
  }

  private _updateText(element: HTMLDivElement, entry: SubtitleEntry): void {
    const speaker = element.querySelector('.subtitle-speaker')
    const source = element.querySelector('.subtitle-source')
    const translated = element.querySelector('.subtitle-translated')
    const cursor = element.querySelector('.subtitle-cursor')

    if (
      !(speaker instanceof HTMLDivElement) ||
      !(source instanceof HTMLDivElement) ||
      !(translated instanceof HTMLDivElement) ||
      !(cursor instanceof HTMLSpanElement)
    ) {
      return
    }

    this._applyEntryState(element, speaker, source, translated, cursor, entry)
  }

  private _applyEntryState(
    wrapper: HTMLDivElement,
    speaker: HTMLDivElement,
    source: HTMLDivElement,
    translated: HTMLDivElement,
    cursor: HTMLSpanElement,
    entry: SubtitleEntry,
  ): void {
    speaker.textContent = entry.speaker ?? ''
    speaker.style.display = entry.speaker ? 'block' : 'none'
    speaker.style.color = entry.speaker ? speakerColor(entry.speaker) : ''

    source.textContent = entry.sourceText
    translated.textContent = entry.translatedText

    const showSource = this._mode !== 'translation_only' && entry.sourceText.length > 0
    const showTranslated =
      this._mode !== 'source_only' && entry.translatedText.length > 0

    source.style.display = showSource ? 'block' : 'none'
    translated.style.display = showTranslated ? 'block' : 'none'
    cursor.style.display = entry.isPartial ? 'inline-block' : 'none'

    wrapper.classList.toggle('only-source', showSource && !showTranslated)
    wrapper.classList.toggle('only-translated', showTranslated && !showSource)
  }

  private _trim(): void {
    const children = Array.from(this._overlay.children)
    while (children.length > this._maxLines) {
      const oldest = children.shift()
      if (!(oldest instanceof HTMLDivElement)) {
        continue
      }

      const segmentId = oldest.dataset.segmentId
      if (segmentId) {
        this._entries.delete(segmentId)
      }

      oldest.style.opacity = '0'
      oldest.style.transform = 'translateY(12px)'
      window.setTimeout(() => oldest.remove(), 220)
    }
  }

  private static _injectStyles(): void {
    if (typeof document === 'undefined') {
      return
    }

    const style = document.createElement('style')
    style.textContent = `
      @keyframes subtitle-blink {
        0%, 50% { opacity: 1; }
        51%, 100% { opacity: 0; }
      }

      .subtitle-entry {
        display: flex;
        flex-direction: column;
        align-items: stretch;
        gap: 4px;
        min-width: 0;
        padding: 10px 14px;
        border-radius: 14px;
        background: var(--subtitle-background, rgba(6, 10, 16, 0.78));
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.22);
        text-align: center;
        transition: opacity 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
      }

      .subtitle-source {
        color: rgba(226, 234, 245, 0.8);
        font-size: max(13px, calc(var(--subtitle-font-size, 22px) - 6px));
        line-height: 1.4;
        word-break: break-word;
      }

      .subtitle-speaker {
        align-self: center;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.4px;
        text-transform: uppercase;
        opacity: 0.92;
      }

      .subtitle-translated {
        color: var(--subtitle-font-color, #ffffff);
        font-size: var(--subtitle-font-size, 22px);
        font-weight: 600;
        line-height: 1.45;
        word-break: break-word;
      }

      .subtitle-entry.only-source .subtitle-source {
        font-size: var(--subtitle-font-size, 22px);
        color: var(--subtitle-font-color, #ffffff);
      }

      .subtitle-entry.only-translated .subtitle-translated {
        font-size: calc(var(--subtitle-font-size, 22px) + 2px);
      }

      .subtitle-cursor {
        align-self: center;
        margin-top: 2px;
        color: #f4c84c;
        animation: subtitle-blink 0.7s infinite;
      }

      .subtitle-entry.revised {
        border-color: rgba(244, 200, 76, 0.5);
      }
    `
    document.head.appendChild(style)
  }
}


function toRgba(hexColor: string, opacity: number): string {
  const normalizedHex = hexColor.replace('#', '')
  const red = parseInt(normalizedHex.slice(0, 2), 16)
  const green = parseInt(normalizedHex.slice(2, 4), 16)
  const blue = parseInt(normalizedHex.slice(4, 6), 16)
  if ([red, green, blue].some((channel) => Number.isNaN(channel))) {
    return 'rgba(10, 14, 22, 0.78)'
  }
  return `rgba(${red}, ${green}, ${blue}, ${Math.min(1, Math.max(0, opacity)).toFixed(2)})`
}

/**
 * 计算条目在给定显示模式下的渲染内容签名，用于跳过未变化条目的 DOM 写入。
 *
 * 包含：说话人、原文、译文、是否 partial（光标显隐）。
 */
function contentSignature(entry: SubtitleEntry, mode: SubtitleMode): string {
  return [
    entry.speaker ?? '',
    entry.sourceText,
    entry.translatedText,
    entry.isPartial ? 'p' : 'f',
    mode,
  ].join('\u0001')
}
