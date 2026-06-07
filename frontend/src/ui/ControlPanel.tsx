import React, { useEffect, useState } from 'react'

import type { DesktopOverlayState } from '../desktop/overlay'
import type { WebOverlayState } from '../desktop/web-overlay'
import type { UiText } from '../i18n'
import type {
  AppStatus,
  ClientDiagnostics,
  LanguageConfig,
  RevisionReason,
  SessionDiagnostics,
  SourceLanguage,
  SubtitleMode,
  TtsDiagnostics,
  TtsSettings,
} from '../types'


interface ControlPanelProps {
  status: AppStatus
  connectionState: string
  subtitleMode: SubtitleMode
  languageConfig: LanguageConfig
  subtitleHistoryCount: number
  translationRevisionCount: number
  asrRevisionCount: number
  lastRevisionReason: RevisionReason | null
  serverDiagnostics: SessionDiagnostics | null
  clientDiagnostics: ClientDiagnostics
  ttsSettings: TtsSettings
  ttsDiagnostics: TtsDiagnostics
  desktopOverlayState: DesktopOverlayState
  webOverlayState: WebOverlayState
  uiText: UiText
  onStart: () => void
  onStop: () => void
  onOpenSettings: () => void
  onManualRevise: () => void
  onOpenHistory: () => void
  onDesktopOverlayToggle: () => void
  onWebOverlayToggle: () => void
  onSubtitleModeChange: (mode: SubtitleMode) => void
  onSourceLanguageChange: (language: SourceLanguage) => void
  onTtsEnabledChange: (enabled: boolean) => void
  onTtsVolumeChange: (volume: number) => void
  onTtsRateChange: (rate: number) => void
}


const STATUS_COLORS: Record<AppStatus, string> = {
  idle: '#8f9aa8',
  capturing: '#58b06a',
  translating: '#4aa3ff',
  error: '#ff6b5e',
}


const SOURCE_LANGUAGE_VALUES: SourceLanguage[] = ['auto', 'en', 'ja', 'ko', 'es', 'fr', 'de']


const tapSafeButtonStyle: React.CSSProperties = {
  WebkitTapHighlightColor: 'transparent',
}


const primaryButtonStyle: React.CSSProperties = {
  ...tapSafeButtonStyle,
  minHeight: '44px',
  border: 'none',
  borderRadius: '12px',
  cursor: 'pointer',
  fontSize: '14px',
  fontWeight: 700,
  color: '#fff',
}


const secondaryButtonStyle: React.CSSProperties = {
  ...tapSafeButtonStyle,
  minHeight: '44px',
  borderRadius: '12px',
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(255,255,255,0.04)',
  color: '#d9e1eb',
  cursor: 'pointer',
  fontSize: '13px',
  fontWeight: 600,
}


const metricStyle: React.CSSProperties = {
  minWidth: 0,
  padding: '8px 10px',
  borderRadius: '12px',
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.06)',
}


const buttonClipStyle: React.CSSProperties = {
  borderRadius: '12px',
  overflow: 'hidden',
}


