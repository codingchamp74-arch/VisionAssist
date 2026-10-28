"""
src/floating_panel.py
---------------------
Compact always-on-top floating status panel for VisionAssist.

Shows:
  • Current mode (CONTROL / LAUNCH / PAUSED)
  • Active profile name
  • Last recognised gesture + mapped action
  • Pause / Resume button
  • Camera off toggle
  • Open main window button

Implemented as a Tkinter Toplevel so it lives alongside the main window.
The panel can be dragged by its title bar area.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, TYPE_CHECKING

# Colour palette (shared with main.py constants — duplicated here to keep
# floating_panel.py importable standalone)
BG_DARK    = "#0d1117"
BG_PANEL   = "#161b22"
BG_CARD    = "#21262d"
ACCENT     = "#58a6ff"
ACCENT2    = "#3fb950"
TEXT_WHITE = "#f0f6fc"
TEXT_MUTED = "#8b949e"
TEXT_WARN  = "#f85149"
BORDER     = "#30363d"
BTN_BG     = "#21262d"


class FloatingPanel:
    """
    Small always-on-top status window.

    Parameters
    ----------
    parent          : tk root or Toplevel
    on_pause_toggle : callback(current_mode: str) → None
    on_camera_toggle: callback(camera_on: bool) → None
    on_show_main    : callback() → None  (deiconify main window)
    on_profile_change: callback(profile_name: str) → None
    profiles        : list[str]  (available profile names)
    """

    def __init__(
        self,
        parent: tk.Misc,
        on_pause_toggle:  Callable[[str], None],
        on_camera_toggle: Callable[[bool], None],
        on_show_main:     Callable[[], None],
        on_profile_change: Callable[[str], None],
        profiles: list[str],
    ) -> None:
        self._on_pause_toggle   = on_pause_toggle
        self._on_camera_toggle  = on_camera_toggle
        self._on_show_main      = on_show_main
        self._on_profile_change = on_profile_change
        self._camera_on         = True

        self._win = tk.Toplevel(parent)
        self._win.title("VisionAssist")
        self._win.configure(bg=BG_DARK)
        self._win.attributes("-topmost", True)
        self._win.resizable(False, False)
        self._win.overrideredirect(True)   # frameless window

        # Position: top-right corner of screen
        sw = self._win.winfo_screenwidth()
        self._win.geometry(f"260x280+{sw - 280}+30")

        self._build(profiles)
        self._enable_drag()

    # ── Build UI ──────────────────────────────────────────────────────────
    def _build(self, profiles: list[str]) -> None:
        try:
            f_bold  = tkfont.Font(family="Segoe UI", size=10, weight="bold")
            f_body  = tkfont.Font(family="Segoe UI", size=9)
            f_tiny  = tkfont.Font(family="Segoe UI", size=8)
            f_big   = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        except Exception:
            f_bold = f_body = f_tiny = f_big = tkfont.Font(size=9)

        # ── Drag handle / title bar ───────────────────────────────────────
        title_bar = tk.Frame(self._win, bg=BG_PANEL, pady=4)
        title_bar.pack(fill=tk.X)
        title_bar.bind("<ButtonPress-1>",   self._on_drag_start)
        title_bar.bind("<B1-Motion>",       self._on_drag_move)

        tk.Label(
            title_bar, text="👁 VisionAssist",
            bg=BG_PANEL, fg=ACCENT, font=f_bold,
        ).pack(side=tk.LEFT, padx=8)

        tk.Button(
            title_bar, text="✕", bg=BG_PANEL, fg=TEXT_MUTED,
            font=f_tiny, bd=0, padx=4,
            command=self._win.withdraw,    # hide but don't destroy
            activebackground=BG_PANEL, activeforeground=TEXT_WARN,
        ).pack(side=tk.RIGHT, padx=4)

        tk.Frame(self._win, bg=BORDER, height=1).pack(fill=tk.X)

        # ── Status area ───────────────────────────────────────────────────
        status_frame = tk.Frame(self._win, bg=BG_DARK, padx=10, pady=6)
        status_frame.pack(fill=tk.X)

        # Mode
        row_mode = tk.Frame(status_frame, bg=BG_DARK)
        row_mode.pack(fill=tk.X, pady=1)
        tk.Label(row_mode, text="Mode:", bg=BG_DARK, fg=TEXT_MUTED,
                 font=f_tiny, width=9, anchor="w").pack(side=tk.LEFT)
        self._lbl_mode = tk.Label(row_mode, text="CONTROL", bg=BG_DARK,
                                   fg=ACCENT2, font=f_bold, anchor="w")
        self._lbl_mode.pack(side=tk.LEFT)

        # Profile
        row_prof = tk.Frame(status_frame, bg=BG_DARK)
        row_prof.pack(fill=tk.X, pady=1)
        tk.Label(row_prof, text="Profile:", bg=BG_DARK, fg=TEXT_MUTED,
                 font=f_tiny, width=9, anchor="w").pack(side=tk.LEFT)
        self._lbl_profile = tk.Label(row_prof, text="demo", bg=BG_DARK,
                                      fg=ACCENT, font=f_bold, anchor="w")
        self._lbl_profile.pack(side=tk.LEFT)

        # Gesture
        row_gest = tk.Frame(status_frame, bg=BG_DARK)
        row_gest.pack(fill=tk.X, pady=1)
        tk.Label(row_gest, text="Gesture:", bg=BG_DARK, fg=TEXT_MUTED,
                 font=f_tiny, width=9, anchor="w").pack(side=tk.LEFT)
        self._lbl_gesture = tk.Label(row_gest, text="—", bg=BG_DARK,
                                      fg=TEXT_WHITE, font=f_body, anchor="w")
        self._lbl_gesture.pack(side=tk.LEFT)

        # Action
        row_act = tk.Frame(status_frame, bg=BG_DARK)
        row_act.pack(fill=tk.X, pady=1)
        tk.Label(row_act, text="Action:", bg=BG_DARK, fg=TEXT_MUTED,
                 font=f_tiny, width=9, anchor="w").pack(side=tk.LEFT)
        self._lbl_action = tk.Label(row_act, text="—", bg=BG_DARK,
                                     fg=ACCENT2, font=f_body, anchor="w",
                                     wraplength=150)
        self._lbl_action.pack(side=tk.LEFT)

        tk.Frame(self._win, bg=BORDER, height=1).pack(fill=tk.X, padx=6)

        # ── Profile selector ──────────────────────────────────────────────
        prof_frame = tk.Frame(self._win, bg=BG_DARK, padx=10, pady=4)
        prof_frame.pack(fill=tk.X)
        tk.Label(prof_frame, text="Profile:", bg=BG_DARK, fg=TEXT_MUTED,
                 font=f_tiny).pack(side=tk.LEFT)
        self._profile_var = tk.StringVar(value=profiles[0] if profiles else "demo")
        prof_menu = tk.OptionMenu(
            prof_frame, self._profile_var, *profiles,
            command=lambda p: self._on_profile_change(p),
        )
        prof_menu.config(
            bg=BTN_BG, fg=TEXT_WHITE, activebackground=BG_PANEL,
            activeforeground=ACCENT, font=f_tiny, bd=0,
            highlightthickness=0,
        )
        prof_menu["menu"].config(bg=BTN_BG, fg=TEXT_WHITE, font=f_tiny)
        prof_menu.pack(side=tk.LEFT, padx=4)

        tk.Frame(self._win, bg=BORDER, height=1).pack(fill=tk.X, padx=6)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_frame = tk.Frame(self._win, bg=BG_DARK, padx=8, pady=6)
        btn_frame.pack(fill=tk.X)

        self._btn_pause = tk.Button(
            btn_frame, text="⏸  Pause",
            bg=BTN_BG, fg=TEXT_WHITE, font=f_body,
            bd=0, padx=8, pady=4, cursor="hand2",
            activebackground=BG_PANEL, activeforeground=ACCENT,
            command=self._handle_pause,
        )
        self._btn_pause.pack(fill=tk.X, pady=2)

        self._btn_camera = tk.Button(
            btn_frame, text="📷  Camera Off",
            bg=BTN_BG, fg=TEXT_WHITE, font=f_body,
            bd=0, padx=8, pady=4, cursor="hand2",
            activebackground=BG_PANEL, activeforeground=ACCENT,
            command=self._handle_camera,
        )
        self._btn_camera.pack(fill=tk.X, pady=2)

        tk.Button(
            btn_frame, text="🖥  Open Main Window",
            bg=BTN_BG, fg=TEXT_MUTED, font=f_body,
            bd=0, padx=8, pady=4, cursor="hand2",
            activebackground=BG_PANEL, activeforeground=TEXT_WHITE,
            command=self._on_show_main,
        ).pack(fill=tk.X, pady=2)

    # ── Button handlers ───────────────────────────────────────────────────
    def _handle_pause(self) -> None:
        mode = self._lbl_mode.cget("text")
        self._on_pause_toggle(mode)

    def _handle_camera(self) -> None:
        self._camera_on = not self._camera_on
        self._on_camera_toggle(self._camera_on)
        self._btn_camera.configure(
            text="📷  Camera On" if not self._camera_on else "📷  Camera Off"
        )

    # ── Public update API (called from main thread) ───────────────────────
    def update(self, mode: str, profile: str, gesture: str, action: str | None) -> None:
        """Refresh all status labels.  Must be called from the main thread."""
        mode_color = {
            "CONTROL": ACCENT2,
            "LAUNCH":  ACCENT,
            "PAUSED":  TEXT_WARN,
        }.get(mode, TEXT_MUTED)
        self._lbl_mode.configure(text=mode, fg=mode_color)
        self._lbl_profile.configure(text=profile)
        self._lbl_gesture.configure(text=gesture or "—")
        self._lbl_action.configure(text=action or "—")

        pause_txt = "▶  Resume" if mode == "PAUSED" else "⏸  Pause"
        pause_fg  = ACCENT2 if mode == "PAUSED" else TEXT_WHITE
        self._btn_pause.configure(text=pause_txt, fg=pause_fg)

        # Sync profile dropdown
        if self._profile_var.get() != profile:
            self._profile_var.set(profile)

    def show(self) -> None:
        self._win.deiconify()
        self._win.lift()

    def hide(self) -> None:
        self._win.withdraw()

    # ── Drag support (frameless window) ───────────────────────────────────
    def _enable_drag(self) -> None:
        self._drag_x = 0
        self._drag_y = 0

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag_move(self, event: tk.Event) -> None:
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y
        x  = self._win.winfo_x() + dx
        y  = self._win.winfo_y() + dy
        self._win.geometry(f"+{x}+{y}")
