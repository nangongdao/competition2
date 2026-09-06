import React, { useState } from 'react'

import { Palette, RotateCcw, X } from 'lucide-react'

import type { UiText } from '../i18n'
import { DEFAULT_SUBTITLE_STYLE } from '../subtitle/subtitle-style'
import type { SubtitleStyleConfig } from '../types'


export interface SubtitleStylePanelProps {
  isOpen: boolean
  style: SubtitleStyleConfig
  uiText: UiText
  onChange: (style: SubtitleStyleConfig) => void
  onClose: () => void
}


const POSITION_VALUES = ['bottom', 'middle', 'top'] as const


export const SubtitleStylePanel: React.FC<SubtitleStylePanelProps> = ({
  isOpen,
  style,
  uiText,
  onChange,
  onClose,
}) => {
  const text = uiText.subtitleStyle
  const [resetArmed, setResetArmed] = useState(false)

  if (!isOpen) {
    return null
  }

  const handleReset = (): void => {
    if (!resetArmed) {
      setResetArmed(true)
      window.setTimeout(() => setResetArmed(false), 2600)
      return
    }
    setResetArmed(false)
    onChange({ ...DEFAULT_SUBTITLE_STYLE })
  }

  return (
    <section aria-label={text.ariaLabel} role="dialog" aria-modal="false" className="glossary-panel">
      <div className="glossary-header">
        <div className="glossary-title">
          <Palette size={18} />
          <h3>{text.title}</h3>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            className="btn-secondary"
            style={{ width: 'auto', minHeight: '34px', padding: '0 10px', fontSize: '12px' }}
            onClick={handleReset}
          >
            <RotateCcw size={13} />
            {resetArmed ? text.confirmReset : text.reset}
          </button>
          <button
            type="button"
            className="btn-secondary"
            style={{ width: 'auto', minHeight: '34px', padding: '0 12px', fontSize: '12px' }}
            onClick={onClose}
          >
            <X size={14} />
            {text.close}
          </button>
        </div>
      </div>

      <div className="glossary-body">
        <p className="tm-description" style={{ fontSize: '12px', opacity: 0.78, margin: 0 }}>
          {text.description}
        </p>

        <label className="subtitle-style-row">
          <span>{text.fontSize}</span>
          <div className="subtitle-style-control">
            <input
              type="range"
              min={12}
              max={36}
              step={1}
              value={style.fontSize}
              aria-label={text.fontSize}
              onChange={(event) =>
                onChange({ ...style, fontSize: Number(event.currentTarget.value) })
              }
            />
            <output>{style.fontSize}px</output>
          </div>
        </label>

        <label className="subtitle-style-row">
          <span>{text.fontColor}</span>
          <div className="subtitle-style-control">
            <input
              type="color"
              value={style.fontColor}
              aria-label={text.fontColor}
              onChange={(event) =>
                onChange({ ...style, fontColor: event.currentTarget.value })
              }
            />
            <code>{style.fontColor}</code>
          </div>
        </label>

        <label className="subtitle-style-row">
          <span>{text.backgroundColor}</span>
          <div className="subtitle-style-control">
            <input
              type="color"
              value={style.backgroundColor}
              aria-label={text.backgroundColor}
              onChange={(event) =>
                onChange({ ...style, backgroundColor: event.currentTarget.value })
              }
            />
            <code>{style.backgroundColor}</code>
          </div>
        </label>

        <label className="subtitle-style-row">
          <span>{text.backgroundOpacity}</span>
          <div className="subtitle-style-control">
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={Math.round(style.backgroundOpacity * 100)}
              aria-label={text.backgroundOpacity}
              onChange={(event) =>
                onChange({
                  ...style,
                  backgroundOpacity: Number(event.currentTarget.value) / 100,
                })
              }
            />
            <output>{Math.round(style.backgroundOpacity * 100)}%</output>
          </div>
        </label>

        <div className="subtitle-style-row">
          <span>{text.position}</span>
          <div className="subtitle-style-control">
            <div className="segmented" style={{ flex: 1 }}>
              {POSITION_VALUES.map((position) => {
                const isSelected = style.position === position
                return (
                  <button
                    key={position}
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => onChange({ ...style, position })}
                  >
                    {text.positionOptions[position]}
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        <div className="subtitle-style-preview">
          <div className="subtitle-style-preview-label">{text.preview}</div>
          <div
            className="subtitle-style-preview-box"
            style={{
              backgroundColor: style.backgroundColor,
              opacity: 0.35 + style.backgroundOpacity * 0.55,
              color: style.fontColor,
              fontSize: Math.min(20, Math.max(12, style.fontSize * 0.72)),
            }}
          >
            <div style={{ fontSize: '0.78em', opacity: 0.7 }}>AI real-time interpretation</div>
            <div>实时同声传译字幕预览</div>
          </div>
        </div>
      </div>
    </section>
  )
}
