import React, { useEffect, useState } from 'react'

import { UI_LANGUAGE_OPTIONS, type UiText } from '../i18n'
import type {
  DesktopAsrProfile,
  DesktopSettingsSaveResult,
  DesktopSettingsSnapshot,
  DesktopSettingsUpdate,
  SourceLanguage,
  TranslationEngine,
  UiLanguage,
} from '../types'


interface SettingsPanelProps {
  isOpen: boolean
  settings: DesktopSettingsSnapshot
  uiText: UiText
  onClose: () => void
  onSave: (update: DesktopSettingsUpdate) => Promise<DesktopSettingsSaveResult>
}


type SaveState = 'idle' | 'saving' | 'saved' | 'failed'


const ASR_PROFILE_OPTIONS: DesktopAsrProfile[] = ['light', 'cpu', 'gpu', 'env']
const TRANSLATION_ENGINE_OPTIONS: TranslationEngine[] = ['openai', 'claude']
const SOURCE_LANGUAGE_OPTIONS: SourceLanguage[] = ['auto', 'en', 'ja', 'ko', 'es', 'fr', 'de']


const tapSafeButtonStyle: React.CSSProperties = {
  border: 'none',
  cursor: 'pointer',
  fontWeight: 700,
  WebkitTapHighlightColor: 'transparent',
}


export const SettingsPanel: React.FC<SettingsPanelProps> = ({
  isOpen,
  settings,
  uiText,
  onClose,
  onSave,
}) => {
  const text = uiText.settings
  const [uiLanguage, setUiLanguage] = useState<UiLanguage>(settings.uiLanguage)
  const [engine, setEngine] = useState<TranslationEngine>(settings.translation.engine)
  const [model, setModel] = useState(settings.translation.model)
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState(settings.translation.openaiBaseUrl)
  const [openaiApiKey, setOpenaiApiKey] = useState('')
  const [anthropicApiKey, setAnthropicApiKey] = useState('')
  const [clearOpenaiApiKey, setClearOpenaiApiKey] = useState(false)
  const [clearAnthropicApiKey, setClearAnthropicApiKey] = useState(false)
  const [asrProfile, setAsrProfile] = useState<DesktopAsrProfile>(settings.runtime.asrProfile)
  const [sourceLanguage, setSourceLanguage] = useState<SourceLanguage>(
    settings.runtime.sourceLanguage,
  )
  const [saveState, setSaveState] = useState<SaveState>('idle')

  useEffect(() => {
    if (!isOpen) {
      return
    }

    setUiLanguage(settings.uiLanguage)
    setEngine(settings.translation.engine)
    setModel(settings.translation.model)
    setOpenaiBaseUrl(settings.translation.openaiBaseUrl)
    setOpenaiApiKey('')
    setAnthropicApiKey('')
    setClearOpenaiApiKey(false)
    setClearAnthropicApiKey(false)
    setAsrProfile(settings.runtime.asrProfile)
    setSourceLanguage(settings.runtime.sourceLanguage)
    setSaveState('idle')
  }, [isOpen, settings])

  useEffect(() => {
    if (!isOpen) {
      return
    }

    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) {
    return null
  }

  const handleSave = async (): Promise<void> => {
    if (!settings.available || saveState === 'saving') {
      return
    }

    setSaveState('saving')
    const result = await onSave({
      uiLanguage,
      translation: {
        engine,
        model,
        openaiBaseUrl,
        openaiApiKey,
        anthropicApiKey,
        clearOpenaiApiKey,
        clearAnthropicApiKey,
      },
      runtime: {
        asrProfile,
        sourceLanguage,
      },
    })

    if (result.success) {
      setOpenaiApiKey('')
      setAnthropicApiKey('')
      setClearOpenaiApiKey(false)
      setClearAnthropicApiKey(false)
      setSaveState('saved')
      window.setTimeout(() => setSaveState('idle'), 1800)
      return
    }

    setSaveState('failed')
    window.setTimeout(() => setSaveState('idle'), 2200)
  }

  return (
    <section
      aria-label={text.ariaLabel}
      role="dialog"
      aria-modal="true"
      className="settings-modal-shell"
    >
      <div className="settings-modal-panel">
        <div className="settings-modal-header">
          <div>
            <div className="settings-modal-title">{text.title}</div>
            <div className="settings-modal-subtitle">{text.subtitle}</div>
          </div>
          <button
            type="button"
            aria-label={text.close}
            style={{
              ...tapSafeButtonStyle,
              minWidth: '64px',
              minHeight: '44px',
              borderRadius: '10px',
              background: 'rgba(255,255,255,0.08)',
              color: '#d9e1eb',
            }}
            onClick={onClose}
          >
            {text.close}
          </button>
        </div>

        {!settings.available ? (
          <div className="settings-unavailable">
            <div style={{ color: '#ffffff', fontWeight: 800 }}>{text.unavailableTitle}</div>
            <div style={{ color: '#9fb0c4', fontSize: '13px', lineHeight: 1.5 }}>
              {text.unavailableBody}
            </div>
          </div>
        ) : (
          <>
            <div className="settings-section">
              <SelectField
                label={text.interfaceLanguage}
                value={uiLanguage}
                onChange={(value) => setUiLanguage(parseUiLanguage(value))}
              >
                {UI_LANGUAGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </SelectField>
            </div>

            <div className="settings-section">
              <SelectField
                label={text.translationEngine}
                value={engine}
                onChange={(value) => setEngine(parseTranslationEngine(value))}
              >
                {TRANSLATION_ENGINE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {text.translationEngineOptions[option]}
                  </option>
                ))}
              </SelectField>

              <TextField
                label={text.model}
                value={model}
                onChange={setModel}
              />

              <TextField
                label={text.openaiBaseUrl}
                value={openaiBaseUrl}
                onChange={setOpenaiBaseUrl}
              />

              <SecretField
                label={text.openaiApiKey}
                status={settings.translation.hasOpenaiApiKey ? text.keyConfigured : text.keyMissing}
                placeholder={text.keyPlaceholder}
                value={openaiApiKey}
                clearLabel={text.clearOpenaiKey}
                clearChecked={clearOpenaiApiKey}
                onValueChange={setOpenaiApiKey}
                onClearChange={setClearOpenaiApiKey}
              />

              <SecretField
                label={text.anthropicApiKey}
                status={
                  settings.translation.hasAnthropicApiKey ? text.keyConfigured : text.keyMissing
                }
                placeholder={text.keyPlaceholder}
                value={anthropicApiKey}
                clearLabel={text.clearAnthropicKey}
                clearChecked={clearAnthropicApiKey}
                onValueChange={setAnthropicApiKey}
                onClearChange={setClearAnthropicApiKey}
              />
            </div>

            <div className="settings-section">
              <SelectField
                label={text.asrProfile}
                value={asrProfile}
                onChange={(value) => setAsrProfile(parseAsrProfile(value))}
              >
                {ASR_PROFILE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {text.asrProfileOptions[option]}
                  </option>
                ))}
              </SelectField>

              <SelectField
                label={text.defaultSourceLanguage}
                value={sourceLanguage}
                onChange={(value) => setSourceLanguage(parseSourceLanguage(value))}
              >
                {SOURCE_LANGUAGE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {uiText.control.sourceOptions[option]}
                  </option>
                ))}
              </SelectField>
            </div>

            <div className="settings-file-note">
              <span>{text.localFile}</span>
              <strong>{settings.configPath ?? '-'}</strong>
            </div>
            <div className="settings-restart-note">{text.restartNotice}</div>
          </>
        )}

        <div className="settings-modal-footer">
          <div aria-live="polite" className="settings-save-status">
            {saveState === 'saved'
              ? text.saved
              : saveState === 'failed'
                ? text.saveFailed
                : ''}
          </div>
          <button
            type="button"
            disabled={!settings.available || saveState === 'saving'}
            style={{
              ...tapSafeButtonStyle,
              minHeight: '44px',
              minWidth: '116px',
              borderRadius: '10px',
              background: !settings.available || saveState === 'saving' ? '#334255' : '#4aa3ff',
              color: '#ffffff',
              cursor: !settings.available || saveState === 'saving' ? 'not-allowed' : 'pointer',
            }}
            onClick={() => {
              void handleSave()
            }}
          >
            {saveState === 'saving' ? text.saving : text.save}
          </button>
        </div>
      </div>
    </section>
  )
}


