# Local Launcher Contract

This project uses a web-first local launcher for the default local demo
workflow, with an optional Electron desktop launcher for transparent floating
subtitles. Both launch modes share the same frontend build, static server,
backend startup, local settings file, and runtime WebSocket URL injection.

## Scenario: Desktop-Style Local Startup

### 1. Scope / Trigger

- Trigger: changes to `tools/desktop_launcher.py`, `frontend/electron/main.cjs`,
  `frontend/electron/preload.cjs`,
  `start-desktop.cmd`, `start-desktop.ps1`, frontend build paths, backend
  startup ports, Electron window behavior, floating subtitle overlay behavior,
  desktop local settings, or desktop shortcut install scripts.
- Scope: local Windows-first startup experience. This is not yet a packaged
  installer and does not replace the later system-audio capture evaluation.

### 2. Signatures

```bash
start-desktop.cmd
powershell.exe -File start-desktop.ps1
start-web.cmd
powershell.exe -File start-web.ps1
install-desktop-shortcut.cmd
powershell.exe -File install-desktop-shortcut.ps1
python tools/desktop_launcher.py [--mode desktop|web] [--build] [--backend-port PORT] [--frontend-port PORT] [--asr-profile PROFILE] [--no-splash]
npm run desktop:window --prefix frontend
```

```python
def ensure_frontend_build(force_build: bool) -> None: ...
def resolve_backend_port(requested_port: int) -> int: ...
def load_desktop_settings(path: Path = DESKTOP_SETTINGS_LOCAL_PATH) -> DesktopSettings: ...
def resolve_desktop_asr_profile(cli_profile: str | None, desktop_settings: DesktopSettings) -> str: ...
def build_backend_environment(port: int, asr_profile: str, desktop_settings: DesktopSettings | None = None) -> dict[str, str]: ...
def start_backend(port: int, asr_profile: str, desktop_settings: DesktopSettings | None = None) -> subprocess.Popen[str] | None: ...
def start_frontend_server(port: int) -> tuple[http.server.ThreadingHTTPServer, str]: ...
def ensure_desktop_runtime() -> Path: ...
def launch_desktop_window(url: str, backend_ws_url: str) -> subprocess.Popen[str]: ...
def launch_web_browser(url: str, backend_ws_url: str) -> str: ...
def wait_for_web_session(app_url: str) -> None: ...
```

### 3. Contracts

- `start-desktop.cmd` must be safe to double-click from Windows Explorer and
  should not leave a visible terminal window open.
- `start-web.cmd` must be safe to double-click from Windows Explorer and should
  leave a visible console window open so the user can stop launcher-owned
  services with `Ctrl+C` or by closing that window.
- `start-desktop.ps1` should prefer `backend/.venv/Scripts/pythonw.exe`, then
  `backend/.venv/Scripts/python.exe`, then `python`.
- `start-web.ps1` should prefer `backend/.venv/Scripts/python.exe`, then
  `python`; it must not use `pythonw.exe` because web mode needs a visible
  lifecycle console.
- `tools/desktop_launcher.py --build` must run the frontend production build
  before serving `frontend/dist`.
- The launcher serves `frontend/dist` from `127.0.0.1` on an available port by
  default.
- The launcher reuses the requested backend port only when `/api/v1/health`
  returns HTTP 200 or the port is available.
- If the requested backend port is occupied but not healthy, the launcher must
  select another available local port. It must not kill or reset an unknown
  process that owns the requested port.
- The launcher must pass the actual backend WebSocket URL to the frontend at
  runtime so the browser/Electron renderer connects to the selected backend
  port.
- In web mode, the launcher opens the default browser with the runtime `wsUrl`
  query parameter and then waits until the user stops the console session.
- The launcher opens Electron with `AI_INTERPRETER_DESKTOP_URL=<frontend-url>`.
- The launcher opens Electron with `AI_INTERPRETER_LOG_FILE=<log-path>` so the
  tray menu can open startup diagnostics.
- Desktop startup defaults to the low-resource ASR profile (`small`, `cpu`,
  `int8`). `--asr-profile env` preserves process/dotenv ASR settings, and
  `--asr-profile gpu` prefers `large-v3` on CUDA float16 for machines with
  enough VRAM.
- Desktop startup may read `config/desktop-settings.local.json` for local UI,
  translation, default source-language, and ASR-profile settings. The tracked
  `config/desktop-settings.example.json` file documents the same shape without
  secrets.
- Real keys in `config/desktop-settings.local.json` must stay ignored by Git.
  The renderer may show key presence but must not display a saved key value.
- Backend-affecting desktop settings are injected into the backend environment
  only when the launcher starts the backend. The UI must tell users to restart
  desktop mode after saving provider/model/API-key/ASR settings.
