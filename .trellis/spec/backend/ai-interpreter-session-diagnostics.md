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

Backend pipeline diagnostics request:

```python
async def Pipeline.emit_diagnostics() -> None:
    """Emit the current session diagnostics snapshot over the WebSocket."""
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
- While audio is arriving, `Pipeline` emits periodic `session_diagnostics`
  snapshots at `settings.diagnostics_emit_interval_seconds` so silent input or
  delayed ASR finals still expose received chunk counts and queue depth.

WebSocket control diagnostics:

- Clients and local validation tools may send
  `{"type": "request_diagnostics"}` over the control channel.
- The backend responds with the current `session_diagnostics` payload without
  mutating revision counters, audio counters, or session state.

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
| Audio arrives but no ASR final is produced | Periodic diagnostics still expose received chunk counts |
| Client sends `request_diagnostics` | Emit one current diagnostics snapshot |
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
  - periodic diagnostics expose received audio counts even when no ASR final is
    produced
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
  --max-queue-depth 8 \
  --max-subtitle-order-violations 0 \
  --monitor-self \
  --monitor-pid backend=<uvicorn_pid> \
  --max-memory-growth-mb 150
```

Control message sent by the runner after audio transmission stops:

```json
{"type": "request_diagnostics"}
```

Core report helpers:

```python
def build_session_url(ws_url: str, session_id: str) -> str: ...
def record_message(state: RunnerState, message: dict[str, object]) -> None: ...
def build_report(...) -> dict[str, object]: ...
def build_memory_summary(samples: list[dict[str, object]]) -> dict[str, dict[str, object]]: ...
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
- After the audio sender finishes normally, the runner sends
  `{"type": "request_diagnostics"}` and keeps receiving for
  `receive_timeout_seconds` so the final report is not limited to the last
  periodic diagnostics tick.
- Reports are JSON files containing:
  - client-side sent chunk/byte counts
  - received message counts
  - status code counts
  - server error messages
  - latest `session_diagnostics`
  - a summary of backend received/dropped chunks, segment counts, reconnects,
    queue depth/capacity, received/sent chunk ratio, latency stats,
    API/revision counters, and final-subtitle ordering anomalies
  - optional `memory_samples` entries when process monitors are configured
  - `summary.memory` grouped by monitor label with process PID, sample count,
    unavailable sample count, start/end/peak RSS, end-growth MB, and peak-growth
    MB
  - `summary.subtitle_ordering.order_violation_count`, which combines duplicate
    final subtitles, out-of-order final subtitles, final-sequence gaps, and
    revisions that reference segments without a previously observed final
    translation message

### 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Duration is non-positive | Fail before connecting |
| Manual revision interval is negative | Fail before connecting |
| WAV path is missing | Fail before connecting |
| WAV is not mono | Fail before connecting |
| WAV sample rate differs from configured sample rate | Fail before connecting |
| WebSocket closes during the run | Stop receiving and write the report from collected data |
| Audio sending finishes normally | Request final diagnostics before closing the WebSocket |
| Dropped chunks exceed configured threshold | Raise a runner error and exit non-zero |
| Backend audio queue max depth exceeds configured threshold | Raise a runner error and exit non-zero |
| Reconnects exceed configured threshold | Raise a runner error and exit non-zero |
| Backend received/sent chunk ratio is below configured threshold | Raise a runner error and exit non-zero |
| Average latency exceeds configured threshold | Raise a runner error and exit non-zero |
| Subtitle order violations exceed configured threshold | Raise a runner error and exit non-zero |
| Monitored process RSS growth exceeds configured threshold | Raise a runner error and exit non-zero |
| A monitored process is unavailable | Keep an unavailable sample with an error; do not fail unless another configured threshold fails |

### 5. Good/Base/Bad Cases

- Good: A 30-60 minute run sends paced WAV audio, receives diagnostics snapshots,
  writes a report under `reports/`, and fails if dropped chunks or latency exceed
  the configured threshold. If `--monitor-self` or `--monitor-pid` are set, the
  report also records process RSS growth.
- Base: A short local smoke run sends generated silence to verify WebSocket
  connectivity and diagnostics emission.
- Bad: The runner sends JSON-wrapped audio, changes backend message schemas, or
  treats the presence of the tool as proof that long-session stability has been
  validated.

### 6. Tests Required

- Unit tests for URL construction, PCM conversion, WAV looping, message
  recording, report summarization, queue-depth reporting, received-ratio
  calculation, API/revision counter summaries, subtitle-order summaries, and
  threshold failures.
- Unit tests for memory summary and memory-growth threshold failures must not
  rely on machine-specific background processes.
- Unit tests for sender completion must assert normal duration expiry leaves the
  receiver open for the drain window instead of setting the shared stop event.
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

## Scenario: Subtitle Artifact Validator

### 1. Scope / Trigger

- Trigger: changes to local validation tooling for exported subtitles,
  transcripts, or learning-note artifacts.
- Applies to `tools/subtitle_artifact_validator.py` and tests that validate real
  export artifacts after a live session.
- The validator reads already-exported files; it must not change frontend export
  format or backend WebSocket schemas.

### 2. Signatures

CLI:

```bash
python tools/subtitle_artifact_validator.py \
  exports/session.txt \
  exports/session.srt \
  exports/session.vtt \
  exports/session.md \
  --output reports/subtitle-artifacts-latest.json
