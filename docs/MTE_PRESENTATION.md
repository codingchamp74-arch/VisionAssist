# VisionAssist — MTE Presentation Guide

**Project:** VisionAssist: A Smart Desktop Assistant Using Face and Gesture Recognition  
**Student:** Vansh Goel | BCA Semester V  
**Date:** October 2026

---

## Slide 1 — Title

**VisionAssist**  
*A Smart Desktop Assistant Using Face and Gesture Recognition*

BCA Final Year Project · Semester V  
Vansh Goel

---

## Slide 2 — Problem Statement

**Mouse and keyboard are the only way to interact with a PC — but not always practical:**
- Presenter advancing slides while standing at a distance
- Accessibility needs — reduced hand mobility
- Hands-free media control while cooking, exercising
- Future: contactless interaction in public kiosks

**Goal:** Control a Windows PC using only webcam hand gestures — no additional hardware required.

---

## Slide 3 — Project Overview

**VisionAssist** is a Python desktop application that:
1. Reads webcam frames in real time
2. Detects hand landmarks using MediaPipe
3. Classifies gesture from 21 landmark points using a rule-based algorithm
4. Maps stable gestures to configurable PC actions

**Current Phase:** Gesture recognition + media control + app launching  
**Future Phases:** Face recognition (user identification) + voice commands

---

## Slide 4 — Technology Stack

| Layer | Technology |
|-------|-----------|
| **Language** | Python 3.11 |
| **Hand Detection** | MediaPipe Tasks HandLandmarker (Tasks API 1.1.x) |
| **Camera** | OpenCV (`cv2.VideoCapture`) |
| **GUI** | Tkinter (standard library) |
| **System Keys** | pyautogui (`press()`) |
| **Active Window** | pywin32 (`win32gui`) |
| **Tests** | pytest 9.1.1 |

No internet connection required at runtime. MediaPipe model is bundled (`models/hand_landmarker.task`, ~7.5 MB).

---

## Slide 5 — System Architecture

```
Webcam (OpenCV)
      ↓ BGR frame
MediaPipe HandLandmarker
      ↓ 21 landmarks (x, y per joint)
GestureClassifier (rule-based)
      ↓ gesture label + confidence state
ProfileManager
      ├─ LAUNCH mode  → launcher.py → os.startfile / webbrowser
      ├─ CONTROL mode → media_control.py → pyautogui.press()
      └─ PAUSED mode  → nothing fires
```

**Threading:** Camera + inference on background daemon thread. UI on main Tkinter thread. Shared state protected by `threading.Lock`.

---

## Slide 6 — Gesture Recognition (How It Works)

**MediaPipe** returns 21 landmark points per hand:

```
  TIP  ← landmark 8 (Index fingertip)
   |
  DIP
   |
  PIP  ← reference joint
   |
  MCP  ← knuckle
   |
 WRIST
```

**Rule:** A finger is "extended" if `TIP.y < PIP.y - 0.04` (tip is **above** PIP by at least 4% of frame height)

**Gestures classified:**

| Gesture | Rule |
|---------|------|
| OPEN_PALM 🖐 | All 4 fingers extended + thumb extended (lateral or upward) |
| FIST ✊ | No fingers extended + all tips below MCP knuckle |
| THUMBS_UP 👍 | Thumb lateral + all 4 fingers past MCP |
| POINTING ☝ | Index only extended |
| PEACE ✌ | Index + middle extended |
| UNKNOWN | Everything else |

---

## Slide 7 — False Positive Prevention

**Problem:** A half-open hand shouldn't fire FIST. A thumb brush shouldn't fire THUMBS_UP.

**Solutions implemented:**
1. **EXTEND_MARGIN (0.04)** — tip must clear reference joint by minimum delta
2. **CURL_MCP_MARGIN (0.02)** — tip must be clearly below knuckle for "curled"
3. **Hold gate (8 frames)** — gesture must be stable for ~0.27 s before firing
4. **UNKNOWN tolerance (2 frames)** — 1-2 missed MediaPipe detections don't reset hold
5. **Cooldown (1.5 s)** — same action can't fire twice within 1.5 seconds

**Visual feedback:** Green bar in sidebar fills left-to-right as gesture is held.

---

## Slide 8 — Mode & Profile System

### Three Modes

```
CONTROL (⚙)   → gestures run active profile's actions (media/demo)
LAUNCH  (🚀)   → gestures open configured apps/websites
PAUSED  (⏸)   → nothing fires, camera still runs
```

### Profiles

