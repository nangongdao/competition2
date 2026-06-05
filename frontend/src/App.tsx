import React, { useEffect, useRef, useState } from 'react'

import { SubtitleRenderer } from './subtitle/SubtitleRenderer'
import { AppController, type AppState } from './store/AppStore'
import { ControlPanel } from './ui/ControlPanel'


const controller = new AppController()


const App: React.FC = () => {
  const [appState, setAppState] = useState<AppState>(controller.state)
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
      window.alert('启动失败，请确认已授予麦克风或系统音频权限。')
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
        translationRevisionCount={appState.translationRevisionCount}
        asrRevisionCount={appState.asrRevisionCount}
        lastRevisionReason={appState.lastRevisionReason}
        onStart={handleStart}
        onStop={() => controller.stop()}
        onManualRevise={() => controller.requestManualRevision()}
        onSubtitleModeChange={(mode) => controller.setSubtitleMode(mode)}
      />

      {appState.status === 'idle' ? (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '10px',
              textAlign: 'center',
              color: '#95a3b5',
            }}
          >
            <div style={{ fontSize: '48px' }}>🎙️</div>
            <div style={{ fontSize: '20px', color: '#e6edf6' }}>AI 同声传译助手</div>
            <div style={{ fontSize: '13px' }}>点击右上角开始翻译，暂停后会自动触发一次静默修正。</div>
          </div>
        </div>
      ) : null}
    </div>
  )
}


export default App
