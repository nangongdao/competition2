# Desktop Startup Resource Fallback

## Goal

Make double-click desktop startup resilient on local Windows machines by avoiding
stale backend port collisions and reducing the default desktop ASR footprint.

## What I Already Know

* The latest launcher log shows `large-v3 on cuda` loaded successfully, then
  startup failed because `127.0.0.1:8000` was already in use.
* The current desktop launcher checks whether port 8000 is healthy, but if an
  unhealthy process owns the port it still starts a new backend on 8000 and
  fails after backend initialization.
* The backend defaults are `WHISPER_MODEL=large-v3`, `WHISPER_DEVICE=cuda`, and
  `WHISPER_COMPUTE_TYPE=float16`, which can trigger GPU memory failures on
  common local machines.
* `backend/.env.local` is local-only and may contain secrets; it must not be
  printed, edited, or committed.

## Requirements

* Detect when the requested backend port is occupied but not healthy, and choose
  an available local fallback port for the launcher-owned backend.
* Pass the actual backend WebSocket URL to the Electron-rendered frontend at
  runtime so the UI connects to the selected backend port.
* Keep browser-only and Vite-dev behavior compatible with the existing
  `VITE_WS_URL` / default `127.0.0.1:8000` behavior.
* Use a low-resource desktop ASR profile by default for `start-desktop`, while
  allowing users to opt back into their local `.env.local` or GPU settings.
* Document the difference between the current failure cause (port collision) and
  GPU memory mitigation.

## Acceptance Criteria

* [x] Starting desktop while port 8000 is occupied by an unhealthy process no
  longer fails solely because of `Errno 10048`; the launcher selects another
  port and injects the matching WebSocket URL.
* [x] The default desktop backend process uses a lower resource Whisper profile
  unless the user explicitly chooses another profile.
* [x] Unit tests cover port fallback, ASR profile environment injection, and
  runtime WebSocket URL resolution.
* [x] Existing frontend and backend tests still pass.
* [x] Startup documentation and the desktop launcher spec reflect the new
  fallback behavior.

## Definition of Done

* Tests added or updated where behavior changes.
* Build, type check, and relevant syntax checks pass.
* Docs and Trellis spec updated for changed desktop startup behavior.
* Changes are committed and pushed to the active PR branch.

## Technical Approach

* Add socket-based port availability checks in `tools/desktop_launcher.py`.
* Resolve a backend port before process startup: reuse healthy backend on the
  requested port, use requested port if free, otherwise pick an available
  fallback port.
* Add a desktop ASR profile argument/environment setting with a low-resource
  default (`small`, `cpu`, `int8`) and an `env` option that preserves
  `.env.local` as the source of truth.
* Append a `wsUrl` runtime query parameter to the Electron app URL.
* Move frontend WebSocket URL resolution into a small tested helper.

## Out of Scope

* Killing unknown processes on port 8000.
* Editing or migrating `backend/.env.local`.
* Replacing Whisper with a cloud ASR provider in this task.
* Packaged installer work or system-audio capture changes.

## Technical Notes

* Relevant code: `tools/desktop_launcher.py`,
  `frontend/src/store/AppStore.ts`, `frontend/electron/main.cjs`,
  `backend/core/config.py`.
* Relevant spec: `.trellis/spec/shared/desktop-launcher.md`.
* The current failure log is a port binding failure, not the observed GPU OOM
  failure from earlier smoke tests.
