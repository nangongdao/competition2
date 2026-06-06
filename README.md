# competition2

AI real-time interpretation assistant for translating one-way foreign-language audio streams into Chinese with subtitle and correction support.

## Current Status

The current documented baseline is an implemented V2 product slice.

Implemented product capabilities now include:

- Live audio capture to WebSocket translation flow.
- Manual revision triggering from the frontend control panel.
- Silence-based and sentence-count-based backend revision checks.
- Bilingual subtitle entries with source text and translated text.
- Revision counters and visible revision metadata.
- Real ASR correction through cached segment audio and Whisper re-decode, with LLM post-edit fallback.
- Live session diagnostics for latency, dropped chunks, reconnects, revision counters, and API call counters.
- Reconnect-safe frontend session IDs with per-session ASR stream state and revision cache isolation.
- AudioWorklet-first browser audio capture with a ScriptProcessor fallback for unsupported browsers.
- Local WebSocket endurance runner for sending paced PCM audio and collecting diagnostics JSON reports.
- Durable subtitle history separated from the short visible subtitle list.
- Transcript copy and TXT download from the subtitle history panel.
- SRT subtitle export, VTT subtitle export, and Markdown learning-note export from
  subtitle history.
- Diagnostics TXT download from the subtitle history panel.
- Responsive control panel behavior for desktop, mobile, and narrow mobile widths.

Recent validation:

- `npm.cmd run build` in `frontend`.
- `python -m unittest backend.test_endurance_runner`.
- `python -m compileall tools backend/test_endurance_runner.py`.
- `.\\backend\\.venv\\Scripts\\python.exe -m unittest discover backend`.
- `.\\backend\\.venv\\Scripts\\python.exe -m compileall backend\\api backend\\core backend\\models backend\\services backend\\storage`.
- `git diff --check`.
- Playwright desktop, mobile, and narrow viewport checks for panel overflow, prompt overlap, button text overflow, and 44px touch targets.

## Next Direction

Recommended improvement sequence:

1. Establish a real reliability baseline with 30-60 minute live endurance runs using Redis, Whisper, provider API keys, and `tools/endurance_runner.py`. Track queue drops, reconnects, subtitle ordering, memory growth, ASR latency, translation latency, revision latency, and API-call counts.
2. Validate post-session artifacts in real sessions: confirm SRT/VTT timing, revised-segment markers, Markdown note readability, and unchanged TXT/diagnostics behavior.
3. Validate the new AudioWorklet capture path in real sessions and compare chunk stability, dropped chunks, and latency against the ScriptProcessor fallback.
4. Add Chinese TTS playback only after the reliability and export baselines are stable. The TTS slice should include playback queueing, volume control, and a clear strategy for revised subtitles.
5. Defer desktop/system-audio capture until the browser workflow has measurable stability. At that point, evaluate Tauri or Electron against real capture, packaging, and memory requirements.

## Reliability Baseline Tool

Run the backend, then use the local endurance runner to send paced 16 kHz mono
float32 PCM chunks and capture a diagnostics report:

```bash
python tools/endurance_runner.py --duration-seconds 1800 --source silence --output reports/endurance-30m.json --max-dropped-chunks 0
```

For speech-like validation, provide a 16 kHz mono PCM WAV file:

```bash
python tools/endurance_runner.py --duration-seconds 3600 --wav path/to/sample.wav --manual-revision-interval-seconds 300 --output reports/endurance-60m.json
```

## Iteration Workflow

Each completed upgrade or feature must leave a meaningful commit record and be submitted through a Pull Request.

Required workflow:

1. Commit the finished upgrade or feature with a meaningful Conventional Commit message, such as `feat: 完成用户登录模块`, `fix: 修复数据展示错误`, or `docs: 更新项目提交和 PR 流程`.
2. Push the branch to `https://github.com/nangongdao/competition2`.
3. Open a Pull Request according to the activity guidance for the repository.
4. In the PR description, summarize the day's progress, validation commands, and any remaining risks or follow-up work.

Keep each PR focused on one upgrade or feature whenever possible, and avoid including unrelated local changes.
