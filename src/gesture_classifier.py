"""
gesture_classifier.py
---------------------
Classifies hand gestures from MediaPipe hand landmarks.

Supported gestures:
    OPEN_PALM   – all five fingers clearly extended
    FIST        – all fingers clearly curled
    THUMBS_UP   – thumb up, other four fingers clearly curled
    POINTING    – index finger extended, rest clearly curled
    PEACE       – index + middle extended, ring + pinky clearly curled
    UNKNOWN     – anything ambiguous or unrecognised

Design: purely functional, no side-effects, easy to unit-test.

False-positive reduction strategy
----------------------------------
* Each finger uses a *margin* threshold: the tip must be a minimum
  number of normalised units ABOVE its PIP (extended) or BELOW its
  MCP (curled) before we commit to a decision.  A finger sitting right
  on the boundary is treated as ambiguous.
* FIST additionally checks that all four finger tips are below their
  respective MCP joints (knuckles) — not just below PIP — to avoid
  a half-curled hand being misread as a fist.
* THUMBS_UP requires that ALL four non-thumb fingers are clearly
  curled (tip below MCP), not just below PIP.
* OPEN_PALM requires that ALL five fingers exceed the extension margin,
  avoiding a spread-but-not-flat palm from misclassifying.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any


# ── Landmark indices (MediaPipe convention) ─────────────────────────────────
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP,  INDEX_PIP,  INDEX_DIP,  INDEX_TIP  = 5,  6,  7,  8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9,  10, 11, 12
RING_MCP,   RING_PIP,   RING_DIP,   RING_TIP   = 13, 14, 15, 16
PINKY_MCP,  PINKY_PIP,  PINKY_DIP,  PINKY_TIP  = 17, 18, 19, 20

# ── Tuning constants ─────────────────────────────────────────────────────────
# Minimum y-delta (normalised [0,1] coords) a tip must be ABOVE its reference
# joint for the finger to count as "extended".  Increasing this reduces false
# positives but requires a more deliberate extension.
EXTEND_MARGIN: float = 0.04   # tip.y must be < ref.y - EXTEND_MARGIN

# Minimum y-delta a tip must be BELOW its MCP knuckle to be "clearly curled".
# Used for stricter fist / thumbs-up checks.
CURL_MCP_MARGIN: float = 0.02  # tip.y must be > mcp.y + CURL_MCP_MARGIN


@dataclass(frozen=True)
class GestureResult:
    gesture: str
    fingers_up: list[bool]


# ── Low-level helpers ────────────────────────────────────────────────────────

def _finger_extended(landmarks: Any, tip: int, pip: int) -> bool:
    """
    True when fingertip y is sufficiently above (smaller y = higher on screen)
    the PIP joint.  Uses EXTEND_MARGIN to require a clear extension.
    """
    return landmarks[tip].y < (landmarks[pip].y - EXTEND_MARGIN)


def _finger_curled_past_mcp(landmarks: Any, tip: int, mcp: int) -> bool:
    """
    True when fingertip y is clearly below (greater y) the MCP knuckle.
    Used to confirm a finger is genuinely folded, not just hovering near PIP.
    """
    return landmarks[tip].y > (landmarks[mcp].y + CURL_MCP_MARGIN)


def _thumb_extended(landmarks: Any, handedness: str) -> bool:
    """
    Thumb uses x-axis (it opens sideways, not upward).
    Requires EXTEND_MARGIN separation on x to reduce false positives.
    """
    tip_x = landmarks[THUMB_TIP].x
    ip_x  = landmarks[THUMB_IP].x
    margin = EXTEND_MARGIN
    if handedness.lower() == "right":
        # Right hand: thumb tip extends to the LEFT (smaller x)
        return tip_x < (ip_x - margin)
    else:
        # Left hand: thumb tip extends to the RIGHT (larger x)
        return tip_x > (ip_x + margin)


def _thumb_extended_for_palm(landmarks: Any, handedness: str) -> bool:
    """
    Relaxed thumb check used ONLY for OPEN_PALM detection.

    When a flat palm faces the camera the thumb opens slightly sideways,
    but the x-delta between THUMB_TIP and THUMB_IP can be less than
    EXTEND_MARGIN because the thumb also points somewhat upward.
    We accept the thumb as "extended" if EITHER:
      a) the standard x-axis check passes (thumb clearly lateral), OR
      b) the thumb tip is clearly above the THUMB_IP joint on the y-axis
         (tip.y < ip.y - EXTEND_MARGIN) — the thumb fans upward as part of
         a flat open palm.  Using IP (not MCP) keeps this strict enough that
         a curled thumb sitting near the palm does NOT pass.
    """
    if _thumb_extended(landmarks, handedness):
        return True
    # Y-axis fallback: thumb tip clearly above its IP joint
    return landmarks[THUMB_TIP].y < (landmarks[THUMB_IP].y - EXTEND_MARGIN)


def _thumb_curled(landmarks: Any, handedness: str) -> bool:
    """
    Thumb is curled when its tip is clearly on the SAME side as (or past)
    the IP joint.  Used for stricter FIST and THUMBS_UP inner-finger checks.
    """
    tip_x = landmarks[THUMB_TIP].x
    mcp_x = landmarks[THUMB_MCP].x
    margin = CURL_MCP_MARGIN
    if handedness.lower() == "right":
        # Curled: tip has moved to the RIGHT (past MCP)
        return tip_x > (mcp_x - margin)
    else:
        return tip_x < (mcp_x + margin)


def count_fingers(landmarks: Any, handedness: str) -> list[bool]:
    """
    Returns a 5-element list [thumb, index, middle, ring, pinky]
    where True means the finger is extended (with margin).
    """
    return [
        _thumb_extended(landmarks, handedness),
        _finger_extended(landmarks, INDEX_TIP,  INDEX_PIP),
        _finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP),
        _finger_extended(landmarks, RING_TIP,   RING_PIP),
        _finger_extended(landmarks, PINKY_TIP,  PINKY_PIP),
    ]


# ── MCP-curl checks for four non-thumb fingers ───────────────────────────────
_FINGER_TIP_MCP = [
    (INDEX_TIP,  INDEX_MCP),
    (MIDDLE_TIP, MIDDLE_MCP),
    (RING_TIP,   RING_MCP),
    (PINKY_TIP,  PINKY_MCP),
]


def _four_fingers_clearly_curled(landmarks: Any) -> bool:
    """All four non-thumb fingers have tips clearly below their MCP knuckles."""
    return all(
        _finger_curled_past_mcp(landmarks, tip, mcp)
        for tip, mcp in _FINGER_TIP_MCP
    )


# ── Main classifier ──────────────────────────────────────────────────────────

def classify(landmarks: Any, handedness: str = "right") -> GestureResult:
    """
    Classify a hand pose from MediaPipe landmarks.

    Parameters
    ----------
    landmarks  : list of NormalizedLandmark  (has .x, .y attributes)
    handedness : 'right' or 'left' (from MediaPipe classification label)

    Returns
    -------
    GestureResult with .gesture (str) and .fingers_up (list[bool])
    """
    fingers = count_fingers(landmarks, handedness)
    thumb, index, middle, ring, pinky = fingers
    extended_count = sum(fingers)

    # ── Rule-based classification (strictest rules first) ─────────────────

    # OPEN_PALM: all four fingers clearly extended AND thumb also extended
    # (uses the relaxed y-fallback thumb check so face-on palms work)
    four_fingers_extended = index and middle and ring and pinky
    thumb_for_palm = _thumb_extended_for_palm(landmarks, handedness)

    if four_fingers_extended and thumb_for_palm:
        gesture = "OPEN_PALM"

    elif extended_count == 0:
        # All five extend-checks failed.  Additionally confirm four fingers are
        # clearly folded past MCP to avoid half-open hands calling FIST.
        if _four_fingers_clearly_curled(landmarks):
            gesture = "FIST"
        else:
            gesture = "UNKNOWN"

    elif thumb and not index and not middle and not ring and not pinky:
        # Thumb extended, but require all four other fingers clearly past MCP.
        if _four_fingers_clearly_curled(landmarks):
            gesture = "THUMBS_UP"
        else:
            gesture = "UNKNOWN"

    elif index and not thumb and not middle and not ring and not pinky:
        # Index only — a relaxed middle/ring/pinky is acceptable for pointing.
        gesture = "POINTING"

    elif index and middle and not thumb and not ring and not pinky:
        # Index + middle only.
        gesture = "PEACE"

    else:
        gesture = "UNKNOWN"

    return GestureResult(gesture=gesture, fingers_up=fingers)
