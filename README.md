# competition2

AI real-time interpretation assistant for translating one-way foreign-language audio streams into Chinese with subtitle and correction support.

## Current Status

The current documented baseline is an implemented V2 product slice.

Implemented product capabilities now include:

- Live audio capture to WebSocket translation flow.
- Session-level source-language selection for English, automatic detection, and
  common foreign-language inputs, with Chinese kept as the target language.
- Manual revision triggering from the frontend control panel.
- Silence-based and sentence-count-based backend revision checks.
- Bilingual subtitle entries with source text and translated text.
- Revision counters and visible revision metadata.
- Real ASR correction through cached segment audio and Whisper re-decode, with LLM post-edit fallback.
- Live session diagnostics for latency, dropped chunks, reconnects, revision counters, and API call counters.
- Backend audio-queue diagnostics for current depth, peak depth, capacity, and queue wait latency.
- Periodic backend diagnostics and explicit diagnostics requests for endurance
  runs where silence or delayed ASR finals would otherwise hide received audio
  counts.
- Reconnect-safe frontend session IDs with per-session ASR stream state and revision cache isolation.
- AudioWorklet-first browser audio capture with a ScriptProcessor fallback for unsupported browsers.
- Client diagnostics show which capture backend is active so AudioWorklet and fallback sessions can be compared.
- Local WebSocket endurance runner for sending paced PCM audio and collecting diagnostics JSON reports.
- Endurance reports now summarize API/revision counters and final-subtitle ordering anomalies.
- Endurance reports can optionally sample runner/backend process RSS memory and
  fail on configured memory-growth thresholds.
- Subtitle artifact validator for checking exported TXT/SRT/VTT/Markdown files
  from real sessions.
- Unified interpreter validation suite that coordinates preflight, optional
  endurance runs, and optional subtitle artifact checks into one audit report.
- Secret-safe endurance preflight for checking Redis, Whisper, CUDA, and provider key readiness before long runs.
- Electron desktop launcher that starts the built frontend, FastAPI backend, and a native desktop window from a double-click entry.
- Electron single-instance, tray restore, minimize-to-tray, and startup-log menu behavior for a more software-like local desktop experience.
- Electron floating subtitle overlay that opens a transparent always-on-top
  subtitle window above other desktop apps while the main window remains the
  control panel.
- Windows desktop shortcut installer scripts for launching the app from the desktop.
- Durable subtitle history separated from the short visible subtitle list.
- Transcript copy and TXT download from the subtitle history panel.
- SRT subtitle export, VTT subtitle export, and Markdown learning-note export from
  subtitle history.
- Diagnostics TXT download from the subtitle history panel.
- Optional local Chinese voice playback through the browser/Electron Web Speech
  API, with queueing, volume control, rate control, and diagnostics.
- Frontend unit tests for AudioWorklet capture startup, ScriptProcessor fallback,
  failed-capture cleanup, local TTS queue behavior, and subtitle export formats.
- Backend unit tests for pipeline queue overflow diagnostics, final ASR-to-translation
  flow, and closed-session audio rejection.
- Responsive control panel behavior for desktop, mobile, and narrow mobile widths.

Recent validation:

- `npm.cmd run test` in `frontend`.
- `npm.cmd run build` in `frontend`.
- `npm.cmd audit` in `frontend`.
- `.\\backend\\.venv\\Scripts\\python.exe -m unittest backend.test_pipeline`.
- `python -m unittest backend.test_endurance_runner`.
- `python -m compileall tools backend/test_endurance_runner.py`.
- `.\\backend\\.venv\\Scripts\\python.exe -m unittest discover backend`.
- `.\\backend\\.venv\\Scripts\\python.exe -m compileall backend\\api backend\\core backend\\models backend\\services backend\\storage`.
- `.\\backend\\.venv\\Scripts\\python.exe tools\\endurance_preflight.py --output reports\\endurance-preflight-latest.json`.
- `.\\backend\\.venv\\Scripts\\python.exe tools\\interpreter_validation_suite.py --output reports\\interpreter-validation-latest.json`.
- `.\\backend\\.venv\\Scripts\\python.exe tools\\endurance_runner.py --duration-seconds 60 --source silence --output reports\\endurance-60s-language-config.json --max-dropped-chunks 0 --max-queue-depth 8 --min-received-ratio 0.99 --max-subtitle-order-violations 0`.
- `.\\backend\\.venv\\Scripts\\python.exe tools\\endurance_runner.py --help`.
- `git diff --check`.
- Playwright desktop, mobile, and narrow viewport checks for panel overflow, prompt overlap, button text overflow, and 44px touch targets.

