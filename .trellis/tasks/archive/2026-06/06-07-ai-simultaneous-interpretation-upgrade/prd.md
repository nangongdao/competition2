# AI Simultaneous Interpretation Assistant Upgrade

## Goal

Improve the implemented live interpretation assistant so it more directly satisfies the competition requirement: one-way foreign-language audio streams should be translated into Chinese in real time, shown as subtitles or local voice playback, and corrected when earlier recognition or translation output is wrong.

## What I Already Know

* The project already has a V2 live interpretation slice with browser audio capture, WebSocket streaming, Whisper ASR, OpenAI-compatible/Claude NMT, subtitle history, manual and automatic revision, diagnostics, export formats, local browser/Electron TTS playback, and endurance tooling.
* The current backend ASR path always transcribes with `language="en"`.
* The current NMT prompts are fixed to English-to-Chinese even though the user requirement includes English or other foreign languages.
* The frontend currently has subtitle mode, revision, history/export, diagnostics, and TTS controls, but no language source selector.
* `config` WebSocket messages are accepted by the backend but only logged; they do not affect the running pipeline.
* The current local model configuration uses an OpenAI-compatible provider with `tencent/Hunyuan-MT-7B`, which previously passed short real-time translation latency checks.

## Requirements

* Add a real language-pair configuration path for a running live interpretation session.
* Let the frontend choose a source language from a small practical set, including automatic detection and common foreign-language inputs.
* Keep the target language Chinese for this task, matching the product requirement.
* Apply the selected source language to Whisper ASR, using automatic detection when selected.
* Apply the selected source and target languages to NMT prompts so OpenAI-compatible and Claude engines are not hard-coded to English-to-Chinese.
* Preserve the existing correction behavior for ASR correction, translation revision, revision metadata, subtitle history, and local TTS playback.
* Add focused tests around language configuration, prompt construction, and WebSocket/config behavior.
* Emit periodic backend diagnostics during active audio ingestion, even when no ASR final segment is produced yet.
* Let local endurance tooling request a final diagnostics snapshot before closing the WebSocket.
* Run the existing backend and frontend validation suites, plus a current-model smoke test where local provider credentials are available.

## Acceptance Criteria

* [ ] Changing the frontend source-language selector sends a WebSocket `config` message during an active session.
* [ ] Starting a session sends the current language config once the WebSocket connects.
* [ ] Backend `config` messages update the active pipeline instead of being only logged.
* [ ] Whisper receives `None` for automatic language detection and receives the configured language code for explicit source languages.
* [ ] NMT prompts include the configured source and Chinese target language labels.
* [ ] ASR correction post-edit prompts are no longer hard-coded only to English.
* [ ] Endurance runs with silence or delayed ASR finals can still observe backend received audio counts through `session_diagnostics`.
* [ ] The endurance runner requests final diagnostics after sending stops so strict received-ratio checks do not depend on timing luck.
* [ ] Existing revision payload fields and diagnostics payload fields stay compatible.
* [ ] Backend unit tests pass.
* [ ] Frontend unit tests and production build pass.
* [ ] A short current-model NMT smoke test succeeds or reports a concrete external blocker without exposing secrets.

## Definition of Done

* Tests added or updated for the changed backend/frontend behavior.
* Backend unit tests pass with the repository virtual environment.
* Frontend test and build commands pass.
* Specs or docs updated if a new cross-layer language config contract is introduced.
* No real API keys or local-only secret files are committed.
* Commit plan separates this task's changes from unrelated pre-existing dirty files.

## Technical Approach

Use the existing WebSocket control channel instead of adding a new API. Add a small shared backend language-config helper for normalizing safe language codes and rendering human-readable prompt labels. Store per-segment source/target languages so revision translation can reuse the language pair without mutable shared NMT state. Add frontend language state and controls that send the config on connection and on changes while connected.

## Decision (ADR-lite)

**Context**: The project already exposes a `config` control message and has per-session pipeline instances. The NMT service itself is shared and should not receive mutable per-session language state.

**Decision**: Keep language configuration as pipeline-local state, write the selected language pair onto each `Segment`, and have NMT derive prompts from the current segment.

**Consequences**: This keeps shared model/client objects stateless across sessions, lets revision reuse the segment language pair, and avoids a larger protocol change. The frontend language list stays intentionally small in this task; broader language/glossary support can be added later.

## Out of Scope

* Full system-audio capture beyond the current browser/Electron launcher.
* Provider-backed TTS audio streaming.
* Glossary or custom terminology management.
* Full multilingual quality benchmarking across every listed source language.
* Packaging a production desktop installer.

## Technical Notes

* Relevant backend files: `backend/core/pipeline.py`, `backend/api/websocket_handler.py`, `backend/services/asr_service.py`, `backend/services/nmt_service.py`, `backend/services/revision_service.py`, `backend/models/segment.py`, `backend/models/messages.py`.
* Relevant frontend files: `frontend/src/store/AppStore.ts`, `frontend/src/ui/ControlPanel.tsx`, `frontend/src/network/WsClient.ts`, `frontend/src/types.ts`.
* Relevant specs: `.trellis/spec/backend/ai-interpreter-revision-contract.md`, `.trellis/spec/backend/ai-interpreter-session-diagnostics.md`, `.trellis/spec/frontend/api-integration.md`, `.trellis/spec/frontend/tts-playback.md`, `.trellis/spec/shared/code-quality.md`.
