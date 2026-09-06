import type { SubtitleEntry, SubtitleMode, SubtitlePosition } from '../types'
import {
  buildSubtitleStyleVarMap,
  normalizeSubtitleStyle,
} from '../subtitle/subtitle-style'
import {
  createDesktopOverlaySnapshot,
  getSubtitleDisplayState,
  type DesktopOverlaySnapshot,
} from './overlay'


export type WebOverlayTransport = 'document-picture-in-picture' | 'popup'


export type WebOverlayReason =
  | 'ready'
  | 'unavailable'
  | 'popup_blocked'
  | 'open_failed'
  | 'closed'


export interface WebOverlayState {
  available: boolean
  visible: boolean
  transport: WebOverlayTransport | null
  reason: WebOverlayReason
}


export interface WebOverlaySnapshotMessage {
  type: 'web-subtitle-snapshot'
  snapshot: DesktopOverlaySnapshot
}


interface DocumentPictureInPictureController {
  requestWindow: (options?: DocumentPictureInPictureWindowOptions) => Promise<Window>
}


interface DocumentPictureInPictureWindowOptions {
  width?: number
  height?: number
  disallowReturnToOpener?: boolean
}


declare global {
  interface Window {
    BroadcastChannel?: typeof BroadcastChannel
    documentPictureInPicture?: DocumentPictureInPictureController
  }
}


type StateListener = (state: WebOverlayState) => void
type SnapshotListener = (snapshot: DesktopOverlaySnapshot) => void


const POSITION_ALIGN: Record<SubtitlePosition, string> = {
  bottom: 'flex-end',
  middle: 'center',
  top: 'flex-start',
}


const WEB_OVERLAY_CHANNEL_NAME = 'ai-interpreter:web-subtitle-overlay'
const WEB_OVERLAY_STORAGE_KEY = 'ai-interpreter:web-subtitle-overlay:latest'
const WEB_OVERLAY_WINDOW_NAME = 'ai-interpreter-web-subtitle-overlay'
const WEB_OVERLAY_WIDTH = 920
const WEB_OVERLAY_HEIGHT = 280
const WEB_OVERLAY_CLOSE_POLL_MS = 800


const INITIAL_SNAPSHOT = createDesktopOverlaySnapshot([], 'bilingual', 0)


const WEB_PIP_OVERLAY_STYLE = `
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html,
body,
#web-subtitle-overlay-root {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: transparent;
}

body {
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: #fff;
}

.desktop-subtitle-overlay-shell {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: var(--subtitle-align, flex-end);
  justify-content: center;
  padding: 0 28px 28px;
  pointer-events: none;
}

.desktop-subtitle-stack {
  display: flex;
  width: min(100%, 980px);
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}

.desktop-subtitle-entry {
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  padding: 10px 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  background: var(--subtitle-background, rgba(4, 7, 11, 0.82));
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.34);
  text-align: center;
}

.desktop-subtitle-source {
  color: rgba(226, 234, 245, 0.84);
  font-size: max(13px, calc(var(--subtitle-font-size, 24px) - 6px));
  line-height: 1.4;
  word-break: break-word;
}

.desktop-subtitle-translated {
  color: var(--subtitle-font-color, #ffffff);
  font-size: var(--subtitle-font-size, 24px);
  font-weight: 700;
  line-height: 1.4;
  word-break: break-word;
}

.desktop-subtitle-entry.only-source .desktop-subtitle-source {
  color: var(--subtitle-font-color, #ffffff);
  font-size: var(--subtitle-font-size, 24px);
  font-weight: 650;
}

.desktop-subtitle-entry.only-translated .desktop-subtitle-translated {
  font-size: calc(var(--subtitle-font-size, 24px) + 2px);
}

.desktop-subtitle-entry.revised {
  border-color: rgba(244, 200, 76, 0.58);
}

.desktop-subtitle-cursor {
  align-self: center;
  color: #f4c84c;
  animation: subtitle-blink 0.7s infinite;
}

@keyframes subtitle-blink {
  0%, 45% {
    opacity: 1;
  }
  46%, 100% {
    opacity: 0.2;
  }
}

@media (prefers-reduced-motion: reduce) {
  .desktop-subtitle-cursor {
    animation: none;
  }
}
`


export function createUnavailableWebOverlayState(): WebOverlayState {
  return {
    available: false,
    visible: false,
    transport: null,
    reason: 'unavailable',
  }
}


export function createWebOverlayUrl(currentUrl: string | URL): string {
  const url = new URL(currentUrl)
  url.searchParams.set('surface', 'overlay')
  url.searchParams.set('transport', 'web')
  return url.toString()
}


