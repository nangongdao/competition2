# Desktop Launcher Contract

This project uses an Electron desktop launcher for the current local demo
workflow. The launcher is a real desktop window, not a browser app-mode tab.

## Scenario: Desktop-Style Local Startup

### 1. Scope / Trigger

- Trigger: changes to `tools/desktop_launcher.py`, `frontend/electron/main.cjs`,
  `start-desktop.cmd`, `start-desktop.ps1`, frontend build paths, backend
  startup ports, Electron window behavior, or desktop shortcut install scripts.
- Scope: local Windows-first startup experience. This is not yet a packaged
  installer and does not replace the later system-audio capture evaluation.

### 2. Signatures

```bash
start-desktop.cmd
powershell.exe -File start-desktop.ps1
install-desktop-shortcut.cmd
powershell.exe -File install-desktop-shortcut.ps1
python tools/desktop_launcher.py [--build] [--backend-port PORT] [--frontend-port PORT] [--no-splash]
npm run desktop:window --prefix frontend
```

```python
def ensure_frontend_build(force_build: bool) -> None: ...
def start_backend(port: int) -> subprocess.Popen[str] | None: ...
def start_frontend_server(port: int) -> tuple[http.server.ThreadingHTTPServer, str]: ...
def ensure_desktop_runtime() -> Path: ...
def launch_desktop_window(url: str) -> subprocess.Popen[str]: ...
```

### 3. Contracts

- `start-desktop.cmd` must be safe to double-click from Windows Explorer and
  should not leave a visible terminal window open.
- `start-desktop.ps1` should prefer `backend/.venv/Scripts/pythonw.exe`, then
  `backend/.venv/Scripts/python.exe`, then `python`.
- `tools/desktop_launcher.py --build` must run the frontend production build
  before serving `frontend/dist`.
- The launcher serves `frontend/dist` from `127.0.0.1` on an available port by
  default.
- The launcher starts the FastAPI backend on `127.0.0.1:8000` only when
  `/api/v1/health` is not already returning HTTP 200.
- The launcher opens Electron with `AI_INTERPRETER_DESKTOP_URL=<frontend-url>`.
- The launcher opens Electron with `AI_INTERPRETER_LOG_FILE=<log-path>` so the
  tray menu can open startup diagnostics.
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
| `AI_INTERPRETER_DESKTOP_URL` | Internal Electron URL injected by the Python launcher |
| `AI_INTERPRETER_LOG_FILE` | Internal Electron path for opening launcher logs from the tray |
| `VITE_WS_URL` | Override frontend WebSocket base URL at build time |

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| `frontend/dist/index.html` is missing | Build frontend when `--build` is set; otherwise fail with a logged error |
| `node_modules` is missing | Run `npm install` before `npm run build` |
| Backend health endpoint is already HTTP 200 | Reuse existing backend and do not terminate it on launcher exit |
| Backend process exits before health check | Show startup error and write details to launcher log |
| Backend health timeout expires | Terminate the backend process started by the launcher |
| Electron runtime is missing | Run `npm install` in `frontend`; fail with a logged error if Electron is still unavailable |
| Electron main file is missing | Fail with a logged startup error |
| Startup fails while splash is visible | Close splash and show an error dialog when Tk is available |
| A second Electron instance is launched | Focus/show the existing window instead of creating duplicate app state |
| The window is minimized while tray is available | Hide to tray and allow restore from tray click or menu |
| Desktop shortcut install script is run | Create or update `AI Interpreter.lnk` on the Windows desktop |

### 5. Good/Base/Bad Cases

- Good: double-click `start-desktop.cmd`, a splash appears, local services start,
  and an Electron desktop window opens without a terminal window.
- Base: backend is already running on `127.0.0.1:8000`; launcher serves frontend
  and opens the app window without owning the backend process.
- Good: run `install-desktop-shortcut.cmd`, then use the desktop shortcut to
  start the same hidden launcher flow.
- Good: minimize the Electron window, restore it from the tray, and quit from
  the tray when done.
- Bad: launcher always kills port `8000` on exit, assumes a hard-coded browser
  path, or opens a normal browser tab/app-mode window as the primary path.

### 6. Tests Required

- Run `python tools/desktop_launcher.py --help` after changing CLI arguments.
- Run `python -m compileall tools/desktop_launcher.py` after changing launcher
  code.
- Run `.\frontend\node_modules\.bin\electron.cmd --version` or another Electron
  CLI smoke check after changing Electron dependency wiring.
- Run `node --check frontend\electron\main.cjs` after changing Electron main
  process behavior.
- Run `npm.cmd run build` in `frontend` after changing Vite base paths,
  `index.html`, public assets, or `import.meta.env` usage.
- Run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File
  install-desktop-shortcut.ps1` when validating shortcut creation manually.
- For a manual smoke test, run `start-desktop.cmd`, verify the Electron window
  opens, then close it and confirm launcher-owned backend/static services stop.

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