export const ControlPanel: React.FC<ControlPanelProps> = ({
  status,
  connectionState,
  subtitleMode,
  languageConfig,
  subtitleHistoryCount,
  translationRevisionCount,
  asrRevisionCount,
  lastRevisionReason,
  serverDiagnostics,
  clientDiagnostics,
  ttsSettings,
  ttsDiagnostics,
  desktopOverlayState,
  webOverlayState,
  uiText,
  onStart,
  onStop,
  onOpenSettings,
  onManualRevise,
  onOpenHistory,
  onDesktopOverlayToggle,
  onWebOverlayToggle,
  onSubtitleModeChange,
  onSourceLanguageChange,
  onTtsEnabledChange,
  onTtsVolumeChange,
  onTtsRateChange,
}) => {
  const [showDetails, setShowDetails] = useState(false)
  const text = uiText.control
  const isActive = status === 'capturing' || status === 'translating'
  const canUseTts = ttsDiagnostics.isSupported
  const floatingSubtitles = resolveFloatingSubtitleControl(
    desktopOverlayState,
    webOverlayState,
    onDesktopOverlayToggle,
    onWebOverlayToggle,
  )

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
    <aside aria-label={text.ariaLabel} className="live-control-panel">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '10px',
          fontSize: '13px',
          color: '#d9e1eb',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', minWidth: 0 }}>
          <span
            aria-hidden="true"
            style={{
              display: 'inline-block',
              width: '8px',
              height: '8px',
              marginRight: '8px',
              borderRadius: '999px',
              background: STATUS_COLORS[status],
            }}
          />
          <span style={{ minWidth: 0 }}>{text.statusLabels[status]}</span>
        </div>
        <button
          type="button"
          style={{
            ...secondaryButtonStyle,
            minHeight: '34px',
            padding: '0 10px',
            borderRadius: '10px',
            fontSize: '12px',
          }}
          onClick={onOpenSettings}
        >
          {text.settingsButton}
        </button>
      </div>

      <div style={{ fontSize: '11px', color: '#91a0b3' }}>
        {text.websocket}: {connectionState}
      </div>

      <label
        style={{
          display: 'grid',
          gridTemplateColumns: '92px minmax(0, 1fr)',
          alignItems: 'center',
          gap: '8px',
          minHeight: '44px',
          color: '#b9c5d3',
          fontSize: '12px',
        }}
      >
        <span>{text.source}</span>
        <select
          value={languageConfig.sourceLanguage}
          aria-label={text.sourceAriaLabel}
          style={{
            minWidth: 0,
            width: '100%',
            minHeight: '38px',
            padding: '0 10px',
            borderRadius: '10px',
            border: '1px solid rgba(255,255,255,0.14)',
            background: 'rgba(255,255,255,0.06)',
            color: '#e6edf6',
            fontSize: '12px',
            fontWeight: 600,
          }}
          onChange={(event) => onSourceLanguageChange(parseSourceLanguage(event.currentTarget.value))}
        >
          {SOURCE_LANGUAGE_VALUES.map((value) => (
            <option key={value} value={value}>
              {text.sourceOptions[value]}
            </option>
          ))}
        </select>
      </label>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '8px',
        }}
      >
        <div style={metricStyle}>
          <div style={{ fontSize: '11px', color: '#91a0b3' }}>{text.translationFixes}</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#ffffff' }}>
            {translationRevisionCount}
          </div>
        </div>
        <div style={metricStyle}>
          <div style={{ fontSize: '11px', color: '#91a0b3' }}>{text.asrFixes}</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#ffffff' }}>
            {asrRevisionCount}
          </div>
        </div>
      </div>

      <div style={{ fontSize: '11px', color: '#91a0b3' }}>
        {text.lastFix}: {lastRevisionReason ? text.revisionLabels[lastRevisionReason] : text.none}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={buttonClipStyle}>
          <button
            type="button"
            style={{
              ...primaryButtonStyle,
              width: '100%',
              background: isActive ? '#d84b45' : '#29945b',
            }}
            onClick={isActive ? onStop : onStart}
          >
            {isActive ? text.stopTranslation : text.startTranslation}
          </button>
        </div>

        <div style={buttonClipStyle}>
          <button
            type="button"
            style={{
              ...secondaryButtonStyle,
              width: '100%',
            }}
            onClick={onManualRevise}
          >
            {text.reviseNow}
          </button>
        </div>

        <div style={buttonClipStyle}>
          <button
            type="button"
            style={{
              ...secondaryButtonStyle,
              width: '100%',
            }}
            onClick={onOpenHistory}
          >
            {text.historyAndExport(subtitleHistoryCount)}
          </button>
        </div>

        {floatingSubtitles.available ? (
          <div style={buttonClipStyle}>
            <button
              type="button"
              aria-pressed={floatingSubtitles.visible}
              style={{
                ...secondaryButtonStyle,
                width: '100%',
                background: floatingSubtitles.visible
                  ? 'rgba(74,163,255,0.18)'
                  : 'rgba(255,255,255,0.04)',
                borderColor: floatingSubtitles.visible
                  ? 'rgba(74,163,255,0.4)'
                  : 'rgba(255,255,255,0.1)',
              }}
              onClick={floatingSubtitles.onToggle}
            >
              {floatingSubtitles.visible
                ? text.closeFloatingSubtitles
                : text.openFloatingSubtitles}
            </button>
          </div>
        ) : null}
      </div>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          padding: '10px',
          borderRadius: '12px',
          background: 'rgba(255,255,255,0.04)',
          border: '1px solid rgba(255,255,255,0.07)',
        }}
      >
        <div style={buttonClipStyle}>
          <button
            type="button"
            aria-pressed={ttsSettings.enabled}
            disabled={!canUseTts}
            style={{
              ...secondaryButtonStyle,
              width: '100%',
              background: ttsSettings.enabled ? 'rgba(74,163,255,0.18)' : 'rgba(255,255,255,0.04)',
              borderColor: ttsSettings.enabled ? 'rgba(74,163,255,0.4)' : 'rgba(255,255,255,0.1)',
              color: canUseTts ? '#ffffff' : '#718093',
              cursor: canUseTts ? 'pointer' : 'not-allowed',
            }}
            onClick={() => onTtsEnabledChange(!ttsSettings.enabled)}
          >
              {canUseTts
                ? (ttsSettings.enabled ? text.voiceOn : text.voiceOff)
                : text.voiceUnavailable}
            </button>
        </div>

        <VoiceSlider
          label={text.volume}
          value={ttsSettings.volume}
          min={0}
          max={1}
          step={0.05}
          disabled={!canUseTts}
          displayValue={`${Math.round(ttsSettings.volume * 100)}%`}
          onChange={onTtsVolumeChange}
        />

        <VoiceSlider
          label={text.rate}
          value={ttsSettings.rate}
          min={0.7}
          max={1.35}
          step={0.05}
          disabled={!canUseTts}
          displayValue={`${ttsSettings.rate.toFixed(2)}x`}
          onChange={onTtsRateChange}
        />

        <div style={{ color: '#91a0b3', fontSize: '11px' }}>
          {text.voiceStatus(
            ttsDiagnostics.isSpeaking ? text.voiceStates.speaking : text.voiceStates.idle,
            ttsDiagnostics.queueLength,
          )}
        </div>
      </div>

      <div className="control-mode-group">
        {text.modeOptions.map((option) => {
          const isSelected = option.value === subtitleMode
          return (
            <div
              key={option.value}
              className="control-mode-option"
            >
              <button
                type="button"
                aria-pressed={isSelected}
                style={{
                  ...secondaryButtonStyle,
                  width: '100%',
                  minHeight: '44px',
                  padding: '0 6px',
                  fontSize: '12px',
                  lineHeight: 1.12,
                  overflowWrap: 'anywhere',
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

      <div style={buttonClipStyle}>
        <button
          type="button"
          style={{
            ...secondaryButtonStyle,
            width: '100%',
            minHeight: '44px',
            fontSize: '12px',
          }}
          onClick={() => setShowDetails((value) => !value)}
        >
          {showDetails ? text.hideDetails : text.showDetails}
        </button>
      </div>

      {showDetails ? (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'stretch',
            gap: '6px',
            padding: '10px 12px',
            borderRadius: '12px',
            background: 'rgba(255,255,255,0.04)',
            fontSize: '12px',
            lineHeight: 1.42,
            color: '#b9c5d3',
          }}
        >
          <DetailRow label={text.details.session} value={serverDiagnostics?.session_id ?? clientDiagnostics.sessionId} />
          <DetailRow label={text.details.capture} value={formatCaptureBackend(clientDiagnostics.captureBackend, text)} />
          <DetailRow label={text.details.voice} value={formatVoiceStatus(ttsDiagnostics, text)} />
          <DetailRow label={text.details.voiceQueue} value={ttsDiagnostics.queueLength.toString()} />
          <DetailRow label={text.details.voiceErrors} value={ttsDiagnostics.failedUtterances.toString()} />
          <DetailRow label={text.details.sentChunks} value={clientDiagnostics.sentAudioChunks.toString()} />
          <DetailRow label={text.details.clientDrops} value={clientDiagnostics.droppedAudioChunks.toString()} />
          <DetailRow label={text.details.serverDrops} value={(serverDiagnostics?.audio_chunks_dropped ?? 0).toString()} />
          <DetailRow label={text.details.reconnects} value={clientDiagnostics.reconnectAttempts.toString()} />
          <DetailRow
            label={text.details.asrLatency}
            value={formatLatency(serverDiagnostics?.latency.capture_to_asr_ms)}
          />
          <DetailRow
            label={text.details.firstToken}
            value={formatLatency(serverDiagnostics?.latency.asr_to_first_token_ms)}
          />
          <DetailRow
            label={text.details.finalText}
            value={formatLatency(serverDiagnostics?.latency.asr_to_translation_final_ms)}
          />
          <DetailRow
            label={text.details.apiCalls}
            value={formatCounterMap(serverDiagnostics?.api_call_counts)}
          />
        </div>
      ) : null}
    </aside>
  )
}


interface DetailRowProps {
  label: string
  value: string
}


interface VoiceSliderProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  disabled: boolean
  displayValue: string
  onChange: (value: number) => void
}


const VoiceSlider: React.FC<VoiceSliderProps> = ({
  label,
  value,
  min,
  max,
  step,
  disabled,
  displayValue,
  onChange,
}) => (
  <label
    style={{
      display: 'grid',
      gridTemplateColumns: '68px minmax(0, 1fr) 48px',
      alignItems: 'center',
      gap: '8px',
      minHeight: '44px',
      color: disabled ? '#718093' : '#b9c5d3',
      fontSize: '12px',
    }}
  >
    <span>{label}</span>
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      disabled={disabled}
      style={{
        width: '100%',
        accentColor: '#4aa3ff',
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
      onChange={(event) => onChange(Number(event.currentTarget.value))}
    />
    <span style={{ textAlign: 'right' }}>{displayValue}</span>
  </label>
)


const DetailRow: React.FC<DetailRowProps> = ({ label, value }) => (
  <div
    style={{
      display: 'grid',
      gridTemplateColumns: 'minmax(86px, 0.8fr) minmax(0, 1.2fr)',
      gap: '8px',
      minWidth: 0,
    }}
  >
    <span style={{ color: '#7f8ea3' }}>{label}</span>
    <span style={{ color: '#d9e1eb', wordBreak: 'break-word' }}>{value || '-'}</span>
  </div>
)


function formatLatency(summary: { count: number; avg_ms: number; max_ms: number } | undefined): string {
  if (!summary || summary.count === 0) {
    return '-'
  }
  return `${summary.avg_ms}ms avg`
}


function formatCaptureBackend(
  backend: ClientDiagnostics['captureBackend'],
  text: UiText['control'],
): string {
  switch (backend) {
    case 'audio-worklet':
      return text.captureBackends.audioWorklet
    case 'script-processor':
      return text.captureBackends.scriptProcessor
    default:
      return text.captureBackends.unknown
  }
}


function formatVoiceStatus(diagnostics: TtsDiagnostics, text: UiText['control']): string {
  if (!diagnostics.isSupported) {
    return text.voiceStates.unsupported
  }
  if (!diagnostics.enabled) {
    return text.voiceStates.off
  }
  return diagnostics.isSpeaking ? text.voiceStates.speaking : text.voiceStates.ready
}


function formatCounterMap(values: Record<string, number> | undefined): string {
  if (!values) {
    return '-'
  }

  const entries = Object.entries(values)
    .filter(([, value]) => value > 0)
    .map(([key, value]) => `${key}:${value}`)

  return entries.length > 0 ? entries.join(', ') : '-'
}


function parseSourceLanguage(value: string): SourceLanguage {
  const option = SOURCE_LANGUAGE_VALUES.find((item) => item === value)
  return option ?? 'en'
}


interface FloatingSubtitleControl {
  available: boolean
  visible: boolean
  onToggle: () => void
}


function resolveFloatingSubtitleControl(
  desktopOverlayState: DesktopOverlayState,
  webOverlayState: WebOverlayState,
  onDesktopOverlayToggle: () => void,
  onWebOverlayToggle: () => void,
): FloatingSubtitleControl {
  if (desktopOverlayState.available) {
    return {
      available: true,
      visible: desktopOverlayState.visible,
      onToggle: onDesktopOverlayToggle,
    }
  }

  return {
    available: webOverlayState.available,
    visible: webOverlayState.visible,
    onToggle: onWebOverlayToggle,
  }
}
