# AI Interpreter Language Configuration Contract

## Scenario: Live Source Language to Chinese Configuration

### 1. Scope / Trigger

- Trigger: changes to live interpretation language-pair selection, WebSocket
  `config` control payloads, Whisper language parameters, NMT prompts, or
  per-segment language metadata.
- This is a cross-layer contract. The frontend owns the user's source-language
  selection; the backend applies it to ASR and translation while preserving
  session isolation.
- Applies to:
  - `frontend/src/types.ts`
  - `frontend/src/network/WsClient.ts`
  - `frontend/src/store/AppStore.ts`
  - `frontend/src/ui/ControlPanel.tsx`
  - `backend/api/websocket_handler.py`
  - `backend/core/pipeline.py`
  - `backend/models/segment.py`
  - `backend/services/asr_service.py`
  - `backend/services/nmt_service.py`
  - `backend/services/revision_service.py`
  - `backend/services/language_config.py`

### 2. Signatures

Frontend language config:

```typescript
export type SourceLanguage = 'auto' | 'en' | 'ja' | 'ko' | 'es' | 'fr' | 'de'
export type TargetLanguage = 'zh-CN'

export interface LanguageConfig {
  sourceLanguage: SourceLanguage
  targetLanguage: TargetLanguage
}
```

WebSocket control payload:

```json
{
  "type": "config",
  "language": "ja",
  "target_language": "zh-CN"
}
```

Backend language config:

```python
@dataclass(frozen=True)
class LanguageConfig:
    source_language: str = "en"
    target_language: str = "zh-CN"

def normalize_source_language(value: object) -> str: ...
def normalize_target_language(value: object) -> str: ...
def whisper_language_code(source_language: object) -> str | None: ...
```

Pipeline update:

```python
async def Pipeline.update_config(
    *,
    language: object | None = None,
    target_language: object | None = None,
) -> None: ...
```

Segment metadata:

```python
@dataclass
class Segment:
    source_language: str = "en"
    target_language: str = "zh-CN"
```

### 3. Contracts

- The frontend sends the current `LanguageConfig` when the WebSocket opens and
  immediately sends a new `config` message when the source language changes on
  an open socket.
- The target language remains `zh-CN` in this task because the product
  requirement is foreign-language audio to Chinese.
- Backend language values must be normalized through the whitelist in
  `services/language_config.py` before being used in prompts or ASR parameters.
  Unknown or unsafe values fall back to defaults instead of being interpolated.
- `SourceLanguage = "auto"` maps to `language=None` for Faster-Whisper so the
  model can detect the source language. Explicit source languages map to their
  language code, such as `"en"`, `"ja"`, or `"fr"`.
- `Pipeline` owns the session language config. Do not store per-session language
  state on shared `NMTService` instances.
- Each `Segment` stores the active `source_language` and `target_language` so
  translation revision and ASR correction can retranslate using the same
  language pair as the original segment.
- NMT system and user prompts must be built from the segment language pair, not
  from hard-coded English-to-Chinese text.
- ASR post-edit prompts must mention the segment source language and require the
  corrected sentence to stay in that source language.

### 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Frontend starts a session | `WsClient` sends `config` after the socket opens |
| User changes source language while connected | `WsClient` sends a new `config` payload immediately |
| `language` is omitted from backend config | Keep the current pipeline source language |
| `target_language` is omitted from backend config | Keep the current pipeline target language |
| `language` is unsupported or prompt-like text | Normalize to default `"en"` |
| `target_language` is unsupported | Normalize to default `"zh-CN"` |
| `language` is `"auto"` | Pass `None` to Faster-Whisper |
| Translation revision reprocesses an old segment | Use that segment's stored language pair |

### 5. Good/Base/Bad Cases

- Good: user selects Japanese, starts capture, frontend sends
  `{"type":"config","language":"ja","target_language":"zh-CN"}`, Whisper receives
  `language="ja"`, and NMT prompts say Japanese to Simplified Chinese.
- Base: user keeps the default English source language; behavior remains
  English-to-Chinese but goes through the same normalized config path.
- Good: user selects Auto detect; Whisper receives `language=None`, while NMT
  prompts describe the source as the detected source language.
- Bad: the backend logs `config` but does not update `Pipeline`; ASR remains
  English-only and NMT prompts stay hard-coded.
- Bad: shared `NMTService` stores mutable language state and leaks one session's
  language into another session.

### 6. Tests Required

- Backend unit tests:
  - language normalization rejects unsupported/prompt-like values
  - `whisper_language_code("auto")` returns `None`
  - `ASRService` passes configured language codes to Whisper
  - `NMTService` OpenAI-compatible prompts include the segment source and target
  - ASR correction post-edit prompts include the segment source language
  - `Pipeline.update_config()` affects future segments and translation calls
  - `WebSocketHandler` routes `config` to `Pipeline.update_config()`
- Frontend unit tests:
  - `WsClient` sends the configured language pair when the socket opens
  - `WsClient` sends a new config immediately when language changes on an open
    socket
- Run backend unittest discovery and frontend test/build after changing this
  contract.

### 7. Wrong vs Correct

#### Wrong

```python
if msg_type == "config":
    language = msg.get("language", "en")
    logger.info("Config updated: {}", language)
    return
```

This accepts the message but does not change ASR or NMT behavior.

#### Correct

```python
if msg_type == "config":
    await pipeline.update_config(
        language=msg.get("language"),
        target_language=msg.get("target_language"),
    )
    return
```

The pipeline normalizes the values, updates the session-owned language config,
and applies the source language to the ASR session.

#### Wrong

```python
class NMTService:
    source_language = "en"  # shared mutable session state
```

This can leak language settings across simultaneous WebSocket sessions.

#### Correct

```python
segment = Segment(
    id=segment_id,
    text_asr=text,
    confidence=confidence,
    source_language=pipeline.language_config.source_language,
    target_language=pipeline.language_config.target_language,
)
```

The language pair travels with the segment, and shared model/client services
remain stateless across sessions.
