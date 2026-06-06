import React, { useEffect, useRef, useState } from 'react'

import { SubtitleRenderer } from './subtitle/SubtitleRenderer'
import { AppController, type AppState } from './store/AppStore'
import { ControlPanel } from './ui/ControlPanel'
import { SubtitleHistoryPanel } from './ui/SubtitleHistoryPanel'


const controller = new AppController()


const App: React.FC = () => {
  const [appState, setAppState] = useState<AppState>(controller.state)
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const rendererRef = useRef<SubtitleRenderer | null>(null)

  useEffect(() => {
    const unsubscribe = controller.subscribe(setAppState)
    return unsubscribe
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

  const handleStart = (): void => {
    controller.start().catch((error: unknown) => {
      console.error('Start failed', error)
      window.alert('Start failed. Check microphone, tab audio, or system audio permissions.')
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
        subtitleHistoryCount={appState.subtitleHistory.length}
        translationRevisionCount={appState.translationRevisionCount}
        asrRevisionCount={appState.asrRevisionCount}
        lastRevisionReason={appState.lastRevisionReason}
        serverDiagnostics={appState.serverDiagnostics}
        clientDiagnostics={appState.clientDiagnostics}
        ttsSettings={appState.ttsSettings}
        ttsDiagnostics={appState.ttsDiagnostics}
        onStart={handleStart}
        onStop={() => controller.stop()}
        onManualRevise={() => controller.requestManualRevision()}
        onOpenHistory={() => setIsHistoryOpen(true)}
        onSubtitleModeChange={(mode) => controller.setSubtitleMode(mode)}
        onTtsEnabledChange={(enabled) => controller.setTtsEnabled(enabled)}
        onTtsVolumeChange={(volume) => controller.setTtsVolume(volume)}
        onTtsRateChange={(rate) => controller.setTtsRate(rate)}
      />

      <SubtitleHistoryPanel
        entries={appState.subtitleHistory}
        isOpen={isHistoryOpen}
        diagnosticsText={appState.diagnosticsText}
        onClose={() => setIsHistoryOpen(false)}
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
              Live Interpreter
            </div>
            <div style={{ fontSize: '13px', lineHeight: 1.5 }}>
              Start translation from the control panel. Pauses in audio trigger an automatic
              revision pass, and history stays available for export.
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}


export default App
