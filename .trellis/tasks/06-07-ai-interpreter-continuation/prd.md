# Continue AI Interpreter Reliability and Artifact Validation

## Goal

Advance the AI simultaneous interpretation assistant from an implemented V2 slice toward a measurable demo baseline. The next project documents prioritize reliability measurement, export validation, and capture validation before adding larger product features, so this task focuses on tooling and tests that make those validation runs repeatable.

## What I Already Know

* The product goal is a real-time one-way foreign-language audio interpretation assistant that presents Chinese subtitles or speech and can revise earlier ASR/translation mistakes.
* README and ROADMAP say the next direction is 30-60 minute reliability baselines, post-session artifact validation, and AudioWorklet capture validation.
* Current implemented features already include WebSocket audio streaming, multi-source-language selection, revision messages, diagnostics, endurance reports, TXT/SRT/VTT/Markdown export, local browser/Electron TTS, and frontend/backend unit tests.
* Existing `tools/endurance_runner.py` reports queue depth, received ratio, latency, revision counters, API counters, and subtitle ordering anomalies.
* The documented reliability baseline still asks for memory-growth tracking, but the current endurance report has no process memory summary or threshold.
* Export formatter tests cover output strings, but there is no reusable validator that summarizes timeline gaps/overlaps, revised marker counts, and readable artifact metadata for real-session exports.

## Requirements

* Add process memory sampling to endurance reports without adding a new dependency.
* Allow long-run validation to fail when monitored process RSS growth exceeds a configured threshold.
* Keep memory monitoring optional and useful for both the runner process and explicitly supplied backend/process PIDs.
* Add an export artifact validation helper that can inspect generated SRT/VTT/Markdown/TXT outputs and summarize whether they are usable for real-session validation.
* Update tests for the new report fields, threshold behavior, and artifact validation.
* Update README/ROADMAP/spec notes so future sessions know how to use the new validation surface.

## Acceptance Criteria

* [ ] `tools/endurance_runner.py` accepts memory-monitoring CLI flags and includes memory summary/sample data in the JSON report.
* [ ] `validate_thresholds()` fails with a clear message when memory growth is above the configured maximum.
* [ ] Unit tests cover memory summary and threshold behavior without relying on machine-specific processes.
* [ ] A reusable export validation module or tool reports cue counts, timeline overlaps/gaps, revision markers, empty artifact detection, and Markdown readability metadata.
* [ ] Frontend export tests or backend/tool tests cover the export validation behavior.
* [ ] README and relevant Trellis specs document how to run the enhanced validation.

## Definition of Done

* Backend/tool unit tests pass.
* Frontend tests pass if frontend formatter code changes.
* Compile/type checks pass for touched Python/TypeScript files.
* `git diff --check` passes.
* Work is committed with meaningful Conventional Commit messages and pushed to the project PR branch.

## Technical Approach

* Implement memory sampling in Python using platform-aware standard-library mechanisms: Windows process APIs via `ctypes`, Linux `/proc/<pid>/status`, and macOS/Linux `resource` fallback where available.
* Keep the runner independent of `psutil` to avoid changing install requirements.
* Extend `RunnerConfig` and `Thresholds` with memory monitor definitions and a `max_memory_growth_mb` threshold.
* Add a small artifact validation tool under `tools/` so real-session exports can be checked outside the browser.
* Use focused tests in `backend/test_endurance_runner.py` and a new test module for artifact validation.

## Decision (ADR-lite)

**Context**: The roadmap's highest-priority remaining gap is measured reliability, not feature expansion. Memory growth and artifact usability must be visible in generated reports to make 30-60 minute runs actionable.

**Decision**: Add optional, dependency-free validation tooling rather than introducing a larger monitoring stack or provider-backed TTS/system-audio slice in this task.

**Consequences**: The next demo can produce stronger evidence from local runs. Process discovery remains explicit via PIDs, which is simpler and less fragile than trying to infer every backend process automatically.

## Out of Scope

* Provider-backed TTS synthesis.
* Full desktop/system-audio capture.
* Real 30-60 minute speech run if local environment or time is not available.
* New paid/commercial features.

## Technical Notes

* Relevant docs: `README.md`, `ROADMAP.md`, `.trellis/spec/backend/ai-interpreter-session-diagnostics.md`, `.trellis/spec/frontend/tts-playback.md`, `.trellis/spec/frontend/api-integration.md`, `.trellis/spec/shared/code-quality.md`.
* Relevant code: `tools/endurance_runner.py`, `backend/test_endurance_runner.py`, `frontend/src/subtitle/subtitle-export.ts`, `frontend/src/subtitle/subtitle-export.test.ts`.
