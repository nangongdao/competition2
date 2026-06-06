# AI Simultaneous Interpretation Assistant Roadmap

## Goal

Identify the next improvement directions for this project so it can satisfy the "AI simultaneous interpretation assistant" requirement: translate a one-way foreign-language audio stream into fluent Chinese in real time, present the result as subtitles or voice, and automatically correct earlier recognition or translation errors.

## What I already know

* The requested product is for users watching English or other foreign-language speeches, technical talks, international conferences, or online courses.
* The core experience must be real-time, smooth, one-way audio interpretation into Chinese.
* Output should support subtitles and/or spoken Chinese.
* The system must have correction capability for earlier ASR or translation mistakes.
* Recent git history includes `feat: implement ai interpreter mvp and roadmap upgrades` and `feat: add subtitle history export`, so the repository likely already contains an MVP and subtitle-related work.
* `README.md` confirms implemented MVP capabilities: live audio capture to WebSocket translation, manual/silence/sentence-count revision, bilingual subtitles, revision counters, durable subtitle history, TXT transcript export, and responsive control panel behavior.
* The current backend is FastAPI + Redis + Faster-Whisper + Claude/OpenAI-compatible LLM translation; the frontend is Vite React + TypeScript.
* The existing code already has an ASR correction path, but it is LLM post-editing gated by low confidence and the last audio chunk, not a true per-segment Whisper re-decode flow.
* `ContextManager` can save/load segment audio in Redis, but `RevisionService.check_asr_correction` does not currently retrieve cached segment audio.
* Voice output, SRT/VTT export, Markdown learning notes, long-session reliability checks, and desktop/system-audio capture remain future work.

## Assumptions (temporary)

* The near-term priority is to improve the existing MVP rather than replace it with a new architecture.
* Subtitle output should be treated as the first-class MVP path, with voice output staged after latency and correction behavior are stable.
* "Real-time" means users can follow a live or playing audio stream with low enough delay for talks/classes, not necessarily broadcast-grade simultaneous interpretation.

## Open Questions

* None for the P0 implementation slice.

## Requirements (evolving)

* Inspect local project documentation and source structure before proposing directions.
* Produce concrete improvement directions mapped to the requested AI interpretation requirements.
* Keep the recommended roadmap compatible with existing project architecture and conventions.
* Prioritize improvements that make the existing MVP more reliable before adding broad new surfaces.
* Treat subtitle output as the primary near-term channel and TTS as a staged follow-up.
* Treat correction quality and latency observability as prerequisites for production confidence.
* Implement P0 first: real and measurable correction.
* Persist enough segment-level audio to support ASR correction for the segment that produced the final ASR text.
* Prefer cached audio re-decode for ASR correction when audio is available; fall back to LLM ASR post-edit only when re-decode is unavailable or does not produce a useful correction.
* Emit correction metadata that allows the frontend and logs to distinguish ASR correction from translation correction and explain what changed.
* Keep the implementation compatible with the current FastAPI + Redis + Faster-Whisper + LLM translation architecture.

## Acceptance Criteria (evolving)

* [x] Local docs and relevant source modules are inspected.
* [x] Current project capabilities are summarized from repository evidence.
* [x] Gaps against the AI simultaneous interpretation requirement are identified.
* [x] Recommended improvement directions are prioritized with trade-offs.
* [x] One key product/technical preference question is asked before implementation scope is locked.
* [x] Segment-level audio is persisted and retrievable for ASR correction.
* [x] ASR correction uses cached segment audio re-decode before LLM post-edit fallback.
* [x] Revision payloads include enough metadata to inspect the correction source and old/new text.
* [x] Backend tests cover ASR re-decode correction, fallback behavior, and no-op cases.

## Definition of Done (team quality bar)

* Tests added/updated if implementation follows.
* Lint / typecheck / CI green if implementation follows.
* Docs/notes updated if behavior changes.
* Rollout/rollback considered if risky.

## Out of Scope (explicit)

* Implementing code changes during this brainstorm step.
* Committing to a paid third-party AI provider before verifying existing project constraints.
* Building bidirectional meeting interpretation unless explicitly added later.
* Prioritizing desktop/Tauri system-audio capture before the browser MVP has stable metrics.
* Adding TTS before subtitle correction and latency behavior are measurable.
* Implementing P1/P2/P3/P4/P5 in this slice.
* Building a new provider abstraction unless needed to make P0 testable.