```

Core helpers:

```python
def validate_artifact(path: Path, *, kind: str | None = None, long_gap_ms: int = 5000) -> dict[str, object]: ...
def validate_artifact_text(text: str, *, kind: str, path_label: str = "", long_gap_ms: int = 5000) -> dict[str, object]: ...
def build_validation_report(paths: list[Path], *, kind: str | None, long_gap_ms: int) -> dict[str, object]: ...
```

### 3. Contracts

- Supported artifact kinds are `txt`, `srt`, `vtt`, and `markdown`; kind may be
  inferred from file extension or overridden for all paths.
- Artifact text must tolerate a leading UTF-8 BOM so Windows-authored TXT or
  Markdown files are not misclassified as missing their first entry or title.
- Timed subtitles must report cue count, invalid timestamp count, overlap count,
  gap count, long-gap count, maximum gap, duration, and empty cue count.
- Plain transcript validation must report numbered entry count plus source and
  translation line counts.
- Markdown validation must report heading count, bullet count, title presence,
  timeline section presence, timeline entry count, source line count, and
  translation line count.
- All artifact kinds must report empty-output status and ASR/translation/generic
  revision marker counts.
- The CLI exits `0` only when every artifact is usable; otherwise it exits `2`
  and still writes the JSON report when `--output` is provided.

### 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Artifact path is missing | Raise a validator error and exit non-zero |
| Extension/kind is unsupported | Raise a validator error and exit non-zero |
| Artifact starts with a UTF-8 BOM | Strip the BOM before format-specific validation |
| VTT file only contains `WEBVTT` | Mark the artifact empty and unusable |
| SRT/VTT cue timestamps are invalid | Mark timed artifact unusable |
| SRT/VTT cues overlap | Mark timed artifact unusable |
| Timed artifact has long gaps | Report long gaps for review; do not make it unusable by itself |
| Markdown lacks title or timeline entries | Mark Markdown artifact unusable |
| TXT lacks numbered entries | Mark TXT artifact unusable |

### 5. Tests Required

- Unit tests for SRT/VTT cue parsing, overlap/gap summaries, empty VTT handling,
  UTF-8 BOM handling, Markdown readability metadata, plain transcript counts,
  extension detection, report aggregation, and unsupported extensions.

## Scenario: Endurance Preflight and Redis Compatibility

### 1. Scope / Trigger

- Trigger: changes to local reliability tooling that checks Redis, Whisper,
  CUDA, or provider key readiness before a 30-60 minute endurance run.
- Applies to `backend/core/config.py`, `tools/endurance_preflight.py`, Redis
  connection setup in `backend/services/context_manager.py`,
  `backend/storage/redis_client.py`, and tests that validate preflight report
  blocking behavior.
- The preflight must not send audio or call provider APIs; it only validates
  readiness and writes a secret-safe JSON report.

### 2. Signatures

CLI:

```bash
python tools/endurance_preflight.py \
  --output reports/endurance-preflight-latest.json \
  --load-whisper-model