export function isWebOverlaySurface(search: string): boolean {
  const params = new URLSearchParams(search)
  return params.get('surface') === 'overlay' && params.get('transport') === 'web'
}


export function createWebOverlaySnapshotMessage(
  snapshot: DesktopOverlaySnapshot,
): WebOverlaySnapshotMessage {
  return {
    type: 'web-subtitle-snapshot',
    snapshot,
  }
}


export function isWebOverlaySnapshotMessage(
  value: unknown,
): value is WebOverlaySnapshotMessage {
  if (!isRecord(value) || value.type !== 'web-subtitle-snapshot') {
    return false
  }

  const snapshot = value.snapshot
  if (!isRecord(snapshot)) {
    return false
  }

  return (
    Array.isArray(snapshot.entries) &&
    isSubtitleMode(snapshot.mode) &&
    typeof snapshot.updatedAt === 'number'
  )
}


export function subscribeToWebOverlaySnapshots(
  listener: SnapshotListener,
  hostWindow = window,
): () => void {
  const cleanupCallbacks: Array<() => void> = []
  const latestSnapshot = readStoredSnapshot(hostWindow)

  if (latestSnapshot) {
    listener(latestSnapshot)
  }

  if (typeof hostWindow.BroadcastChannel !== 'undefined') {
    const channel = new hostWindow.BroadcastChannel(WEB_OVERLAY_CHANNEL_NAME)
    const handleMessage = (event: MessageEvent<unknown>): void => {
      const message = event.data
      if (isWebOverlaySnapshotMessage(message)) {
        listener(message.snapshot)
      }
    }

    channel.addEventListener('message', handleMessage)
    cleanupCallbacks.push(() => {
      channel.removeEventListener('message', handleMessage)
      channel.close()
    })
  }

  const handleStorage = (event: StorageEvent): void => {
    if (event.key !== WEB_OVERLAY_STORAGE_KEY || !event.newValue) {
      return
    }

    const message = parseSnapshotMessage(event.newValue)
    if (message) {
      listener(message.snapshot)
    }
  }

  hostWindow.addEventListener('storage', handleStorage)
  cleanupCallbacks.push(() => hostWindow.removeEventListener('storage', handleStorage))

  return () => {
    cleanupCallbacks.forEach((cleanup) => cleanup())
  }
}


export class WebFloatingSubtitleOverlay {
  private readonly _hostWindow: Window
  private readonly _listeners: Set<StateListener> = new Set()
  private _state: WebOverlayState = {
    available: true,
    visible: false,
    transport: null,
    reason: 'ready',
  }
  private _floatingWindow: Window | null = null
  private _transport: WebOverlayTransport | null = null
  private _lastSnapshot: DesktopOverlaySnapshot = INITIAL_SNAPSHOT
  private _pipStackElement: HTMLElement | null = null
  private _pipShellElement: HTMLElement | null = null
  private _closePollId: number | null = null
  private _broadcastChannel: BroadcastChannel | null = null

  constructor(hostWindow = window) {
    this._hostWindow = hostWindow
  }

  get state(): WebOverlayState {
    return { ...this._state }
  }

  subscribe(listener: StateListener): () => void {
    this._listeners.add(listener)
    listener(this.state)
    return () => this._listeners.delete(listener)
  }

  async open(): Promise<WebOverlayState> {
    if (this._floatingWindow && !this._floatingWindow.closed) {
      this._floatingWindow.focus()
      this._updateState({
        available: true,
        visible: true,
        transport: this._transport,
        reason: 'ready',
      })
      this.sendSnapshot(this._lastSnapshot)
      return this.state
    }

    const pictureInPicture = this._hostWindow.documentPictureInPicture
    if (pictureInPicture) {
      try {
        const pipWindow = await pictureInPicture.requestWindow({
          width: WEB_OVERLAY_WIDTH,
          height: WEB_OVERLAY_HEIGHT,
          disallowReturnToOpener: false,
        })
        this._attachPictureInPictureWindow(pipWindow)
        return this.state
      } catch (error) {
        console.warn('[WebFloatingSubtitleOverlay] Document Picture-in-Picture failed', error)
      }
    }

    try {
      const popupWindow = this._hostWindow.open(
        createWebOverlayUrl(this._hostWindow.location.href),
        WEB_OVERLAY_WINDOW_NAME,
        createPopupFeatures(),
      )

      if (!popupWindow) {
        this._handleOpenFailure('popup_blocked')
        return this.state
      }

      this._attachPopupWindow(popupWindow)
      return this.state
    } catch (error) {
      console.warn('[WebFloatingSubtitleOverlay] Popup overlay failed', error)
      this._handleOpenFailure('open_failed')
      return this.state
    }
  }