## Research References

* [`research/local-codebase-findings.md`](research/local-codebase-findings.md) — local documentation and codebase findings, current capabilities, gaps, and recommended roadmap.

## Recommended Improvement Directions

### P0: Make correction real and measurable

Turn correction into the next core product slice:

* Store segment-level audio spans instead of only checking `ASRService.get_last_audio_chunk`.
* Use cached per-segment audio for Whisper re-decode, or clearly separate that path from LLM ASR post-edit fallback.
* Preserve and emit revision metadata: trigger, old/new source, old/new translation, confidence, latency, and reason.
* Expand revision tests for ASR correction, translation correction, cache hits, and no-op behavior.

### P1: Add latency, stability, and cost observability

Make "real-time and smooth" measurable:

* Track capture-to-ASR, ASR-to-first-token, translation-final, and revision-final latencies.
* Track dropped chunks, reconnects, translation cache hit rate, revision counts, and API call/cost counters.
* Add a diagnostic session summary that can be displayed or exported.
* Add long-session test scaffolding for 30-60 minute runs, subtitle ordering, memory growth, and WebSocket recovery.

### P2: Harden session isolation and reconnect behavior

Reduce production correctness risks:

* Avoid shared mutable ASR/NMT/Revision state leaking across sessions.
* Define reconnect semantics for session IDs, missing audio, and in-flight work cancellation.
* Ensure WebSocket disconnects stop or cancel outstanding translation/revision tasks.

### P3: Expand subtitle/export experience

Improve live and post-session usefulness:

* Add SRT/VTT export.
* Add Markdown bilingual learning-note export.
* Improve timestamps so exports use backend segment timing instead of only frontend receipt time.

### P4: Add Chinese TTS playback

Add voice output after subtitle/correction stability:

* Add a TTS provider abstraction.
* Queue finalized translated segments for playback.
* Define correction playback behavior to avoid confusing replays.
* Track TTS lag against subtitle timing.

### P5: Expand input sources and desktop capture

Broaden real-world coverage after the browser MVP is stable:

* Add file-input simulation for repeatable tests.
* Consider microphone mode for demos.
* Explore Tauri/Electron system-audio capture later for Zoom/Teams/local-player scenarios.

## Technical Approach

Chosen implementation slice:

1. Segment-level audio buffer and Redis retrieval contract.
2. Real ASR correction using cached segment audio, with LLM post-edit as fallback.
3. Correction observability events and frontend counters.
4. Focused backend tests for ASR correction and revision-cache behavior.

## Decision (ADR-lite)

**Context**: The project already has a working browser-based subtitle MVP, but the hardest requirement is automatic correction of previous recognition or translation errors.

**Decision**: Prioritize real, measurable correction over TTS, desktop capture, or advanced export formats.

**Consequences**: This delays visible new surfaces like voice playback, but it strengthens the core interpretation loop and creates the metrics needed to make later features reliable.

## P0 Implementation Decision

**Context**: The user approved the recommended P0 direction.

**Decision**: Implement P0 first, scoped to segment-level audio correction and revision metadata.

**Consequences**: The implementation should stay backend-heavy and test-focused. Frontend changes should be limited to preserving/displaying revision metadata already sent over the existing `revision` WebSocket message shape.

## Technical Notes

* Task directory: `.trellis/tasks/06-06-ai-interpreter-roadmap/`
* Trellis workflow: `.trellis/workflow.md`
* Cross-project guide index: `.trellis/spec/guides/index.md`
* README status and next direction: `README.md`
* Roadmap snapshot: `ROADMAP.md`
* Backend pipeline: `backend/core/pipeline.py`
* Revision service: `backend/services/revision_service.py`
* ASR service: `backend/services/asr_service.py`
* Redis context/audio cache: `backend/services/context_manager.py`
* WebSocket session handling: `backend/api/websocket_handler.py`
* Frontend audio capture: `frontend/src/audio/AudioCapture.ts`
* Frontend app state and protocol handling: `frontend/src/store/AppStore.ts`
* Subtitle storage/render/export: `frontend/src/subtitle/SubtitleStore.ts`, `frontend/src/subtitle/SubtitleRenderer.ts`, `frontend/src/ui/SubtitleHistoryPanel.tsx`
