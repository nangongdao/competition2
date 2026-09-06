import React, { useEffect, useRef, useState } from 'react'

import {
  BookMarked,
  BookOpenText,
  ChevronDown,
  ChevronUp,
  CircleCheck,
  CircleX,
  Cpu,
  Coins,
  Database,
  FileUp,
  History,
  Languages,
  Mic,
  Palette,
  Pause,
  Play,
  RefreshCw,
  Settings,
  Sparkles,
  TerminalSquare,
  TrendingUp,
  Users,
  Volume2,
  VolumeX,
  Wallet,
} from 'lucide-react'

import type { DesktopOverlayState } from '../desktop/overlay'
import type { WebOverlayState } from '../desktop/web-overlay'
import type { UiText } from '../i18n'
import type {
  AppStatus,
  AudioSourceType,
  ClientDiagnostics,
  LanguageConfig,
  RevisionReason,
  SessionDiagnostics,
  SourceLanguage,
  SubtitleMode,
  TargetLanguage,
  TtsDiagnostics,
  TtsEngine,
  TtsSettings,
  TranslationStyle,
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
  audioSource: AudioSourceType
  audioFileName: string | null
  audioFileEnded: boolean
  ttsSettings: TtsSettings
  ttsDiagnostics: TtsDiagnostics
  ttsEngine: TtsEngine
  /** 当前翻译风格预设（阶段 3）。 */
  translationStyle: TranslationStyle
  /** 阶段 2：ASR 术语热词注入开关。 */
  asrHotwordsEnabled: boolean
  /** 阶段 8：auto 模式下 Whisper 检测到的源语言代码（如 en/ja），未检测时为 null。 */
  detectedSourceLanguage: string | null
  desktopOverlayState: DesktopOverlayState
  webOverlayState: WebOverlayState
  uiText: UiText
  onStart: () => void
  onStop: () => void
  onOpenSettings: () => void
  onManualRevise: () => void
  onOpenHistory: () => void
  onOpenTerminal: () => void
  onOpenSummary: () => void
  onOpenGlossary: () => void
  onOpenTranslationMemory: () => void
  onOpenSubtitleStyle: () => void
  onOpenCollaboration: () => void
  onOpenSubscription: () => void
  onOpenCost: () => void
  onOpenSessionHistory: () => void
  onOpenRevisionTimeline: () => void
  onGlossaryImport: (file: File) => Promise<boolean> | boolean
  onDesktopOverlayToggle: () => void
  onWebOverlayToggle: () => void
  onSubtitleModeChange: (mode: SubtitleMode) => void
  onSourceLanguageChange: (language: SourceLanguage) => void
  onTargetLanguageChange: (language: TargetLanguage) => void
  onTranslationStyleChange: (style: TranslationStyle) => void
  onAsrHotwordsEnabledChange: (enabled: boolean) => void
  onTtsEnabledChange: (enabled: boolean) => void
  onTtsEngineChange: (engine: TtsEngine) => void
  onTtsVolumeChange: (volume: number) => void
  onTtsRateChange: (rate: number) => void
  onAudioSourceChange: (source: AudioSourceType, file?: File) => Promise<boolean> | boolean
}


const STATUS_CLASS: Record<AppStatus, string> = {
  idle: 'idle',
  capturing: 'capturing',
  translating: 'translating',
  error: 'error',
}


