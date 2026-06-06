# Local Codebase Findings

## Scope

Inspected local documentation, Trellis spec indexes, and the current backend/frontend implementation to identify the next improvement directions for the AI simultaneous interpretation assistant.

## Documentation Evidence

* `README.md` states the project is an AI real-time interpretation assistant for one-way foreign-language audio streams into Chinese with subtitles and correction support.
* `README.md` lists implemented capabilities: live audio capture to WebSocket translation flow, manual revision, silence-based and sentence-count-based revision, bilingual subtitles, revision counters, durable subtitle history, TXT transcript copy/download, and responsive control panel behavior.
* `README.md` recommends the next iterations: real ASR correction through cached audio and Whisper re-decode, long-session stability/latency/revision-cost observability, SRT/VTT and Markdown learning-note export, Chinese TTS playback, and desktop/system-audio capture after browser stability.
* `ROADMAP.md` has a current progress snapshot that matches the README and frames the next slice as turning correction from a translation-only demo into a more reliable production feature.
* The Trellis spec indexes are partially template-oriented for a Next.js/oRPC architecture, while the actual codebase is Vite React + FastAPI + Redis + Whisper/LLM. Apply the shared principles, but follow the real project structure.

## Current Implementation Evidence

### Backend

* `backend/core/pipeline.py` coordinates ASR, NMT, Redis context, and revision for a session.
* `Pipeline` stores a raw audio chunk after an ASR final segment via `ContextManager.save_audio_chunk`.
* Revision triggers are already present:
  * manual trigger via `trigger_manual_revision`
  * silence trigger via `revision_silence_seconds`
  * sentence-count trigger via `revision_trigger_sentences`
  * semantic ambiguity trigger via `RevisionService.has_semantic_ambiguity`
* `backend/services/revision_service.py` implements:
  * translation-window revision
  * translation request caching
  * edit-distance-style change detection via `SequenceMatcher`
  * low-confidence ASR correction using an LLM post-edit prompt
* `backend/services/context_manager.py` can save and load audio bytes per segment in Redis with TTL.
* `backend/services/asr_service.py` uses Faster-Whisper and decodes buffered audio in 2-second chunks.
* `backend/api/websocket_handler.py` shares one `ASRService`, `NMTService`, `ContextManager`, and `RevisionService` instance across active pipelines.

### Frontend

* `frontend/src/audio/AudioCapture.ts` captures browser/tab/system audio through `navigator.mediaDevices.getDisplayMedia`, converts to 16 kHz mono float32 PCM, and sends chunks every 100 ms.
* `frontend/src/store/AppStore.ts` tracks subtitle mode, ASR/translation revision counts, last revision reason, subtitle history, and transcript text.
* `frontend/src/subtitle/SubtitleStore.ts` stores a short visible subtitle list plus durable history and exports a TXT transcript.
* `frontend/src/subtitle/SubtitleRenderer.ts` renders bilingual/source/translation subtitle modes and visually marks revisions.
* `frontend/src/ui/SubtitleHistoryPanel.tsx` supports copy/download as TXT only.
* `frontend/src/network/WsClient.ts` has reconnect support, but audio chunks are dropped while disconnected and session continuity is not fully restored.

## Gaps Against The User Requirement

1. Real ASR correction is not yet production-grade.
   * The code gates ASR correction on low confidence and `get_last_audio_chunk`, but the correction itself is LLM post-editing, not Whisper re-decode against the cached segment audio.
   * `ContextManager.get_audio_chunk` exists, but `RevisionService.check_asr_correction` does not retrieve per-segment cached audio.
   * `ASRService.get_last_audio_chunk` only returns the last 100 ms-ish frontend chunk, while ASR final segments are decoded from a larger 2-second buffer.

2. Real-time quality lacks observability.
   * There are no first-class metrics for capture-to-ASR latency, ASR-to-first-token latency, final-translation latency, revision latency, dropped chunks, reconnect count, or revision cost.
   * Without these metrics, it is hard to judge whether subtitle rhythm is actually good enough for live talks/classes.