  close(): void {
    this._stopClosePolling()

    if (this._floatingWindow && !this._floatingWindow.closed) {
      this._floatingWindow.close()
    }

    this._floatingWindow = null
    this._transport = null
    this._pipStackElement = null
    this._pipShellElement = null
    clearStoredSnapshot(this._hostWindow)
    this._updateState({
      available: true,
      visible: false,
      transport: null,
      reason: 'closed',
    })
  }

  sendSnapshot(snapshot: DesktopOverlaySnapshot): void {
    this._lastSnapshot = snapshot

    if (this._transport === 'document-picture-in-picture') {
      this._renderPictureInPictureSnapshot(snapshot)
    }

    if (
      this._transport === 'popup' &&
      this._floatingWindow &&
      !this._floatingWindow.closed
    ) {
      publishSnapshot(snapshot, this._hostWindow, this._getBroadcastChannel())
    }
  }

  destroy(): void {
    this.close()
    if (this._broadcastChannel) {
      this._broadcastChannel.close()
      this._broadcastChannel = null
    }
    this._listeners.clear()
  }

  private _attachPictureInPictureWindow(pipWindow: Window): void {
    this._stopClosePolling()
    this._floatingWindow = pipWindow
    this._transport = 'document-picture-in-picture'
    this._preparePictureInPictureDocument(pipWindow.document)
    this._listenForClose(pipWindow)
    this._updateState({
      available: true,
      visible: true,
      transport: 'document-picture-in-picture',
      reason: 'ready',
    })
    this.sendSnapshot(this._lastSnapshot)
  }

  private _attachPopupWindow(popupWindow: Window): void {
    this._stopClosePolling()
    this._floatingWindow = popupWindow
    this._transport = 'popup'
    popupWindow.focus()
    this._listenForClose(popupWindow)
    this._updateState({
      available: true,
      visible: true,
      transport: 'popup',
      reason: 'ready',
    })
    this.sendSnapshot(this._lastSnapshot)
  }

  private _preparePictureInPictureDocument(targetDocument: Document): void {
    targetDocument.title = 'AI Interpreter Subtitles'
    targetDocument.documentElement.dataset.surface = 'subtitle-overlay'
    targetDocument.head.replaceChildren()
    targetDocument.body.replaceChildren()

    const style = targetDocument.createElement('style')
    style.textContent = WEB_PIP_OVERLAY_STYLE
    targetDocument.head.appendChild(style)

    const root = targetDocument.createElement('div')
    root.id = 'web-subtitle-overlay-root'

    const shell = targetDocument.createElement('main')
    shell.setAttribute('aria-label', 'Floating subtitles')
    shell.className = 'desktop-subtitle-overlay-shell'

    const stack = targetDocument.createElement('div')
    stack.className = 'desktop-subtitle-stack'

    shell.appendChild(stack)
    root.appendChild(shell)
    targetDocument.body.appendChild(root)

    this._pipStackElement = stack
    this._pipShellElement = shell
  }

  private _renderPictureInPictureSnapshot(snapshot: DesktopOverlaySnapshot): void {
    const stack = this._pipStackElement
    if (!stack) {
      return
    }

    const targetDocument = stack.ownerDocument
    const nodes = snapshot.entries.map((entry) =>
      createSubtitleEntryElement(entry, snapshot.mode, targetDocument),
    )
    stack.replaceChildren(...nodes)

    const style = normalizeSubtitleStyle(snapshot.style)
    applyCssVarMap(stack, buildSubtitleStyleVarMap(style))
    if (this._pipShellElement) {
      this._pipShellElement.style.setProperty('--subtitle-align', POSITION_ALIGN[style.position])
    }
  }

  private _listenForClose(targetWindow: Window): void {
    const handleClosed = (): void => {
      if (this._floatingWindow !== targetWindow) {
        return
      }
      this._floatingWindow = null
      this._transport = null
      this._pipStackElement = null
      this._pipShellElement = null
      this._stopClosePolling()
      clearStoredSnapshot(this._hostWindow)
      this._updateState({
        available: true,
        visible: false,
        transport: null,
        reason: 'closed',
      })
    }

    targetWindow.addEventListener('pagehide', handleClosed, { once: true })
    targetWindow.addEventListener('beforeunload', handleClosed, { once: true })

    this._closePollId = this._hostWindow.setInterval(() => {
      if (!targetWindow.closed) {
        return
      }
      handleClosed()
    }, WEB_OVERLAY_CLOSE_POLL_MS)
  }

