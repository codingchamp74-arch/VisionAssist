"""
action_map.py
-------------
Maps recognized gestures → demo actions.

Rules:
  • No arbitrary shell commands.
  • Actions only mutate the shared AppState dict.
  • A gesture must be held for HOLD_FRAMES consecutive frames
    before it triggers (debounce / stability requirement).
  • After triggering, COOLDOWN_FRAMES must pass before the same
    gesture can fire again (prevents repeated rapid-fire).
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Callable

# ── Tuning knobs ────────────────────────────────────────────────────────────
HOLD_FRAMES     = 8   # frames a gesture must be stable before it fires
COOLDOWN_SEC    = 1.5 # seconds before same gesture can fire again
MAX_UNKNOWN_SKIP = 2  # consecutive UNKNOWN frames tolerated without resetting hold


# ── Action definitions ───────────────────────────────────────────────────────
@dataclass
class Action:
    name: str
    description: str
    fn: Callable[[dict], None]


def _next_slide(state: dict) -> None:
    state["slide"] = min(state.get("slide", 1) + 1, state.get("max_slides", 6))
    state["status_msg"] = f"➡  Slide {state['slide']}"

def _prev_slide(state: dict) -> None:
    state["slide"] = max(state.get("slide", 1) - 1, 1)
    state["status_msg"] = f"⬅  Slide {state['slide']}"

def _toggle_mode(state: dict) -> None:
    state["demo_mode"] = not state.get("demo_mode", False)
    state["status_msg"] = "🔵 Presentation Mode" if state["demo_mode"] else "⚪ Normal Mode"

def _select_item(state: dict) -> None:
    state["selected"] = not state.get("selected", False)
    state["status_msg"] = "✅ Selected" if state["selected"] else "☐ Deselected"

def _pause_resume(state: dict) -> None:
    state["paused"] = not state.get("paused", False)
    state["status_msg"] = "⏸ Paused" if state["paused"] else "▶ Resumed"


GESTURE_ACTIONS: dict[str, Action] = {
    "OPEN_PALM": Action(
        name="Toggle Mode",
        description="Switch between Presentation / Normal mode",
        fn=_toggle_mode,
    ),
    "FIST": Action(
        name="Pause / Resume",
        description="Pause or resume the demo",
        fn=_pause_resume,
    ),
    "THUMBS_UP": Action(
        name="Next Slide",
        description="Advance to the next demo slide",
        fn=_next_slide,
    ),
    "POINTING": Action(
        name="Prev Slide",
        description="Go back to the previous demo slide",
        fn=_prev_slide,
    ),
    "PEACE": Action(
        name="Select / Deselect",
        description="Toggle selection state",
        fn=_select_item,
    ),
}


class ActionController:
    """
    Stateful controller that:
      1. Tracks how many consecutive frames a gesture has been held.
      2. Fires the mapped action once the gesture is stable.
      3. Enforces a per-gesture cooldown after firing.
    """

    def __init__(self) -> None:
        self._hold_count:    dict[str, int]   = {}
        self._last_fired:    dict[str, float] = {}
        self._prev_gesture:  str = ""
        self._unknown_streak: int = 0   # consecutive UNKNOWN frames

    def process(self, gesture: str, state: dict) -> str | None:
        """
        Call once per frame with the current gesture label.

        Returns the action name if an action was triggered this frame,
        otherwise None.
        """
        now = time.monotonic()

        # Reset hold counter when gesture changes
        if gesture != self._prev_gesture:
            self._hold_count = {}
        self._prev_gesture = gesture

        if gesture == "UNKNOWN" or gesture not in GESTURE_ACTIONS:
            return None

        # Increment hold counter
        self._hold_count[gesture] = self._hold_count.get(gesture, 0) + 1

        # Check cooldown
        last = self._last_fired.get(gesture, 0.0)
        if now - last < COOLDOWN_SEC:
            return None

        # Check stability
        if self._hold_count[gesture] < HOLD_FRAMES:
            return None

        # Fire!
        action = GESTURE_ACTIONS[gesture]
        action.fn(state)
        self._last_fired[gesture]  = now
        self._hold_count[gesture]  = 0
        return action.name

    def process_raw(self, gesture: str) -> bool:
        """
        Apply the hold + cooldown gate for *any* gesture (not just ones in
        GESTURE_ACTIONS).  Returns True exactly once per stable+cooled gesture.
        Does NOT call any action function — the caller handles that.

        Used by ProfileManager for media and launch actions.

        Tolerates up to MAX_UNKNOWN_SKIP consecutive UNKNOWN frames before
        resetting the hold counter.  This prevents a single MediaPipe detection
        miss from nullifying a held gesture.
        """
        now = time.monotonic()

        if gesture == "UNKNOWN":
            self._unknown_streak += 1
            if self._unknown_streak > MAX_UNKNOWN_SKIP:
                # Sustained UNKNOWN — user has moved hand away
                self._hold_count = {}
                self._prev_gesture = gesture
            return False

        # Non-UNKNOWN gesture: reset streak counter
        self._unknown_streak = 0

        # Reset hold counter when gesture changes
        if gesture != self._prev_gesture:
            self._hold_count = {}
        self._prev_gesture = gesture

        self._hold_count[gesture] = self._hold_count.get(gesture, 0) + 1

        last = self._last_fired.get(gesture, 0.0)
        if now - last < COOLDOWN_SEC:
            return False

        if self._hold_count[gesture] < HOLD_FRAMES:
            return False

        # Gate passed — mark fired
        self._last_fired[gesture] = now
        self._hold_count[gesture] = 0
        return True
