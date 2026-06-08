# Local TTS Playback Contract

## Scenario: Browser SpeechSynthesis Playback

### 1. Scope / Trigger

- Trigger: changes to `frontend/src/audio/TtsPlayer.ts`,
  `frontend/src/store/AppStore.ts`, voice controls in
  `frontend/src/ui/ControlPanel.tsx`, or diagnostics export text for voice
  playback.
- Scope: local browser/Electron demo playback through the Web Speech API. This
  is not the future backend/provider TTS API and does not add WebSocket message
  types.

### 2. Signatures

```typescript
export interface TtsSettings {
  enabled: boolean
  volume: number
  rate: number
}

export interface TtsDiagnostics {
  isSupported: boolean
  enabled: boolean
  isSpeaking: boolean
  queueLength: number
  spokenUtterances: number
  skippedUtterances: number
  failedUtterances: number
  lastError: string | null
}
```

```typescript
class TtsPlayer {
  get settings(): TtsSettings
  get diagnostics(): TtsDiagnostics
  setEnabled(enabled: boolean): void
  setVolume(volume: number): void
  setRate(rate: number): void
  enqueueFinalTranslation(segmentId: string, text: string): void
  handleRevisedTranslation(segmentId: string, text: string): void
  reset(): void
  cancelQueue(): void
}
```

```typescript
class AppController {
  setTtsEnabled(enabled: boolean): void
  setTtsVolume(volume: number): void
  setTtsRate(rate: number): void
}
```

### 3. Contracts

- TTS is opt-in. Do not enqueue or play translated text while
  `TtsSettings.enabled` is `false`.
- Use `SpeechSynthesisUtterance` with `lang = "zh-CN"` for the local demo
  playback path.
- Queue only finalized translated subtitles after a
  `translation_token` message with `is_final: true`. Partial translation tokens
  must never be spoken.
- Normalize whitespace before queueing speech text. Empty text increments
  `skippedUtterances` instead of speaking a blank utterance.
- Clamp volume to `0..1` and rate to `0.7..1.35`. Non-finite volume or
  rate values must fall back to the default setting instead of storing `NaN`
  or `Infinity`.
- Revision handling:
  - If a revised segment is still queued, update the queued text.
  - If the revised segment is currently speaking or already spoken, do not replay
    it automatically; increment `skippedUtterances`.
  - If a revision arrives before the segment was spoken and is not queued,
    enqueue the revised text.
- `reset()` cancels any active utterance and clears queue/counters/segment
  memory while preserving the user's enabled/volume/rate settings.
- Client diagnostics export must include voice support, enablement, speaking
  state, queue length, spoken/skipped/failed counts, and last voice error.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Browser lacks `speechSynthesis` or `SpeechSynthesisUtterance` | Voice toggle is unavailable and diagnostics report `isSupported: false` |
| User enables voice in a supported browser | Future finalized translations are spoken in queue order |
| User disables voice | Active speech and queued speech are cancelled |
| Translation token is partial | Do not enqueue speech |
| Final translation text is empty | Increment skipped count and leave queue unchanged |
| Volume/rate receives `NaN` or `Infinity` | Fall back to the default value and keep diagnostics usable |
| Revision arrives for queued segment | Replace queued text with revised text |
| Revision arrives for current/already-spoken segment | Do not replay automatically; increment skipped count |
| Speech synthesis emits an error | Increment failed count, capture `lastError`, continue draining later queued items |
| User stops a translation run | Cancel active/queued speech and reset counters for the next run |

### 5. Good/Base/Bad Cases

- Good: user turns Voice on, final Chinese subtitles are spoken once in order,
  and diagnostics show queue/spoken counts.
- Base: browser has no voice support; the UI disables Voice and the rest of live
  subtitles continue working.
- Good: a queued subtitle is revised before playback starts; the revised Chinese
  text is spoken instead of the stale text.
- Bad: partial translation tokens are spoken word by word, revisions replay over
  already-spoken content, or stopping translation leaves speech running.

### 6. Tests Required

- Run `npm.cmd run test` and `npm.cmd run build` after changing TTS types,
  controls, or state wiring.
- Automated frontend tests must cover queue update-on-revision,
  skip-after-spoken revision behavior, volume/rate clamping, and non-finite
  volume/rate fallback.
- Manual browser/Electron smoke:
  - turn Voice on,
  - feed two finalized translated segments,
  - verify one utterance per final segment in order,
  - stop translation and verify playback cancels.
- Manual unsupported-path smoke when possible by mocking/removing
  `window.speechSynthesis`: verify Voice is unavailable and diagnostics export
  reports unsupported.

### 7. Wrong vs Correct

#### Wrong

```typescript
if (!message.is_final) {
  ttsPlayer.enqueueFinalTranslation(message.segment_id, message.token)
}
```

This speaks streaming partial tokens, producing repeated and stale audio.

#### Correct

```typescript
if (message.is_final) {
  subtitleStore.finalizeSubtitle(message.segment_id)
  const entry = subtitleStore.getEntry(message.segment_id)
  if (entry) {
    ttsPlayer.enqueueFinalTranslation(entry.segmentId, entry.translatedText)
  }
}
```

This waits until the subtitle store has the complete finalized translation before
queueing one utterance.
