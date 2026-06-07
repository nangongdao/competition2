import React, { useEffect, useRef, useState } from 'react'

import {
  createDesktopOverlaySnapshot,
  getDesktopBridge,
  type DesktopOverlayState,
} from './desktop/overlay'
import {
  createUnavailableDesktopSettings,
  loadDesktopSettings,
  saveDesktopSettings,
} from './desktop/settings'
import { getUiText } from './i18n'
import { SubtitleRenderer } from './subtitle/SubtitleRenderer'
import { AppController, type AppState } from './store/AppStore'
import { ControlPanel } from './ui/ControlPanel'
import { SettingsPanel } from './ui/SettingsPanel'
import { SubtitleHistoryPanel } from './ui/SubtitleHistoryPanel'
import type {
  DesktopSettingsSaveResult,
  DesktopSettingsSnapshot,
  DesktopSettingsUpdate,
} from './types'


const controller = new AppController()


const App: React.FC = () => {
  const [appState, setAppState] = useState<AppState>(controller.state)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [desktopSettings, setDesktopSettings] = useState<DesktopSettingsSnapshot>(
    createUnavailableDesktopSettings(),
  )
  const [desktopOverlayState, setDesktopOverlayState] = useState<DesktopOverlayState>({
    available: false,
    visible: false,
  })
  const containerRef = useRef<HTMLDivElement | null>(null)
  const rendererRef = useRef<SubtitleRenderer | null>(null)
  const uiText = getUiText(desktopSettings.uiLanguage)

  useEffect(() => {
    const unsubscribe = controller.subscribe(setAppState)
    return unsubscribe
  }, [])

  useEffect(() => {
    let isMounted = true

    loadDesktopSettings()
      .then((settings) => {
        if (!isMounted) {
          return
        }
        setDesktopSettings(settings)
        controller.setSourceLanguage(settings.runtime.sourceLanguage)
      })
      .catch((error: unknown) => {
        console.warn('[App] failed to load desktop settings', error)
      })

    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    const bridge = getDesktopBridge()
    if (!bridge) {
      return undefined
    }

    let isMounted = true
    const unsubscribe = bridge.onOverlayStateChange((state) => {
      setDesktopOverlayState(state)
    })

    bridge
      .getOverlayState()
      .then((state) => {
        if (isMounted) {
          setDesktopOverlayState(state)
        }
      })
      .catch((error: unknown) => {
        console.warn('[App] failed to read desktop overlay state', error)
      })

    return () => {
      isMounted = false
      unsubscribe()
    }
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!container || rendererRef.current) {
      return
    }

    const renderer = new SubtitleRenderer({
      container,
      maxLines: 6,
      bottomOffset: '12%',
    })
    renderer.setMode(appState.subtitleMode)

    rendererRef.current = renderer
    controller.setSubtitleRenderer(renderer)

    return () => {
      renderer.destroy()
      rendererRef.current = null
    }
  }, [appState.subtitleMode])

  useEffect(() => {
    const bridge = getDesktopBridge()
    if (!bridge) {
      return
    }

    bridge.sendSubtitleSnapshot(
      createDesktopOverlaySnapshot(appState.visibleSubtitles, appState.subtitleMode),
    )
  }, [appState.visibleSubtitles, appState.subtitleMode])

  const handleStart = (): void => {
    controller.start().catch((error: unknown) => {
      console.error('Start failed', error)
      window.alert(uiText.startError)
    })
  }

  const handleSettingsSave = async (
    update: DesktopSettingsUpdate,
  ): Promise<DesktopSettingsSaveResult> => {
    const result = await saveDesktopSettings(update)
    if (result.success && result.settings) {
      setDesktopSettings(result.settings)
      controller.setSourceLanguage(result.settings.runtime.sourceLanguage)
    }
    return result
  }

  const handleDesktopOverlayToggle = (): void => {
    const bridge = getDesktopBridge()
    if (!bridge || !desktopOverlayState.available) {
      return
    }

    bridge.setOverlayVisible(!desktopOverlayState.visible)
  }

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        position: 'relative',
        display: 'flex',
        alignItems: 'stretch',
        minHeight: 0,
      }}
    >
      <ControlPanel
        status={appState.status}
        connectionState={appState.connectionState}
        subtitleMode={appState.subtitleMode}
        languageConfig={appState.languageConfig}
        subtitleHistoryCount={appState.subtitleHistory.length}
        translationRevisionCount={appState.translationRevisionCount}
        asrRevisionCount={appState.asrRevisionCount}
        lastRevisionReason={appState.lastRevisionReason}
        serverDiagnostics={appState.serverDiagnostics}
        clientDiagnostics={appState.clientDiagnostics}
        ttsSettings={appState.ttsSettings}
        ttsDiagnostics={appState.ttsDiagnostics}
        desktopOverlayState={desktopOverlayState}
        uiText={uiText}
        onStart={handleStart}
        onStop={() => controller.stop()}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onManualRevise={() => controller.requestManualRevision()}
        onOpenHistory={() => setIsHistoryOpen(true)}
        onDesktopOverlayToggle={handleDesktopOverlayToggle}
        onSubtitleModeChange={(mode) => controller.setSubtitleMode(mode)}
        onSourceLanguageChange={(language) => controller.setSourceLanguage(language)}
        onTtsEnabledChange={(enabled) => controller.setTtsEnabled(enabled)}
        onTtsVolumeChange={(volume) => controller.setTtsVolume(volume)}
        onTtsRateChange={(rate) => controller.setTtsRate(rate)}
      />

      <SubtitleHistoryPanel
        entries={appState.subtitleHistory}
        isOpen={isHistoryOpen}
        diagnosticsText={appState.diagnosticsText}
        uiText={uiText}
        onClose={() => setIsHistoryOpen(false)}
      />

      <SettingsPanel
        isOpen={isSettingsOpen}
        settings={desktopSettings}
        uiText={uiText}
        onClose={() => setIsSettingsOpen(false)}
        onSave={handleSettingsSave}
      />

      {appState.status === 'idle' ? (
        <div className="app-idle-prompt">
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '10px',
              maxWidth: 'min(88vw, 520px)',
              padding: '0 24px',
              textAlign: 'center',
              color: '#95a3b5',
            }}
          >
            <div style={{ fontSize: '42px', lineHeight: 1 }}>AI</div>
            <div style={{ fontSize: '20px', color: '#e6edf6', fontWeight: 700 }}>
              {uiText.idleTitle}
            </div>
            <div style={{ fontSize: '13px', lineHeight: 1.5 }}>
              {uiText.idleDescription}
            </div>
            <button
              type="button"
              style={{
                minHeight: '44px',
                padding: '0 18px',
                border: '1px solid rgba(255,255,255,0.14)',
                borderRadius: '10px',
                background: 'rgba(255,255,255,0.07)',
                color: '#e6edf6',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: 700,
                pointerEvents: 'auto',
                WebkitTapHighlightColor: 'transparent',
              }}
              onClick={() => setIsSettingsOpen(true)}
            >
              {uiText.idleSettingsButton}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}


export default App
