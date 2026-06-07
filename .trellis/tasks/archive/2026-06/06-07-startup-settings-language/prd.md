# Startup Settings and UI Language

## Goal

Add a settings experience to the desktop startup/control page so users can configure local AI provider/model settings without manually editing secret files, and switch the interface language between Chinese and English.

## What I Already Know

* The user wants settings inside the project startup page instead of requiring manual API-key file editing.
* Secret values must stay local; the repository should only contain a matching template/example file for GitHub.
* The existing app is a Vite + React frontend with an Electron desktop launcher and floating subtitle overlay.
* The backend reads translation/provider settings from environment variables and dotenv files at process startup.
* The desktop launcher already owns backend startup, ASR profile selection, frontend static serving, and Electron launch.

## Requirements

* Add a settings entry in the desktop/control UI that is visible before translation starts.
* Provide UI language selection with exactly two choices: Chinese and English.
* Persist UI language locally and apply it immediately in the frontend where practical.
* Provide settings for OpenAI-compatible translation configuration:
  * translation engine
  * model name
  * OpenAI-compatible base URL
  * API key, saved locally without exposing the existing stored key back to the renderer
* Preserve existing Anthropic/Claude configuration support where it is already part of the backend settings surface.
* Provide a desktop ASR resource profile setting so users can choose low-resource CPU or GPU behavior from the UI.
* Store real secrets in a local ignored file and commit only a same-shape example/template file.
* Have the desktop launcher read the local settings file and pass supported values to the backend environment on startup.
* Show clear UI status when provider/model/ASR settings require app restart before taking effect.
* Keep browser mode usable; if desktop settings IPC is unavailable, show a read-only/unavailable state instead of crashing.

## Acceptance Criteria

* [ ] Electron desktop mode shows a Settings button in the startup/control experience.
* [ ] Settings panel can switch UI language between Chinese and English.
* [ ] Settings panel can save OpenAI-compatible model/base URL/API key into a local ignored settings file.
* [ ] The frontend never displays the stored secret value after loading settings; it only shows whether a key is configured.
* [ ] `tools/desktop_launcher.py` loads local settings and injects provider/model/source-language/ASR-profile values into backend startup environment.
* [ ] A tracked example settings file documents the local file shape without secrets.
* [ ] Frontend tests cover settings bridge helpers and language dictionaries.
* [ ] Launcher tests cover local settings env injection and ASR profile selection from settings.
* [ ] `npm.cmd run test`, `npm.cmd run build`, and relevant backend/tool tests pass.

## Definition of Done

* Tests added/updated where behavior changes.
* Build and unit tests pass for touched frontend/backend/tooling.
* Docs updated for the new settings workflow and local/template file split.
* No real API keys or local secrets are committed or printed.
* Changes are committed, pushed to the project repository branch, and PR progress is updated.

## Technical Approach

Use Electron IPC as the settings boundary for desktop mode. The renderer can read a secret-redacted snapshot and submit updates; Electron main process validates and writes the local settings file. The Python desktop launcher reads the same local file before backend startup and maps supported fields into environment variables.

The backend process still receives settings through the existing environment/dotenv mechanism. Provider/model/ASR changes saved after backend startup require restarting the desktop app. UI language is frontend-only and can apply immediately.

## Decision (ADR-lite)

**Context**: Secrets should be configurable through the UI, but should not be committed or exposed through normal browser JavaScript. The launcher already controls backend process startup.

**Decision**: Store desktop settings in `config/desktop-settings.local.json` and commit `config/desktop-settings.example.json`. Electron IPC writes the local file, and `tools/desktop_launcher.py` reads it on the next startup.

**Consequences**: This avoids committing secrets and keeps backend configuration compatible with the current environment-driven code. Backend-affecting settings require restart until a dedicated runtime-reload mechanism is added.

## Out of Scope

* Packaged installer/signing.
* Browser-mode secret editing without Electron.
* Hot-restarting the backend from the Electron renderer.
* Full multi-language target translation; the product target remains Simplified Chinese.
* Cloud TTS provider configuration.

## Technical Notes

* Likely frontend files: `frontend/src/App.tsx`, `frontend/src/ui/ControlPanel.tsx`, `frontend/src/ui/SubtitleHistoryPanel.tsx`, new settings/i18n modules.
* Likely Electron files: `frontend/electron/main.cjs`, `frontend/electron/preload.cjs`.
* Likely tooling files: `tools/desktop_launcher.py`, `tools/test_desktop_launcher.py`.
* Existing local secret ignores include `.env`, `.env.local`, `backend/.env`, and `backend/.env.local`; add the new desktop local settings file to `.gitignore`.
* Existing backend provider settings: `NMT_ENGINE`, `NMT_MODEL`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `ANTHROPIC_API_KEY`.
