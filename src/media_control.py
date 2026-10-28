"""
src/media_control.py
--------------------
System media-key and keyboard actions via pyautogui.

Whitelist approach: only a fixed set of named actions are allowed.
No arbitrary key strings can be passed in from config without going
through the ALLOWED_ACTIONS map first.

Also provides active-window detection via win32gui so the profile
manager can auto-select a profile based on what's running.
"""

from __future__ import annotations

import importlib
import subprocess
from typing import Callable

# ── Lazy imports (graceful if pyautogui / win32 not installed) ────────────────
def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        return None

_pag     = None   # pyautogui, loaded on first use
_win32gui = None  # win32gui, loaded on first use
_win32process = None


def _get_pag():
    global _pag
    if _pag is None:
        _pag = _try_import("pyautogui")
        if _pag:
            _pag.FAILSAFE = False   # disable corner-move abort
    return _pag


def _get_win32():
    global _win32gui, _win32process
    if _win32gui is None:
        _win32gui   = _try_import("win32gui")
        _win32process = _try_import("win32process")
    return _win32gui, _win32process


# ── Allowed media / keyboard actions ─────────────────────────────────────────
# Maps config action key → (label, callable)
# Callables receive no arguments (all side-effects).

def _press(key: str) -> Callable[[], None]:
    """Return a zero-arg lambda that presses `key` via pyautogui."""
    def _fn() -> None:
        pag = _get_pag()
        if pag is None:
            raise RuntimeError("pyautogui not installed — media keys unavailable.")
        pag.press(key)
    return _fn


def _hotkey(*keys: str) -> Callable[[], None]:
    def _fn() -> None:
        pag = _get_pag()
        if pag is None:
            raise RuntimeError("pyautogui not installed — media keys unavailable.")
        pag.hotkey(*keys)
    return _fn


# Maps the string from config → (human label, action callable)
ALLOWED_ACTIONS: dict[str, tuple[str, Callable]] = {
    # Media transport
    "playpause":  ("Play / Pause",     _press("playpause")),
    "stop":       ("Stop",             _press("stop")),
    "nexttrack":  ("Next Track",       _press("nexttrack")),
    "prevtrack":  ("Previous Track",   _press("prevtrack")),
    "volumemute": ("Mute",             _press("volumemute")),
    "volumeup":   ("Volume Up",        _press("volumeup")),
    "volumedown": ("Volume Down",      _press("volumedown")),
    # Navigation keys (presentation)
    "right":      ("→ Next Slide",     _press("right")),
    "left":       ("← Prev Slide",     _press("left")),
    "f5":         ("Start Slideshow",  _press("f5")),
    "escape":     ("End / Escape",     _press("escape")),
    "b":          ("Black Screen",     _press("b")),
    "w":          ("White Screen",     _press("w")),
    # General
    "space":      ("Space",            _press("space")),
    "enter":      ("Enter",            _press("enter")),
}


def execute(action_key: str) -> tuple[bool, str]:
    """
    Execute a whitelisted media/key action by its config key.

    Returns (True, label) on success, (False, error_msg) on failure.
    """
    entry = ALLOWED_ACTIONS.get(action_key)
    if entry is None:
        return False, f"Unknown media action: '{action_key}'"
    label, fn = entry
    try:
        fn()
        return True, label
    except Exception as exc:
        return False, f"Media action '{action_key}' failed: {exc}"


def get_label(action_key: str) -> str:
    """Human-readable label for a media action key, or the key itself."""
    entry = ALLOWED_ACTIONS.get(action_key)
    return entry[0] if entry else action_key


# ── Active window detection ───────────────────────────────────────────────────

def get_active_exe() -> str | None:
    """
    Return the lowercase exe name of the currently active window,
    e.g. 'powerpnt.exe', 'spotify.exe'.
    Returns None if win32gui is unavailable or an error occurs.
    """
    win32gui, win32process = _get_win32()
    if win32gui is None or win32process is None:
        return None
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        import psutil  # optional; graceful fallback
        proc = psutil.Process(pid)
        return proc.name().lower()
    except Exception:
        return None


def get_active_exe_fallback() -> str | None:
    """
    Fallback exe detection using tasklist when psutil isn't available.
    Only works on Windows. Returns None on failure.
    """
    win32gui, win32process = _get_win32()
    if win32gui is None or win32process is None:
        return None
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        # Query tasklist for the exe name
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=1,
        )
        line = result.stdout.strip()
        if line and line.startswith('"'):
            parts = line.split('","')
            if parts:
                return parts[0].strip('"').lower()
        return None
    except Exception:
        return None


def detect_active_exe() -> str | None:
    """Try psutil first, then tasklist fallback."""
    try:
        result = get_active_exe()
        if result:
            return result
    except Exception:
        pass
    return get_active_exe_fallback()
