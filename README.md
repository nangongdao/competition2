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
- Durable subtitle history separated from the short visible subtitle list.
- Transcript copy and TXT download from the subtitle history panel.
- Responsive control panel behavior for desktop, mobile, and narrow mobile widths.

Recent validation:

- `npm.cmd run build` in `frontend`.
- `.\\backend\\.venv\\Scripts\\python.exe -m unittest backend.test_revision_service`.
- `git diff --check`.
- Playwright desktop, mobile, and narrow viewport checks for panel overflow, prompt overlap, button text overflow, and 44px touch targets.

## Next Direction

Recommended follow-up iterations:

1. Implement real ASR correction through cached audio and Whisper re-decode, instead of only translation-window revision.
2. Add long-session stability checks, latency metrics, and revision cost observability.
3. Expand transcript export to SRT/VTT and Markdown learning notes.
4. Add Chinese TTS playback for translated output.
5. Explore desktop/system-audio capture after browser flow is stable.

## Iteration Workflow

Use meaningful Conventional Commit messages, for example `feat: add subtitle history export` or `fix: prevent mobile control panel overflow`.

Feature work should be pushed to a feature branch and merged through a Pull Request. The PR description should summarize the day's progress, validation commands, and remaining risks or follow-up work.
