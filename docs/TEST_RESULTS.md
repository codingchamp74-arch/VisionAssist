# VisionAssist — Test Results

> **Last updated:** 2026-10-26  
> **Python:** 3.11.9 · **pytest:** 9.1.1 · **Platform:** Windows 11

---

## Summary

```
72 passed  |  0 failed  |  0 skipped  |  0.57 s
```

All tests are **automated unit tests** running in-process with no webcam, no real media player, and no real launcher. Actions that would hit the OS (pyautogui, launcher, webbrowser) are **mocked** using `unittest.mock.patch`.

---

## Test Suite Breakdown

### `tests/test_gesture_classifier.py` — 25 tests

Tests the rule-based landmark classifier with synthetic landmark coordinates.  
No webcam involved.

| Test | What it checks |
|------|---------------|
| `test_all_extended` | `count_fingers` returns `[True, True, True, True, True]` |
| `test_all_curled` | `count_fingers` returns `[False, False, False, False, False]` |
| `test_index_only` | `count_fingers` returns `[False, True, False, False, False]` |
| `test_open_palm` | All 5 extended → `OPEN_PALM` |
| `test_fist` | All curled + past MCP → `FIST` |
| `test_thumbs_up` | Thumb up, 4 fingers past MCP → `THUMBS_UP` |
| `test_pointing` | Index only → `POINTING` |
| `test_peace` | Index + middle → `PEACE` |
| `test_unknown_three_fingers` | 3 fingers → `UNKNOWN` |
| `test_result_has_fingers_up` | `GestureResult.fingers_up` correctly set |
| `test_finger_below_margin_counts_as_not_extended` | Just-below-margin tip → not extended |
| `test_finger_exactly_at_margin_counts_as_not_extended` | Exactly at margin → not extended |
| `test_open_palm_requires_all_five_extended` | 4 fingers + curled thumb → `UNKNOWN` (curled thumb TIP is below its IP joint on y-axis) |
| `test_fist_requires_mcp_curl` | Fingers below PIP but not MCP → `UNKNOWN` (not FIST) |
| `test_thumbs_up_requires_four_fingers_past_mcp` | Half-curl → `UNKNOWN` (not THUMBS_UP) |
| `test_pointing_with_thumb_also_extended_is_unknown` | Index + thumb → `UNKNOWN` |
| `test_four_fingers_up_no_thumb_is_unknown` | 4 fingers + curled thumb (TIP below IP) → `UNKNOWN` |
| `test_left_hand_thumbs_up` | Left-hand mirror x-axis logic → `THUMBS_UP` |

**OPEN_PALM note:** The classifier uses a dual thumb check — x-axis lateral extension OR y-axis upward extension (tip above IP joint). The test mock places a curled thumb's TIP at `y=0.75` (below `IP.y=0.6`), correctly representing a curled thumb, which the y-fallback rejects.

---

### `tests/test_action_map.py` — 7 tests

Tests `ActionController` hold gate and cooldown logic. No gestures dispatched to OS.

| Test | What it checks |
|------|---------------|
| `test_action_fires_after_hold` | Action fires on frame N = HOLD_FRAMES |
| `test_action_does_not_fire_before_hold` | Fires on frame N-1 → None |
| `test_cooldown_prevents_rapid_fire` | Same gesture within COOLDOWN_SEC → does not re-fire |
| `test_gesture_change_resets_hold` | Different gesture resets hold counter |
| `test_unknown_never_fires` | UNKNOWN gesture → never fires |
| `test_open_palm_toggles_mode` | OPEN_PALM → demo `Toggle Mode` action |
| `test_fist_pauses` | FIST → demo `Pause / Resume` action |

---

### `tests/test_profile_manager.py` — 20 tests

Tests all three modes and profile routing. pyautogui and launcher calls are **mocked**.

**Mode tests (7):**

| Test | Result |
|------|--------|
| Default mode is CONTROL | ✅ PASSED |
| `set_mode(PAUSED)` changes mode | ✅ PASSED |
| `set_mode("FLYING")` raises ValueError | ✅ PASSED |
| `toggle_pause()` CONTROL → PAUSED | ✅ PASSED |
| `toggle_pause()` PAUSED → CONTROL | ✅ PASSED |
| `toggle_launch_mode()` CONTROL ↔ LAUNCH | ✅ PASSED |
| PAUSED blocks all gesture actions | ✅ PASSED |