## Next Direction

Recommended improvement sequence:

1. Establish a real reliability baseline with 30-60 minute live endurance runs using Redis, Whisper, provider API keys, and `tools/endurance_runner.py`. Track queue depth, queue wait latency, queue drops, reconnects, subtitle ordering, memory growth, ASR latency, translation latency, revision latency, and API-call counts.
2. Validate post-session artifacts in real sessions with `tools/subtitle_artifact_validator.py`: confirm SRT/VTT timing, revised-segment markers, Markdown note readability, and unchanged TXT/diagnostics behavior while keeping the frontend export unit tests green.
3. Validate the new AudioWorklet capture path in real sessions and compare chunk stability, dropped chunks, and latency against the ScriptProcessor fallback.
4. Validate the local Web Speech voice playback in real browser/Electron sessions, then decide whether the next TTS slice needs provider-backed synthesis, audio artifact caching, or backend delivery.
5. Keep the Electron desktop launcher for local demos, but defer full packaged desktop/system-audio capture until the browser workflow has measurable stability. At that point, evaluate Electron/Tauri capture, packaging, and memory requirements against real sessions.

## Desktop-Style Startup

On Windows, double-click `start-desktop.cmd` from the project root. The launcher:

1. Builds the Vite frontend when needed.
2. Serves the built frontend from a local static server.
3. Starts the FastAPI backend from `backend/.venv` when the requested backend
   port is not already healthy.
4. Opens the UI in an Electron `BrowserWindow`, not in a browser app-mode tab.
5. Opens a transparent always-on-top subtitle overlay window for desktop-style
   viewing over other apps and browser tabs.
6. Keeps a single app instance, supports tray restore, minimize-to-tray,
   floating-subtitle show/hide, and startup-log menu behavior.
7. Stops the services it started when the app window exits.

In desktop mode, use the main window as the control panel. Live subtitles appear
in the floating overlay near the bottom of the screen, not only inside the main
window. The control panel button `Floating subtitles on/off` and the tray menu
can hide or restore the overlay without stopping the translation session.

Startup logs are written to `logs/desktop-launcher.log`. If port `8000` is
occupied by an unhealthy or stale process, the launcher chooses another local
backend port and injects the matching WebSocket URL into the Electron window.
Override paths, ports, or ASR profile with `AI_INTERPRETER_PYTHON`,
`AI_INTERPRETER_BACKEND_PORT`, `AI_INTERPRETER_FRONTEND_PORT`, or
`AI_INTERPRETER_DESKTOP_ASR_PROFILE` when needed.

Desktop startup defaults to a low-resource ASR profile:

