# Improve Subtitle Display Surface

## Goal

Make the AI simultaneous interpretation assistant present subtitles where users naturally watch content, instead of requiring them to look back at the app page. The current app-page subtitle overlay is acceptable for diagnostics but not for a polished user workflow.

## What I Already Know

- The current subtitle overlay is rendered inside the AI Interpreter web page by `frontend/src/subtitle/SubtitleRenderer.ts`.
- The overlay appears at the bottom center of the app page only after subtitle entries arrive.
- The browser capture path captures audio from a shared screen/window/tab but does not display the captured video in the app.
- The Electron desktop launcher exists, but `frontend/electron/main.cjs` currently creates only one normal app window.
- The user expects one of these product shapes:
  - subtitles injected into the original webpage,
  - original video/screen mirrored into the project page with subtitles over it,
  - or a screen-level floating subtitle overlay like desktop translation software.

## Assumptions

- The next step should improve real user testing ergonomics, not only explain the current limitation.
- Windows local desktop use is acceptable as the first target because the project already has Electron launcher support.
- Browser-only behavior should remain usable, even if the best overlay experience is desktop-only.

## Requirements

- Provide a subtitle display surface that does not require users to stare at the control page during normal viewing.
- Implement the next MVP as an Electron desktop floating subtitle overlay.
- Keep the control panel in the existing Electron app window.
- Render translated subtitles in a transparent, always-on-top overlay window above other desktop windows.
- Preserve the existing translation pipeline, language selection, revision behavior, history/export, and diagnostics.
- Keep the current in-page subtitle renderer as a fallback or diagnostic mode unless it conflicts with the new surface.
- Make the UX clear enough that users understand where subtitles will appear.

## Acceptance Criteria

- [ ] The user can start a desktop session and see live subtitles in a floating overlay above other windows.
- [ ] The overlay can be shown/hidden or restored without stopping the translation session.
- [ ] The control panel still shows connection, capture, queue, revision, and export status.
- [ ] Browser-only startup still works with the existing in-page subtitle fallback.
- [ ] Frontend tests cover the new subtitle routing/state behavior where practical.
- [ ] Manual validation documents Windows overlay behavior and known limitations.

## Definition of Done

- Tests added/updated where appropriate.
- Frontend build and tests pass.
- Backend tests remain green if backend behavior is touched.
- README or roadmap notes are updated if startup or usage changes.
- Changes are committed and delivered through the existing PR workflow when implementation is complete.

## Out of Scope

- Chrome/Edge extension injection into arbitrary original webpages.
- Full system-audio capture without browser display-capture permission prompts.
- Packaged installer/signing for a production desktop app.
- Mobile support.
- Guaranteed overlay behavior on DRM/protected fullscreen video surfaces.

## Technical Approach

Recommended MVP: add an Electron transparent always-on-top subtitle overlay window while keeping the existing app window as the control panel. The overlay should receive subtitle updates from the existing frontend state and render them in a click-through floating window.

## Decision (ADR-lite)

**Context**: The current subtitle renderer appears only inside the AI Interpreter page, which is useful for debugging but awkward for real viewing. Users expect subtitles either over the original content or as a screen-level floating utility.

**Decision**: Build an Electron transparent always-on-top subtitle overlay as the next MVP. Keep the browser in-page renderer as a fallback for development and browser-only startup.

**Consequences**: This gives the best near-term user experience on Windows desktop while avoiding the larger browser-extension scope. The feature remains desktop-first and will need explicit manual validation for click-through, z-order, fullscreen, DPI, and multi-monitor behavior.

## Research References

- [`research/display-surface-options.md`](research/display-surface-options.md) - compares in-app video preview, Electron overlay, and browser extension injection.

## Open Questions

- None for MVP scope. Implementation can proceed with the Electron overlay direction.

## Technical Notes

- Current renderer: `frontend/src/subtitle/SubtitleRenderer.ts`.
- App controller/state: `frontend/src/store/AppStore.ts`.
- Electron main process: `frontend/electron/main.cjs`.
- Desktop launcher: `tools/desktop_launcher.py` and `start-desktop.ps1`.

## Validation Notes

- `npm.cmd run test` in `frontend` passed with 18 tests.
- `npm.cmd run build` in `frontend` passed.
- `node --check frontend\electron\main.cjs` passed.
- `node --check frontend\electron\preload.cjs` passed.
- `.\\backend\\.venv\\Scripts\\python.exe -m compileall tools\\desktop_launcher.py` passed.
- `.\\backend\\.venv\\Scripts\\python.exe -m unittest discover backend` passed with 62 tests.
- `git diff --check` reported only Windows LF-to-CRLF warnings.
- Desktop smoke: `start-desktop.cmd` loaded the Electron main window and
  `?surface=overlay` subtitle window when launched with temporary
  `AI_INTERPRETER_BACKEND_PORT=8001`,
  `VITE_WS_URL=ws://127.0.0.1:8001/api/v1/ws/translate`,
  `WHISPER_DEVICE=cpu`, and `WHISPER_COMPUTE_TYPE=int8`.
- Local caveat: the default `backend/.env.local` CUDA `large-v3` startup failed
  with GPU out-of-memory during manual smoke. The file was not changed.
