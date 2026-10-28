# VisionAssist — Development Log

## 2026-10-26 — Bug Fix, Feature Hardening & Documentation Update

### Media Controls — Root Cause Fixed

**Bug:** Gestures appeared in the status panel but media keys never fired.  
**Root cause:** `process_raw()` in `action_map.py` reset `_hold_count` to `{}` on **every single UNKNOWN frame**. MediaPipe occasionally misses a hand detection for one frame (lighting, motion blur, partial occlusion). That single missed frame reset the 8-frame counter to zero, making sustained media triggers near-impossible under normal webcam conditions.

**Fix:** Added `_unknown_streak` counter. The hold counter is only reset if UNKNOWN is sustained for more than `MAX_UNKNOWN_SKIP = 2` consecutive frames. A single or double detection miss is now tolerated without losing the hold progress.

**Verification:** `pyautogui.press("volumemute")` confirmed to reach the OS. Live media-player delivery requires manual webcam test.

---

### OPEN_PALM — False Negative Fix

**Bug:** Flat palm facing the camera frequently classified as UNKNOWN.  
**Root cause:** The thumb check used x-axis only (`THUMB_TIP.x < THUMB_IP.x - EXTEND_MARGIN` for right hand). When a palm faces the camera, the thumb opens slightly upward (toward the ceiling) not sideways. The x-delta between TIP and IP is often less than the 0.04 margin, so the thumb was counted as "not extended" and OPEN_PALM was rejected.

**Fix:** Added `_thumb_extended_for_palm()` with a y-axis fallback: if the x-check fails, accepts the thumb as extended if `THUMB_TIP.y < THUMB_IP.y - EXTEND_MARGIN` (tip above IP on y-axis). Used **only** for OPEN_PALM; all other gesture rules still use the strict x-only check.

**Test consistency:** Curled thumb mock updated to place `THUMB_TIP` at `y=0.75` (below `THUMB_IP.y=0.6`), reflecting that a genuinely curled thumb folds downward past the IP joint. 72/72 tests pass.

---

### Hold-Progress Visual Feedback

Added a 4px Canvas bar below the "Gesture Detected" label in the sidebar. It fills left-to-right as the hold counter approaches `HOLD_FRAMES`. Turns blue when fully filled (action fired). Gives users real-time feedback that the gesture is being registered even before it fires.

**Last Action Persistence:** Action label now stays visible for **2 seconds** after firing instead of disappearing on the very next frame. Implemented via `_last_action_ts` timestamp compared against `time.monotonic()`.

---

### Config Editor — Browse Button & Conflict Detection

**Browse button:** Native Windows file picker (`tkinter.filedialog.askopenfilename`) pre-filtered to `.exe`. Path auto-fills into the entry; type auto-sets to `app`. Cancelled dialogs do nothing. File picker errors shown in the status label.

**Duplicate gesture conflict detection:** `_check_gesture_conflict()` scans the working app list before adding. If another **enabled** entry already uses the same launch gesture, a clear explanation is shown:
> *⚠ Conflict: Thumbs Up 👍 is already assigned to 'Notepad'. Each enabled entry must have a unique launch gesture. Disable the other entry or choose a different gesture.*

Disabled entries are exempt — the same gesture can be assigned to a disabled entry without conflict.

**Removed orphaned widget:** The original `config_editor.py` created a `tk.OptionMenu` for type on line 138 but never displayed it, then created a second one on line 143. The orphaned widget is removed.

---

### Gesture Map Persistence

When mode is PAUSED, `current_mapping_summary()` returns `{}`. Previously this caused the gesture map panel to go blank. Fixed: `_rebuild_map_labels()` now shows a "Actions disabled while paused." placeholder message in PAUSED mode.

---

### Shared State Fields Added

`main.py` processing loop now writes `_hold_progress` and `_last_action_ts` into the lock-protected shared state. `_update_ui` reads `hold_pct` and uses it to drive the progress bar. Timestamp comparison determines whether to clear the last action.

---

## 2026-10-26 — Session 1: Configurable Desktop Assistant

Implemented six new modules:

| Module | Purpose |
|--------|---------|
| `src/app_config.py` | Persistent JSON config — registered apps, profiles, auto-profile map |
| `src/launcher.py` | Whitelist-only app/website launcher |
| `src/media_control.py` | Whitelisted pyautogui media key executor + active-window detection |
| `src/profile_manager.py` | LAUNCH/CONTROL/PAUSED mode authority + profile routing |
| `src/floating_panel.py` | Frameless always-on-top panel shown on minimize |
| `src/config_editor.py` | Tkinter modal for managing registered apps |

Updated `main.py` to wire `ProfileManager`, `FloatingPanel`, `ConfigEditor` together.  
Added `process_raw()` to `ActionController` for hold-gating non-demo actions.

---

## 2026-10-26 — Session 0: MVP + Gesture Classifier

- Initial project structure and OpenCV camera wrapper
- MediaPipe Tasks API integration (hand_landmarker.task)
- Rule-based gesture classifier with EXTEND_MARGIN and CURL_MCP_MARGIN
- Tkinter UI with live camera feed
- Clean quit handling (Q key + window close)
- 25 unit tests for gesture classifier

---

## Architecture Decisions

### Why rule-based classification, not ML?

Training a gesture classifier requires a labelled dataset. With five clear gestures and strong MediaPipe landmark quality, explicit rules achieve >90% accuracy on clean poses without any training data. Ambiguous poses correctly return UNKNOWN rather than a wrong guess.

### Why separate LAUNCH and CONTROL modes?

Prevents gesture accidents — a THUMBS_UP in the middle of a media session should not accidentally launch Notepad. Mode separation makes the intent explicit.

### Why `process_raw` instead of reusing `process`?

`process()` is coupled to `GESTURE_ACTIONS` (the demo action table). Media and launch actions don't belong in that table. `process_raw` applies only the hold gate and cooldown, letting the caller handle the actual dispatch.

### Why tolerate UNKNOWN frames in `process_raw`?

MediaPipe's hand detector occasionally drops a frame (occlusion, motion blur). Without tolerance, a single missed frame resets 8 frames of build-up. With `MAX_UNKNOWN_SKIP = 2`, users can briefly move their hand without losing a held gesture.