const SOURCE_LANGUAGE_VALUES: SourceLanguage[] = ['auto', 'en', 'zh-CN', 'ja', 'ko', 'es', 'fr', 'de']
const TARGET_LANGUAGE_VALUES: TargetLanguage[] = ['zh-CN', 'en', 'ja', 'ko', 'es', 'fr', 'de']
const TRANSLATION_STYLE_VALUES: TranslationStyle[] = ['concise', 'faithful', 'lecture']


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
  audioSource,
  audioFileName,
  audioFileEnded,
  ttsSettings,
  ttsDiagnostics,
  ttsEngine,
  translationStyle,
  asrHotwordsEnabled,
  detectedSourceLanguage,
  desktopOverlayState,
  webOverlayState,
  uiText,
  onStart,
  onStop,
  onOpenSettings,
  onManualRevise,
  onOpenHistory,
  onOpenTerminal,
  onOpenSummary,
  onOpenGlossary,
  onOpenTranslationMemory,
  onOpenSubtitleStyle,
  onOpenCollaboration,
  onOpenSubscription,
  onOpenCost,
  onOpenSessionHistory,
  onOpenRevisionTimeline,
  onGlossaryImport,
  onDesktopOverlayToggle,
  onWebOverlayToggle,
  onSubtitleModeChange,
  onSourceLanguageChange,
  onTargetLanguageChange,
  onTranslationStyleChange,
  onAsrHotwordsEnabledChange,
  onTtsEnabledChange,
  onTtsEngineChange,
  onTtsVolumeChange,
  onTtsRateChange,
  onAudioSourceChange,
}) => {
  const [showDetails, setShowDetails] = useState(false)
  const [glossaryStatus, setGlossaryStatus] = useState<'idle' | 'ok' | 'failed'>('idle')
  const glossaryInputRef = useRef<HTMLInputElement>(null)
  const audioFileInputRef = useRef<HTMLInputElement>(null)
  const [fileLoadState, setFileLoadState] = useState<'idle' | 'ok' | 'failed'>('idle')
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
      <div className="panel-header">
        <div className="panel-brand">
          <div className="panel-brand-logo">
            <Languages size={18} />
          </div>
          <div className="panel-brand-name">{uiText.appName}</div>
        </div>
        <button
          type="button"
          className="btn-secondary"
          style={{ minHeight: '34px', width: 'auto', padding: '0 12px', fontSize: '12px' }}
          onClick={onOpenSettings}
        >
          <Settings size={14} />
          {text.settingsButton}
        </button>
      </div>

      <div className="panel-status">
        <span className={`status-dot ${STATUS_CLASS[status]}`} />
        <span>{text.statusLabels[status]}</span>
      </div>

      <div className={`connection-label connection-${connectionState === 'connected' ? 'ok' : 'warn'}`}>
        <WifiIcon />
        <span>{text.websocket}: {connectionState}</span>
        {connectionState !== 'connected' ? <span className="connection-hint">{text.connectionHint}</span> : null}
      </div>

      <div className="panel-group-title">
        <Languages size={13} />
        {text.groupLanguages}
      </div>

      <label className="field">
        <span>
          <Languages size={14} />
          {text.source}
        </span>
        <select
          value={languageConfig.sourceLanguage}
          aria-label={text.sourceAriaLabel}
          onChange={(event) => onSourceLanguageChange(parseSourceLanguage(event.currentTarget.value))}
        >
          {SOURCE_LANGUAGE_VALUES.map((value) => (
            <option key={value} value={value}>
              {text.sourceOptions[value]}
            </option>
          ))}
        </select>
        {languageConfig.sourceLanguage === 'auto' && detectedSourceLanguage && (
          <span className="field-hint detected-language-hint">
            {text.detectedSource(detectedSourceLanguage)}
          </span>
        )}
      </label>

      <label className="field">
        <span>
          <Languages size={14} />
          {text.target}
        </span>
        <select
          value={languageConfig.targetLanguage}
          aria-label={text.targetAriaLabel}
          onChange={(event) => onTargetLanguageChange(parseTargetLanguage(event.currentTarget.value))}
        >
          {TARGET_LANGUAGE_VALUES.map((value) => (
            <option key={value} value={value}>
              {text.targetOptions[value]}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>
          <Sparkles size={14} />
          {text.translationStyle}
        </span>
        <select
          value={translationStyle}
          aria-label={text.translationStyleAriaLabel}
          onChange={(event) => onTranslationStyleChange(parseTranslationStyle(event.currentTarget.value))}
        >
          {TRANSLATION_STYLE_VALUES.map((value) => (
            <option key={value} value={value}>
              {text.translationStyleOptions[value]}
            </option>
          ))}
        </select>
      </label>

      <label className="field field-checkbox">
        <input
          type="checkbox"
          checked={asrHotwordsEnabled}
          aria-label={text.asrHotwords}
          onChange={(event) => onAsrHotwordsEnabledChange(event.currentTarget.checked)}
        />
        <span className="field-checkbox-label">
          <BookMarked size={14} />
          {text.asrHotwords}
        </span>
      </label>

      <label className="field">
        <span>
          <Mic size={14} />
          {text.audioSource}
        </span>
        <select
          value={audioSource}
          aria-label={text.audioSource}
          onChange={(event) => {
            const next = event.currentTarget.value as AudioSourceType
            if (next === 'file') {
              // 文件源：先弹出文件选择，选完后再切换源并加载。
              audioFileInputRef.current?.click()
              return
            }
            void onAudioSourceChange(next)
          }}
        >
          {text.audioSourceOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {audioSource === 'file' && (
          <span className={`field-hint ${audioFileEnded ? 'file-ended' : ''}`}>
            {audioFileEnded
              ? text.audioFileEnded
              : audioFileName
                ? text.audioFileLoaded
                : fileLoadState === 'failed'
                  ? text.audioFileLoadFailed
                  : text.audioFilePick}
          </span>
        )}
      </label>

      <input
        ref={audioFileInputRef}
        type="file"
        accept="audio/*,.wav,.mp3,.ogg,.flac,.m4a"
        className="visually-hidden"
        aria-label={text.audioFilePick}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0]
          event.currentTarget.value = ''
          if (!file) {
            return
          }
          const result = onAudioSourceChange('file', file)
          Promise.resolve(result)
            .then((ok) => {
              setFileLoadState(ok ? 'ok' : 'failed')
            })
            .catch(() => setFileLoadState('failed'))
        }}
      />

      <div className="metric-row">
        <div className="metric-card">
          <div className="metric-label">
            <RefreshCw size={13} />
            {text.translationFixes}
          </div>
          <div className="metric-value">{translationRevisionCount}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">
            <Mic size={13} />
            {text.asrFixes}
          </div>
          <div className="metric-value">{asrRevisionCount}</div>
        </div>
      </div>

      <div className="connection-label">
        <CircleCheck size={13} />
        <span>{text.lastFix}: {lastRevisionReason ? text.revisionLabels[lastRevisionReason] : text.none}</span>
      </div>

      <div className="panel-group-title">
        <Play size={13} />
        {text.groupActions}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <button
          type="button"
          className={`btn-primary ${isActive ? 'stop' : 'start'}`}
          onClick={isActive ? onStop : onStart}
        >
          {isActive ? <Pause size={18} /> : <Play size={18} />}
          {isActive ? text.stopTranslation : text.startTranslation}
        </button>

        <button type="button" className="btn-secondary" onClick={onManualRevise}>
          <RefreshCw size={16} />
          {text.reviseNow}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenHistory}>
          <History size={16} />
          {text.historyAndExport(subtitleHistoryCount)}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenTerminal}>
          <TerminalSquare size={16} />
          {text.openTerminal}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenSummary}>
          <Sparkles size={16} />
          {text.openSummary}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenGlossary}>
          <BookOpenText size={16} />
          {text.openGlossary}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenTranslationMemory}>
          <BookMarked size={16} />
          {text.openTranslationMemory}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenSubtitleStyle}>
          <Palette size={16} />
          {text.openSubtitleStyle}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenCollaboration}>
          <Users size={16} />
          {text.openCollaboration}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenSubscription}>
          <Wallet size={16} />
          {text.openSubscription}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenCost}>
          <Coins size={16} />
          {text.openCost}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenSessionHistory}>
          <Database size={16} />
          {text.openSessionHistory}
        </button>

        <button type="button" className="btn-secondary" onClick={onOpenRevisionTimeline}>
          <TrendingUp size={16} />
          {text.openRevisionTimeline}
        </button>

        <input
          ref={glossaryInputRef}
          type="file"
          accept=".json,.csv"
          style={{ display: 'none' }}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (!file) {
              return
            }
            const result = onGlossaryImport(file)
            const resolved = result instanceof Promise ? result : Promise.resolve(result)
            resolved
              .then((success) => setGlossaryStatus(success ? 'ok' : 'failed'))
              .catch(() => setGlossaryStatus('failed'))
            event.target.value = ''
            window.setTimeout(() => setGlossaryStatus('idle'), 2000)
          }}
        />
        <button
          type="button"
          className="btn-secondary"
          style={glossaryStatus === 'failed' ? { color: 'var(--red)' } : glossaryStatus === 'ok' ? { color: 'var(--green)' } : undefined}
          onClick={() => glossaryInputRef.current?.click()}
        >
          {glossaryStatus === 'failed' ? (
            <CircleX size={16} />
          ) : glossaryStatus === 'ok' ? (
            <CircleCheck size={16} />
          ) : (
            <FileUp size={16} />
          )}
          {glossaryStatus === 'failed'
            ? text.glossaryImportFailed
            : glossaryStatus === 'ok'
              ? text.glossaryImported
              : text.glossaryImport}
        </button>

        {floatingSubtitles.available ? (
          <button
            type="button"
            aria-pressed={floatingSubtitles.visible}
            className="btn-secondary"
            style={floatingSubtitles.visible ? undefined : undefined}
            onClick={floatingSubtitles.onToggle}
          >
            <BookOpenText size={16} />
            {floatingSubtitles.visible
              ? text.closeFloatingSubtitles
              : text.openFloatingSubtitles}
          </button>
        ) : null}
      </div>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          padding: '12px',
          borderRadius: '16px',
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid var(--line)',
        }}
      >
        <button
          type="button"
          aria-pressed={ttsSettings.enabled}
          disabled={!canUseTts}
          className="btn-secondary"
          style={ttsSettings.enabled ? undefined : undefined}
          onClick={() => onTtsEnabledChange(!ttsSettings.enabled)}
        >
          {ttsSettings.enabled ? <Volume2 size={16} /> : <VolumeX size={16} />}
          {canUseTts
            ? (ttsSettings.enabled ? text.voiceOn : text.voiceOff)
            : text.voiceUnavailable}
        </button>

        <label className="connection-label" style={{ gap: '6px' }}>
          <Cpu size={13} />
          <span>{text.voiceEngine}</span>
          <select
            aria-label={text.voiceEngine}
            value={ttsEngine}
            disabled={!canUseTts}
            onChange={(event) => onTtsEngineChange(event.target.value as TtsEngine)}
            style={{
              flex: 1,
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid var(--line)',
              color: 'inherit',
              borderRadius: '8px',
              padding: '4px 8px',
              fontSize: '12px',
            }}
          >
            {text.voiceEngineOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

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

        <div className="connection-label">
          <Volume2 size={13} />
          {text.voiceStatus(
            ttsDiagnostics.isSpeaking ? text.voiceStates.speaking : text.voiceStates.idle,
            ttsDiagnostics.queueLength,
          )}
        </div>
      </div>

      <div className="segmented">
        {text.modeOptions.map((option) => {
          const isSelected = option.value === subtitleMode
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSubtitleModeChange(option.value)}
            >
              {option.label}
            </button>
          )
        })}
      </div>

      <button
        type="button"
        className="btn-secondary"
        style={{ minHeight: '40px', fontSize: '12px' }}
        onClick={() => setShowDetails((value) => !value)}
      >
        {showDetails ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        {showDetails ? text.hideDetails : text.showDetails}
      </button>

      {showDetails ? (
        <div className="detail-panel">
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
      gridTemplateColumns: '60px minmax(0, 1fr) 48px',
      alignItems: 'center',
      gap: '8px',
      minHeight: '40px',
      color: disabled ? 'var(--text-3)' : 'var(--text-1)',
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
        accentColor: 'var(--accent)',
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
      onChange={(event) => onChange(Number(event.currentTarget.value))}
    />
    <span style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{displayValue}</span>
  </label>
)


const DetailRow: React.FC<DetailRowProps> = ({ label, value }) => (
  <div className="detail-row">
    <span className="d-label">{label}</span>
    <span className="d-value">{value || '-'}</span>
  </div>
)


const WifiIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12.55a11 11 0 0 1 14.08 0" />
    <path d="M1.42 9a16 16 0 0 1 21.16 0" />
    <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
    <line x1="12" x2="12.01" y1="20" y2="20" />
  </svg>
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


function parseTargetLanguage(value: string): TargetLanguage {
  const option = TARGET_LANGUAGE_VALUES.find((item) => item === value)
  return option ?? 'zh-CN'
}


function parseTranslationStyle(value: string): TranslationStyle {
  const option = TRANSLATION_STYLE_VALUES.find((item) => item === value)
  return option ?? 'concise'
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