| Profile | Gesture → Action |
|---------|-----------------|
| **demo** | THUMBS_UP → Next Slide, POINTING → Prev Slide, … |
| **media** | THUMBS_UP → Next Track, OPEN_PALM → Play/Pause, POINTING → Prev Track |
| **presentation** | THUMBS_UP → → key, POINTING → ← key, OPEN_PALM → F5 |

**Why separate modes?** A THUMBS_UP in a media session cannot accidentally launch an app and vice versa.

---

## Slide 9 — Configuration & Settings

**File → Settings** opens the configuration editor:

- Add apps (exe name or full path) and websites (URL)
- **Browse button** — native Windows file picker (no typing paths manually)
- Assign a unique launch gesture per entry
- **Conflict detection** — warns if two enabled apps share the same gesture
- Config saved to `data/visionassist_config.json`; reloaded without restart

**Auto-profile switching:** If Spotify is the foreground window → media profile activates automatically.

---

## Slide 10 — Demo Walkthrough

> ⚠️ **Note:** The following is the intended live demo sequence. Gesture accuracy depends on lighting and webcam quality.

**Step 1 — Start the app**
```bash
python main.py
```
Camera feed appears in left panel. Mode: CONTROL. Profile: demo.

**Step 2 — Demo mode (slide navigation)**
- Hold 🖐 Open Palm → Toggle presentation mode
- Hold 👍 Thumbs Up → Next slide (Demo State panel updates)
- Hold ☝ Pointing → Previous slide

**Step 3 — Switch to media profile**
- Click the Profile dropdown → select "media"
- Gesture map updates in sidebar

**Step 4 — Media control**
- Hold 👍 Thumbs Up → Next Track (system key sent)
- Hold 🖐 Open Palm → Play/Pause

**Step 5 — Minimize**
- Minimize main window → floating always-on-top overlay appears
- Shows current mode, last gesture, Pause/Camera-Off buttons

**Step 6 — Settings**
- Click File → Settings
- Click Browse → select an .exe
- Assign a gesture → Save
- Switch to 🚀 Launch mode → hold the gesture → app launches

---

## Slide 11 — Test Results

```
72 tests  |  72 passed  |  0 failed  |  0.57 s
```

| Suite | Tests | Focus |
|-------|-------|-------|
| `test_gesture_classifier` | 25 | Landmark rules, ambiguous poses, margins |
| `test_action_map` | 7 | Hold gate, cooldown, demo actions |
| `test_profile_manager` | 20 | Mode transitions, profile routing (mocked) |
| `test_app_config` | 20 | Config I/O, validation, launcher safety |

**Media + launcher calls are mocked** — tests verify routing logic, not OS-level delivery. Real key delivery verified separately with `pyautogui`.

---

## Slide 12 — Limitations & Honest Assessment

| Limitation | Details |
|-----------|---------|
| Windows only | `pywin32` for active-window detection; media keys tested on Windows 11 |
| Single hand | Only the first detected hand is classified |
| Lighting-dependent | MediaPipe degrades in poor lighting or heavy shadow |
| No face recognition | Planned Phase 2 — not implemented |
| No voice commands | Planned Phase 2 — not implemented |
| Gesture accuracy untested at webcam level | Synthetic tests pass; real-world accuracy requires manual verification |

---

## Slide 13 — Future Roadmap

| Phase | Feature | Technology |
|-------|---------|-----------|
| Phase 2A | Face recognition | `face_recognition` / OpenCV LBPH |
| Phase 2B | Voice commands | `SpeechRecognition` + `pyaudio` |
| Phase 3 | Custom gesture training | Landmark feature extraction + lightweight classifier |
| Phase 3 | Cross-platform support | Linux/macOS media key backends |
| Phase 3 | Gesture history logging | SQLite + timeline viewer |

---

## Slide 14 — Key Takeaways

✅ **Working** real-time gesture recognition on commodity webcam  
✅ **Configurable** — users define their own apps, gestures, and profiles  
✅ **Safe** — whitelist-only launcher, gesture conflict detection, no shell injection  
✅ **Tested** — 72 automated tests with honest mock boundaries  
✅ **Honest** — limitations and untested features clearly documented  

**The core pipeline (camera → MediaPipe → classifier → action) is solid.  
Everything else builds on top of it.**

---

## Appendix — Running the Project

```bash
# 1. Clone
git clone https://github.com/mrvanshgoel/VisionAssist.git
cd VisionAssist

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download MediaPipe model
python -c "
import urllib.request, os; os.makedirs('models', exist_ok=True)
urllib.request.urlretrieve(
  'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
  'models/hand_landmarker.task')"

# 4. Run tests
python -m pytest tests/ -v

# 5. Launch app
python main.py
```

**Requirements:** Python 3.10+, Windows 10/11, webcam
