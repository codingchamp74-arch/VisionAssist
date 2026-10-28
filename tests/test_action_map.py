"""
tests/test_action_map.py
------------------------
Unit tests for ActionController (debounce + cooldown logic).
"""

import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch
from src.action_map import ActionController, HOLD_FRAMES, COOLDOWN_SEC


def _run_frames(controller, gesture, state, n=HOLD_FRAMES):
    """Feed `n` identical gesture frames into the controller."""
    results = [controller.process(gesture, state) for _ in range(n)]
    return results


class TestActionController:

    def test_action_fires_after_hold(self):
        ctrl  = ActionController()
        state = {"slide": 1, "max_slides": 6}
        results = _run_frames(ctrl, "THUMBS_UP", state, HOLD_FRAMES)
        # Last frame in HOLD_FRAMES should trigger
        assert results[-1] == "Next Slide"
        assert state["slide"] == 2

    def test_action_does_not_fire_before_hold(self):
        ctrl  = ActionController()
        state = {"slide": 1, "max_slides": 6}
        # One frame short of threshold
        results = _run_frames(ctrl, "THUMBS_UP", state, HOLD_FRAMES - 1)
        assert all(r is None for r in results), "Should not fire before hold threshold"
        assert state["slide"] == 1

    def test_cooldown_prevents_rapid_fire(self):
        ctrl  = ActionController()
        state = {"slide": 1, "max_slides": 6}
        # Trigger once
        _run_frames(ctrl, "THUMBS_UP", state, HOLD_FRAMES)
        initial_slide = state["slide"]
        # Immediately try again (cooldown not elapsed)
        _run_frames(ctrl, "THUMBS_UP", state, HOLD_FRAMES * 2)
        assert state["slide"] == initial_slide, "Should not fire again during cooldown"

    def test_gesture_change_resets_hold(self):
        ctrl  = ActionController()
        state = {}
        # Build up HOLD_FRAMES-1 for THUMBS_UP
        _run_frames(ctrl, "THUMBS_UP", state, HOLD_FRAMES - 1)
        # Switch gesture — resets counter
        ctrl.process("FIST", state)
        # Back to THUMBS_UP — should need full HOLD_FRAMES again
        results = _run_frames(ctrl, "THUMBS_UP", state, HOLD_FRAMES - 1)
        assert all(r is None for r in results)

    def test_unknown_never_fires(self):
        ctrl  = ActionController()
        state = {}
        results = _run_frames(ctrl, "UNKNOWN", state, HOLD_FRAMES * 3)
        assert all(r is None for r in results)

    def test_open_palm_toggles_mode(self):
        ctrl  = ActionController()
        state = {"demo_mode": False}
        _run_frames(ctrl, "OPEN_PALM", state, HOLD_FRAMES)
        assert state["demo_mode"] is True

    def test_fist_pauses(self):
        ctrl  = ActionController()
        state = {"paused": False}
        _run_frames(ctrl, "FIST", state, HOLD_FRAMES)
        assert state["paused"] is True
