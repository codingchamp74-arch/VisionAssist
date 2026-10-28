"""
src/launcher.py
---------------
Safe application and website launcher.

Rules:
  • Only launches apps/websites that appear in registered_apps config.
  • Validates paths before launching (absolute paths must exist).
  • Bare exe names are resolved via ShellExecute so Windows PATH is respected.
  • Opens websites in the system default browser.
  • Never executes arbitrary strings — only pre-validated path_or_url values.
  • Returns a (success: bool, message: str) tuple for UI feedback.
"""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path


def launch(app_entry: dict) -> tuple[bool, str]:
    """
    Launch an app or website from a registered_apps entry.

    Parameters
    ----------
    app_entry : dict with keys: name, type, path_or_url, enabled

    Returns
    -------
    (True, message)  on success
    (False, message) on failure or if disabled
    """
    name       = app_entry.get("name", "?")
    kind       = app_entry.get("type", "app")
    path_or_url = str(app_entry.get("path_or_url", "")).strip()
    enabled    = app_entry.get("enabled", True)

    if not enabled:
        return False, f"{name} is disabled in config."

    if not path_or_url:
        return False, f"{name}: no path or URL configured."

    if kind == "website":
        return _open_url(path_or_url, name)
    else:
        return _open_app(path_or_url, name)


def _open_url(url: str, name: str) -> tuple[bool, str]:
    """Open a URL in the system default browser."""
    if not (url.lower().startswith("http://") or url.lower().startswith("https://")):
        return False, f"{name}: invalid URL '{url}' (must start with http/https)."
    try:
        webbrowser.open(url)
        return True, f"🌐 Opened {name}"
    except Exception as exc:
        return False, f"{name}: browser error — {exc}"


def _open_app(path_or_url: str, name: str) -> tuple[bool, str]:
    """
    Launch an application.

    Strategy:
      1. If path looks absolute, verify it exists.
      2. Use os.startfile on Windows (respects file associations, no shell injection).
      3. Fall back to subprocess.Popen with the bare exe name (resolved via PATH).
    """
    path = Path(path_or_url)

    # Absolute path — must exist
    if path.is_absolute():
        if not path.exists():
            return False, f"{name}: file not found — {path_or_url}"
        try:
            os.startfile(str(path))          # type: ignore[attr-defined]
            return True, f"🚀 Launched {name}"
        except Exception as exc:
            return False, f"{name}: launch failed — {exc}"

    # Bare exe name or relative path — try ShellExecute via os.startfile,
    # then fall back to Popen so it runs through the system PATH.
    try:
        os.startfile(path_or_url)            # type: ignore[attr-defined]
        return True, f"🚀 Launched {name}"
    except AttributeError:
        # os.startfile not available (non-Windows); try subprocess
        pass
    except Exception:
        pass                                 # fall through to Popen

    try:
        subprocess.Popen(
            [path_or_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True, f"🚀 Launched {name}"
    except FileNotFoundError:
        return False, f"{name}: '{path_or_url}' not found on PATH."
    except Exception as exc:
        return False, f"{name}: launch failed — {exc}"


def get_launch_map(cfg: dict) -> dict[str, dict]:
    """
    Build a gesture → app_entry map from registered_apps.
    Only includes enabled entries that have a launch_gesture set.
    If two apps share the same gesture, the first one wins.
    """
    result: dict[str, dict] = {}
    for app in cfg.get("registered_apps", []):
        gesture = app.get("launch_gesture")
        if gesture and app.get("enabled", True) and gesture not in result:
            result[gesture] = app
    return result