```text
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

Set `AI_INTERPRETER_DESKTOP_ASR_PROFILE=env` to use the ASR values from
`backend/.env.local` exactly, or `AI_INTERPRETER_DESKTOP_ASR_PROFILE=gpu` to
prefer `large-v3` on CUDA when your machine has enough VRAM.

To create a Windows desktop shortcut, run:

```powershell
.\install-desktop-shortcut.cmd
```

The shortcut starts `start-desktop.ps1` through a hidden PowerShell process and opens the Electron desktop window.

## Reliability Baseline Tool

Before running a 30-60 minute baseline, keep secrets in the local-only
`backend/.env.local` file. The tracked `backend/.env.example` file is the GitHub
template; do not put real keys there.

```powershell
if (!(Test-Path backend/.env.local)) { Copy-Item backend/.env.example backend/.env.local }
```

Then edit `backend/.env.local` and configure Redis, Whisper, and one provider
key:

- `REDIS_URL` and `REDIS_PROTOCOL`.
- `ASR_ENGINE=whisper`, `WHISPER_MODEL`, `WHISPER_DEVICE`, and
  `WHISPER_COMPUTE_TYPE`.
- `ANTHROPIC_API_KEY` for `NMT_ENGINE=claude`, or `OPENAI_API_KEY` for
  `NMT_ENGINE=openai`.

The backend and endurance preflight load `backend/.env.local` automatically
from explicit project paths, so the same file works when commands are run from
the repository root or from the `backend` directory. Real environment variables
still override file values when both are set.

For repeatable project-level validation, run the interpreter validation suite.
By default it runs the secret-safe preflight and writes a combined report:

```bash
python tools/interpreter_validation_suite.py --output reports/interpreter-validation-latest.json
```

When the backend is running and preflight is ready, include the endurance run
and thresholds in the same report:

```bash
python tools/interpreter_validation_suite.py --run-endurance --duration-seconds 1800 --monitor-self --monitor-pid backend=<uvicorn_pid> --max-memory-growth-mb 150 --max-dropped-chunks 0 --max-queue-depth 8 --min-received-ratio 0.99 --max-subtitle-order-violations 0 --output reports/interpreter-validation-30m.json
```

After exporting session artifacts, pass them to the same suite so the final
report includes subtitle usability evidence:

```bash
python tools/interpreter_validation_suite.py --artifact exports/session.txt --artifact exports/session.srt --artifact exports/session.vtt --artifact exports/session.md --output reports/interpreter-validation-artifacts.json
```

The suite writes child reports for preflight, endurance, and artifact validation
under `reports/` and exits non-zero when an executed step is blocked or failed.

Run the secret-safe preflight first:

```bash
python tools/endurance_preflight.py --output reports/endurance-preflight-latest.json
```

The tracked template and built-in defaults use `WHISPER_MODEL=small`,
`WHISPER_DEVICE=cpu`, and `WHISPER_COMPUTE_TYPE=int8` for first-run reliability.
For higher accuracy on a GPU machine, set `WHISPER_MODEL=large-v3`,
`WHISPER_DEVICE=cuda`, and `WHISPER_COMPUTE_TYPE=float16`. To verify the actual
Whisper model load during preflight, add `--load-whisper-model`; this may
download model files.

Run the backend, then use the local endurance runner to send paced 16 kHz mono
float32 PCM chunks and capture a diagnostics report:

```bash
python tools/endurance_runner.py --duration-seconds 1800 --source silence --output reports/endurance-30m.json --max-dropped-chunks 0 --max-queue-depth 8 --min-received-ratio 0.99 --max-subtitle-order-violations 0
```

To include memory-growth evidence, pass the runner process and any backend
process PIDs you want to watch:

```bash
python tools/endurance_runner.py --duration-seconds 1800 --source silence --output reports/endurance-30m.json --monitor-self --monitor-pid backend=<uvicorn_pid> --memory-sample-interval-seconds 5 --max-memory-growth-mb 150 --max-dropped-chunks 0 --max-queue-depth 8 --min-received-ratio 0.99 --max-subtitle-order-violations 0
```

For speech-like validation, provide a 16 kHz mono PCM WAV file:

```bash
python tools/endurance_runner.py --duration-seconds 3600 --wav path/to/sample.wav --manual-revision-interval-seconds 300 --output reports/endurance-60m.json
```

After a real session, validate exported subtitle artifacts:

```bash
python tools/subtitle_artifact_validator.py exports/session.txt exports/session.srt exports/session.vtt exports/session.md --output reports/subtitle-artifacts-latest.json
```

The artifact validator reports cue counts, timestamp overlaps, long gaps,
revision markers, empty artifacts, transcript line counts, and Markdown timeline
readability.

## Iteration Workflow

Each completed upgrade or feature must leave a meaningful commit record and be submitted through a Pull Request.

Required workflow:

1. Commit the finished upgrade or feature with a meaningful Conventional Commit message, such as `feat: 完成用户登录模块`, `fix: 修复数据展示错误`, or `docs: 更新项目提交和 PR 流程`.
2. Push the branch to `https://github.com/nangongdao/competition2`.
3. Open a Pull Request according to the activity guidance for the repository.
4. In the PR description, summarize the day's progress, validation commands, and any remaining risks or follow-up work.

Keep each PR focused on one upgrade or feature whenever possible, and avoid including unrelated local changes.
