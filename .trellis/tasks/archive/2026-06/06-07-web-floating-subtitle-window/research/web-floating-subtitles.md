# Web Floating Subtitle Options

## Constraints

* The user wants to keep `start-web.cmd` as the reliable startup path.
* Electron has been unreliable on the user's machine, so the MVP should not depend on Electron.
* A normal website cannot inject UI into unrelated websites without a browser extension.
* A normal website cannot create a native transparent OS overlay with guaranteed always-on-top behavior.
* The current app already has a reusable subtitle overlay React surface and snapshot format.

## Options

### Option A: Document Picture-in-Picture plus popup fallback

How it works:

* Main app opens a Document Picture-in-Picture window when supported by Chromium browsers.
* The PiP/popup window loads the existing subtitle overlay route.
* Main app pushes subtitle snapshots via `BroadcastChannel` and a `localStorage` fallback.

Pros:

* Works from web startup.
* Does not need Electron or a local model.
* Best browser-native approximation of an always-floating subtitle window.
* Reuses existing subtitle rendering.

Cons:

* Browser support is strongest in Chromium/Edge.
* Popup fallback is not guaranteed always-on-top.

### Option B: Browser extension injection

How it works:

* Build a Chrome/Edge extension that injects subtitle DOM into the current video page.
* Extension connects to the local backend or receives subtitles from the app.

Pros:

* Best match for "subtitles on the original page".
* Can place subtitles directly over web videos.

Cons:

* Larger new product surface.
* Requires install/permissions flow and extension packaging.
* More security and cross-origin edge cases.

### Option C: Native overlay

How it works:

* Use Electron, Tauri, or another native shell to create an always-on-top transparent subtitle layer.

Pros:

* Strongest OS-level overlay behavior.
* Can float over non-browser apps.

Cons:

* The user has explicitly had repeated Electron startup failures.
* Adds desktop runtime complexity.

## Recommended MVP

Implement Option A now. It gives a materially better user experience under the web-only constraint and leaves Options B/C as future upgrades.
