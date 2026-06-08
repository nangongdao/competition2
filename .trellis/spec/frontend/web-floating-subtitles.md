# Web Floating Subtitles

## Scenario: Browser external subtitle window

### 1. Scope / Trigger

- Trigger: changes to web-mode subtitle display outside the main control page.
- Applies to `frontend/src/desktop/web-overlay.ts`,
  `frontend/src/desktop/DesktopSubtitleOverlay.tsx`, and `frontend/src/App.tsx`.
- Does not apply to Electron IPC overlay wiring except where the shared
  `DesktopOverlaySnapshot` contract is reused.

### 2. Signatures

```typescript
type WebOverlayTransport = 'document-picture-in-picture' | 'popup'

interface WebOverlayState {
  available: boolean
  visible: boolean
  transport: WebOverlayTransport | null
  reason: 'ready' | 'unavailable' | 'popup_blocked' | 'open_failed' | 'closed'
}

interface WebOverlaySnapshotMessage {
  type: 'web-subtitle-snapshot'
  snapshot: DesktopOverlaySnapshot
}
```

Main app usage:

```typescript
const overlay = new WebFloatingSubtitleOverlay()
await overlay.open()
overlay.sendSnapshot(createDesktopOverlaySnapshot(entries, mode))
overlay.close()
```

Overlay route usage:

```typescript
subscribeToWebOverlaySnapshots((snapshot) => setSnapshot(snapshot))
```

### 3. Contracts

- The main app remains the only audio-capture and WebSocket owner in web mode.
- The external web subtitle window is display-only.
- Use `DocumentPictureInPicture.requestWindow()` first when available.
- Use `window.open(createWebOverlayUrl(...))` as fallback.
- Popup route URL must include `surface=overlay&transport=web`.
- Popup communication uses `BroadcastChannel` plus `localStorage` fallback.
- `localStorage` may store only the latest `WebOverlaySnapshotMessage`, only
  while the popup fallback is open, and must be cleared on close.
- Document Picture-in-Picture renders in memory and must not persist subtitle
  text to storage.

### 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Document Picture-in-Picture succeeds | Render subtitle entries directly into the PiP document |
| Document Picture-in-Picture throws | Fall back to popup open |
| Popup is blocked | Set `reason = 'popup_blocked'` and keep `visible = false` |
| Popup route receives malformed message | Ignore it |
| User closes popup/PiP window | Set `visible = false`, clear stored snapshot |
| Electron bridge is available | Prefer Electron overlay controls over web overlay controls |

### 5. Good/Base/Bad Cases

- Good: web startup shows a floating-subtitle button, opens a PiP window in
  Chromium, and keeps revisions/mode changes in sync via the same snapshot.
- Base: browsers without Document Picture-in-Picture open a normal popup and
  sync snapshots through `BroadcastChannel` or the latest stored snapshot.
- Bad: the main page writes every subtitle token to persistent storage when no
  popup is open, or the overlay route tries to capture audio itself.

### 6. Tests Required

- Unit test `createWebOverlayUrl()` preserves existing runtime query params and
  adds `surface=overlay&transport=web`.
- Unit test `isWebOverlaySurface()` requires both overlay and web transport
  params.
- Unit test malformed `WebOverlaySnapshotMessage` values are rejected.
- Frontend build must type-check custom browser APIs without `any` or
  `@ts-ignore`.

### 7. Wrong vs Correct

#### Wrong

```typescript
// Writes private subtitle text even when the user never opened a popup.
localStorage.setItem('subtitle', JSON.stringify(snapshot))
```

#### Correct

```typescript
if (transport === 'popup' && popupWindow && !popupWindow.closed) {
  publishSnapshot(snapshot)
}
```

#### Wrong

```typescript
// Web overlay route starts another capture session.
controller.start()
```

#### Correct

```typescript
// Web overlay route only receives snapshots from the main app.
subscribeToWebOverlaySnapshots(setSnapshot)
```
