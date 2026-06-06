# AI Interpreter Session Diagnostics and Reconnect Contract

## Scenario: Live Session Diagnostics and Isolation

### 1. Scope / Trigger

- Trigger: changes to live interpretation session lifecycle, WebSocket reconnect behavior, queueing/cancellation, or diagnostics payload fields.
- This is a cross-layer contract: backend pipeline diagnostics are emitted over WebSocket and consumed by frontend state, control details, and diagnostics export.
- Applies to:
  - `backend/api/websocket_handler.py`
  - `backend/core/pipeline.py`
  - `backend/services/session_diagnostics.py`
  - `backend/services/context_manager.py`
  - `backend/models/messages.py`
  - `frontend/src/network/WsClient.ts`
  - `frontend/src/store/AppStore.ts`
  - `frontend/src/types.ts`
  - `frontend/src/ui/ControlPanel.tsx`
  - `frontend/src/ui/SubtitleHistoryPanel.tsx`

### 2. Signatures

Backend diagnostics:

```python
@dataclass
class SessionDiagnostics:
    session_id: str

    def record_audio_chunk(self, size_bytes: int) -> None: ...
    def record_dropped_audio_chunk(self) -> None: ...
    def record_asr_segment(self, latency_ms: int | None = None) -> None: ...
    def record_translation_segment(
        self,
        *,
        first_token_latency_ms: int | None,
        final_latency_ms: int | None,
    ) -> None: ...
    def record_revision(
        self,
        *,
        reason: str,
        source: str | None,
        trigger: str | None,
        latency_ms: int | None,
    ) -> None: ...
    def snapshot(self) -> dict: ...
```

Backend context/session:

```python
async def ContextManager.init_session(session_id: str) -> int:
    """Return reconnect count."""

async def ContextManager.next_segment_index(session_id: str) -> int:
    """Return a reconnect-safe segment index."""
```

Backend ASR stream isolation:

```python
async def ASRService.process_chunk(audio_bytes: bytes) -> int:
    """Return the number of final ASR segments emitted."""

def ASRService.create_session() -> ASRService:
    """Return isolated stream buffers/callbacks sharing the initialized model."""

def ASRService.reset_session_state() -> None:
    """Clear callbacks and audio buffers for a single stream state."""
```

Frontend diagnostics:

```typescript
export interface SessionDiagnosticsMessage {
  type: 'session_diagnostics'
  diagnostics: SessionDiagnostics
}

export interface ClientDiagnostics {
  sessionId: string
  sentAudioChunks: number
  droppedAudioChunks: number
  reconnectAttempts: number
  connectionOpens: number
  lastDisconnectAt: number | null
}
```

### 3. Contracts

WebSocket session ID:

- Frontend generates a stable 8-character session ID for a running capture session.
- Frontend connects to `/api/v1/ws/translate/{session_id}` so reconnects reuse the same server session context.
- `WsClient.resetSession()` must be called for a user-initiated stop/new run so a fresh session ID is used.

Backend session isolation:

- `WebSocketHandler` keeps shared model/client resources only where they are stateless for a live stream.
- `ASRService.create_session()` must be used per WebSocket connection so audio buffers and callbacks do not leak across sessions.
- `RevisionService()` must be constructed per pipeline because translation cache, fingerprints, and revision counters are session-local.
- `NMTService.translate_stream()` consumers must accumulate the translation locally; do not read shared `NMTService.last_translation`.

Backend audio queue:

- `Pipeline.process_audio()` enqueues chunks into a bounded queue with `settings.audio_queue_max_chunks`.
- Queue overflow increments `audio_chunks_dropped`, emits status code `AUDIO_QUEUE_FULL`, and emits a diagnostics snapshot.
- `Pipeline.stop()` cancels the audio worker and silence timer so in-flight ASR/NMT/revision work does not continue after disconnect.

Diagnostics response:

```json
{
  "type": "session_diagnostics",
  "diagnostics": {
    "session_id": "abc123ef",
    "status": "running",
    "duration_ms": 12000,
    "audio_chunks_received": 100,
    "audio_bytes_received": 640000,
    "audio_chunks_dropped": 0,
    "asr_segments": 3,
    "translation_segments": 3,
    "revision_segments": 1,
    "reconnect_count": 0,
    "latency": {
      "capture_to_asr_ms": { "count": 3, "avg_ms": 2100, "max_ms": 2300 }
    },
    "api_call_counts": { "nmt_stream": 4 },
    "revision_counts": { "asr_correction": 1 },
    "revision_sources": { "audio_redecode": 1 },
    "revision_triggers": { "low_confidence": 1 }
  }
}
```

Latency keys:

- `capture_to_asr_ms`
- `asr_to_first_token_ms`
- `asr_to_translation_final_ms`
- `revision_final_ms`

### 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| New client run | Generate a new frontend session ID and connect to `/ws/translate/{session_id}` |
| Automatic reconnect during a run | Reuse the same session ID; backend increments `reconnect_count` |
| Same session connects while old pipeline is active | Stop old pipeline before installing the new one; old handler must not pop the new pipeline |
| Audio queue is full | Drop the chunk, increment diagnostics, emit `AUDIO_QUEUE_FULL` |
| WebSocket disconnects | Cancel worker/silence tasks and reset ASR session buffers/callbacks |
| Redis meta exists but reconnect count is missing | `hincrby` creates/updates the field; do not reset segment count |
| Backend diagnostics are unavailable at startup | Frontend still reports client diagnostics and can export them |

### 5. Good/Base/Bad Cases

- Good: A browser tab briefly loses WebSocket connectivity, reconnects with the same session ID, backend emits `SESSION_RECONNECTED`, segment IDs continue from Redis `segment_count`, and diagnostics show one reconnect.
- Base: A single-user demo runs without reconnects; diagnostics still show audio chunk counts, latency summaries, API call counters, and revision counters.
- Bad: Two sessions share one ASR buffer or one revision cache; one user's audio or cached revision changes another user's subtitles.

### 6. Tests Required

- Unit test `SessionDiagnostics.snapshot()`:
  - audio chunk and drop counters are preserved
  - latency summaries expose `count`, `avg_ms`, and `max_ms`
  - API/revision counters are emitted as plain objects
- Revision tests must keep passing after per-session revision counters are added.
- Frontend build must pass after adding `SessionDiagnosticsMessage`, `ClientDiagnostics`, and diagnostics export UI.
- For future integration tests:
  - connect twice with the same session ID and assert the second connection reports `SESSION_RECONNECTED`
  - force queue overflow and assert `AUDIO_QUEUE_FULL` plus `audio_chunks_dropped > 0`
  - stop a pipeline during translation and assert no further messages are emitted by the stopped pipeline

### 7. Wrong vs Correct

#### Wrong

```python
pipeline = Pipeline(
    session_id=session_id,
    asr=self._asr,
    nmt=self._nmt,
    ctx_manager=self._ctx_manager,
    revision=self._revision,
)
segment.text_translated = self._nmt.last_translation
```

This shares ASR callbacks/buffers, revision cache, and translated text state across live sessions.

#### Correct

```python
pipeline = Pipeline(
    session_id=session_id,
    asr=self._asr.create_session(),
    nmt=self._nmt,
    ctx_manager=self._ctx_manager,
    revision=RevisionService(),
)

translated_parts: list[str] = []
async for token in self._nmt.translate_stream(context_window, segment):
    if token != "<FINAL>":
        translated_parts.append(token)
segment.text_translated = "".join(translated_parts).strip()
```

The model/client may be shared, but mutable live-stream state stays owned by one pipeline.
