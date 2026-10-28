"""
tests/test_profile_manager.py
------------------------------
Unit tests for ProfileManager, AppMode, and the action routing pipeline.
No real pyautogui calls, no real launchers, no GUI.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
from copy import deepcopy

from src.profile_manager import ProfileManager, AppMode
from src.action_map import HOLD_FRAMES


# ── Minimal config fixture ────────────────────────────────────────────────────
def _base_cfg(extra_apps=None, active_profile="demo"):
    cfg = {
        "schema_version": 1,
        "registered_apps": [
            {
                "name": "Notepad",
                "type": "app",
                "path_or_url": "notepad.exe",
                "launch_gesture": "THUMBS_UP",
                "enabled": True,
            },
        ],
        "profiles": {
            "demo": {
                "description": "Demo",
                "gesture_actions": {
                    "OPEN_PALM": "demo:Toggle Mode",
                    "FIST":      "demo:Pause / Resume",
                    "THUMBS_UP": "demo:Next Slide",
                    "POINTING":  "demo:Prev Slide",
                    "PEACE":     "demo:Select / Deselect",
                },
            },
            "media": {
                "description": "Media",
                "gesture_actions": {
                    "THUMBS_UP": "media:nexttrack",
                    "POINTING":  "media:prevtrack",
                    "OPEN_PALM": "media:playpause",
                },
            },
            "launch": {
                "description": "Launch",
                "gesture_actions": {},
            },
        },
        "active_profile": active_profile,
        "auto_profile": {
            "spotify.exe": "media",
        },
        "settings": {},
    }
    if extra_apps:
        cfg["registered_apps"].extend(extra_apps)
    return cfg


def _run(pm, gesture, state, n=HOLD_FRAMES):
    """Feed n identical frames."""
    results = [pm.handle_gesture(gesture, state) for _ in range(n)]
    return results


# ════════════════════════════════════════════════════════════════════════════
# Mode transitions
# ════════════════════════════════════════════════════════════════════════════

class TestModes:
    def test_default_mode_is_control(self):
        pm = ProfileManager(_base_cfg())
        assert pm.mode == AppMode.CONTROL

    def test_set_mode_paused(self):
        pm = ProfileManager(_base_cfg())
        pm.set_mode(AppMode.PAUSED)
        assert pm.mode == AppMode.PAUSED

    def test_set_mode_invalid_raises(self):
        pm = ProfileManager(_base_cfg())
        with pytest.raises(ValueError):
            pm.set_mode("FLYING")

    def test_toggle_pause_control_to_paused(self):
        pm = ProfileManager(_base_cfg())
        new = pm.toggle_pause()
        assert new == AppMode.PAUSED

    def test_toggle_pause_paused_to_control(self):
        pm = ProfileManager(_base_cfg())
        pm.set_mode(AppMode.PAUSED)
        new = pm.toggle_pause()
        assert new == AppMode.CONTROL

    def test_toggle_launch_mode(self):
        pm = ProfileManager(_base_cfg())
        new = pm.toggle_launch_mode()
        assert new == AppMode.LAUNCH
        new2 = pm.toggle_launch_mode()
        assert new2 == AppMode.CONTROL

    def test_paused_mode_blocks_all_gestures(self):
        pm  = ProfileManager(_base_cfg())
        pm.set_mode(AppMode.PAUSED)
        state = {}
        results = _run(pm, "THUMBS_UP", state, HOLD_FRAMES * 3)
        # Nothing should fire in PAUSED
        assert all(label is None for label, _ in results)
        assert "slide" not in state   # demo action didn't mutate state


# ════════════════════════════════════════════════════════════════════════════
# Profile management
# ════════════════════════════════════════════════════════════════════════════

class TestProfiles:
    def test_available_profiles_includes_demo(self):
        pm = ProfileManager(_base_cfg())
        assert "demo" in pm.available_profiles()

    def test_set_profile_valid(self):
        pm = ProfileManager(_base_cfg())
        ok = pm.set_profile("media")
        assert ok is True
        assert pm.profile == "media"

    def test_set_profile_invalid_returns_false(self):
        pm = ProfileManager(_base_cfg())
        ok = pm.set_profile("nonexistent")
        assert ok is False
        assert pm.profile == "demo"   # unchanged

    def test_set_profile_resets_hold_counter(self):
        """Switching profile mid-gesture resets the hold counter."""
        pm    = ProfileManager(_base_cfg())
        state = {"slide": 1, "max_slides": 6}
        # Build up partial hold (HOLD_FRAMES - 1)
        _run(pm, "THUMBS_UP", state, HOLD_FRAMES - 1)
        # Switch profile — resets controller
        pm.set_profile("media")
        # Now gesture shouldn't fire on the very next frame despite the old count
        with patch("src.media_control.execute", return_value=(True, "Next Track")):
            result = _run(pm, "THUMBS_UP", state, 1)
        assert result[0][0] is None   # first frame after reset — not fired yet


# ════════════════════════════════════════════════════════════════════════════
# Demo profile routing
# ════════════════════════════════════════════════════════════════════════════

class TestDemoProfile:
    def test_thumbs_up_next_slide(self):
        pm    = ProfileManager(_base_cfg())
        state = {"slide": 1, "max_slides": 6}
        results = _run(pm, "THUMBS_UP", state, HOLD_FRAMES)
        assert results[-1][0] == "Next Slide"
        assert state["slide"] == 2

    def test_unknown_gesture_returns_none(self):
        pm    = ProfileManager(_base_cfg())
        state = {}
        results = _run(pm, "UNKNOWN", state, HOLD_FRAMES * 2)
        assert all(label is None for label, _ in results)

    def test_gesture_not_in_profile_returns_none(self):
        """PEACE is in demo profile → fires; test a gesture absent from media profile."""
        pm    = ProfileManager(_base_cfg(), )
        pm.set_profile("media")   # media profile has no PEACE mapping
        state = {}
        results = _run(pm, "PEACE", state, HOLD_FRAMES * 2)
        assert all(label is None for label, _ in results)


# ════════════════════════════════════════════════════════════════════════════
# Media profile routing
# ════════════════════════════════════════════════════════════════════════════

class TestMediaProfile:
    def test_thumbs_up_calls_nexttrack(self):
        pm    = ProfileManager(_base_cfg())
        pm.set_profile("media")
        state = {}
        with patch("src.media_control.execute", return_value=(True, "Next Track")) as mock_exec:
            results = _run(pm, "THUMBS_UP", state, HOLD_FRAMES)
        mock_exec.assert_called_once_with("nexttrack")
        label, msg = results[-1]
        assert label == "Next Track"

    def test_media_action_failure_returns_none_label(self):
        pm    = ProfileManager(_base_cfg())
        pm.set_profile("media")
        state = {}
        with patch("src.media_control.execute", return_value=(False, "Error msg")):
            results = _run(pm, "THUMBS_UP", state, HOLD_FRAMES)
        label, _ = results[-1]
        assert label is None   # failed action → no label

    def test_media_action_does_not_fire_before_hold(self):
        pm    = ProfileManager(_base_cfg())
        pm.set_profile("media")
        state = {}
        with patch("src.media_control.execute", return_value=(True, "Next Track")) as m:
            _run(pm, "THUMBS_UP", state, HOLD_FRAMES - 1)
        m.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# Launch mode
# ════════════════════════════════════════════════════════════════════════════

class TestLaunchMode:
    def test_launch_mode_fires_registered_app(self):
        pm    = ProfileManager(_base_cfg())
        pm.set_mode(AppMode.LAUNCH)
        state = {}
        with patch("src.launcher.launch", return_value=(True, "🚀 Launched Notepad")) as mock_launch:
            results = _run(pm, "THUMBS_UP", state, HOLD_FRAMES)
        mock_launch.assert_called_once()
        label, msg = results[-1]
        assert label == "Notepad"

    def test_launch_mode_unmapped_gesture_returns_none(self):
        pm    = ProfileManager(_base_cfg())
        pm.set_mode(AppMode.LAUNCH)
        state = {}
        # PEACE has no launch_gesture in base config
        with patch("src.launcher.launch", return_value=(True, "ok")) as m:
            results = _run(pm, "PEACE", state, HOLD_FRAMES * 2)
        m.assert_not_called()
        assert all(label is None for label, _ in results)

    def test_launch_mode_does_not_fire_before_hold(self):
        pm    = ProfileManager(_base_cfg())
        pm.set_mode(AppMode.LAUNCH)
        state = {}
        with patch("src.launcher.launch", return_value=(True, "ok")) as m:
            _run(pm, "THUMBS_UP", state, HOLD_FRAMES - 1)
        m.assert_not_called()

    def test_control_mode_does_not_launch(self):
        """In CONTROL mode with demo profile, THUMBS_UP should NOT launch Notepad."""
        pm    = ProfileManager(_base_cfg())
        # pm is already in CONTROL mode
        state = {"slide": 1, "max_slides": 6}
        with patch("src.launcher.launch", return_value=(True, "ok")) as m:
            _run(pm, "THUMBS_UP", state, HOLD_FRAMES)
        m.assert_not_called()
        assert state["slide"] == 2   # demo action fired instead


# ════════════════════════════════════════════════════════════════════════════
# Config reload
# ════════════════════════════════════════════════════════════════════════════

class TestConfigReload:
    def test_reload_updates_launch_map(self):
        pm  = ProfileManager(_base_cfg())
        new_cfg = _base_cfg(extra_apps=[{
            "name": "Calc", "type": "app",
            "path_or_url": "calc.exe",
            "launch_gesture": "PEACE",
            "enabled": True,
        }])
        pm.reload_config(new_cfg)
        # Launch map should now include PEACE → Calc
        assert "PEACE" in pm._launch_map
        assert pm._launch_map["PEACE"]["name"] == "Calc"

    def test_reload_preserves_valid_profile(self):
        pm = ProfileManager(_base_cfg())
        pm.set_profile("media")
        pm.reload_config(_base_cfg())   # media still present
        assert pm.profile == "media"

    def test_reload_falls_back_if_profile_removed(self):
        pm = ProfileManager(_base_cfg())
        pm.set_profile("media")
        # New config without 'media' profile
        new_cfg = _base_cfg()
        del new_cfg["profiles"]["media"]
        new_cfg["active_profile"] = "demo"
        pm.reload_config(new_cfg)
        assert pm.profile == "demo"
