# Web Floating Subtitle Window

## Goal

Upgrade web mode so live subtitles are not limited to the main control page. Users should be able to open an external subtitle window from the web app and place it above a video, meeting the "floating subtitle" workflow without relying on Electron or local model downloads.

## Requirements

* Keep web startup as the primary path.
* Add a control-panel entry for opening or closing a web floating subtitle window.
* Prefer Chromium Document Picture-in-Picture when available so the subtitle window can float above other browser content.
* Fall back to a normal popup window when Document Picture-in-Picture is unavailable.
* Reuse the existing subtitle snapshot/display contract so revisions, bilingual/source/translation modes, partial cursor state, and max visible subtitles remain consistent with the existing overlay.
* Keep the main web page responsible for audio capture, WebSocket translation, settings, and history export.
* Show the existing in-page subtitles unchanged for users who do not open the floating window.
* Document that web floating subtitles do not inject DOM into third-party video pages and that true OS-level always-on-top behavior remains Electron-only.

## Acceptance Criteria

* [ ] In web mode, the control panel shows a usable floating-subtitle button even when Electron is unavailable.
* [ ] Clicking the button opens an external subtitle surface and streams current/future subtitle snapshots into it.
* [ ] Closing the external surface updates the control-panel state.
* [ ] Subtitle mode changes and translation revisions propagate to the external surface.
* [ ] Browsers without Document Picture-in-Picture fall back to a popup window.
* [ ] Existing Electron overlay behavior remains compatible.
* [ ] Frontend tests cover the new web floating-window controller logic.
* [ ] Build and test commands pass.

## Definition of Done

* Tests added or updated for new frontend behavior.
* `npm.cmd run test` and `npm.cmd run build` pass.
* Documentation updated where current web-mode limitation is described.
* Changes are committed and pushed to the existing PR branch per project delivery requirements.

## Technical Approach

Add a web floating subtitle controller that can open either a Document Picture-in-Picture window or a popup window. The controller will render the existing `DesktopSubtitleOverlay` surface at `?surface=overlay&transport=web`, then send `DesktopOverlaySnapshot` values via `BroadcastChannel` with `localStorage` event fallback. `DesktopSubtitleOverlay` will listen to both Electron preload messages and the new web transport. `App.tsx` will manage the controller state and send snapshots whenever `visibleSubtitles` or subtitle mode changes.

## Decision (ADR-lite)

**Context**: The user rejected subtitles that only appear inside the app page and also rejected Electron because local Electron startup has been unreliable.

**Decision**: Implement a browser-native floating subtitle window for web mode. Use Document Picture-in-Picture first, then popup fallback.

**Consequences**: This gives a practical floating experience from `start-web.cmd` without GPU/model downloads. It cannot inject subtitles directly into arbitrary websites and cannot guarantee OS-level always-on-top behavior in non-supporting browsers.

## Out of Scope

* Browser extension that injects subtitle DOM into original video pages.
* Reworking audio capture or ASR/MT backend behavior.
* Electron fixes or packaged desktop distribution.
* Native OS transparent overlay outside browser APIs.

## Research References

* [`research/web-floating-subtitles.md`](research/web-floating-subtitles.md) - Compares web external subtitle display options under the current project constraints.

## Technical Notes

* Existing overlay snapshot helpers live in `frontend/src/desktop/overlay.ts`.
* Existing Electron overlay surface is `frontend/src/desktop/DesktopSubtitleOverlay.tsx`.
* Main app already emits overlay snapshots to Electron in `frontend/src/App.tsx`.
* Control-panel button currently only appears when `desktopOverlayState.available` is true.
* README currently says web mode is page-only; update that section after implementation.