```

Redis settings:

```python
settings.redis_url: str
settings.redis_protocol: int = 2
```

Environment settings:

```python
ENV_FILE_PATHS = (
    REPO_ROOT / ".env",
    BACKEND_ROOT / ".env",
    BACKEND_ROOT / ".env.local",
)
settings.anthropic_api_key: str
settings.openai_api_key: str
```

Core helpers:

```python
async def check_redis() -> dict[str, object]: ...
def build_provider_check() -> dict[str, object]: ...
def build_whisper_check(*, load_model: bool) -> dict[str, object]: ...
def build_report(...) -> dict[str, object]: ...
def redact_url(url: str) -> str: ...
```

### 3. Contracts

- `REDIS_PROTOCOL` defaults to `2` so Redis 3.x does not fail on RESP3
  `HELLO` during local validation.
- Redis hash initialization that needs multiple fields must use single-field
  `HSET` commands, optionally through a pipeline, because Redis 3.x rejects
  multi-field `HSET`.
- Backend settings must load dotenv files from explicit project paths, not from
  the process working directory. The load order is root `.env`, `backend/.env`,
  then `backend/.env.local`; later files override earlier files, and real
  environment variables override all dotenv values.
- Real provider keys belong in ignored local files such as
  `backend/.env.local`. The tracked `backend/.env.example` file is only a
  template and must use placeholder values.
- The preflight report contains:
  - `status`: `ready` or `blocked`
  - `blockers`: plain strings suitable for PR or daily progress notes
  - `checks.redis`: redacted URL, protocol, version, and error metadata
  - `checks.provider`: engine, model, required key name, and `key_present`
  - `checks.whisper`: engine, package version, model, device, compute type,
    CUDA availability, and optional model-load result
  - `next_command_when_ready`: the 30-minute endurance runner command
- Provider key values, Redis passwords, and API secrets must never be printed or
  written to reports. Only key names and boolean presence are allowed.

### 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Redis ping fails | Report `status=blocked` and include Redis error type/message |
| Redis URL includes credentials | Report only the redacted URL |
| Provider engine is unsupported | Report `status=blocked` |
| Required provider key is empty or placeholder | Report `status=blocked` |
| `backend/.env.local` is missing | Fall back to root `.env`, `backend/.env`, or defaults |
| Environment variable and dotenv value both exist | Use the real environment variable |
| `ASR_ENGINE` is not `whisper` | Report `status=blocked` |
| `faster-whisper` is missing | Report `status=blocked` |
| `WHISPER_DEVICE=cuda` but CUDA is unavailable | Report `status=blocked` |
| `--load-whisper-model` fails | Report `status=blocked` |
| All checks pass | Report `status=ready` and exit successfully |

### 5. Good/Base/Bad Cases

- Good: Preflight passes with Redis reachable, provider key configured,
  Whisper installed, and the configured device available from
  `backend/.env.local`; the operator then starts the backend and runs
  `tools/endurance_runner.py` for 30-60 minutes.
- Base: Preflight writes a blocked report on a developer machine because a
  provider key is missing; the report is safe to commit because it contains no
  secret values.
- Bad: A long endurance run is started without preflight, fails after backend
  startup because Redis 3 rejects `HELLO` or because the provider key is a
  placeholder, and no actionable report is produced.
- Bad: Settings only read `.env` from the current working directory, so the
  desktop launcher and root-level tools silently use different provider keys.

### 6. Tests Required

- Unit tests for URL redaction and placeholder key detection.
- Unit tests that `build_report()` blocks when provider keys are missing,
  CUDA configuration is impossible, Redis fails, or Whisper is not configured.
- Unit test that `build_report()` returns `ready` when Redis, provider, and
  Whisper checks are valid.
- Unit tests that settings load root `.env`, `backend/.env`, and
  `backend/.env.local` in order, ignore unknown dotenv keys, and still let real
  environment variables override file values.
- Redis compatibility should be manually validated against Redis 3.x when the
  local environment exposes it: initialize `ContextManager`, create a session,
  reserve a segment index, and clean up the test key.

### 7. Wrong vs Correct

#### Wrong

```python
self._redis = aioredis.from_url(settings.redis_url)
await self._redis.hset(meta_key, mapping={"segment_count": "0"})
```

This can negotiate RESP3 against Redis 3.x and can also emit a multi-field
`HSET` shape that Redis 3.x rejects.

```python
class Settings(BaseSettings):
    class Config:
        env_file = ".env"
```

This depends on the command working directory and can make root-level tools and
the backend launcher read different secret files.

#### Correct

```python
self._redis = aioredis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
    protocol=settings.redis_protocol,
)

pipeline = self._redis.pipeline()
for field, value in values.items():
    pipeline.hset(meta_key, field, value)
await pipeline.execute()
```

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=tuple(str(path) for path in ENV_FILE_PATHS),
        env_file_encoding="utf-8",
        extra="ignore",
    )
```

This makes local secret loading deterministic while preserving normal
environment-variable overrides.

The connection protocol is explicit, and hash initialization remains compatible
with both Redis 3.x and newer Redis versions.