  private _stopClosePolling(): void {
    if (this._closePollId === null) {
      return
    }

    this._hostWindow.clearInterval(this._closePollId)
    this._closePollId = null
  }

  private _handleOpenFailure(reason: WebOverlayReason): void {
    this._floatingWindow = null
    this._transport = null
    this._pipStackElement = null
    this._pipShellElement = null
    this._updateState({
      available: true,
      visible: false,
      transport: null,
      reason,
    })
  }

  private _getBroadcastChannel(): BroadcastChannel | null {
    if (this._broadcastChannel) {
      return this._broadcastChannel
    }

    if (typeof this._hostWindow.BroadcastChannel === 'undefined') {
      return null
    }

    this._broadcastChannel = new this._hostWindow.BroadcastChannel(WEB_OVERLAY_CHANNEL_NAME)
    return this._broadcastChannel
  }

  private _updateState(state: WebOverlayState): void {
    this._state = state
    const nextState = this.state
    this._listeners.forEach((listener) => listener(nextState))
  }
}


function createPopupFeatures(): string {
  const features = [
    'popup=yes',
    `width=${WEB_OVERLAY_WIDTH}`,
    `height=${WEB_OVERLAY_HEIGHT}`,
    'left=160',
    'top=120',
    'resizable=yes',
    'scrollbars=no',
    'noopener=no',
  ]
  return features.join(',')
}


function createSubtitleEntryElement(
  entry: SubtitleEntry,
  mode: SubtitleMode,
  targetDocument: Document,
): HTMLElement {
  const displayState = getSubtitleDisplayState(entry, mode)
  const section = targetDocument.createElement('section')
  section.className = displayState.className
  section.dataset.segmentId = entry.segmentId

  if (displayState.showSource) {
    const source = targetDocument.createElement('div')
    source.className = 'desktop-subtitle-source'
    source.textContent = entry.sourceText
    section.appendChild(source)
  }

  if (displayState.showTranslated) {
    const translated = targetDocument.createElement('div')
    translated.className = 'desktop-subtitle-translated'
    translated.textContent = entry.translatedText
    section.appendChild(translated)
  }

  if (entry.isPartial) {
    const cursor = targetDocument.createElement('span')
    cursor.setAttribute('aria-hidden', 'true')
    cursor.className = 'desktop-subtitle-cursor'
    cursor.textContent = '|'
    section.appendChild(cursor)
  }

  return section
}


function publishSnapshot(
  snapshot: DesktopOverlaySnapshot,
  hostWindow: Window,
  channel: BroadcastChannel | null,
): void {
  const message = createWebOverlaySnapshotMessage(snapshot)

  channel?.postMessage(message)

  try {
    hostWindow.localStorage.setItem(WEB_OVERLAY_STORAGE_KEY, JSON.stringify(message))
  } catch (error) {
    console.warn('[WebFloatingSubtitleOverlay] Failed to store subtitle snapshot', error)
  }
}


function readStoredSnapshot(hostWindow: Window): DesktopOverlaySnapshot | null {
  try {
    const raw = hostWindow.localStorage.getItem(WEB_OVERLAY_STORAGE_KEY)
    if (!raw) {
      return null
    }
    return parseSnapshotMessage(raw)?.snapshot ?? null
  } catch (error) {
    console.warn('[WebFloatingSubtitleOverlay] Failed to read stored subtitle snapshot', error)
    return null
  }
}


function clearStoredSnapshot(hostWindow: Window): void {
  try {
    hostWindow.localStorage.removeItem(WEB_OVERLAY_STORAGE_KEY)
  } catch (error) {
    console.warn('[WebFloatingSubtitleOverlay] Failed to clear stored subtitle snapshot', error)
  }
}


function parseSnapshotMessage(raw: string): WebOverlaySnapshotMessage | null {
  try {
    const parsed: unknown = JSON.parse(raw)
    return isWebOverlaySnapshotMessage(parsed) ? parsed : null
  } catch {
    return null
  }
}


function applyCssVarMap(element: HTMLElement, vars: Record<string, string>): void {
  Object.entries(vars).forEach(([key, value]) => {
    element.style.setProperty(key, value)
  })
}


function isSubtitleMode(value: unknown): value is SubtitleMode {
  return value === 'bilingual' || value === 'translation_only' || value === 'source_only'
}


function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}
