# competition2

AI real-time interpretation assistant for translating one-way foreign-language audio streams into Chinese with subtitle and correction support.

## Current Status

The project is on branch `feat/roadmap-big-question-upgrades`.

Implemented product capabilities now include:

- Live audio capture to WebSocket translation flow.
- Manual revision triggering from the frontend control panel.
- Silence-based and sentence-count-based backend revision checks.
- Bilingual subtitle entries with source text and translated text.
- Revision counters and visible revision metadata.
- Real ASR correction through cached segment audio and Whisper re-decode, with LLM post-edit fallback.
- Live session diagnostics for latency, dropped chunks, reconnects, revision counters, and API call counters.
- Reconnect-safe frontend session IDs with per-session ASR stream state and revision cache isolation.
- Durable subtitle history separated from the short visible subtitle list.
- Transcript copy and TXT download from the subtitle history panel.
- Diagnostics TXT download from the subtitle history panel.
- Responsive control panel behavior for desktop, mobile, and narrow mobile widths.

Recent validation:

- `npm.cmd run build` in `frontend`.
- `.\\backend\\.venv\\Scripts\\python.exe -m unittest discover backend`.
- `.\\backend\\.venv\\Scripts\\python.exe -m compileall backend\\api backend\\core backend\\models backend\\services backend\\storage`.
- `git diff --check`.
- Playwright desktop, mobile, and narrow viewport checks for panel overflow, prompt overlap, button text overflow, and 44px touch targets.

## Next Direction

Recommended follow-up iterations:

1. Run true 30-60 minute live endurance tests with Redis, Whisper, and provider API keys.
2. Expand transcript export to SRT/VTT and Markdown learning notes.
3. Add Chinese TTS playback for translated output.
4. Explore desktop/system-audio capture after browser flow is stable.

## Iteration Workflow

Each completed upgrade or feature must leave a meaningful commit record and be submitted through a Pull Request.

Required workflow:

1. Commit the finished upgrade or feature with a meaningful Conventional Commit message, such as `feat: 完成用户登录模块`, `fix: 修复数据展示错误`, or `docs: 更新项目提交和 PR 流程`.
2. Push the branch to `https://github.com/nangongdao/competition2`.
3. Open a Pull Request according to the activity guidance for the repository.
4. In the PR description, summarize the day's progress, validation commands, and any remaining risks or follow-up work.

Keep each PR focused on one upgrade or feature whenever possible, and avoid including unrelated local changes.