- Desktop settings must be validated through allowlists before use:
  `uiLanguage` (`zh-CN`, `en-US`), `translation.engine` (`openai`, `claude`),
  `runtime.asrProfile` (`light`, `cpu`, `gpu`, `env`), and
  `runtime.sourceLanguage` (`auto`, `en`, `ja`, `ko`, `es`, `fr`, `de`).
- Electron must render the app in a `BrowserWindow` with `nodeIntegration:
  false`, `contextIsolation: true`, and `sandbox: true`.
- Electron should enforce a single app instance and focus the existing window
  when a second instance is requested.
- Electron should provide tray restore, minimize-to-tray, reload, startup-log,
  and quit controls while preserving the existing close-to-exit lifecycle.
- The launcher must stop only processes it started. If the backend was already
  healthy before launch, leave that external backend running.
- `install-desktop-shortcut.cmd` must create a Windows desktop shortcut that
  launches `start-desktop.ps1` through hidden PowerShell with the project root
  as the working directory.
- Startup logs go to `logs/desktop-launcher.log`, and `logs/` must stay ignored
  by Git.

Environment keys:

| Key | Purpose |
| --- | --- |
| `AI_INTERPRETER_PYTHON` | Override Python executable for backend startup |
| `AI_INTERPRETER_BACKEND_PORT` | Override backend port |
| `AI_INTERPRETER_FRONTEND_PORT` | Override static frontend port, or `0` for any available port |
| `AI_INTERPRETER_DESKTOP_ASR_PROFILE` | Desktop ASR profile: `light`, `cpu`, `gpu`, or `env` |
| `AI_INTERPRETER_DESKTOP_URL` | Internal Electron URL injected by the Python launcher |
| `AI_INTERPRETER_LOG_FILE` | Internal Electron path for opening launcher logs from the tray |
| `VITE_WS_URL` | Override frontend WebSocket base URL at build time |

Local desktop settings keys:

| JSON path | Backend/runtime mapping |
| --- | --- |
| `uiLanguage` | Frontend interface language only |
| `translation.engine` | `NMT_ENGINE` |
| `translation.model` | `NMT_MODEL` |
| `translation.openaiBaseUrl` | `OPENAI_BASE_URL` |
| `translation.openaiApiKey` | `OPENAI_API_KEY` |
| `translation.anthropicApiKey` | `ANTHROPIC_API_KEY` |
| `runtime.asrProfile` | Desktop launcher ASR profile selection |
| `runtime.sourceLanguage` | `SOURCE_LANGUAGE` |

## Scenario: Floating Subtitle Overlay

### 1. Scope / Trigger

- Trigger: changes to Electron preload IPC, transparent overlay window options,
  desktop subtitle snapshot routing, or the `?surface=overlay` frontend entry.
- Scope: desktop subtitle presentation only. It does not imply system-audio
  capture, browser extension injection, or packaged installer support.

### 2. Contracts

- Electron should create the main app window as the control panel and a second
  transparent, frameless, always-on-top subtitle overlay window.
- The overlay window loads the same built frontend with
  `?surface=overlay`; this route must render only subtitles and must not start
  audio capture, WebSocket sessions, or backend requests.
- The overlay window must stay click-through with `setIgnoreMouseEvents(true)`
  so it does not block the app, browser tabs, video players, or meeting windows
  underneath it.
- The main renderer sends cloneable subtitle snapshots through the preload API;
  the Electron main process forwards those snapshots to the overlay window.
- The preload bridge must expose only the minimal desktop overlay API and must
  preserve `contextIsolation: true`, `nodeIntegration: false`, and
  `sandbox: true`.
- The main control panel and tray menu must allow the user to hide or restore
  the floating subtitle overlay without stopping the translation session.
- Browser-only startup must keep the existing in-page subtitle renderer as the
  fallback path when `window.aiInterpreterDesktop` is unavailable.
- Browser-only startup must keep the settings panel safe: when the preload
  bridge is absent, the frontend may read/write local settings only through the
  local backend settings API. If that API is unavailable, controls are disabled
  or reported unavailable.
- The overlay should use the primary display work area for MVP positioning and
  reposition when display metrics change.

### 3. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Desktop bridge is unavailable | Browser UI works, overlay controls stay hidden, in-page subtitles remain usable |
| Overlay window finishes loading after subtitles already exist | Latest subtitle snapshot is replayed to the overlay |
| User hides overlay | Overlay window hides, translation and history/export continue |
| User restores overlay | Overlay window reappears without reconnecting the backend session |
| Main window closes | Overlay window closes and launcher cleanup proceeds normally |
| Display metrics change | Overlay bounds are refreshed to the primary work area |
| Browser mode opens settings with backend API available | Settings panel loads/saves local settings through the backend API and does not expose saved key values |
| Browser mode opens settings without backend API | Settings panel reports local settings unavailable and does not crash |
| Saved API key exists | Renderer shows configured/missing state, not the raw saved key |
| User leaves key field blank | Electron preserves the existing saved key |
| User clears key | Electron writes an empty key value to the local settings file |
| User saves provider/model/ASR settings | UI warns that restart is required before backend changes take effect |

