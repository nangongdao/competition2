# brainstorm: project improvement directions

## Goal

Assess the current project progress from the repository code and documentation, then record practical improvement directions in the local project documents so future iterations have a clear order of work.

## What I already know

* The user asked for improvement directions based on current progress and related documents, and asked that the result be written into project files.
* `README.md` lists an implemented V2 slice including live audio capture, manual and automatic revision triggers, bilingual subtitles, ASR correction, diagnostics, history, TXT export, and responsive control-panel behavior.
* `ROADMAP.md` already contains a broad long-term plan, but its top "Next Development Direction" still treats real `asr_correction` as pending even though the code now implements Whisper re-decode plus LLM post-edit fallback.
* `backend/core/pipeline.py` contains an audio queue, silence-triggered revision, per-session diagnostics, low-confidence ASR correction, cached segment audio, and revision payload emission.
* `backend/services/revision_service.py` implements revision caching, semantic-ambiguity triggers, ASR re-decode, LLM post-edit fallback, and API-call counters.
* `frontend/src/ui/SubtitleHistoryPanel.tsx` supports TXT transcript export and diagnostics TXT export, but SRT/VTT and Markdown learning-note exports are not implemented yet.
* `frontend/src/audio/AudioCapture.ts` still uses `ScriptProcessorNode`; `ROADMAP.md` already records the AudioWorklet migration as technical debt.
* The project has backend unit tests for revision behavior and session diagnostics, but no long-session endurance harness is present in the visible files.

## Assumptions

* This task is a documentation and planning update, not a feature implementation.
* Formal project documentation should remain in English, following `.trellis/spec/shared/index.md`.
* The most useful output is a short prioritized set of near-term improvements, not another broad feature wishlist.

## Requirements

* Update project-level documentation with a current progress-aware improvement plan.
* Prioritize work that reduces product risk before adding distant capabilities.
* Distinguish immediate, next, and deferred directions.
* Include concrete acceptance signals so each future iteration can be verified.
* Preserve the existing delivery workflow requirement for meaningful commits and PRs.

## Acceptance Criteria

* [x] `README.md` contains a current, prioritized improvement plan.
* [x] `ROADMAP.md` contains an updated 2026-06-06 progress snapshot and improvement direction that no longer lists already-implemented ASR correction as pending.
* [x] The documented directions include reliability/endurance validation, richer export formats, AudioWorklet migration, TTS, and desktop/system-audio capture sequencing.
* [x] No unrelated source-code behavior is changed.
* [x] Basic documentation quality checks pass.

## Definition of Done

* Project docs are updated.
* Trellis task PRD records the reasoning.
* `git diff --check` passes.
* No spec update is needed unless the task reveals a new executable convention.
* A meaningful documentation commit is prepared after verification.

## Original Documentation-Slice Out of Scope

* Implementing SRT/VTT, Markdown notes, TTS, AudioWorklet, desktop capture, or endurance-test tooling in this task.
* Pushing to GitHub or opening a PR without explicit user confirmation.
* Refactoring corrupted or stale long-form roadmap content outside the top-level current-plan sections.

## 2026-06-07 Continuation

The user redirected the session from planning-only documentation to continuing
project implementation. The next roadmap priority is reliability-baseline
observability, so this continuation extends the local endurance runner without
changing backend WebSocket payload schemas.

### Additional Requirements

* Summarize API-call counters and revision counters in endurance reports.
* Track final-subtitle ordering anomalies during long WebSocket runs.
* Add a CLI threshold so subtitle-order violations can fail a baseline run.
* Update project documentation and Trellis backend diagnostics specs to match
  the new report behavior.

### Additional Acceptance Criteria

* [x] `tools/endurance_runner.py` reports API/revision counter summaries.
* [x] `tools/endurance_runner.py` reports duplicate final subtitles,
  out-of-order final subtitles, final-sequence gaps, and revisions targeting
  unknown final segments.
* [x] `tools/endurance_runner.py --help` documents
  `--max-subtitle-order-violations`.
* [x] `backend/test_endurance_runner.py` covers the new report summaries and
  threshold failure.
* [x] `README.md`, `ROADMAP.md`, and
  `.trellis/spec/backend/ai-interpreter-session-diagnostics.md` are updated.

## Technical Notes

* Files inspected: `README.md`, `ROADMAP.md`, `task.md`, `AGENTS.md`, `backend/core/pipeline.py`, `backend/services/revision_service.py`, `backend/services/asr_service.py`, `backend/core/config.py`, `frontend/src/App.tsx`, `frontend/src/store/AppStore.ts`, `frontend/src/network/WsClient.ts`, `frontend/src/audio/AudioCapture.ts`, `frontend/src/subtitle/SubtitleStore.ts`, `frontend/src/ui/ControlPanel.tsx`, `frontend/src/ui/SubtitleHistoryPanel.tsx`.
* Relevant specs inspected: `.trellis/spec/shared/index.md`, `.trellis/spec/backend/index.md`, `.trellis/spec/frontend/index.md`, `.trellis/spec/big-question/index.md`, `.trellis/spec/guides/index.md`.
* Complexity classification: simple-to-moderate documentation update. The user requested implementation directly and the necessary context is derivable from local files, so no blocking question is needed.
* Verification: `git diff --check`; `rg -n "[ \t]+$" README.md ROADMAP.md .trellis/tasks/06-06-project-improvement-directions/prd.md`; `python -m unittest backend.test_endurance_runner`; `python -m compileall tools backend/test_endurance_runner.py`; `.\\backend\\.venv\\Scripts\\python.exe -m unittest discover backend`; `.\\backend\\.venv\\Scripts\\python.exe -m compileall backend\\api backend\\core backend\\models backend\\services backend\\storage tools`; `python tools\\endurance_runner.py --help`.
* Spec update judgment: `.trellis/spec/backend/ai-interpreter-session-diagnostics.md` was updated because the endurance runner report contract and threshold behavior changed.
