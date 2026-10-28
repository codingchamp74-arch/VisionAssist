# VisionAssist — Smart Desktop Assistant Using Face and Gesture Recognition

> **BCA Final Year Project** — Hand gesture recognition system with configurable app launching, system media control, and profile-based gesture mapping.

---

## Quick Start

### Prerequisites
- Python 3.10 or 3.11
- Laptop/desktop webcam

### Install

```bash
git clone https://github.com/mrvanshgoel/VisionAssist.git
cd VisionAssist
pip install -r requirements.txt
```

### Download the MediaPipe model (required, ~7.5 MB)

```bash
python -c "
import urllib.request, os
os.makedirs('models', exist_ok=True)
urllib.request.urlretrieve(
    'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
    'models/hand_landmarker.task'
)"
```

### Run

```bash
python main.py
```

Press **Q** or close the window to quit.

---

## Architecture

```
main.py (Tkinter UI, main thread)
  └── processing thread
        ├── Camera           → raw BGR frames (OpenCV)
        ├── HandDetector     → MediaPipe Tasks HandLandmarker
        ├── GestureClassifier → rule-based landmark classifier
        └── ProfileManager   → mode routing + action dispatch
              ├── CONTROL mode → demo / media / launch actions
              ├── LAUNCH mode  → open registered apps/websites
              └── PAUSED mode  → camera runs, nothing fires
```

---

## Modes

| Mode | What happens | How to activate |
|------|-------------|-----------------|
| **CONTROL** | Gestures run the active profile's actions | Default; or click ⚙ Control button |
| **LAUNCH** | Gestures open registered apps/websites | Click 🚀 Launch button |
| **PAUSED** | All actions disabled; camera still runs | Click ⏸ Pause button |

**Modes are completely separate** — launch gestures cannot accidentally trigger media actions and vice versa.

---

## Profiles

Switch profiles via the **Profile** dropdown in the sidebar or `Profile` menu.

| Profile | Gestures → Actions |
|---------|--------------------|
| **demo** | Slide navigation (demo only, no real PC actions) |
| **media** | System media keys (play/pause, next, prev, mute) |
| **presentation** | Keyboard arrows + F5/Escape for slideshows |
| **launch** | Open apps/websites (configured via Settings) |

Auto-profile switching: if Spotify or VLC is the foreground window, the `media` profile activates automatically. PowerPoint/LibreOffice Impress activates `presentation`.

---

## Gestures

| Gesture | Recognition rule |
|---------|-----------------|
| **Open Palm** 🖐 | All 4 fingers extended past PIP + thumb either lateral (x-axis) or pointing up past IP |
| **Fist** ✊ | No fingers extended + all 4 tips below their MCP knuckles |
| **Thumbs Up** 👍 | Thumb extended + all 4 fingers clearly past MCP |
| **Pointing** ☝ | Index only extended (no thumb) |
| **Peace** ✌ | Index + middle extended (no thumb) |
| **UNKNOWN** | Anything ambiguous |

A gesture must be held **8 consecutive frames** (~0.27 s at 30 fps) before firing. The sidebar shows a green progress bar filling up as you hold.

---

## Configuration — Registered Apps

Open **File → Settings** to add apps and websites:

- **Name**: display name shown in the sidebar
- **Type**: `app` (exe) or `website` (URL)
- **Path / URL**: exe name (`notepad.exe`), full path (`C:\…\app.exe`), or `https://…`
- **Browse**: native Windows file picker for selecting executables
- **Launch Gesture**: gesture that opens this entry in Launch Mode
- Each enabled entry must have a **unique** launch gesture (conflicts are flagged)

Config is saved to `data/visionassist_config.json` and reloaded without restart.

---

## Media Controls (media profile)

| Gesture | Key sent |
|---------|----------|
| Open Palm | Play / Pause |
| Fist | Stop |
| Thumbs Up | Next Track |
| Pointing | Previous Track |
| Peace | Mute |

Keys are sent via `pyautogui.press()`. **Verified**: `pyautogui` successfully sends `volumemute` at the OS level on Windows 11. Live delivery to a running media player requires the media player to be the foreground audio sink; tested statically.

---

## Floating Panel

When the main window is **minimized**, a compact always-on-top overlay appears showing:
- Current mode and profile
- Last gesture and action
- Pause / Resume button
- Camera Off toggle
- Open Main Window button

The panel is **frameless and draggable**. Click ✕ to hide it (does not quit the app).

---

## Dependencies

```
opencv-python >= 4.8      # webcam capture + drawing
mediapipe >= 1.1          # hand landmark detection
numpy >= 1.24             # array operations
Pillow >= 9.0             # frame display in Tkinter
pyautogui >= 0.9          # system media key delivery
pywin32 >= 305            # active-window detection (Windows)
pytest >= 7.0             # test runner
```

Install all: `pip install -r requirements.txt`

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Expected: **72 passed** (as of the current commit).

Test files:
- `tests/test_gesture_classifier.py` — 25 tests (classifier rules + ambiguous poses)
- `tests/test_action_map.py` — 7 tests (hold gate, cooldown, demo actions)
- `tests/test_profile_manager.py` — 20 tests (modes, profiles, routing)
- `tests/test_app_config.py` — 20 tests (load/save/validate/launcher safety)

---

## Limitations

- **No face recognition** — planned future module; not implemented
- **No voice commands** — planned future module; not implemented
- **Windows only** for media key delivery (`pyautogui`) and active-window detection (`pywin32`)
- Gesture accuracy depends on lighting and webcam quality
- Auto-profile switching uses foreground exe name; only works if the target app is in `auto_profile` config

---

## File Structure

```
VisionAssist/
├── main.py                    # UI entry point
├── config.py                  # camera/detection tuning constants
├── requirements.txt
├── models/
│   └── hand_landmarker.task   # MediaPipe model (not in git, download separately)
├── data/
│   └── visionassist_config.json  # user config (auto-created)
├── src/
│   ├── camera.py              # OpenCV webcam wrapper
│   ├── hand_detector.py       # MediaPipe Tasks HandLandmarker
│   ├── gesture_classifier.py  # rule-based landmark → gesture
│   ├── action_map.py          # hold gate, cooldown, demo actions
│   ├── profile_manager.py     # LAUNCH/CONTROL/PAUSED routing
│   ├── app_config.py          # JSON config load/save/validate
│   ├── launcher.py            # safe app/website launcher
│   ├── media_control.py       # whitelisted pyautogui media keys
│   ├── floating_panel.py      # always-on-top overlay
│   └── config_editor.py       # Tkinter settings dialog
├── tests/
│   ├── test_gesture_classifier.py
│   ├── test_action_map.py
│   ├── test_profile_manager.py
│   └── test_app_config.py
└── docs/
    ├── PROGRESS_REPORT.md
    ├── MTE_PRESENTATION.md
    ├── DEVELOPMENT_LOG.md
    └── TEST_RESULTS.md
```
