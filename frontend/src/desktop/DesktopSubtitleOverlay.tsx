import React, { useEffect, useState } from 'react'

import {
  createDesktopOverlaySnapshot,
  getDesktopBridge,
  getSubtitleDisplayState,
  type DesktopOverlaySnapshot,
} from './overlay'
import { isWebOverlaySurface, subscribeToWebOverlaySnapshots } from './web-overlay'


const EMPTY_OVERLAY_SNAPSHOT = createDesktopOverlaySnapshot([], 'bilingual', 0)


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

  return (
    <main aria-label="Floating subtitles" className="desktop-subtitle-overlay-shell">
      <div className="desktop-subtitle-stack">
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
