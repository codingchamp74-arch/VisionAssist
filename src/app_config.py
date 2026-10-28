"""
src/app_config.py
-----------------
Persistent, user-editable configuration for VisionAssist.

Stores:
  • registered_apps   – apps/websites the user wants to launch by gesture
  • profiles          – named gesture→action profiles (media, presentation, …)
  • active_profile    – which profile is currently loaded
  • settings          – misc tweaks (always-on-top, start minimized, etc.)

File: <project_root>/data/visionassist_config.json  (auto-created)

All public functions are pure-ish: they read/write the JSON file and return
validated plain dicts, so they are easy to unit-test without a GUI.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

# ── Path constants ────────────────────────────────────────────────────────────
_ROOT       = Path(__file__).resolve().parent.parent
DATA_DIR    = _ROOT / "data"
CONFIG_FILE = DATA_DIR / "visionassist_config.json"

# ── Allowed gestures ──────────────────────────────────────────────────────────
VALID_GESTURES = {"OPEN_PALM", "FIST", "THUMBS_UP", "POINTING", "PEACE"}

# ── URL validation pattern ────────────────────────────────────────────────────
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# ── Default configuration skeleton ───────────────────────────────────────────
_DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,

    # Named apps/sites the user can launch by gesture
    # Each entry: {name, type, path_or_url, launch_gesture}
    "registered_apps": [
        {
            "name":           "Notepad",
            "type":           "app",
            "path_or_url":    "notepad.exe",
            "launch_gesture": "THUMBS_UP",
            "enabled":        True,
        },
        {
            "name":           "Google",
            "type":           "website",
            "path_or_url":    "https://www.google.com",
            "launch_gesture": "PEACE",
            "enabled":        True,
        },
    ],

    # Named gesture→action profiles
    # profile action values:
    #   "demo:<action_name>"        – existing demo actions (always safe)
    #   "media:<key>"               – system media key via pyautogui
    #   "launch:<app_name>"         – launch a registered app
    "profiles": {
        "demo": {
            "description": "Original demo actions (always available)",
            "gesture_actions": {
                "OPEN_PALM":  "demo:Toggle Mode",
                "FIST":       "demo:Pause / Resume",
                "THUMBS_UP":  "demo:Next Slide",
                "POINTING":   "demo:Prev Slide",
                "PEACE":      "demo:Select / Deselect",
            },
        },
        "media": {
            "description": "System media key controls",
            "gesture_actions": {
                "OPEN_PALM":  "media:playpause",
                "FIST":       "media:stop",
                "THUMBS_UP":  "media:nexttrack",
                "POINTING":   "media:prevtrack",
                "PEACE":      "media:volumemute",
            },
        },
        "presentation": {
            "description": "Slide presentation controls",
            "gesture_actions": {
                "OPEN_PALM":  "media:f5",           # Start slideshow
                "FIST":       "media:escape",        # End slideshow
                "THUMBS_UP":  "media:right",         # Next slide
                "POINTING":   "media:left",          # Prev slide
                "PEACE":      "media:b",             # Black screen toggle
            },
        },
        "launch": {
            "description": "Launch Mode — gestures open apps/websites",
            "gesture_actions": {},   # populated from registered_apps at runtime
        },
    },

    # Which profile is selected by default
    "active_profile": "demo",

    # Profile auto-selection: maps exe name (lowercase) → profile name
    "auto_profile": {
        "powerpnt.exe":      "presentation",
        "soffice.bin":       "presentation",
        "evince.exe":        "presentation",
        "spotify.exe":       "media",
        "vlc.exe":           "media",
        "wmplayer.exe":      "media",
    },

    "settings": {
        "always_on_top":       False,
        "start_minimized":     False,
        "camera_on_minimize":  True,   # keep camera running when minimized
        "launch_mode_gesture": None,   # reserved for future hold-to-activate
    },
}


# ── Load / Save ───────────────────────────────────────────────────────────────

def load() -> dict[str, Any]:
    """
    Load config from disk.  Creates the file with defaults if missing.
    Merges any missing top-level keys from _DEFAULT_CONFIG into the saved file
    (forward-compatibility when new keys are added).
    Returns a validated, deep-copied dict.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists():
        _write(deepcopy(_DEFAULT_CONFIG))
        return deepcopy(_DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Cannot read config file {CONFIG_FILE}: {exc}") from exc

    # Merge missing top-level keys from defaults (non-destructive)
    merged = deepcopy(_DEFAULT_CONFIG)
    merged.update(saved)

    return _validate(merged)


def save(cfg: dict[str, Any]) -> None:
    """Validate and persist the config dict to disk."""
    validated = _validate(cfg)
    _write(validated)


def _write(cfg: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)


# ── Validation ────────────────────────────────────────────────────────────────

def _validate(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Light validation.  Raises ValueError on fatal problems.
    Non-fatal issues are silently corrected (bad launch_gesture → None).
    """
    # registered_apps
    apps = cfg.get("registered_apps", [])
    seen_names: set[str] = set()
    valid_apps = []
    for app in apps:
        name = str(app.get("name", "")).strip()
        if not name or name in seen_names:
            continue                               # skip unnamed / duplicate
        seen_names.add(name)
        kind = app.get("type", "app")
        if kind not in ("app", "website"):
            kind = "app"
        pou = str(app.get("path_or_url", "")).strip()
        lg = app.get("launch_gesture")
        if lg not in VALID_GESTURES:
            lg = None
        valid_apps.append({
            "name":           name,
            "type":           kind,
            "path_or_url":    pou,
            "launch_gesture": lg,
            "enabled":        bool(app.get("enabled", True)),
        })
    cfg["registered_apps"] = valid_apps

    # active_profile must exist
    profiles = cfg.get("profiles", {})
    if cfg.get("active_profile") not in profiles:
        cfg["active_profile"] = next(iter(profiles), "demo")

    return cfg


# ── Convenience accessors ─────────────────────────────────────────────────────

def get_profile(cfg: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Return a single profile dict or None."""
    return cfg.get("profiles", {}).get(name)


def list_profiles(cfg: dict[str, Any]) -> list[str]:
    """Names of all defined profiles."""
    return list(cfg.get("profiles", {}).keys())


def get_app(cfg: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Return a registered app by exact name, or None."""
    for app in cfg.get("registered_apps", []):
        if app["name"] == name:
            return app
    return None


def add_app(cfg: dict[str, Any], name: str, kind: str,
            path_or_url: str, launch_gesture: str | None = None) -> dict[str, Any]:
    """
    Add or update a registered app entry.
    Returns the updated cfg (caller must call save() to persist).
    """
    apps = cfg.setdefault("registered_apps", [])
    # Remove existing entry with same name
    cfg["registered_apps"] = [a for a in apps if a["name"] != name]
    cfg["registered_apps"].append({
        "name":           name,
        "type":           kind,
        "path_or_url":    path_or_url,
        "launch_gesture": launch_gesture if launch_gesture in VALID_GESTURES else None,
        "enabled":        True,
    })
    return cfg


def validate_app_entry(kind: str, path_or_url: str) -> str | None:
    """
    Validate an app/website entry.
    Returns an error string, or None if valid.
    """
    if not path_or_url.strip():
        return "Path or URL cannot be empty."
    if kind == "website":
        if not _URL_RE.match(path_or_url):
            return "Website URL must start with http:// or https://"
        return None
    # kind == "app"
    # Allow bare exe names (resolved via PATH) or absolute paths
    path = Path(path_or_url)
    if path.is_absolute() and not path.exists():
        return f"Executable not found: {path_or_url}"
    return None
