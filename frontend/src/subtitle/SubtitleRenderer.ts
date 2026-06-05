import type { SubtitleEntry, SubtitleMode } from '../types'


export interface SubtitleRendererConfig {
  container: HTMLElement
  maxLines?: number
  bottomOffset?: string
}


export class SubtitleRenderer {
  private _overlay: HTMLDivElement
  private _maxLines: number
  private _entries: Map<string, HTMLDivElement> = new Map()
  private _mode: SubtitleMode = 'bilingual'
  private static _styleInjected = false

  constructor(config: SubtitleRendererConfig) {
    this._maxLines = config.maxLines ?? 6

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

    config.container.appendChild(this._overlay)
  }

  setMode(mode: SubtitleMode): void {
    this._mode = mode
  }

  render(entry: SubtitleEntry): void {
    const existing = this._entries.get(entry.segmentId)
    if (existing) {
      this._updateText(existing, entry)
    } else {
      const element = this._createSubtitleElement(entry)
      this._overlay.appendChild(element)
      this._entries.set(entry.segmentId, element)
    }

    this._trim()
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

    const source = document.createElement('div')
    source.className = 'subtitle-source'

    const translated = document.createElement('div')
    translated.className = 'subtitle-translated'

    const cursor = document.createElement('span')
    cursor.className = 'subtitle-cursor'
    cursor.textContent = '|'

    wrapper.appendChild(source)
    wrapper.appendChild(translated)
    wrapper.appendChild(cursor)

    this._applyEntryState(wrapper, source, translated, cursor, entry)
    return wrapper
  }

  private _updateText(element: HTMLDivElement, entry: SubtitleEntry): void {
    const source = element.querySelector('.subtitle-source')
    const translated = element.querySelector('.subtitle-translated')
    const cursor = element.querySelector('.subtitle-cursor')

    if (
      !(source instanceof HTMLDivElement) ||
      !(translated instanceof HTMLDivElement) ||
      !(cursor instanceof HTMLSpanElement)
    ) {
      return
    }

    this._applyEntryState(element, source, translated, cursor, entry)
  }

  private _applyEntryState(
    wrapper: HTMLDivElement,
    source: HTMLDivElement,
    translated: HTMLDivElement,
    cursor: HTMLSpanElement,
    entry: SubtitleEntry,
  ): void {
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
        background: rgba(6, 10, 16, 0.78);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.22);
        text-align: center;
        transition: opacity 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
      }

      .subtitle-source {
        color: rgba(226, 234, 245, 0.8);
        font-size: 15px;
        line-height: 1.4;
        word-break: break-word;
      }

      .subtitle-translated {
        color: #ffffff;
        font-size: 21px;
        font-weight: 600;
        line-height: 1.45;
        word-break: break-word;
      }

      .subtitle-entry.only-source .subtitle-source {
        font-size: 20px;
        color: #ffffff;
      }

      .subtitle-entry.only-translated .subtitle-translated {
        font-size: 22px;
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