**Profile tests (4):**

| Test | Result |
|------|--------|
| `available_profiles()` includes "demo" | ✅ PASSED |
| `set_profile("media")` → True | ✅ PASSED |
| `set_profile("nonexistent")` → False | ✅ PASSED |
| Profile switch resets hold counter | ✅ PASSED |

**Demo profile routing (3):**

| Test | Result |
|------|--------|
| THUMBS_UP → Next Slide (slide increments) | ✅ PASSED |
| UNKNOWN → no action | ✅ PASSED |
| Gesture not in media profile → no action | ✅ PASSED |

**Media profile routing (3):** *(pyautogui mocked)*

| Test | Result |
|------|--------|
| THUMBS_UP → `media_control.execute("nexttrack")` called | ✅ PASSED |
| Failed execute → no label returned | ✅ PASSED |
| Action does not fire before hold frames | ✅ PASSED |

**Launch mode (4):** *(launcher.launch mocked)*

| Test | Result |
|------|--------|
| LAUNCH mode fires registered app | ✅ PASSED |
| Unmapped gesture → no launch | ✅ PASSED |
| Does not fire before hold | ✅ PASSED |
| CONTROL mode does NOT trigger launcher | ✅ PASSED |

**Config reload (2):**

| Test | Result |
|------|--------|
| Reload updates launch map | ✅ PASSED |
| Reload preserves valid profile | ✅ PASSED |
| Reload falls back if profile removed | ✅ PASSED |

---

### `tests/test_app_config.py` — 20 tests

Tests config load/save/validate and launcher safety. Uses temp directories — real config file never touched.

**Load (4):**

| Test | Result |
|------|--------|
| Creates default when missing | ✅ PASSED |
| Config file written on first load | ✅ PASSED |
| Roundtrip save + load preserves data | ✅ PASSED |
| Invalid JSON raises RuntimeError | ✅ PASSED |

**Validation (7):**

| Test | Result |
|------|--------|
| Duplicate names deduplicated | ✅ PASSED |
| Invalid gesture set to None | ✅ PASSED |
| Missing active_profile corrected | ✅ PASSED |
| Website needs http/https | ✅ PASSED |
| Valid URL passes | ✅ PASSED |
| Empty path fails | ✅ PASSED |
| Bare exe name allowed | ✅ PASSED |

**Helpers (4):** `get_app`, `get_app` miss, `add_app`, `add_app` replaces — all ✅ PASSED

**Launcher safety (8):**

| Test | Result |
|------|--------|
| Disabled app not launched | ✅ PASSED |
| Empty path returns error | ✅ PASSED |
| `ftp://` URL rejected | ✅ PASSED |
| Non-existent absolute path rejected | ✅ PASSED |
| `get_launch_map` excludes disabled entries | ✅ PASSED |
| Duplicate gesture: first wins | ✅ PASSED |
| No gesture set → excluded from map | ✅ PASSED |
| `_open_url` calls `webbrowser.open` (mocked) | ✅ PASSED |

---

## Features Verified Live (Webcam Required)

> ⚠️ The following features cannot be unit-tested. Manual verification is required.

| Feature | Status |
|---------|--------|
| `pyautogui.press("volumemute")` reaches OS | ✅ **Verified** — sent successfully during development |
| Camera feed displays in Tkinter at ~30 fps | ⬜ Requires webcam test |
| MediaPipe detects hand landmarks in real time | ⬜ Requires webcam test |
| OPEN_PALM recognized from real flat palm | ⬜ Requires webcam test |
| Hold-progress bar fills visibly while holding | ⬜ Requires webcam test |
| Last action persists 2 s after firing | ⬜ Requires webcam test |
| Floating panel appears on minimize | ⬜ Requires visual test |
| Browse button opens Windows file picker | ⬜ Requires UI test |
| Active-window auto-profile switch (e.g. Spotify) | ⬜ Requires live app test |

---

## Known Automated-Test Limitations

- **Gesture accuracy** at the real hand level is not tested — synthetic coordinates always produce clean results that real webcam frames may not
- **UNKNOWN-skip tolerance** in `process_raw` (2 frames) is tested via hold-gate logic but not with real detection drops
- **`media_control.execute`** is mocked — real key delivery to a media player requires manual testing
