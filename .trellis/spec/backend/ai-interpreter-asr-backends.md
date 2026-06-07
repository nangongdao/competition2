# AI Interpreter ASR Backends Contract

## Scenario: Remote ASR Default With Optional Local Whisper

### 1. Scope / Trigger

- Trigger: changes to ASR backend selection, ASR environment keys, launcher ASR
  profiles, `backend/core/config.py`, or `backend/services/asr_service.py`.
- Scope: live audio-to-text before translation. This contract covers startup
  behavior, remote OpenAI-compatible transcription, local Whisper fallback, and
  the frontend/launcher profile value that selects the backend.

### 2. Signatures

Backend settings:

```text
ASR_ENGINE=openai|remote|whisper|deepgram|azure
ASR_OPENAI_MODEL=whisper-1
ASR_OPENAI_API_KEY=<optional override>
ASR_OPENAI_BASE_URL=<optional override>
WHISPER_MODEL=small
WHISPER_DEVICE=cpu|cuda
WHISPER_COMPUTE_TYPE=int8|float16
OPENAI_API_KEY=<fallback for remote ASR>
OPENAI_BASE_URL=<fallback for remote ASR>
```

ASR service:

```python
async def ASRService.initialize() -> None: ...
async def ASRService.process_chunk(audio_bytes: bytes) -> int: ...
async def ASRService.redecode_audio(audio_bytes: bytes) -> ASRDecodeResult | None: ...
def ASRService.create_session() -> ASRService: ...
def float32_audio_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes: ...
```

Launcher profile:

```text
AI_INTERPRETER_DESKTOP_ASR_PROFILE=remote|light|cpu|gpu|env
python tools/desktop_launcher.py --asr-profile remote|light|cpu|gpu|env
```

### 3. Contracts

- Local web/desktop startup defaults to `remote`. The launcher must set
  `ASR_ENGINE=openai` for this profile and must not inject `WHISPER_MODEL`,
  `WHISPER_DEVICE`, or `WHISPER_COMPUTE_TYPE`.
- `ASR_ENGINE=openai` and `ASR_ENGINE=remote` initialize an `AsyncOpenAI`
  client and do not import, download, or load Faster-Whisper models during
  startup.
- Remote ASR uses `ASR_OPENAI_API_KEY` / `ASR_OPENAI_BASE_URL` when set, then
  falls back to `OPENAI_API_KEY` / `OPENAI_BASE_URL`.
- Remote ASR receives frontend float32 PCM chunks, buffers the same 2-second
  window as Whisper, converts the window to mono 16-bit WAV, and sends it to
  the OpenAI-compatible audio transcription API using `ASR_OPENAI_MODEL`.
- `SourceLanguage="auto"` omits the remote transcription `language` parameter;
  explicit supported source languages pass their ISO code.
- Local profiles `light`, `cpu`, and `gpu` must set `ASR_ENGINE=whisper` and
  the matching Whisper model/device/compute values. These profiles may load or
  download model files on first use.
- Profile `env` must preserve process and dotenv ASR settings exactly.
- `ASRService.create_session()` must share the initialized remote client or
  Whisper model while keeping stream buffers and callbacks isolated per session.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Default launcher startup | Backend starts with remote ASR and no Whisper load log |
| Remote provider supports audio transcriptions | `asr_final` emits transcribed text and confidence `0.0` |
| Remote provider rejects audio transcription | Log decode error, keep the buffered audio for retry, and emit no segment |
| Remote response has blank text | Emit no segment for that window |
| Missing remote API key at startup | Surface ASR initialization failure through backend startup health failure |
| User selects local `light`/`cpu`/`gpu` | Backend initializes Whisper with the selected local profile |
| User selects `env` | Launcher does not inject ASR variables |
| Source language is `auto` | Do not send a remote transcription language parameter |

### 5. Good/Base/Bad Cases

- Good: double-click `start-web.cmd`; launcher chooses `remote`, backend health
  passes, and logs show OpenAI-compatible ASR initialization without Whisper
  model loading.
- Base: user sets `AI_INTERPRETER_DESKTOP_ASR_PROFILE=light`; launcher starts
  local Whisper CPU/int8, accepting the possible first-use model load.
- Good: user sets `ASR_OPENAI_MODEL=gpt-4o-mini-transcribe`; remote ASR uses it
  while translation continues to use `NMT_MODEL`.
- Bad: default startup injects `WHISPER_MODEL=small` and downloads HuggingFace
  files on a machine configured for remote API use.
- Bad: frontend accepts `remote` but Electron/backend local settings reject it,
  causing the saved setting to fall back to a local profile.

### 6. Tests Required

- Backend unit tests:
  - remote ASR buffers float32 PCM and calls the fake OpenAI transcription
    client with a WAV file payload
  - `auto` source language omits the remote transcription language parameter
  - `float32_audio_to_wav_bytes()` writes a WAV container
- Launcher unit tests:
  - `remote` sets `ASR_ENGINE=openai` and does not inject Whisper variables
  - local profiles set `ASR_ENGINE=whisper`
  - `env` injects no ASR variables
  - no profile resolves to `remote`
- Frontend/Electron tests:
  - settings sanitizers accept `remote` and default to it
  - settings UI offers `remote`
- Smoke test:
  - start backend with `ASR_ENGINE=openai` and dummy API key; `/api/v1/health`
    returns HTTP 200 and logs contain no Whisper model load.

### 7. Wrong vs Correct

#### Wrong

```python
DEFAULT_DESKTOP_ASR_PROFILE = "light"
set_default_env_value(env, "WHISPER_MODEL", "small")
```

This makes the normal local startup path download or load a local Whisper model.

#### Correct

```python
DEFAULT_DESKTOP_ASR_PROFILE = "remote"
set_default_env_value(env, "ASR_ENGINE", "openai")
```

This keeps the default local startup remote-first while preserving explicit
local Whisper profiles for users who choose them.
