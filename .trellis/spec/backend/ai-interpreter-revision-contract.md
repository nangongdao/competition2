# AI Interpreter Revision Contract

## Scenario: Segment Audio ASR Correction

### 1. Scope / Trigger

- Trigger: changes to the live interpretation correction path, especially ASR correction, translation revision, or WebSocket `revision` payload fields.
- This is a cross-layer contract: backend revision services emit data consumed by frontend subtitle state and diagnostics.
- Applies to:
  - `backend/services/asr_service.py`
  - `backend/services/revision_service.py`
  - `backend/core/pipeline.py`
  - `backend/models/messages.py`
  - `frontend/src/types.ts`

### 2. Signatures

Backend ASR re-decode:

```python
@dataclass(frozen=True)
class ASRDecodeResult:
    text: str
    confidence: float

async def ASRService.redecode_audio(audio_bytes: bytes) -> ASRDecodeResult | None:
    ...
```

Backend revision result:

```python
@dataclass
class RevisionResult:
    segment_id: str
    new_text: str
    reason: str
    source_text: str | None = None
    old_text: str | None = None
    old_source_text: str | None = None
    correction_source: str | None = None
    trigger: str | None = None
    latency_ms: int | None = None
    confidence: float | None = None
```

Frontend revision message:

```typescript
export interface RevisionMessage {
  type: 'revision'
  segment_id: string
  new_text: string
  source_text?: string
  reason: 'asr_correction' | 'translation_correction'
  old_text?: string
  old_source_text?: string
  correction_source?: string
  trigger?: string
  latency_ms?: number
  confidence?: number
}
```

### 3. Contracts

ASR correction priority:

1. Only consider ASR correction for segments below `settings.asr_correction_confidence_threshold`.
2. If cached segment audio is available, call `ASRService.redecode_audio(audio_bytes)` first.
3. If re-decode returns a source text that differs after normalization, use that correction with `correction_source = "audio_redecode"`.
4. If re-decode is unavailable or produces no useful source change, fall back to LLM ASR post-edit with `correction_source = "llm_post_edit"`.
5. If neither path produces a source change, emit no revision.

Redis audio cache:

- Key pattern: `session:{session_id}:audio:{segment_id}`
- Value: hex-encoded float32 PCM bytes
- TTL: `settings.audio_ttl_seconds`

WebSocket `revision` response:

- Required: `type`, `segment_id`, `new_text`, `reason`
- Required for ASR correction when source changed: `source_text`
- Optional diagnostic fields: `old_text`, `old_source_text`, `correction_source`, `trigger`, `latency_ms`, `confidence`
- Omit optional fields when unavailable; do not send `null` values.

### 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Segment confidence is above threshold | Return no ASR correction |
| Cached audio is missing or empty | Skip re-decode and try LLM post-edit |
| Re-decode raises an exception | Log a warning and try LLM post-edit |
| Re-decode text normalizes to original text | Try LLM post-edit |
| LLM post-edit returns `CORRECT` or empty text | Return no ASR correction |
| Corrected source differs but retranslation fails | Restore original source and return no revision |
| Translation-window revision changes text | Emit `translation_correction` with old/new metadata |

### 5. Good/Base/Bad Cases

- Good: low-confidence `grain sand`, cached audio re-decodes to `great sentence`, translation is regenerated, and revision emits `correction_source = "audio_redecode"`.
- Base: cached audio re-decodes to the same text, LLM post-edit returns `great sentence`, and revision emits `correction_source = "llm_post_edit"`.
- Bad: source text is already correct, both re-decode and post-edit produce no source change, and no translation call is made.

### 6. Tests Required

Unit tests must cover:

- Translation revision returns `translation_correction` metadata.
- ASR correction prefers audio re-decode and does not call LLM post-edit when re-decode produces a useful source change.
- ASR correction falls back to LLM post-edit when re-decode produces no source change.
- ASR correction returns `None` and does not retranslate when no source change is found.
- Revision payload metadata contains old/new source and translation fields where applicable.

### 7. Wrong vs Correct

#### Wrong

```python
if not asr.get_last_audio_chunk():
    return None
corrected = await llm_post_edit(segment.text_asr)
```

This only checks the last input chunk and relies on LLM post-editing. It does not use the segment-level cached audio that produced the final ASR text.

#### Correct

```python
cached_audio = await ctx.get_audio_chunk(session_id, segment.id)
result = await revision.check_asr_correction(
    segment,
    context_window,
    nmt,
    asr,
    audio_chunk=cached_audio,
    trigger="low_confidence",
)
```

The correction service receives the segment audio, tries Whisper re-decode first, and only then falls back to LLM post-edit.