## Scenario: Interpreter Validation Suite

### 1. Scope / Trigger

- Trigger: changes to local validation orchestration that combines preflight,
  endurance, or subtitle artifact checks.
- Applies to `tools/interpreter_validation_suite.py` and tests that validate
  suite report aggregation or child command construction.
- The suite is an operator-facing wrapper only. It must not replace the
  underlying validation tools, change backend WebSocket schemas, or change
  frontend export formats.

### 2. Signatures

CLI:

```bash
python tools/interpreter_validation_suite.py \
  --run-endurance \
  --duration-seconds 1800 \
  --monitor-self \
  --monitor-pid backend=<uvicorn_pid> \
  --max-memory-growth-mb 150 \
  --max-dropped-chunks 0 \
  --max-queue-depth 8 \
  --min-received-ratio 0.99 \
  --max-subtitle-order-violations 0 \
  --artifact exports/session.txt \
  --artifact exports/session.srt \
  --artifact exports/session.vtt \
  --artifact exports/session.md \
  --output reports/interpreter-validation-30m.json
```

Core helpers:

```python
def run_suite(config: SuiteConfig, *, command_runner=run_command) -> tuple[int, dict[str, object]]: ...
def build_suite_report(steps: list[dict[str, object]]) -> dict[str, object]: ...
def determine_overall_status(steps: list[dict[str, object]]) -> str: ...
def build_next_actions(steps: list[dict[str, object]], status: str) -> list[str]: ...
```

### 3. Contracts

- By default the suite runs `tools/endurance_preflight.py` and skips endurance
  until `--run-endurance` is provided.
- Endurance is skipped when preflight is blocked or failed. Operators may use
  `--skip-preflight` when intentionally running a local smoke test without the
  readiness gate.
- Subtitle artifact validation runs only when one or more `--artifact` paths
  are provided.
- Before each child step runs, the suite removes that child report path so a
  failed child process cannot be summarized from stale JSON.
- The combined report contains:
  - top-level `generated_at`
  - top-level `status`: `passed`, `blocked`, `failed`, or `incomplete`
  - one entry per step with name, status, exit code, safe command metadata,
    child report path, stdout/stderr excerpts, and a small summary
  - `next_actions` with actionable follow-up items
- The suite exits `0` only when every executed child step passes. It exits
  non-zero when a child step fails, preflight blocks the run, or no step was
  executed.
- Provider key values and Redis credentials must never be written to the suite
  report. The suite may include provider key names and boolean key presence from
  the existing secret-safe preflight report.

### 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Preflight passes and no other steps are requested | Write a passed suite report with endurance/artifacts marked skipped |
| Preflight returns a blocked child report | Mark preflight blocked, skip endurance, and exit non-zero |
| `--skip-preflight --run-endurance` is used | Run endurance directly |
| Endurance child exits non-zero | Mark endurance failed and exit non-zero |
| Artifact validator exits non-zero | Mark artifacts failed and include unusable paths when a child report exists |
| No preflight, endurance, or artifacts are executed | Mark the suite incomplete and exit non-zero |
| Child process fails before writing a JSON report | Mark the step failed and report `report_available=false` |

### 5. Good/Base/Bad Cases

- Good: A real operator runs preflight, a 30-60 minute endurance baseline, and
  exported TXT/SRT/VTT/Markdown artifact checks through one suite command; the
  combined report shows every executed step passed and keeps child report paths.
- Base: A developer runs the suite with no extra flags; preflight passes, while
  endurance and artifacts are explicitly marked skipped with next actions.
- Bad: The suite treats an old child JSON report as current evidence after a
  child command fails before writing a new report.
- Bad: The suite accepts provider keys as CLI arguments or writes secret values
  into the combined report.

### 6. Tests Required

- Unit tests for preflight-only success.
- Unit tests for blocked preflight skipping endurance.
- Unit tests for artifact-only success and unusable artifact failure.
- Unit tests that stale child reports are removed before child command
  execution.
- Unit tests for CLI argument construction of endurance thresholds and memory
  monitor flags.

### 7. Wrong vs Correct

#### Wrong

```python
child_report = load_json_report(config.endurance_output_path)
result = command_runner(command)
```

This can summarize stale endurance evidence when the new child command fails
before writing a report.

#### Correct

```python
remove_existing_report(config.endurance_output_path)
result = command_runner(command)
child_report = load_json_report(config.endurance_output_path)
```

Each suite run summarizes only child reports produced by the current execution.
