# Subtitle Display Surface Options

## Current implementation

- The React app creates `SubtitleRenderer` inside `frontend/src/App.tsx`.
- `SubtitleRenderer` appends a fixed-position `#subtitle-overlay` to the app page and renders subtitle entries near the bottom center of that page.
- Audio capture uses browser display capture in `frontend/src/audio/AudioCapture.ts`, but it does not render the captured source video in the app.
- Electron currently opens one ordinary `BrowserWindow` in `frontend/electron/main.cjs`; it does not create a transparent always-on-top subtitle overlay window.

## Feasible approaches

### Approach A: In-app video preview with subtitles

How it works:

- When the user starts capture, show the selected screen/window/tab stream in a video element inside the AI Interpreter page.
- Keep subtitles over that preview.
- The user watches the content inside the app instead of the original tab/window.

Pros:

- Fits the current browser architecture.
- Can be built without a browser extension or OS-level overlay.
- Easier to test with Playwright and frontend unit tests.

Cons:

- The user must watch a mirrored capture in the app.
- Some protected video or conferencing surfaces may not render or may have capture restrictions.
- It does not overlay subtitles on the original app.

### Approach B: Electron transparent always-on-top overlay

How it works:

- Keep the existing app window as the control panel.
- Add a second transparent, frameless, always-on-top Electron window that only renders subtitles.
- The overlay floats over the user's screen like a subtitle/translation utility.

Pros:

- Closest to the user's expected desktop translation experience.
- Works across websites and apps without modifying the original page.
- Reuses the existing backend/WebSocket/subtitle pipeline with a new subtitle surface.

Cons:

- Desktop-only and primarily Windows-focused for this project.
- Needs careful click-through, positioning, multi-monitor, and DPI behavior.
- Browser-only users still need a fallback.

### Approach C: Browser extension injection

How it works:

- Build a Chrome/Edge extension that injects subtitle DOM into supported pages.
- The extension connects to the local backend and renders subtitles in the original webpage.

Pros:

- Best fit for original-webpage subtitles.
- Good for YouTube, course sites, and web conferences when page permissions allow it.

Cons:

- New extension packaging, permissions, content-script lifecycle, and store/distribution surface.
- Does not help native desktop apps.
- Site CSP, iframes, shadow DOM, and protected players can complicate injection.

## Recommendation

For this repo's next MVP, implement Approach B first: Electron transparent always-on-top subtitle overlay. It gives the intended product feel with the least disruption to the existing translation pipeline and avoids the extension distribution problem.

Keep Approach A as a browser fallback later. Approach C should be a separate larger task after the desktop overlay is stable.