### 4. Tests Required

- Run `node --check frontend\electron\main.cjs` after changing Electron main
  process behavior.
- Run `node --check frontend\electron\preload.cjs` after changing preload IPC.
- Run `npm.cmd run test` in `frontend` after changing desktop subtitle snapshot,
  desktop settings helpers, i18n, or routing.
- Run `npm.cmd run build` in `frontend` after changing the overlay entry,
  TypeScript types, CSS, or Vite assets.
- Manually smoke-test `start-desktop.cmd`: confirm the main control window
  opens, the floating subtitle window is visible above other windows after
  subtitles arrive, the overlay is click-through, and the control panel/tray can
  hide and restore it.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| `frontend/dist/index.html` is missing | Build frontend when `--build` is set; otherwise fail with a logged error |
| `node_modules` is missing | Run `npm install` before `npm run build` |
| Backend health endpoint is already HTTP 200 | Reuse existing backend and do not terminate it on launcher exit |
| Requested backend port is occupied but health check fails | Select a different local backend port and inject the matching runtime WebSocket URL |
| Backend process exits before health check | Show startup error and write details to launcher log |
| Backend health timeout expires | Terminate the backend process started by the launcher |
| Electron runtime is missing | Run `npm install` in `frontend`; fail with a logged error if Electron is still unavailable |
| Electron main file is missing | Fail with a logged startup error |
| Startup fails while splash is visible | Close splash and show an error dialog when Tk is available |
| A second Electron instance is launched | Focus/show the existing window instead of creating duplicate app state |
| The window is minimized while tray is available | Hide to tray and allow restore from tray click or menu |
| Desktop shortcut install script is run | Create or update `AI Interpreter.lnk` on the Windows desktop |

### 5. Good/Base/Bad Cases

- Good: double-click `start-web.cmd`, local services start, the default browser
  opens with a runtime `wsUrl`, and the console explains how to stop services.
- Good: double-click `start-desktop.cmd`, a splash appears, local services start,
  and an Electron desktop window opens without a terminal window.
- Base: backend is already running on `127.0.0.1:8000`; launcher serves frontend
  and opens the app window without owning the backend process.
- Good: run `install-desktop-shortcut.cmd`, then use the desktop shortcut to
  start the same hidden launcher flow.
- Good: minimize the Electron window, restore it from the tray, and quit from
  the tray when done.
- Bad: launcher always kills port `8000` on exit, assumes a hard-coded browser
  path, or opens a browser URL without injecting the selected backend WebSocket
  URL.

### 6. Tests Required

- Run `python tools/desktop_launcher.py --help` after changing CLI arguments.
- Run `python -m unittest tools.test_desktop_launcher` after changing desktop
  launcher helper behavior.
- Run `python -m compileall tools/desktop_launcher.py` after changing launcher
  code.
- Run `.\frontend\node_modules\.bin\electron.cmd --version` or another Electron
  CLI smoke check after changing Electron dependency wiring.
- Run `node --check frontend\electron\main.cjs` after changing Electron main
  process behavior.
- Run `node --check frontend\electron\preload.cjs` after changing Electron
  preload behavior.
- Run `npm.cmd run build` in `frontend` after changing Vite base paths,
  `index.html`, public assets, or `import.meta.env` usage.
- Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
  install-desktop-shortcut.ps1` when validating shortcut creation manually.
- For a manual web smoke test, run `start-web.cmd`, verify the browser opens,
  settings can load, and `Ctrl+C` stops launcher-owned backend/static services.
- For a manual desktop smoke test, run `start-desktop.cmd`, verify the Electron
  window opens, then close it and confirm launcher-owned backend/static services
  stop.

### 7. Wrong vs Correct

#### Wrong

```powershell
Start-Process "http://localhost:5173"
```

This opens a normal browser tab and assumes the developer already started both
frontend and backend services.

#### Correct

```powershell
Start-Process `
    -FilePath $python `
    -ArgumentList @($launcherScript, "--build") `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden
```

This delegates lifecycle management to `tools/desktop_launcher.py`, which owns
build, service startup, Electron launch, logging, and cleanup.

#### Wrong

```typescript
const wsUrl = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/api/v1/ws/translate'
```

This breaks when the launcher avoids an unhealthy occupied backend port and
starts the backend on a different local port.

#### Correct

```typescript
const runtimeUrl = new URLSearchParams(window.location.search).get('wsUrl')
const wsUrl = runtimeUrl || import.meta.env.VITE_WS_URL || defaultWsUrl
```

This lets Electron desktop startup inject the actual backend WebSocket URL at
runtime while preserving browser and Vite-dev fallbacks.
