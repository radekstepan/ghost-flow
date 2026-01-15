# Ghost Flow – Agent Guide

This document is for AI coding agents working in this repository. It explains how the app is structured and how to make safe updates.

## Architecture Overview

- **Python backend (PyQt6):** Owns app lifecycle, audio recording, AI calls, and the overlay state.
- **Web UI (QWebEngine + React):** Renders the settings window and overlay using local HTML + React (Babel in browser).
- **Bridge (QWebChannel):** Connects Python ↔ JS through a `pyBridge` object.

Key flow:
1. `GhostApp` emits overlay updates (`listening → processing → done → idle`).
2. `UIBridge` emits `overlay_update` to JS.
3. `app.html` listens and renders overlay.

## Key Files

- [src/main.py](src/main.py): App lifecycle, recording, AI worker, overlay state updates.
- [src/gui/bridge.py](src/gui/bridge.py): QWebChannel bridge (signals + slots). Holds latest overlay state.
- [src/gui/web_window.py](src/gui/web_window.py): QWebEngine window setup, loads `app.html`.
- [src/ui/app.html](src/ui/app.html): React UI + fallback UI + bridge connection logic.
- [src/core/recorder.py](src/core/recorder.py): Audio capture.
- [src/core/ai.py](src/core/ai.py): OpenAI transcription + refinement.
- [src/config.py](src/config.py): Config storage (~/.ghostflow_config.json).

## Bridge Contract (Python ↔ JS)

Signals emitted from Python (`UIBridge`):
- `overlay_update(str)`: JSON with `{ stage, text }`.
- `settings_loaded(str)`: JSON config payload for settings UI.

Slots called from JS:
- `request_settings()` → emits `settings_loaded`.
- `save_settings(json_str)` → updates `current_config`.
- `simulate_recording()` → triggers a 3s simulated cycle.
- `get_overlay_state()` → returns latest overlay JSON.

**Important:** Always keep the JS and Python sides in sync when changing signal names or payloads.

## Overlay State Machine

Stages:
- `idle` → hidden
- `listening`
- `processing`
- `done`

Python source of truth: `GhostApp._update_overlay()`.

JS rendering:
- React overlay (default)
- Fallback overlay (no React or when CDN scripts fail)

JS also polls `get_overlay_state()` every 250ms to guarantee updates even if signals are missed.

## Updating the UI

- Main UI lives in [src/ui/app.html](src/ui/app.html).
- React is loaded from CDN (`unpkg.com`).
- Tailwind is loaded from CDN.
- Babel compiles JSX at runtime.

### Fallback UI
A non-React fallback is embedded in `app.html` and kicks in if React doesn’t boot. Keep this minimal and resilient.

### When changing the UI
- Avoid breaking `id` values used by fallback UI (e.g., `gf-overlay-pill`).
- Keep `window.__GF_BOOTED__` and `gf:booted` event intact.
- If you change overlay payload shape, update both React and fallback rendering.

## Debugging UI Updates

If overlay doesn’t update:
1. Confirm Python emits overlay state (`DEBUG: Bridge emitting overlay_update...`).
2. Check for JS log: `JS [Global]: overlay_update`.
3. Verify `get_overlay_state()` returns the latest payload.
4. Confirm the overlay window uses `#overlay` fragment (set in `WebWindow`).

## Running the App

Use the script:
- [scripts/run_ghost_flow.sh](scripts/run_ghost_flow.sh)

This sets up venv, installs deps, and runs `src/main.py`.

## Common Pitfalls

- **No API key:** Transcription fails with `No OpenAI API Key set.`
- **macOS permissions:** Accessibility/Input Monitoring required for global hotkey.
- **Web assets blocked:** CDN issues will force fallback UI.
- **Signal timing:** UI may connect after the first signal; rely on `get_overlay_state()`.

## Development Notes

- Keep changes small and focused.
- Prefer modifying [src/ui/app.html](src/ui/app.html) for UI changes.
- If you add new settings, update both:
  - `current_config` in [src/config.py](src/config.py)
  - `UIBridge.request_settings()` and `save_settings()` in [src/gui/bridge.py](src/gui/bridge.py)
  - React settings state in [src/ui/app.html](src/ui/app.html)
