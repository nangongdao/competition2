# Roadmap And Big-Question Upgrades

## Goal

Ship a concrete V2 upgrade slice from `ROADMAP.md` that improves the product's live translation experience instead of only documenting future work. This iteration should make revision behavior easier to trigger and more useful in practice, while also improving subtitle readability and frontend resilience on mobile and across layout environments.

## Requirements

* Add a manual revision trigger from the frontend control panel and route it to the backend pipeline.
* Add silence-based revision triggering in the backend so revisions can run when audio input pauses, not only every fixed number of finalized sentences.
* Preserve the existing sentence-count-based revision trigger.
* Upgrade frontend subtitle data and rendering so the UI can show bilingual subtitles: ASR source text plus translated text.
* Keep revision updates visible in the bilingual subtitle display.
* Improve touch interaction styling to avoid common WebKit tap highlight issues on rounded controls.
* Keep layout behavior explicit and stable, following the flexbox guidance from `big-question`.

## Acceptance Criteria

* [ ] Clicking a manual revise control sends a control message to the backend and triggers revision checks without requiring a new finalized sentence.
* [ ] When audio pauses for the configured silence window, the backend attempts a revision check once.
* [ ] Existing periodic revision checks based on finalized sentence count still work.
* [ ] Subtitle entries retain both source and translated text and can render in bilingual mode.
* [ ] Revision messages update the translated line for the affected subtitle entry without breaking rendering.
* [ ] Interactive controls use explicit tap-highlight suppression and preserve rounded-corner visuals on mobile WebKit.
* [ ] Frontend layout changes follow explicit stretch/min-height patterns so they remain robust across build environments.

## Definition Of Done

* Relevant frontend and backend code paths are updated end to end.
* Verification is run for the available frontend and backend checks in this repo.
* Any limitations or unimplemented roadmap items are explicitly documented in the final handoff.

## Technical Approach

Implement the smallest coherent V2 slice:

* Backend:
  * extend WebSocket control handling with `manual_revise`
  * add silence timers in `Pipeline`
  * expose a forced revision path that bypasses only the sentence-count gate
* Frontend:
  * extend subtitle types/store/renderer for bilingual entries
  * add a revise action in `ControlPanel`
  * wire `AppController` to send source ASR text into the subtitle store and issue manual revise commands
  * harden button/touch styling and main overlay/container layout

## Decision (ADR-lite)

**Context**: `ROADMAP.md` proposes several V2 improvements, but not all are equally implementable in one pass. The current code already has a functioning revision service and subtitle pipeline, so the best leverage is to upgrade existing flows rather than introducing new infrastructure-heavy features like audio archival or ASR re-decoding.

**Decision**: Implement the revision-trigger and bilingual-display subset now, and defer ASR correction/audio archival to a later task.

**Consequences**:

* Pros:
  * delivers user-visible product improvements immediately
  * keeps the implementation bounded and testable
  * aligns directly with existing roadmap and known frontend pitfalls
* Cons:
  * does not yet implement true `asr_correction`
  * bilingual UI will initially focus on a default mode rather than a full settings system

## Out Of Scope

* Whisper re-decode or persisted audio archival
* LLM-based ASR post-editing
* Multi-language expansion beyond the existing source/target flow
* Desktop client or system audio capture work

## Technical Notes

* Source planning reference: [ROADMAP.md](/E:/competiton2/ROADMAP.md)
* Known pitfalls reviewed:
  * [.trellis/spec/big-question/turbopack-webpack-flexbox.md](/E:/competiton2/.trellis/spec/big-question/turbopack-webpack-flexbox.md)
  * [.trellis/spec/big-question/webkit-tap-highlight.md](/E:/competiton2/.trellis/spec/big-question/webkit-tap-highlight.md)
* Relevant code inspected:
  * `backend/core/pipeline.py`
  * `backend/api/websocket_handler.py`
  * `backend/services/revision_service.py`
  * `frontend/src/store/AppStore.ts`
  * `frontend/src/ui/ControlPanel.tsx`
  * `frontend/src/subtitle/SubtitleStore.ts`
  * `frontend/src/subtitle/SubtitleRenderer.ts`
