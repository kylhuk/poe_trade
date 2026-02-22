# ExileLens — Linux Item Capture Client (Clipboard + OCR)

## Goal
When you hover an item and trigger ExileLens, it extracts the item text (clipboard-first, OCR fallback) and calls Ledger API for:
- price estimate + confidence
- “sellable >= 10c” flag
- craft EV candidates (if any)

## Why clipboard-first is the default
- Highest accuracy and lowest latency.
- Avoids OCR errors and font/render issues.
- Works well on Wayland where arbitrary screen capture can be restricted.

PoE supports copying item text to clipboard via Ctrl+C and advanced copy via Ctrl+Alt+C.

## Supported modes
### Mode A — Clipboard watcher (default)
- You hover item, press PoE copy shortcut.
- ExileLens detects clipboard change that matches PoE item text format.
- Sends text to backend and shows a notification/overlay.

### Mode B — Screenshot + OCR (fallback / X11-friendly)
- Hotkey captures a configured region (tooltip area).
- Preprocess image and run OCR (Tesseract).
- Send OCR text to backend.

## Linux capture considerations
- X11: cursor-relative capture is straightforward.
- Wayland: cross-desktop region capture may require portals and can prompt the user; clipboard-first is recommended.
- Implement both, auto-select based on session type, and allow manual override.

## Client architecture
1) Trigger
- Global hotkey listener (e.g., Ctrl+Shift+Space).
- Clipboard watcher trigger (recommended).

2) Capture provider (OCR mode)
- Fixed ROI from config (bbox: x,y,w,h).
- Calibration mode to set ROI once and store it.

3) OCR pipeline
- OpenCV preprocessing (grayscale, scale-up, threshold).
- Tesseract OCR with tuned page segmentation.
- Optional confidence gate: if too low, tell user to use clipboard mode.

4) Normalizer
- Fix whitespace and common OCR artifacts.
- Optional fuzzy matching to known mod lines if you maintain a mod dictionary.

5) Backend client
- HTTP POST to `POST /v1/item/analyze`.

6) Result UI
- Desktop notification or small overlay:
  - est chaos (big)
  - confidence
  - recommended list price (fast/normal/patient)
  - top craft EV suggestion (if any)

## Backend contract
Endpoint: `POST /v1/item/analyze`

Request:
- source: "clipboard" | "ocr"
- text: string
- league, realm (optional)
- ts_client
- image_b64 (optional; debug only)

Response:
- parsed item (canonical fields)
- price: est_chaos, list_fast, list_normal, list_patient, confidence, comps_count
- craft: candidates[{plan_id, ev_chaos, cost_chaos, risk_score, short_steps}]
- flags: is_sellable, is_craft_candidate

## Implementation tasks (client)
- A1: skeleton + config + packaging
- A2: clipboard watcher + debounce + API call + notification
- A3: OCR capture with ROI calibration + OCR pipeline
- A4: X11/Wayland detection + mode defaults
- A5: history log of last N scans (optional)

## Guardrails
- Do not simulate inputs by default (no key injection).
- Do not store screenshots unless debug mode is enabled.
