# VisionAssist — Progress Report

**Project Title:** VisionAssist: A Smart Desktop Assistant Using Face and Gesture Recognition  
**Student:** Vansh Goel  
**Program:** BCA (Bachelor of Computer Applications)  
**Semester:** V  
**Submission Date:** October 2026

---

## 1. Executive Summary

VisionAssist is a Python desktop application that uses a laptop webcam to recognise hand gestures in real time and map them to configurable computer actions — system media controls, application launching, and a slide-navigation demo. The system uses MediaPipe's Tasks API for hand landmark detection and a custom rule-based classifier to identify five distinct gestures with explicit false-positive suppression.

This report documents what has been implemented, tested, and verified, and what is planned for future phases.

---

## 2. Objectives vs Status

| Objective | Status |
|-----------|--------|
| Real-time hand gesture recognition via webcam | ✅ **Implemented & testable** |
| Gesture-to-action mapping with hold gate | ✅ **Implemented & unit tested** |
| Configurable application/website launching | ✅ **Implemented & unit tested** |
| System media key delivery | ✅ **Implemented — pyautogui OS delivery verified** |
| Three separated modes (LAUNCH / CONTROL / PAUSED) | ✅ **Implemented & unit tested** |
| Profile system (demo, media, presentation, launch) | ✅ **Implemented & unit tested** |
| Persistent JSON configuration | ✅ **Implemented & unit tested** |
| Tkinter GUI with sidebar, progress bar, mode controls | ✅ **Implemented** |
| Always-on-top floating panel on minimize | ✅ **Implemented** |
| Native file picker in Settings dialog | ✅ **Implemented** |
| Duplicate gesture conflict detection | ✅ **Implemented** |
| Face recognition | ⬜ Planned (Phase 2) |
| Voice commands | ⬜ Planned (Phase 2) |

---

## 3. Architecture

### 3.1 Component Overview

```
main.py                     Tkinter UI, lifecycle, config loading
  │
  ├─ src/camera.py          OpenCV VideoCapture wrapper
  ├─ src/hand_detector.py   MediaPipe Tasks HandLandmarker (VIDEO mode)
  ├─ src/gesture_classifier.py  Rule-based landmark→gesture classifier
  ├─ src/action_map.py      Hold gate (8 frames), cooldown (1.5 s), demo actions
  ├─ src/profile_manager.py  Mode + profile routing authority
  │     ├─ src/media_control.py   Whitelisted pyautogui media key sender
  │     ├─ src/launcher.py        Safe app/website opener
  │     └─ src/app_config.py      JSON config schema, load/save/validate
  │
  ├─ src/floating_panel.py  Compact always-on-top overlay (shown on minimize)
  └─ src/config_editor.py   Tkinter Settings dialog with Browse button
```

### 3.2 Threading Model

- **Main thread:** Tkinter event loop only
- **Background daemon thread (`VisionAssist-Capture`):** Camera capture, MediaPipe inference, gesture dispatch
- Shared state (`_current_frame`, `_gesture_label`, `_last_action`, `_hold_progress`) is protected by `threading.Lock`
- Tkinter UI is updated via `root.after(33, ...)` polling loop (≈30 fps)

---

## 4. Gesture Recognition

### 4.1 Supported Gestures

| Gesture | Recognition Conditions |
|---------|----------------------|
| Open Palm | All 4 fingers above PIP + EXTEND_MARGIN; thumb either lateral (x > IP by margin) or upward (tip above IP on y-axis) |
| Fist | All fingers below PIP; additionally all 4 tips below their MCP knuckles |
| Thumbs Up | Thumb lateral; all 4 fingers past MCP knuckles |
| Pointing | Index only above PIP; no thumb |
| Peace | Index + middle above PIP; no thumb |
| UNKNOWN | All other poses |

### 4.2 False-Positive Reduction

