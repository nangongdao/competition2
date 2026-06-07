# Web-first Startup

## Goal

Make the browser workflow the recommended and reliable startup path for the AI simultaneous interpretation assistant because the Electron launcher repeatedly fails for the user. The app should start local backend/static services, open in the default browser, and allow model/API/runtime settings to be edited from the web UI without requiring Electron.

## What I already know

* The user reports Electron has not successfully started once and wants to use the web startup path instead.
* The current launcher, docs, and shortcut scripts still frame Electron desktop mode as the primary startup path.
* The frontend settings panel currently depends on the Electron preload bridge; in a normal browser it reports settings unavailable.
* The Python launcher already knows how to build/serve the Vite app, start the backend, select a backend port, apply local settings to backend environment, and inject the WebSocket URL into the frontend query string.
* Local settings should remain in a Git-ignored file and secrets must not be printed or committed.

## Requirements

* Add a web-first one-click startup path for Windows that does not require Electron.
* Reuse the existing Python service lifecycle where practical: frontend build/static server, backend startup, backend health checks, port fallback, startup log, and low-resource ASR default.
* Open the app in the user's default browser with the correct runtime WebSocket URL.
* Let browser mode load and save the same local settings file used by desktop mode through a local backend API.
* Keep real API keys write-only from the renderer/browser perspective: show only configured/missing state and preserve existing saved keys when the secret input is blank.
* Make the UI copy accurate for browser mode, including restart guidance for backend-affecting settings.
* Update README/roadmap documentation so web startup is the recommended path and Electron is clearly optional/fallback.
* Keep Electron support available unless removing it is necessary for web startup.

## Acceptance Criteria

* [x] `start-web.cmd` or equivalent starts the app without invoking Electron.
* [x] The web launcher opens a browser URL containing the runtime `wsUrl` for the selected backend port.
* [x] Browser mode settings panel is available and can save to `config/desktop-settings.local.json` without exposing saved secret values back to the UI.
* [x] Backend startup reads the saved settings on the next launcher run and injects supported values into backend environment.
* [x] Existing frontend tests pass, and tests cover browser settings load/save behavior.
* [x] Launcher unit tests cover web mode and browser opening without starting Electron.
* [x] Documentation explains that browser mode subtitles appear inside the web page; the transparent always-on-top overlay remains Electron-only.

## Definition of Done

* Tests added/updated where the behavior changed.
* Frontend build and relevant backend/tool unit tests pass.
* Docs updated for web-first usage and known limitations.
* No API keys or local-only settings are committed.
* Work is committed with a meaningful Conventional Commit, pushed, and PR #3 is updated.

## Technical Approach

Extend the existing launcher instead of creating a second lifecycle implementation. Add a launch mode or browser entry point that uses the same static server/backend startup flow, then opens the default browser and waits until the user exits the launcher. Add backend settings endpoints for localhost browser use, sharing normalization/persistence rules with the existing Electron settings bridge as closely as possible.

## Decision (ADR-lite)

**Context**: Electron is currently blocking the user's ability to run the project at all, while the Vite/browser UI already contains the core interpretation experience.

**Decision**: Make browser startup the recommended default path and keep Electron as an optional desktop overlay path.

**Consequences**: Browser mode is lower-risk and avoids Electron startup failures, but transparent always-on-top subtitles and tray/window behavior remain unavailable outside Electron. Browser mode subtitles are visible inside the app page unless a future browser extension or native overlay path is added.

## Out of Scope

* Fixing Electron startup failures in this task.
* Implementing a browser extension that injects subtitles into arbitrary web pages.
* Implementing OS-level transparent overlays without Electron.
* Full system-audio capture outside browser microphone/tab-audio permissions.
* Hot-restarting the backend immediately after settings save.

## Technical Notes

* Relevant launcher file: `tools/desktop_launcher.py`.
* Relevant frontend settings files: `frontend/src/desktop/settings.ts`, `frontend/src/ui/SettingsPanel.tsx`, `frontend/src/App.tsx`.
* Relevant backend router file: `backend/api/router.py`.
* Relevant docs: `README.md`, `ROADMAP.md`, `.trellis/spec/shared/desktop-launcher.md`.

## Validation

* `npm.cmd run test`
* `npm.cmd run build`
* `.\\backend\\.venv\\Scripts\\python.exe -m unittest backend.test_local_settings tools.test_desktop_launcher`
* `.\\backend\\.venv\\Scripts\\python.exe -m unittest discover backend`
* `.\\backend\\.venv\\Scripts\\python.exe -m compileall tools\\desktop_launcher.py tools\\test_desktop_launcher.py backend\\api backend\\services backend\\test_local_settings.py`
* `.\\backend\\.venv\\Scripts\\python.exe tools\\desktop_launcher.py --help`
* `node --check frontend\\electron\\main.cjs`
* `node --check frontend\\electron\\preload.cjs`
* `git diff --check`
