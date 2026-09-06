import React, { lazy, Suspense, useEffect, useRef, useState } from 'react'

import { createDesktopOverlaySnapshot, getDesktopBridge, type DesktopOverlayState } from './desktop/overlay'
import {
  getTauriOverlayState,
  setTauriOverlayVisible,
} from './desktop/tauri'
import {
  createUnavailableDesktopSettings,
  loadDesktopSettings,
  saveDesktopSettings,
} from './desktop/settings'
import {
  createUnavailableWebOverlayState,
  WebFloatingSubtitleOverlay,
  type WebOverlayState,
} from './desktop/web-overlay'
import { getUiText } from './i18n'
import { matchKeyboardEvent, nextSubtitleMode } from './shortcuts'
import { fetchSessionSummary } from './summary/session-summary'
import { SubtitleRenderer } from './subtitle/SubtitleRenderer'
import { AppController, type AppState } from './store/AppStore'
import { ControlPanel } from './ui/ControlPanel'
import { SettingsPanel } from './ui/SettingsPanel'
import type {
  AudioSourceType,
  DesktopSettingsSaveResult,
  DesktopSettingsSnapshot,
  DesktopSettingsUpdate,
  SubtitleStyleConfig,
} from './types'
import { Languages, Play, Settings as SettingsIcon } from 'lucide-react'

// 性能优化：xterm 与导出模块体积较大，首次渲染不加载，
// 用户打开终端/历史面板时才按需拉取（React.lazy + 独立 chunk）。
const TerminalPanel = lazy(() => import('./ui/TerminalPanel').then((m) => ({ default: m.TerminalPanel })))
const SubtitleHistoryPanel = lazy(() =>
  import('./ui/SubtitleHistoryPanel').then((m) => ({ default: m.SubtitleHistoryPanel })),
)
const SummaryPanel = lazy(() =>
  import('./ui/SummaryPanel').then((m) => ({ default: m.SummaryPanel })),
)
const GlossaryPanel = lazy(() =>
  import('./ui/GlossaryPanel').then((m) => ({ default: m.GlossaryPanel })),
)
const TranslationMemoryPanel = lazy(() =>
  import('./ui/TranslationMemoryPanel').then((m) => ({ default: m.TranslationMemoryPanel })),
)
const SubtitleStylePanel = lazy(() =>
  import('./ui/SubtitleStylePanel').then((m) => ({ default: m.SubtitleStylePanel })),
)
const CollaborationPanel = lazy(() =>
  import('./ui/CollaborationPanel').then((m) => ({ default: m.CollaborationPanel })),
)
const SubscriptionPanel = lazy(() =>
  import('./ui/SubscriptionPanel').then((m) => ({ default: m.SubscriptionPanel })),
)
const CostPanel = lazy(() =>
  import('./ui/CostPanel').then((m) => ({ default: m.CostPanel })),
)
const SessionHistoryPanel = lazy(() =>
  import('./ui/SessionHistoryPanel').then((m) => ({ default: m.SessionHistoryPanel })),
)
const RevisionTimelinePanel = lazy(() =>
  import('./ui/RevisionTimelinePanel').then((m) => ({ default: m.RevisionTimelinePanel })),
)


const controller = new AppController()


