# Desktop Launcher Contract

This project uses a lightweight desktop-style launcher instead of a packaged
desktop runtime for the current local demo workflow.

## Scenario: Desktop-Style Local Startup

### 1. Scope / Trigger

- Trigger: changes to `tools/desktop_launcher.py`, `start-desktop.cmd`,
  `start-desktop.ps1`, frontend build paths, backend startup ports, or local
  browser app-mode behavior.
- Scope: local Windows-first startup experience. This is not a packaged desktop
  client and does not replace the later Tauri/Electron system-audio capture
  evaluation.

### 2. Signatures

```bash
start-desktop.cmd
powershell.exe -File start-desktop.ps1
python tools/desktop_launcher.py [--build] [--backend-port PORT] [--frontend-port PORT] [--no-splash]
```

```python
def ensure_frontend_build(force_build: bool) -> None: ...
def start_backend(port: int) -> subprocess.Popen[str] | None: ...
def start_frontend_server(port: int) -> tuple[http.server.ThreadingHTTPServer, str]: ...
def launch_browser_app(url: str, profile_dir: Path) -> subprocess.Popen[str] | None: ...
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
- The launcher opens Edge or Chrome with `--app=<frontend-url>` and an isolated
  temporary browser profile.
- The launcher must stop only processes it started. If the backend was already
  healthy before launch, leave that external backend running.
- Startup logs go to `logs/desktop-launcher.log`, and `logs/` must stay ignored
  by Git.

Environment keys:

| Key | Purpose |
| --- | --- |
| `AI_INTERPRETER_PYTHON` | Override Python executable for backend startup |
| `AI_INTERPRETER_BROWSER` | Override app-mode browser executable |
| `AI_INTERPRETER_BACKEND_PORT` | Override backend port |
| `AI_INTERPRETER_FRONTEND_PORT` | Override static frontend port, or `0` for any available port |
| `VITE_WS_URL` | Override frontend WebSocket base URL at build time |

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| `frontend/dist/index.html` is missing | Build frontend when `--build` is set; otherwise fail with a logged error |
| `node_modules` is missing | Run `npm install` before `npm run build` |
| Backend health endpoint is already HTTP 200 | Reuse existing backend and do not terminate it on launcher exit |
| Backend process exits before health check | Show startup error and write details to launcher log |
| Backend health timeout expires | Terminate the backend process started by the launcher |
| Edge/Chrome is unavailable | Fall back to the default browser and keep services alive until interruption |
| Startup fails while splash is visible | Close splash and show an error dialog when Tk is available |

### 5. Good/Base/Bad Cases

- Good: double-click `start-desktop.cmd`, a splash appears, local services start,
  and an app-mode Edge/Chrome window opens without a terminal window.
- Base: backend is already running on `127.0.0.1:8000`; launcher serves frontend
  and opens the app window without owning the backend process.
- Bad: launcher always kills port `8000` on exit, assumes a hard-coded browser
  path, or opens a normal browser tab with address bar as the primary path.

### 6. Tests Required

- Run `python tools/desktop_launcher.py --help` after changing CLI arguments.
- Run `python -m compileall tools/desktop_launcher.py` after changing launcher
  code.
- Run `npm.cmd run build` in `frontend` after changing Vite base paths,
  `index.html`, public assets, or `import.meta.env` usage.
- For a manual smoke test, run `start-desktop.cmd`, verify the app-mode window
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
build, service startup, app-mode launch, logging, and cleanup.
