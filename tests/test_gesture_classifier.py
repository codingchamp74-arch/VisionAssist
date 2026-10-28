"""
tests/test_gesture_classifier.py
---------------------------------
Unit tests for gesture_classifier.py.
Run with:  python -m pytest tests/ -v
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock
from src.gesture_classifier import (
    classify, count_fingers,
    EXTEND_MARGIN, CURL_MCP_MARGIN,
    INDEX_TIP, INDEX_PIP, INDEX_MCP,
    MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP,
    RING_TIP, RING_PIP, RING_MCP,
    PINKY_TIP, PINKY_PIP, PINKY_MCP,
    THUMB_TIP, THUMB_IP, THUMB_MCP,
)


def _make_landmark(x: float, y: float, z: float = 0.0):
    """Build a mock landmark object."""
    lm = MagicMock()
    lm.x = x
    lm.y = y
    lm.z = z
    return lm


def _make_hand(finger_states: list[bool], handedness: str = "right"):
    """
    Build a fake 21-landmark list that encodes specific finger states
    with large, unambiguous margins (delta >> EXTEND_MARGIN).

    Layout (simplified):
        Index 0  = WRIST (y=0.9)
        Thumb TIP (4) vs IP (3)  → use x-axis trick
        Other fingers TIP vs PIP / MCP → use y-axis
    """
    lms = [_make_landmark(0.5, 0.5) for _ in range(21)]

    # WRIST at bottom
    lms[0] = _make_landmark(0.5, 0.9)

    # Thumb: use x-axis for 'right' hand (large delta = 0.25)
    if finger_states[0]:
        lms[THUMB_MCP] = _make_landmark(0.5,  0.7)
        lms[THUMB_IP]  = _make_landmark(0.5,  0.6)
        lms[THUMB_TIP] = _make_landmark(0.25, 0.5)   # extended: clearly left of IP
    else:
        lms[THUMB_MCP] = _make_landmark(0.5,  0.7)
        lms[THUMB_IP]  = _make_landmark(0.55, 0.6)
        lms[THUMB_TIP] = _make_landmark(0.6,  0.75)  # curled: right of IP AND below IP.y

    # Helper: set a non-thumb finger with clear states
    def _set_finger(tip_idx, pip_idx, mcp_idx, extended: bool):
        lms[mcp_idx] = _make_landmark(0.5, 0.6)   # MCP at y=0.6
        lms[pip_idx] = _make_landmark(0.5, 0.5)   # PIP at y=0.5
        if extended:
            # Tip clearly above PIP: delta = 0.3 >> EXTEND_MARGIN
            lms[tip_idx] = _make_landmark(0.5, 0.2)
        else:
            # Tip clearly below MCP: delta = 0.2 >> CURL_MCP_MARGIN
            lms[tip_idx] = _make_landmark(0.5, 0.8)

    _set_finger(INDEX_TIP,  INDEX_PIP,  INDEX_MCP,  finger_states[1])
    _set_finger(MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP, finger_states[2])
    _set_finger(RING_TIP,   RING_PIP,   RING_MCP,   finger_states[3])
    _set_finger(PINKY_TIP,  PINKY_PIP,  PINKY_MCP,  finger_states[4])

    return lms


def _make_ambiguous_finger(tip_idx, pip_idx, mcp_idx, lms, delta: float):
    """
    Place a finger tip just `delta` units above its PIP — near the margin
    boundary.  MCP placed slightly below PIP so curl check might fail too.
    """
    lms[mcp_idx] = _make_landmark(0.5, 0.65)
    lms[pip_idx] = _make_landmark(0.5, 0.50)
    # tip.y = pip.y - delta  (positive delta → tip above pip)
    lms[tip_idx] = _make_landmark(0.5, 0.50 - delta)
    return lms


# ════════════════════════════════════════════════════════════════════════════
# Existing tests (kept for regression)
# ════════════════════════════════════════════════════════════════════════════

class TestCountFingers:
    def test_all_extended(self):
        lms = _make_hand([True, True, True, True, True])
        fingers = count_fingers(lms, "right")
        assert fingers == [True, True, True, True, True]

    def test_all_curled(self):
        lms = _make_hand([False, False, False, False, False])
        fingers = count_fingers(lms, "right")
        assert fingers == [False, False, False, False, False]

    def test_index_only(self):
        lms = _make_hand([False, True, False, False, False])
        fingers = count_fingers(lms, "right")
        assert fingers[1] is True
        assert fingers[2] is False
        assert fingers[3] is False
        assert fingers[4] is False


class TestClassify:
    def test_open_palm(self):
        lms = _make_hand([True, True, True, True, True])
        result = classify(lms, "right")
        assert result.gesture == "OPEN_PALM"

    def test_fist(self):
        lms = _make_hand([False, False, False, False, False])
        result = classify(lms, "right")
        assert result.gesture == "FIST"

    def test_thumbs_up(self):
        lms = _make_hand([True, False, False, False, False])
        result = classify(lms, "right")
        assert result.gesture == "THUMBS_UP"

    def test_pointing(self):
        lms = _make_hand([False, True, False, False, False])
        result = classify(lms, "right")
        assert result.gesture == "POINTING"

    def test_peace(self):
        lms = _make_hand([False, True, True, False, False])
        result = classify(lms, "right")
        assert result.gesture == "PEACE"

    def test_unknown_three_fingers(self):
        lms = _make_hand([False, True, True, True, False])
        result = classify(lms, "right")
        assert result.gesture == "UNKNOWN"

    def test_result_has_fingers_up(self):
        lms = _make_hand([True, True, True, True, True])
        result = classify(lms, "right")
        assert len(result.fingers_up) == 5
        assert all(result.fingers_up)


# ════════════════════════════════════════════════════════════════════════════
# New: ambiguous-pose tests — should return UNKNOWN, not a false positive
# ════════════════════════════════════════════════════════════════════════════

class TestAmbiguousPoses:

    def test_finger_below_margin_counts_as_not_extended(self):
        """
        A finger tip just 50 % of EXTEND_MARGIN above its PIP should NOT
        count as extended.
        """
        lms = _make_hand([False, False, False, False, False])
        # Move index tip to be only half-margin above PIP  → still not extended
        half_margin = EXTEND_MARGIN * 0.5
        lms = _make_ambiguous_finger(INDEX_TIP, INDEX_PIP, INDEX_MCP, lms, half_margin)
        fingers = count_fingers(lms, "right")
        assert fingers[1] is False, "Sub-margin extension should not count as extended"

    def test_finger_exactly_at_margin_counts_as_not_extended(self):
        """
        Tip exactly at PIP.y - EXTEND_MARGIN is NOT extended (requires strictly less than).
        """
        lms = _make_hand([False, False, False, False, False])
        # delta = EXTEND_MARGIN exactly: tip.y == pip.y - EXTEND_MARGIN
        # condition: tip.y < pip.y - EXTEND_MARGIN → False when equal
        lms = _make_ambiguous_finger(INDEX_TIP, INDEX_PIP, INDEX_MCP, lms, EXTEND_MARGIN)
        fingers = count_fingers(lms, "right")
        assert fingers[1] is False, "Exactly at margin boundary should not count as extended"

    def test_open_palm_requires_all_five_extended(self):
        """
        Four fingers extended but pinky borderline (sub-margin) → UNKNOWN not OPEN_PALM.
        """
        lms = _make_hand([True, True, True, True, True])
        # Collapse pinky to sub-margin extension
        half_margin = EXTEND_MARGIN * 0.5
        lms = _make_ambiguous_finger(PINKY_TIP, PINKY_PIP, PINKY_MCP, lms, half_margin)
        result = classify(lms, "right")
        assert result.gesture != "OPEN_PALM", (
            "Four clear fingers + one sub-margin finger should not classify as OPEN_PALM"
        )

    def test_fist_requires_mcp_curl(self):
        """
        All tips below PIP (no finger passes extend check) but NOT below MCP
        (tips floating mid-palm) → UNKNOWN not FIST.
        """
        lms = [_make_landmark(0.5, 0.5) for _ in range(21)]
        lms[0] = _make_landmark(0.5, 0.9)   # wrist
        # Thumb: curled on x-axis
        lms[THUMB_MCP] = _make_landmark(0.5,  0.7)
        lms[THUMB_IP]  = _make_landmark(0.55, 0.6)
        lms[THUMB_TIP] = _make_landmark(0.6,  0.5)
        # Four fingers: tip is between MCP and PIP (not extended, but not past MCP either)
        for tip_i, pip_i, mcp_i in [
            (INDEX_TIP,  INDEX_PIP,  INDEX_MCP),
            (MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP),
            (RING_TIP,   RING_PIP,   RING_MCP),
            (PINKY_TIP,  PINKY_PIP,  PINKY_MCP),
        ]:
            lms[mcp_i] = _make_landmark(0.5, 0.55)  # MCP at y=0.55
            lms[pip_i] = _make_landmark(0.5, 0.50)  # PIP at y=0.50
            # tip just below PIP but above MCP: y = 0.52 → not extended, but NOT past MCP
            lms[tip_i] = _make_landmark(0.5, 0.52)
        result = classify(lms, "right")
        assert result.gesture == "UNKNOWN", (
            "Tips above MCP should not classify as FIST"
        )

    def test_thumbs_up_requires_four_fingers_past_mcp(self):
        """
        Thumb extended, but fingers only barely below PIP (not past MCP) → UNKNOWN.
        """
        lms = _make_hand([True, False, False, False, False])
        # Override the four fingers so they are just below PIP but NOT past MCP
        for tip_i, pip_i, mcp_i in [
            (INDEX_TIP,  INDEX_PIP,  INDEX_MCP),
            (MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP),
            (RING_TIP,   RING_PIP,   RING_MCP),
            (PINKY_TIP,  PINKY_PIP,  PINKY_MCP),
        ]:
            lms[mcp_i] = _make_landmark(0.5, 0.55)
            lms[pip_i] = _make_landmark(0.5, 0.50)
            # tip at y=0.52: below PIP (so not extended) but above MCP (y=0.55)
            lms[tip_i] = _make_landmark(0.5, 0.52)
        result = classify(lms, "right")
        assert result.gesture == "UNKNOWN", (
            "Thumb up with fingers not past MCP should not classify as THUMBS_UP"
        )

    def test_pointing_with_thumb_also_extended_is_unknown(self):
        """
        Index AND thumb extended is not a supported gesture → UNKNOWN.
        """
        lms = _make_hand([True, True, False, False, False])
        result = classify(lms, "right")
        assert result.gesture == "UNKNOWN", (
            "Index + thumb both extended should be UNKNOWN, not POINTING"
        )

    def test_four_fingers_up_no_thumb_is_unknown(self):
        """
        All four fingers extended, thumb curled — doesn't match any defined gesture.
        """
        lms = _make_hand([False, True, True, True, True])
        result = classify(lms, "right")
        assert result.gesture == "UNKNOWN"

    def test_left_hand_thumbs_up(self):
        """Thumb handedness flip — left hand thumbs-up still classifies correctly."""
        lms = _make_hand([True, False, False, False, False], handedness="left")
        # For left hand, thumb extends to the RIGHT (larger x).
        # _make_hand sets thumb TIP at x=0.25 (left of IP) for right hand.
        # Override for left hand: tip to the right of IP.
        lms[THUMB_MCP] = _make_landmark(0.5,  0.7)
        lms[THUMB_IP]  = _make_landmark(0.45, 0.6)
        lms[THUMB_TIP] = _make_landmark(0.75, 0.5)   # clearly right of IP + margin
        result = classify(lms, "left")
        assert result.gesture == "THUMBS_UP"