3. Long-session reliability is not proven.
   * README says recent validation includes frontend build and revision tests, but no 30-60 minute endurance test.
   * Shared singleton ASR/NMT/Revision instances across sessions are a risk for multi-session correctness and state isolation.

4. Subtitle output is usable but not yet learning-product grade.
   * TXT export exists; SRT/VTT and Markdown learning-note export do not.
   * Segment timestamps are frontend-side receipt times, not backend ASR timing, so subtitle export will need timing improvements.

5. Voice output is missing.
   * The requirement allows subtitles or voice, but README/ROADMAP already recommend TTS after subtitle and correction stability.

6. Input source coverage is browser-limited.
   * Current capture is browser `getDisplayMedia`; broader desktop/system-audio capture is planned but should wait until the browser MVP is measurable and stable.

## Recommended Roadmap

### P0: Make correction real and measurable

Goal: turn "correction exists" into a trustworthy product differentiator.

Work:
* Store segment-level audio spans, not just the last chunk.
* Use cached segment audio for Whisper re-decode or a clearly named ASR post-edit fallback.
* Emit structured revision metadata: reason, old source, new source, old translation, new translation, confidence, trigger, latency.
* Add unit tests around ASR correction, translation correction, cache hits, and no-op behavior.

Why first:
* This directly satisfies the "automatically correct previous recognition or translation errors" requirement.
* It reduces the risk of adding TTS or exports on top of unstable text.

### P1: Add latency, stability, and cost observability

Goal: know whether users can actually follow a live talk.

Work:
* Add per-segment timestamps from audio receive -> ASR final -> first translation token -> translation final -> revision final.
* Track reconnects, dropped chunks, revision trigger counts, translation cache hit rate, and API call counts.
* Add a small frontend diagnostics panel or exportable session diagnostics.
* Add long-session test scaffolding for ordering, memory growth, reconnect, and repeated revision.

Why second:
* "Real-time and smooth" cannot be improved safely without measurements.

### P2: Harden session isolation and reconnect behavior

Goal: avoid cross-session state pollution and make live usage recoverable.

Work:
* Isolate per-session mutable state from shared model clients.
* Avoid shared `last_translation` and shared revision cache across simultaneous sessions.
* Preserve session IDs on reconnect and define whether audio is resumed, dropped, or explicitly marked as a gap.
* Cancel in-flight tasks on WebSocket disconnect.

Why third:
* The current architecture is fine for a single-user demo, but session isolation becomes a correctness issue as soon as the product is used for real.

### P3: Expand subtitle/export experience

Goal: make output valuable both during and after watching.

Work:
* Add SRT and VTT export.
* Add Markdown bilingual notes with revision markers.
* Improve timestamp source from frontend receipt time to backend segment timing.
* Add style settings only after core subtitle timing is stable.

Why after P0/P1:
* Export quality depends on accurate segment timing and correction history.

### P4: Add Chinese TTS playback

Goal: satisfy the voice-output branch of the product requirement.

Work:
* Add backend or frontend TTS provider abstraction.
* Queue translated final segments for playback.
* Define correction playback behavior: do not replay minor corrections by default; optionally announce major corrected meaning.
* Add latency budget controls so TTS does not lag too far behind subtitles.

Why later:
* TTS makes correction and latency problems more visible, so it should build on stable subtitles and metrics.

### P5: Expand input sources and desktop capture

Goal: reach YouTube, local players, Zoom/Teams, courses, and conferences more reliably.

Work:
* Add file-input simulation for repeatable tests.
* Add microphone mode if needed for demos.
* Explore Tauri/Electron system-audio capture after browser flow has metrics and export coverage.

Why later:
* Input expansion multiplies platform-specific bugs; it should follow a stable browser MVP.

## Suggested MVP Slice

Recommended next implementation slice:

1. Segment-level audio buffer and retrieval.
2. Real ASR correction path using cached segment audio, with LLM post-edit as fallback.
3. Correction observability events and counters.
4. Tests for ASR correction and revision-cache behavior.

This is the highest-leverage slice because it addresses the hardest product requirement and creates the measurement foundation for the rest of the roadmap.