interface TextFieldProps {
  label: string
  value: string
  onChange: (value: string) => void
}


interface SelectFieldProps {
  label: string
  value: string
  children: React.ReactNode
  onChange: (value: string) => void
}


interface SecretFieldProps {
  label: string
  status: string
  placeholder: string
  value: string
  clearLabel: string
  clearChecked: boolean
  onValueChange: (value: string) => void
  onClearChange: (checked: boolean) => void
}


const TextField: React.FC<TextFieldProps> = ({ label, value, onChange }) => (
  <label className="settings-field">
    <span>{label}</span>
    <input
      value={value}
      spellCheck={false}
      onChange={(event) => onChange(event.currentTarget.value)}
    />
  </label>
)


const SelectField: React.FC<SelectFieldProps> = ({ label, value, children, onChange }) => (
  <label className="settings-field">
    <span>{label}</span>
    <select value={value} onChange={(event) => onChange(event.currentTarget.value)}>
      {children}
    </select>
  </label>
)


const SecretField: React.FC<SecretFieldProps> = ({
  label,
  status,
  placeholder,
  value,
  clearLabel,
  clearChecked,
  onValueChange,
  onClearChange,
}) => (
  <div className="settings-secret-field">
    <label className="settings-field">
      <span>
        {label}
        <em>{status}</em>
      </span>
      <input
        type="password"
        value={value}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        onChange={(event) => onValueChange(event.currentTarget.value)}
      />
    </label>
    <label className="settings-checkbox">
      <input
        type="checkbox"
        checked={clearChecked}
        onChange={(event) => onClearChange(event.currentTarget.checked)}
      />
      <span>{clearLabel}</span>
    </label>
  </div>
)


function parseUiLanguage(value: string): UiLanguage {
  return value === 'en-US' ? 'en-US' : 'zh-CN'
}


function parseTranslationEngine(value: string): TranslationEngine {
  return value === 'claude' ? 'claude' : 'openai'
}


function parseAsrProfile(value: string): DesktopAsrProfile {
  switch (value) {
    case 'cpu':
    case 'gpu':
    case 'env':
      return value
    default:
      return 'light'
  }
}


function parseSourceLanguage(value: string): SourceLanguage {
  switch (value) {
    case 'auto':
    case 'ja':
    case 'ko':
    case 'es':
    case 'fr':
    case 'de':
      return value
    default:
      return 'en'
  }
}
