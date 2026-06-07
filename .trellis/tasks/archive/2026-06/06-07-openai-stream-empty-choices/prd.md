# Fix OpenAI Streaming Empty Choices Handling

## Goal

Make the backend OpenAI-compatible translation path tolerant of streaming chunks that contain no choices or no content delta, so third-party OpenAI-compatible providers can be used for real-time translation without crashing.

## Requirements

* Keep `NMT_ENGINE=openai` using the existing `AsyncOpenAI.chat.completions.create(..., stream=True)` path.
* Skip streaming chunks with an empty `choices` list.
* Skip chunks whose first choice has no `delta.content`.
* Preserve the existing behavior of yielding translated text tokens followed by `<FINAL>`.
* Preserve existing error wrapping through `NMTError`.
* Do not log, print, store, or commit API keys.

## Acceptance Criteria

* [x] Unit tests cover OpenAI streaming chunks with empty choices.
* [x] Unit tests cover OpenAI streaming chunks with missing or empty content.
* [x] Existing backend tests pass.
* [x] A real smoke test against the configured OpenAI-compatible provider returns translated text with `openai/gpt-oss-20b`.
* [ ] Current local `z-ai/glm-5.1` smoke test is stable. It timed out during validation, while the provider and key worked with another listed model.

## Definition of Done

* Tests added or updated for the compatibility behavior.
* Relevant backend validation commands pass.
* The task is committed with a meaningful Conventional Commit message.
* The existing delivery PR is updated with the day's progress.

## Technical Approach

Add defensive checks inside `NMTService._translate_openai` before indexing `chunk.choices[0]`. The service should continue consuming the stream and only yield non-empty content tokens.

## Decision (ADR-lite)

**Context**: The configured provider returns at least one streaming chunk with an empty `choices` list. The current implementation assumes every chunk has `choices[0].delta.content`, causing `list index out of range`.

**Decision**: Treat empty choices and missing content as non-content stream metadata, skip them, and keep the existing stream contract.

**Consequences**: This improves compatibility with OpenAI-style providers while preserving behavior for standard OpenAI responses. If a provider returns no content at all, the caller will still receive `<FINAL>` after the stream ends.

## Out of Scope

* Changing provider credentials or local `.env.local` values.
* Adding provider-specific model discovery UI.
* Replacing the OpenAI SDK or changing non-streaming completion behavior.

## Technical Notes

* Relevant code: `backend/services/nmt_service.py`.
* Relevant tests: backend service/unit tests under `backend/`.
* Observed failure with configured provider: `list index out of range` when streaming `z-ai/glm-5.1`.
* Post-fix smoke result: `openai/gpt-oss-20b` returned `早上好。`; `z-ai/glm-5.1` timed out on repeated short requests.