- **EXTEND_MARGIN = 0.04** — tip must clear reference joint by this normalised delta
- **CURL_MCP_MARGIN = 0.02** — tip must be this far below MCP to count as "clearly curled"
- **Hold gate** — gesture must be stable for **8 consecutive frames** (~0.27 s at 30 fps)
- **MAX_UNKNOWN_SKIP = 2** — up to 2 missed detection frames are tolerated before resetting the hold counter (prevents single MediaPipe drop-outs from nullifying a held gesture)
- **Cooldown = 1.5 s** — same gesture cannot re-fire within 1.5 seconds

### 4.3 OPEN_PALM Fix (This Release)

Previous implementation: thumb check was x-axis only → when palm faces camera, thumb opens upward not sideways, causing frequent OPEN_PALM false negatives.

Fix: added `_thumb_extended_for_palm()` that ORs the x-axis check with a y-axis check (tip above IP joint). Used exclusively in the OPEN_PALM branch; all other gestures still use the strict x-axis-only check.

---

## 5. Mode and Profile System

### 5.1 Modes

| Mode | Behaviour |
|------|-----------|
| CONTROL | Gestures run the active profile's action mapping |
| LAUNCH | Gestures open registered apps/websites; profile actions disabled |
| PAUSED | All actions disabled; camera still running; map shows placeholder |

Mode buttons in the sidebar (⏸ Pause / 🚀 Launch) and the Mode menu ensure users can switch at any time. The header indicator (● ACTIVE / ● PAUSED / ● LAUNCH) reflects current mode.

### 5.2 Profiles

| Profile | Actions |
|---------|---------|
| demo | Slide navigation (Next/Prev/Pause/Select/ToggleMode). State displayed in Demo State panel. |
| media | System media keys: play/pause, next, prev, stop, mute. Sent via `pyautogui.press()`. |
| presentation | Arrow keys + F5/Escape for slideshow control. |
| launch | Gesture-to-app mapping (same as LAUNCH mode). |

Auto-profile selection checks the foreground process name using `win32gui` + `psutil`/`tasklist`.

---

## 6. Configuration System

- **File:** `data/visionassist_config.json` (auto-created on first run)
- **Schema version 1:** `registered_apps`, `profiles`, `active_profile`, `auto_profile`, `settings`
- **Validation on every load:** invalid gestures set to None, duplicate names deduplicated, missing active_profile corrected
- **Config Editor** (File → Settings): add/edit/remove apps, Browse button for native file picker, gesture conflict detection
- **Hot reload:** changes take effect immediately without restarting

---

## 7. Testing

### 7.1 Automated Tests

```
72 passed  |  0 failed  |  0.57 s
pytest 9.1.1, Python 3.11.9
```

**Media actions and launcher calls are mocked** — tests confirm routing and dispatch logic, not OS-level key delivery.

### 7.2 Live Verification

| Item | Status |
|------|--------|
| `pyautogui.press("volumemute")` → OS | ✅ Verified during development |
| Camera feed in Tkinter | ⬜ Manual test required |
| Real hand gesture detection | ⬜ Manual test required |

---

## 8. Known Limitations

1. **Windows only** — `pywin32` for active-window detection; `pyautogui` media keys tested on Windows 11
2. **Single hand** — only the first detected hand is classified
3. **No face recognition** — not implemented; planned for Phase 2
4. **No voice commands** — not implemented; planned for Phase 2
5. **Lighting-dependent** — MediaPipe hand detection degrades in poor lighting
6. **Gesture accuracy not unit-tested at real-webcam level** — synthetic landmark tests pass; real-world accuracy must be verified manually

---

## 9. Future Work

| Feature | Description |
|---------|-------------|
| Face recognition | Identify registered users; grant/deny gesture control |
| Voice commands | `speech_recognition` for selected operations |
| Custom gesture training | User-defined gestures via a training wizard |
| Cross-platform | Linux/macOS launcher + media key backends |
| Gesture recording | Log gesture history with timestamps |
