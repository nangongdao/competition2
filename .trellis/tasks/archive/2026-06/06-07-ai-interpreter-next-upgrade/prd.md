# AI Interpreter Validation Suite

## Goal

Make the existing AI simultaneous interpretation assistant easier to validate as a real product slice by adding a single command that coordinates preflight checks, optional endurance runs, and optional subtitle artifact validation into one auditable report.

## What I Already Know

* The project already has secret-safe Redis/Whisper/provider readiness checks in `tools/endurance_preflight.py`.
* The project already has paced WebSocket audio endurance diagnostics in `tools/endurance_runner.py`.
* The project already has subtitle export validation in `tools/subtitle_artifact_validator.py`.
* README and ROADMAP both say the next product work should focus on measurable reliability, real export validation, AudioWorklet comparison, and TTS validation before expanding the feature surface.
* True 30-60 minute live validation may require local Redis, Whisper, provider keys, browser/Electron access, and real session artifacts; the new code should not require secrets to pass unit tests.

## Requirements

* Add a repository-local validation suite CLI that can run:
  * endurance preflight,
  * optional WebSocket endurance runner,
  * optional subtitle artifact validation.
* Write a combined JSON report under `reports/` with:
  * generated timestamp,
  * overall status,
  * per-step status, exit code, command metadata, report path, and key blockers/failures,
  * recommended next actions when validation is blocked or incomplete.
* Keep provider secrets safe:
  * never print or store actual API keys,
  * reuse existing preflight redaction behavior.
* Support dry and local-friendly operation:
  * allow skipping preflight,
  * allow skipping endurance,
  * allow running artifact validation only when artifact paths are provided,
  * expose common endurance thresholds and memory monitor flags.
* Add focused unit tests for report aggregation, command construction, and status handling without requiring Redis, Whisper, provider keys, backend server, or real exported artifacts.
* Make subtitle artifact validation tolerate a leading UTF-8 BOM so Windows-authored TXT/Markdown files are not misclassified as missing their first entry or title.
* Update README and ROADMAP with the new validation-suite workflow.

## Acceptance Criteria

* [ ] `python tools/interpreter_validation_suite.py --help` documents the suite.
* [ ] The suite can run preflight only and still writes a combined report.
* [ ] The suite can skip preflight/endurance and validate supplied artifacts through the existing artifact validator.
* [ ] Failed or blocked child steps produce a non-zero suite exit and clear next actions.
* [ ] Unit tests cover success, blocked preflight, skipped steps, and artifact validation behavior.
* [ ] Existing backend and frontend tests remain green.

## Definition of Done

* Tests added or updated for new behavior.
* Backend unit tests and relevant tool help commands pass.
* Frontend tests/build are run if frontend files are touched.
* README, ROADMAP, and any relevant Trellis specs are updated.
* Changes are committed with meaningful Conventional Commit messages and pushed to the active PR branch.

## Technical Approach

Create `tools/interpreter_validation_suite.py` as a small orchestrator around existing tools instead of duplicating their internal logic. The suite should invoke child tool entry points through the same Python executable, read child JSON reports when available, summarize the result, and return exit code `0` only when all required executed steps pass.

## Decision (ADR-lite)

**Context**: The project needs real validation evidence, but the individual commands are easy to run inconsistently and some require local secrets or long-running services.

**Decision**: Add a lightweight Python CLI orchestrator that composes existing tools and reports one validation state, while keeping the underlying tools independently usable.

**Consequences**: This improves repeatability without adding dependencies or provider coupling. It does not replace real browser/Electron validation or real 30-60 minute sessions; it makes those sessions easier to execute and audit.

## Out of Scope

* No provider-backed TTS implementation in this task.
* No system-audio capture implementation in this task.
* No real 30-60 minute provider-backed run from CI or without local credentials.
* No storage or display of real API keys.

## Technical Notes

* Existing relevant files:
  * `tools/endurance_preflight.py`
  * `tools/endurance_runner.py`
  * `tools/subtitle_artifact_validator.py`
  * `backend/test_endurance_preflight.py`
  * `backend/test_endurance_runner.py`
  * `backend/test_subtitle_artifact_validator.py`
* Relevant docs:
  * `README.md`
  * `ROADMAP.md`
  * `.trellis/spec/backend/ai-interpreter-session-diagnostics.md`
  * `.trellis/spec/shared/code-quality.md`
* During artifact smoke testing, PowerShell-created UTF-8 files exposed that a leading BOM could hide the first TXT entry or Markdown title. The validator now strips that marker before format-specific validation.
