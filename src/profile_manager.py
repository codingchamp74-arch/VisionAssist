"""
src/profile_manager.py
----------------------
Manages the currently active gesture profile and the application mode.

Modes (separate from profiles):
  LAUNCH   – gestures trigger app/website launches from registered_apps
  CONTROL  – gestures run the active profile's action mapping
  PAUSED   – all gesture actions disabled; camera may still run

Profile action routing:
  "demo:<name>"    → call the matching demo Action.fn from action_map.GESTURE_ACTIONS
  "media:<key>"    → call media_control.execute(key)
  "launch:<name>"  → call launcher.launch(app_entry)

The ProfileManager is the single source of truth for what gesture
does what right now. main.py asks it; it decides and executes.
"""

from __future__ import annotations

from typing import Any
from src import app_config, launcher, media_control
from src.action_map import GESTURE_ACTIONS, ActionController


class AppMode:
    LAUNCH  = "LAUNCH"
    CONTROL = "CONTROL"
    PAUSED  = "PAUSED"


class ProfileManager:
    """
    Ties together: config, mode, profile selection, and action dispatch.

    Usage
    -----
        pm = ProfileManager(cfg)
        pm.set_mode(AppMode.CONTROL)
        pm.set_profile("media")
        result = pm.handle_gesture("THUMBS_UP", app_state)
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._cfg         = cfg
        self._mode        = AppMode.CONTROL
        self._profile     = cfg.get("active_profile", "demo")
        self._controller  = ActionController()
        # Build launch map from registered_apps
        self._launch_map  = launcher.get_launch_map(cfg)

    # ── Public properties ──────────────────────────────────────────────────
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def profile(self) -> str:
        return self._profile

    @property
    def cfg(self) -> dict[str, Any]:
        return self._cfg

    # ── Mode control ───────────────────────────────────────────────────────
    def set_mode(self, mode: str) -> None:
        if mode not in (AppMode.LAUNCH, AppMode.CONTROL, AppMode.PAUSED):
            raise ValueError(f"Unknown mode: {mode}")
        self._mode = mode

    def toggle_pause(self) -> str:
        """Toggle between PAUSED and CONTROL.  Returns new mode."""
        if self._mode == AppMode.PAUSED:
            self._mode = AppMode.CONTROL
        else:
            self._mode = AppMode.PAUSED
        return self._mode

    def toggle_launch_mode(self) -> str:
        """Toggle between LAUNCH and CONTROL.  Returns new mode."""
        if self._mode == AppMode.LAUNCH:
            self._mode = AppMode.CONTROL
        else:
            self._mode = AppMode.LAUNCH
        return self._mode

    # ── Profile control ────────────────────────────────────────────────────
    def set_profile(self, name: str) -> bool:
        """Set active profile by name.  Returns False if not found."""
        if name not in self._cfg.get("profiles", {}):
            return False
        self._profile = name
        self._controller = ActionController()   # reset hold/cooldown state
        return True

    def available_profiles(self) -> list[str]:
        return list(self._cfg.get("profiles", {}).keys())

    def auto_select_profile(self) -> str | None:
        """
        Detect the active Windows app and auto-select a matching profile.
        Returns the profile name if switched, None otherwise.
        """
        exe = media_control.detect_active_exe()
        if not exe:
            return None
        auto_map = self._cfg.get("auto_profile", {})
        target = auto_map.get(exe)
        if target and target != self._profile:
            if self.set_profile(target):
                return target
        return None

    def reload_config(self, cfg: dict[str, Any]) -> None:
        """Hot-reload a new config dict (e.g. after user edits)."""
        self._cfg        = cfg
        self._launch_map = launcher.get_launch_map(cfg)
        # Keep current mode/profile if they still exist; else fall back
        if self._profile not in cfg.get("profiles", {}):
            self._profile = cfg.get("active_profile", "demo")

    # ── Gesture dispatch ───────────────────────────────────────────────────
    def handle_gesture(
        self,
        gesture: str,
        app_state: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        """
        Process one frame's gesture through the current mode and profile.

        Returns
        -------
        (action_label, feedback_msg)
          action_label : short name of what fired (or None)
          feedback_msg : string for the status bar (or None)
        """
        # ── PAUSED: nothing fires ──────────────────────────────────────────
        if self._mode == AppMode.PAUSED:
            return None, None

        # ── LAUNCH mode: gestures launch apps ─────────────────────────────
        if self._mode == AppMode.LAUNCH:
            return self._handle_launch(gesture, app_state)

        # ── CONTROL mode: gestures run profile actions ─────────────────────
        return self._handle_control(gesture, app_state)

    def _handle_launch(
        self, gesture: str, app_state: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        """Fire a launch action if gesture matches a registered app."""
        app_entry = self._launch_map.get(gesture)
        if app_entry is None:
            return None, None

        # Reuse ActionController for hold + cooldown (prevents misfire)
        fired = self._controller.process_raw(gesture)
        if not fired:
            return None, None

        ok, msg = launcher.launch(app_entry)
        app_state["status_msg"] = msg
        return app_entry["name"], msg

    def _handle_control(
        self, gesture: str, app_state: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        """Route gesture through the active profile's action mapping."""
        profile_def = self._cfg.get("profiles", {}).get(self._profile, {})
        gesture_actions = profile_def.get("gesture_actions", {})

        action_str = gesture_actions.get(gesture)
        if not action_str:
            # Gesture not mapped in this profile
            self._controller.process(gesture, app_state)  # still updates hold counter
            return None, None

        kind, _, value = action_str.partition(":")

        # ── demo:<name> ────────────────────────────────────────────────────
        if kind == "demo":
            # Delegate fully to ActionController (preserves existing hold/cooldown)
            fired = self._controller.process(gesture, app_state)
            return fired, app_state.get("status_msg") if fired else None

        # ── media:<key> and launch:<name> need their own hold gate ─────────
        fired = self._controller.process_raw(gesture)
        if not fired:
            return None, None

        if kind == "media":
            ok, label = media_control.execute(value)
            msg = f"🎵 {label}" if ok else f"⚠ {label}"
            app_state["status_msg"] = msg
            return label if ok else None, msg

        if kind == "launch":
            app_entry = next(
                (a for a in self._cfg.get("registered_apps", []) if a["name"] == value),
                None,
            )
            if app_entry is None:
                msg = f"⚠ App '{value}' not found in config"
                app_state["status_msg"] = msg
                return None, msg
            ok, msg = launcher.launch(app_entry)
            app_state["status_msg"] = msg
            return value if ok else None, msg

        return None, None

    # ── Describe current mapping ───────────────────────────────────────────
    def current_mapping_summary(self) -> dict[str, str]:
        """
        Returns {gesture: human_label} for the current mode+profile,
        suitable for display in the sidebar.
        """
        if self._mode == AppMode.LAUNCH:
            return {
                gesture: app["name"]
                for gesture, app in self._launch_map.items()
            }
        if self._mode == AppMode.PAUSED:
            return {}

        profile_def = self._cfg.get("profiles", {}).get(self._profile, {})
        gesture_actions = profile_def.get("gesture_actions", {})
        summary = {}
        for gesture, action_str in gesture_actions.items():
            kind, _, value = action_str.partition(":")
            if kind == "demo":
                da = GESTURE_ACTIONS.get(gesture)
                summary[gesture] = da.name if da else value
            elif kind == "media":
                summary[gesture] = media_control.get_label(value)
            elif kind == "launch":
                summary[gesture] = f"Launch: {value}"
            else:
                summary[gesture] = action_str
        return summary
