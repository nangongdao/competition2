import React, { useEffect, useState } from 'react'

import type { AppStatus, SubtitleMode } from '../types'


interface ControlPanelProps {
  status: AppStatus
  connectionState: string
  subtitleMode: SubtitleMode
  translationRevisionCount: number
  asrRevisionCount: number
  lastRevisionReason: 'asr_correction' | 'translation_correction' | null
  onStart: () => void
  onStop: () => void
  onManualRevise: () => void
  onSubtitleModeChange: (mode: SubtitleMode) => void
}


const STATUS_LABELS: Record<AppStatus, string> = {
  idle: '就绪',
  capturing: '正在采集音频',
  translating: '正在翻译',
  error: '错误',
}


const STATUS_COLORS: Record<AppStatus, string> = {
  idle: '#8f9aa8',
  capturing: '#58b06a',
  translating: '#4aa3ff',
  error: '#ff6b5e',
}


const MODE_OPTIONS: Array<{ label: string; value: SubtitleMode }> = [
  { label: '双语', value: 'bilingual' },
  { label: '仅译文', value: 'translation_only' },
  { label: '仅原文', value: 'source_only' },
]


const panelStyle: React.CSSProperties = {
  position: 'fixed',
  top: '16px',
  right: '16px',
  zIndex: 100000,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'stretch',
  gap: '10px',
  minWidth: '248px',
  maxWidth: 'min(88vw, 280px)',
  padding: '14px',
  borderRadius: '16px',
  background: 'rgba(12, 18, 28, 0.84)',
  border: '1px solid rgba(255,255,255,0.08)',
  backdropFilter: 'blur(14px)',
  boxShadow: '0 16px 36px rgba(0, 0, 0, 0.26)',
}


const primaryButtonStyle: React.CSSProperties = {
  minHeight: '44px',
  border: 'none',
  borderRadius: '12px',
  cursor: 'pointer',
  fontSize: '14px',
  fontWeight: 700,
  color: '#fff',
  WebkitTapHighlightColor: 'transparent',
}


const secondaryButtonStyle: React.CSSProperties = {
  minHeight: '40px',
  borderRadius: '12px',
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(255,255,255,0.04)',
  color: '#d9e1eb',
  cursor: 'pointer',
  fontSize: '13px',
  fontWeight: 600,
  WebkitTapHighlightColor: 'transparent',
}


export const ControlPanel: React.FC<ControlPanelProps> = ({
  status,
  connectionState,
  subtitleMode,
  translationRevisionCount,
  asrRevisionCount,
  lastRevisionReason,
  onStart,
  onStop,
  onManualRevise,
  onSubtitleModeChange,
}) => {
  const [showSettings, setShowSettings] = useState(false)
  const isActive = status === 'capturing' || status === 'translating'

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.ctrlKey && event.key.toLowerCase() === 'r') {
        event.preventDefault()
        onManualRevise()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onManualRevise])

  return (
    <div style={panelStyle}>
      <div style={{ display: 'flex', alignItems: 'center', fontSize: '13px', color: '#d9e1eb' }}>
        <span
          style={{
            display: 'inline-block',
            width: '8px',
            height: '8px',
            marginRight: '8px',
            borderRadius: '999px',
            background: STATUS_COLORS[status],
          }}
        />
        <span>{STATUS_LABELS[status]}</span>
      </div>

      <div style={{ fontSize: '11px', color: '#91a0b3' }}>
        WS: {connectionState}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '8px',
        }}
      >
        <div
          style={{
            padding: '8px 10px',
            borderRadius: '12px',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <div style={{ fontSize: '11px', color: '#91a0b3' }}>翻译修正</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#ffffff' }}>
            {translationRevisionCount}
          </div>
        </div>
        <div
          style={{
            padding: '8px 10px',
            borderRadius: '12px',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <div style={{ fontSize: '11px', color: '#91a0b3' }}>ASR 修正</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#ffffff' }}>
            {asrRevisionCount}
          </div>
        </div>
      </div>

      <div style={{ fontSize: '11px', color: '#91a0b3' }}>
        最近修正: {lastRevisionReason === 'asr_correction'
          ? 'ASR'
          : lastRevisionReason === 'translation_correction'
            ? '翻译'
            : '暂无'}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ borderRadius: '12px', overflow: 'hidden' }}>
          <button
            type="button"
            style={{
              ...primaryButtonStyle,
              width: '100%',
              background: isActive ? '#d84b45' : '#29945b',
            }}
            onClick={isActive ? onStop : onStart}
          >
            {isActive ? '停止翻译' : '开始翻译'}
          </button>
        </div>

        <div style={{ borderRadius: '12px', overflow: 'hidden' }}>
          <button
            type="button"
            style={{
              ...secondaryButtonStyle,
              width: '100%',
            }}
            onClick={onManualRevise}
          >
            ↻ 修正一次
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '8px' }}>
        {MODE_OPTIONS.map((option) => {
          const isSelected = option.value === subtitleMode
          return (
            <div
              key={option.value}
              style={{ flex: 1, borderRadius: '10px', overflow: 'hidden' }}
            >
              <button
                type="button"
                style={{
                  ...secondaryButtonStyle,
                  width: '100%',
                  minHeight: '36px',
                  background: isSelected ? 'rgba(74,163,255,0.18)' : 'rgba(255,255,255,0.03)',
                  borderColor: isSelected ? 'rgba(74,163,255,0.4)' : 'rgba(255,255,255,0.1)',
                  color: isSelected ? '#ffffff' : '#b9c5d3',
                }}
                onClick={() => onSubtitleModeChange(option.value)}
              >
                {option.label}
              </button>
            </div>
          )
        })}
      </div>

      <div style={{ borderRadius: '12px', overflow: 'hidden' }}>
        <button
          type="button"
          style={{
            ...secondaryButtonStyle,
            width: '100%',
            minHeight: '34px',
            fontSize: '12px',
          }}
          onClick={() => setShowSettings((value) => !value)}
        >
          {showSettings ? '收起设置' : '展开设置'}
        </button>
      </div>

      {showSettings ? (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            padding: '10px 12px',
            borderRadius: '12px',
            background: 'rgba(255,255,255,0.04)',
            fontSize: '12px',
            color: '#b9c5d3',
          }}
        >
          <div>快捷键：`Ctrl + R` 触发手动修正</div>
          <div>推荐：演示时使用“双语”模式，便于观察修正前后差异</div>
        </div>
      ) : null}
    </div>
  )
}