const App: React.FC = () => {
  const [appState, setAppState] = useState<AppState>(controller.state)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [isTerminalOpen, setIsTerminalOpen] = useState(false)
  const [isSummaryOpen, setIsSummaryOpen] = useState(false)
  const [isGlossaryOpen, setIsGlossaryOpen] = useState(false)
  const [isTranslationMemoryOpen, setIsTranslationMemoryOpen] = useState(false)
  const [isSubtitleStyleOpen, setIsSubtitleStyleOpen] = useState(false)
  const [isCollaborationOpen, setIsCollaborationOpen] = useState(false)
  const [isSubscriptionOpen, setIsSubscriptionOpen] = useState(false)
  const [isCostOpen, setIsCostOpen] = useState(false)
  const [isSessionHistoryOpen, setIsSessionHistoryOpen] = useState(false)
  const [isRevisionTimelineOpen, setIsRevisionTimelineOpen] = useState(false)
  const [desktopSettings, setDesktopSettings] = useState<DesktopSettingsSnapshot>(
    createUnavailableDesktopSettings(),
  )
  const [desktopOverlayState, setDesktopOverlayState] = useState<DesktopOverlayState>({
    available: false,
    visible: false,
  })
  const [webOverlayState, setWebOverlayState] = useState<WebOverlayState>(
    createUnavailableWebOverlayState(),
  )
  const containerRef = useRef<HTMLDivElement | null>(null)
  const rendererRef = useRef<SubtitleRenderer | null>(null)
  const webOverlayRef = useRef<WebFloatingSubtitleOverlay | null>(null)
  const subtitleStyleSaveTimerRef = useRef<number | null>(null)
  const uiText = getUiText(desktopSettings.uiLanguage)

  useEffect(() => {
    const unsubscribe = controller.subscribe(setAppState)
    return unsubscribe
  }, [])

  // 第二梯队-方向 6：全局快捷键（浏览器 / 聚焦 Tauri 窗口内有效）。
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      const action = matchKeyboardEvent(event)
      if (!action) {
        return
      }

      // 输入框/文本域内不触发快捷键，避免误伤打字。
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      ) {
        return
      }

      event.preventDefault()
      switch (action) {
        case 'toggle_translation': {
          const active = appState.status === 'capturing' || appState.status === 'translating'
          if (active) {
            controller.stop()
          } else {
            controller.start().catch((error: unknown) => {
              console.error('[App] shortcut start failed', error)
            })
          }
          break
        }
        case 'cycle_subtitle_mode': {
          controller.setSubtitleMode(nextSubtitleMode(appState.subtitleMode))
          break
        }
        case 'toggle_history': {
          setIsHistoryOpen((open) => !open)
          break
        }
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [appState.status, appState.subtitleMode])

  useEffect(() => {
    let isMounted = true

    loadDesktopSettings()
      .then((settings) => {
        if (!isMounted) {
          return
        }
        setDesktopSettings(settings)
        controller.setSourceLanguage(settings.runtime.sourceLanguage)
        controller.setTargetLanguage(settings.runtime.targetLanguage)
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
    if (bridge) {
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
    }

    // Tauri 环境：通过命令桥读取悬浮窗状态
    let isMounted = true
    getTauriOverlayState()
      .then((state) => {
        if (isMounted && state) {
          setDesktopOverlayState({ available: state.available, visible: state.visible })
        }
      })
      .catch((error: unknown) => {
        console.warn('[App] failed to read tauri overlay state', error)
      })

    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    if (getDesktopBridge()) {
      return undefined
    }

    const webOverlay = new WebFloatingSubtitleOverlay()
    webOverlayRef.current = webOverlay
    const unsubscribe = webOverlay.subscribe(setWebOverlayState)

    return () => {
      unsubscribe()
      webOverlay.destroy()
      webOverlayRef.current = null
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
    const snapshot = createDesktopOverlaySnapshot(
      appState.visibleSubtitles,
      appState.subtitleMode,
      Date.now(),
      appState.subtitleStyle,
    )
    const bridge = getDesktopBridge()
    if (bridge) {
      bridge.sendSubtitleSnapshot(snapshot)
    }

    webOverlayRef.current?.sendSnapshot(snapshot)
  }, [appState.visibleSubtitles, appState.subtitleMode, appState.subtitleStyle])

  const handleStart = (): void => {
    controller.start().catch((error: unknown) => {
      console.error('Start failed', error)
      window.alert(uiText.startError)
    })
  }

  const handleAudioSourceChange = async (
    source: AudioSourceType,
    file?: File,
  ): Promise<boolean> => {
    return controller.setAudioSource(source, file)
  }

  const handleSettingsSave = async (
    update: DesktopSettingsUpdate,
  ): Promise<DesktopSettingsSaveResult> => {
    const result = await saveDesktopSettings(update)
    if (result.success && result.settings) {
      setDesktopSettings(result.settings)
      controller.setSourceLanguage(result.settings.runtime.sourceLanguage)
      controller.setTargetLanguage(result.settings.runtime.targetLanguage)
    }
    return result
  }

  const handleSubtitleStyleChange = (style: SubtitleStyleConfig): void => {
    controller.setSubtitleStyle(style)

    if (subtitleStyleSaveTimerRef.current !== null) {
      window.clearTimeout(subtitleStyleSaveTimerRef.current)
    }
    subtitleStyleSaveTimerRef.current = window.setTimeout(() => {
      void persistSubtitleStyle(style, desktopSettings, setDesktopSettings)
    }, 350)
  }

  const handleDesktopOverlayToggle = (): void => {
    const bridge = getDesktopBridge()
    if (bridge && desktopOverlayState.available) {
      bridge.setOverlayVisible(!desktopOverlayState.visible)
      return
    }

    // Tauri 环境
    void setTauriOverlayVisible(!desktopOverlayState.visible)
      .then((ok) => {
        if (ok) {
          setDesktopOverlayState((current) => ({
            available: true,
            visible: !current.visible,
          }))
        }
      })
      .catch((error: unknown) => {
        console.warn('[App] failed to toggle tauri overlay', error)
      })
  }

  const handleWebOverlayToggle = (): void => {
    const webOverlay = webOverlayRef.current
    if (!webOverlay || !webOverlayState.available) {
      return
    }

    if (webOverlayState.visible) {
      webOverlay.close()
      return
    }

    webOverlay.open().then((state) => {
      if (state.reason === 'popup_blocked' || state.reason === 'open_failed') {
        window.alert(uiText.control.floatingSubtitlesOpenFailed)
      }
    }).catch((error: unknown) => {
      console.error('[App] failed to open web subtitle overlay', error)
      window.alert(uiText.control.floatingSubtitlesOpenFailed)
    })
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
        audioSource={appState.audioSource}
        audioFileName={appState.audioFileName}
        audioFileEnded={appState.audioFileEnded}
        ttsSettings={appState.ttsSettings}
        ttsDiagnostics={appState.ttsDiagnostics}
        ttsEngine={appState.ttsEngine}
        translationStyle={appState.translationStyle}
        asrHotwordsEnabled={appState.asrHotwordsEnabled}
        detectedSourceLanguage={appState.detectedSourceLanguage}
        desktopOverlayState={desktopOverlayState}
        webOverlayState={webOverlayState}
        uiText={uiText}
        onStart={handleStart}
        onStop={() => controller.stop()}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onManualRevise={() => controller.requestManualRevision()}
        onOpenHistory={() => setIsHistoryOpen(true)}
        onOpenTerminal={() => setIsTerminalOpen(true)}
        onOpenSummary={() => setIsSummaryOpen(true)}
        onOpenGlossary={() => setIsGlossaryOpen(true)}
        onOpenTranslationMemory={() => setIsTranslationMemoryOpen(true)}
        onOpenSubtitleStyle={() => setIsSubtitleStyleOpen(true)}
        onOpenCollaboration={() => setIsCollaborationOpen(true)}
        onOpenSubscription={() => setIsSubscriptionOpen(true)}
        onOpenCost={() => setIsCostOpen(true)}
        onOpenSessionHistory={() => setIsSessionHistoryOpen(true)}
        onOpenRevisionTimeline={() => setIsRevisionTimelineOpen(true)}
        onGlossaryImport={(file) => controller.uploadGlossary(file)}
        onDesktopOverlayToggle={handleDesktopOverlayToggle}
        onWebOverlayToggle={handleWebOverlayToggle}
        onSubtitleModeChange={(mode) => controller.setSubtitleMode(mode)}
        onSourceLanguageChange={(language) => controller.setSourceLanguage(language)}
        onTargetLanguageChange={(language) => controller.setTargetLanguage(language)}
        onTranslationStyleChange={(style) => controller.setTranslationStyle(style)}
        onAsrHotwordsEnabledChange={(enabled) => controller.setAsrHotwordsEnabled(enabled)}
        onTtsEnabledChange={(enabled) => controller.setTtsEnabled(enabled)}
        onTtsEngineChange={(engine) => controller.setTtsEngine(engine)}
        onTtsVolumeChange={(volume) => controller.setTtsVolume(volume)}
        onTtsRateChange={(rate) => controller.setTtsRate(rate)}
        onAudioSourceChange={handleAudioSourceChange}
      />

      <Suspense fallback={null}>
        <SubtitleHistoryPanel
          entries={appState.subtitleHistory}
          isOpen={isHistoryOpen}
          diagnosticsText={appState.diagnosticsText}
          uiText={uiText}
          fileSampleCount={controller.fileSampleCount}
          onSeekToSample={(sampleOffset) => controller.seekFileToSample(sampleOffset)}
          onClose={() => setIsHistoryOpen(false)}
        />
      </Suspense>

      <Suspense fallback={null}>
        <SummaryPanel
          sessionId={controller.sessionId}
          isOpen={isSummaryOpen}
          hasSubtitles={appState.subtitleHistory.length > 0}
          uiText={uiText}
          fetchSummary={(sessionId, options) => fetchSessionSummary(sessionId, options)}
          onClose={() => setIsSummaryOpen(false)}
        />
      </Suspense>

      <Suspense fallback={null}>
        <TerminalPanel
          isOpen={isTerminalOpen}
          onClose={() => setIsTerminalOpen(false)}
        />
      </Suspense>

      <Suspense fallback={null}>
        <GlossaryPanel
          isOpen={isGlossaryOpen}
          uiText={uiText}
          onClose={() => setIsGlossaryOpen(false)}
        />
      </Suspense>

      <Suspense fallback={null}>
        <TranslationMemoryPanel
          isOpen={isTranslationMemoryOpen}
          uiText={uiText}
          onClose={() => setIsTranslationMemoryOpen(false)}
        />
      </Suspense>

      <Suspense fallback={null}>
        <SubtitleStylePanel
          isOpen={isSubtitleStyleOpen}
          style={appState.subtitleStyle}
          uiText={uiText}
          onChange={handleSubtitleStyleChange}
          onClose={() => setIsSubtitleStyleOpen(false)}
        />
      </Suspense>

      <Suspense fallback={null}>
        <CollaborationPanel
          isOpen={isCollaborationOpen}
          sessionId={controller.sessionId}
          uiText={uiText}
          onClose={() => setIsCollaborationOpen(false)}
        />
      </Suspense>

      <Suspense fallback={null}>
        <SubscriptionPanel
          isOpen={isSubscriptionOpen}
          uiText={uiText}
          onClose={() => setIsSubscriptionOpen(false)}
        />
      </Suspense>

      <Suspense fallback={null}>
        <CostPanel
          isOpen={isCostOpen}
          uiText={uiText}
          onClose={() => setIsCostOpen(false)}
        />
      </Suspense>

      <Suspense fallback={null}>
        <SessionHistoryPanel
          isOpen={isSessionHistoryOpen}
          uiText={uiText}
          onClose={() => setIsSessionHistoryOpen(false)}
        />
      </Suspense>

      <Suspense fallback={null}>
        <RevisionTimelinePanel
          events={appState.revisionHistory}
          isOpen={isRevisionTimelineOpen}
          uiText={uiText}
          onClose={() => setIsRevisionTimelineOpen(false)}
        />
      </Suspense>

      <SettingsPanel
        isOpen={isSettingsOpen}
        settings={desktopSettings}
        uiText={uiText}
        onClose={() => setIsSettingsOpen(false)}
        onSave={handleSettingsSave}
      />

      {appState.status === 'idle' ? (
        <div className="app-idle-prompt">
          <div className="idle-hero">
            <div className="idle-eyebrow">
              <Languages size={13} />
              Live Interpreter
            </div>
            <div className="idle-title">{uiText.idleTitle}</div>
            <div className="idle-desc">{uiText.idleDescription}</div>
            <div className="idle-features">
              {uiText.idleFeatures.map((feature) => (
                <div className="idle-feature" key={feature.title}>
                  <span className="idle-feature-icon">{feature.icon}</span>
                  <span className="idle-feature-text">
                    <strong>{feature.title}</strong>
                    <em>{feature.desc}</em>
                  </span>
                </div>
              ))}
            </div>
            <div className="idle-actions">
              <button
                type="button"
                className="btn-primary start"
                style={{ width: 'auto', padding: '0 26px', minHeight: '46px' }}
                onClick={handleStart}
              >
                <Play size={18} />
                {uiText.idleStartButton}
              </button>
              <button
                type="button"
                className="btn-secondary"
                style={{ width: 'auto', padding: '0 22px', minHeight: '46px' }}
                onClick={() => setIsSettingsOpen(true)}
              >
                <SettingsIcon size={16} />
                {uiText.idleSettingsButton}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}


async function persistSubtitleStyle(
  style: SubtitleStyleConfig,
  current: DesktopSettingsSnapshot,
  setDesktopSettings: React.Dispatch<React.SetStateAction<DesktopSettingsSnapshot>>,
): Promise<void> {
  try {
    const result = await saveDesktopSettings({
      uiLanguage: current.uiLanguage,
      translation: {
        engine: current.translation.engine,
        model: current.translation.model,
        openaiBaseUrl: current.translation.openaiBaseUrl,
        openaiApiKey: '',
        anthropicApiKey: '',
        clearOpenaiApiKey: false,
        clearAnthropicApiKey: false,
      },
      asr: {
        model: current.asr.model,
        openaiBaseUrl: current.asr.openaiBaseUrl,
        openaiApiKey: '',
        clearOpenaiApiKey: false,
      },
      runtime: {
        asrProfile: current.runtime.asrProfile,
        sourceLanguage: current.runtime.sourceLanguage,
        targetLanguage: current.runtime.targetLanguage,
      },
      subtitleStyle: style,
    })
    if (result.success && result.settings) {
      setDesktopSettings(result.settings)
    }
  } catch (error) {
    console.warn('[App] failed to persist subtitle style', error)
  }
}


export default App
