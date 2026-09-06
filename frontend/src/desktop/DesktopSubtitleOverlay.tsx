import React, { useEffect, useState } from 'react'

import {
  buildSubtitleStyleVarMap,
  normalizeSubtitleStyle,
} from '../subtitle/subtitle-style'
import type { SubtitlePosition } from '../types'
import {
  createDesktopOverlaySnapshot,
  getDesktopBridge,
  getSubtitleDisplayState,
  type DesktopOverlaySnapshot,
} from './overlay'
import { isWebOverlaySurface, subscribeToWebOverlaySnapshots } from './web-overlay'


const EMPTY_OVERLAY_SNAPSHOT = createDesktopOverlaySnapshot([], 'bilingual', 0)


const POSITION_ALIGN: Record<SubtitlePosition, string> = {
  bottom: 'flex-end',
  middle: 'center',
  top: 'flex-start',
}


export const DesktopSubtitleOverlay: React.FC = () => {
  const [snapshot, setSnapshot] = useState<DesktopOverlaySnapshot>(EMPTY_OVERLAY_SNAPSHOT)

  useEffect(() => {
    document.documentElement.dataset.surface = 'subtitle-overlay'
    const bridge = getDesktopBridge()
    const cleanupCallbacks: Array<() => void> = []

    if (bridge) {
      cleanupCallbacks.push(
        bridge.onSubtitleSnapshot((nextSnapshot) => {
          setSnapshot(nextSnapshot)
        }),
      )
    }

    if (isWebOverlaySurface(window.location.search)) {
      cleanupCallbacks.push(subscribeToWebOverlaySnapshots(setSnapshot))
    }

    return () => {
      cleanupCallbacks.forEach((cleanup) => cleanup())
    }
  }, [])

  const style = normalizeSubtitleStyle(snapshot.style)
  const shellStyle = {
    '--subtitle-align': POSITION_ALIGN[style.position],
  } as React.CSSProperties
  const stackStyle = buildSubtitleStyleVarMap(style) as React.CSSProperties

  return (
    <main
      aria-label="Floating subtitles"
      className="desktop-subtitle-overlay-shell"
      style={shellStyle}
    >
      <div className="desktop-subtitle-stack" style={stackStyle}>
        {snapshot.entries.map((entry) => {
          const displayState = getSubtitleDisplayState(entry, snapshot.mode)

          return (
            <section
              key={entry.segmentId}
              className={displayState.className}
              data-segment-id={entry.segmentId}
            >
              <div
                className="desktop-subtitle-source"
                style={{ display: displayState.showSource ? 'block' : 'none' }}
              >
                {entry.sourceText}
              </div>
              <div
                className="desktop-subtitle-translated"
                style={{ display: displayState.showTranslated ? 'block' : 'none' }}
              >
                {entry.translatedText}
              </div>
              {entry.isPartial ? (
                <span aria-hidden="true" className="desktop-subtitle-cursor">
                  |
                </span>
              ) : null}
            </section>
          )
        })}
      </div>
    </main>
  )
}
