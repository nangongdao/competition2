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
    def record_audio_queue_depth(self, depth: int, capacity: int) -> None: ...
    def record_audio_queue_wait(self, latency_ms: int) -> None: ...
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
  captureBackend: 'audio-worklet' | 'script-processor' | null
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
- Frontend client diagnostics should include the active browser capture backend
  while capture is running and clear it when capture stops or fails.

Backend session isolation:

- `WebSocketHandler` keeps shared model/client resources only where they are stateless for a live stream.
- `ASRService.create_session()` must be used per WebSocket connection so audio buffers and callbacks do not leak across sessions.
- `RevisionService()` must be constructed per pipeline because translation cache, fingerprints, and revision counters are session-local.
- `NMTService.translate_stream()` consumers must accumulate the translation locally; do not read shared `NMTService.last_translation`.

Backend audio queue:

- `Pipeline.process_audio()` enqueues chunks into a bounded queue with `settings.audio_queue_max_chunks`.
- Queue diagnostics must expose current depth, maximum observed depth, queue capacity, and average/max queue wait latency so long-session runs can detect backlog before chunks drop.
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
    "audio_queue_depth": 0,
    "audio_queue_max_depth": 3,
    "audio_queue_capacity": 16,
    "asr_segments": 3,
    "translation_segments": 3,
    "revision_segments": 1,
    "reconnect_count": 0,
    "latency": {
      "audio_queue_wait_ms": { "count": 100, "avg_ms": 8, "max_ms": 44 },
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

- `audio_queue_wait_ms`
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
| Audio queue grows without overflowing | Update `audio_queue_depth`, `audio_queue_max_depth`, and `audio_queue_wait_ms` without emitting an error |
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
  - audio queue depth, maximum depth, capacity, and wait-latency summaries are preserved
  - latency summaries expose `count`, `avg_ms`, and `max_ms`
  - API/revision counters are emitted as plain objects
- Unit test `Pipeline` with fake ASR/NMT/context services:
  - queue overflow emits `AUDIO_QUEUE_FULL`, increments received/dropped counters,
    and preserves queue capacity plus maximum observed depth
  - a final ASR segment emits translation tokens, persists cached segment audio,
    updates the context segment, and records queue wait/capture/translation latency
  - `stop()` resets ASR session state, closes the context session, emits closed
    diagnostics, and ignores later audio chunks
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

## Scenario: WebSocket Endurance Runner

### 1. Scope / Trigger

- Trigger: changes to local reliability tooling that sends audio over the live
  WebSocket or reads `session_diagnostics` payloads.
- Applies to `tools/endurance_runner.py` and tests that validate report
  summarization or threshold behavior.
- The runner is a client-side validation tool only; it must not change backend
  WebSocket payload schemas.

### 2. Signatures

CLI:

```bash
python tools/endurance_runner.py \
  --duration-seconds 1800 \
  --url ws://localhost:8000/api/v1/ws/translate \
  --output reports/endurance-30m.json \
  --min-received-ratio 0.99 \
  --max-queue-depth 8
```

Core report helpers:

```python
def build_session_url(ws_url: str, session_id: str) -> str: ...
def record_message(state: RunnerState, message: dict[str, object]) -> None: ...
def build_report(...) -> dict[str, object]: ...
def validate_thresholds(report: dict[str, object], thresholds: Thresholds) -> None: ...
```

### 3. Contracts

- Default WebSocket URL is `/api/v1/ws/translate`; when that base route is used,
  the runner appends a generated or provided session ID.
- Audio chunks are sent as binary 16 kHz mono float32 PCM, matching the browser
  capture payload shape.
- Generated sources may be `silence` or `tone`; WAV input must be mono PCM at the
  configured sample rate.
- Manual revision controls are sent as text JSON
  `{"type": "manual_revise"}` when a positive interval is configured.
- Reports are JSON files containing:
  - client-side sent chunk/byte counts
  - received message counts
  - status code counts
  - server error messages
  - latest `session_diagnostics`
  - a summary of backend received/dropped chunks, segment counts, reconnects,
    queue depth/capacity, received/sent chunk ratio, and latency stats

### 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Duration is non-positive | Fail before connecting |
| Manual revision interval is negative | Fail before connecting |
| WAV path is missing | Fail before connecting |
| WAV is not mono | Fail before connecting |
| WAV sample rate differs from configured sample rate | Fail before connecting |
| WebSocket closes during the run | Stop receiving and write the report from collected data |
| Dropped chunks exceed configured threshold | Raise a runner error and exit non-zero |
| Backend audio queue max depth exceeds configured threshold | Raise a runner error and exit non-zero |
| Reconnects exceed configured threshold | Raise a runner error and exit non-zero |
| Backend received/sent chunk ratio is below configured threshold | Raise a runner error and exit non-zero |
| Average latency exceeds configured threshold | Raise a runner error and exit non-zero |

### 5. Good/Base/Bad Cases

- Good: A 30-60 minute run sends paced WAV audio, receives diagnostics snapshots,
  writes a report under `reports/`, and fails if dropped chunks or latency exceed
  the configured threshold.
- Base: A short local smoke run sends generated silence to verify WebSocket
  connectivity and diagnostics emission.
- Bad: The runner sends JSON-wrapped audio, changes backend message schemas, or
  treats the presence of the tool as proof that long-session stability has been
  validated.

### 6. Tests Required

- Unit tests for URL construction, PCM conversion, WAV looping, message
  recording, report summarization, queue-depth reporting, received-ratio
  calculation, and threshold failures.
- `python -m unittest backend.test_endurance_runner`
- `python -m compileall tools backend/test_endurance_runner.py`
- A real reliability baseline still requires a live backend with Redis, Whisper,
  provider API keys, and a 30-60 minute run.

### 7. Wrong vs Correct

#### Wrong

```python
await websocket.send(json.dumps({"type": "audio_chunk", "data": chunk.hex()}))
```

This sends a payload shape the backend does not process as audio.

#### Correct

```python
await websocket.send(chunk)
```

The backend receives binary float32 PCM bytes, the same shape produced by the
browser capture path.
