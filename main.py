"""
main.py
-------
VisionAssist — Main application entry point.

Architecture
------------
• Camera          → raw BGR frames
• HandDetector    → MediaPipe hand landmarks
• GestureClassifier → gesture label from landmarks
• ProfileManager  → mode (LAUNCH/CONTROL/PAUSED) + profile routing
  ├─ demo actions  → AppState dict mutations
  ├─ media actions → pyautogui system key presses
  └─ launch actions → os.startfile / webbrowser
• VisionAssistUI  → Tkinter main window
• FloatingPanel   → compact always-on-top overlay (shown when minimized)

Run with:
    python main.py
Exit:
    Press Q while the application has focus, or close the main window.
"""

from __future__ import annotations
import sys
import os
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
import cv2
import numpy as np
from PIL import Image, ImageTk

# ── Ensure src/ is importable whether run from project root or src/ ───────────
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import time as _time
from src.camera             import Camera
from src.hand_detector      import HandDetector, draw_landmarks
from src.gesture_classifier import classify
from src import app_config
from src.profile_manager    import ProfileManager, AppMode
from src.floating_panel     import FloatingPanel
from src.config_editor      import ConfigEditor

# ── Constants ─────────────────────────────────────────────────────────────────
PREVIEW_W = 640
PREVIEW_H = 480
APP_TITLE  = "VisionAssist — Smart Desktop Assistant"

GESTURE_EMOJI = {
    "OPEN_PALM": "🖐  Open Palm",
    "FIST":      "✊  Fist",
    "THUMBS_UP": "👍  Thumbs Up",
    "POINTING":  "☝  Pointing",
    "PEACE":     "✌  Peace",
    "UNKNOWN":   "❓  Unknown",
}

# ── Colour palette ─────────────────────────────────────────────────────────────
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

MODE_COLORS = {
    AppMode.CONTROL: ACCENT2,
    AppMode.LAUNCH:  ACCENT,
    AppMode.PAUSED:  TEXT_WARN,
}


class VisionAssistUI:
    """
    Tkinter-based GUI.

    Processing (camera + gesture) runs on a background daemon thread.
    All Tkinter calls happen on the main thread via root.after().
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root     = root
        self.running  = True
        self._camera_enabled = True    # user can turn camera off via floating panel

        # ── Load config ────────────────────────────────────────────────────
        try:
            self._cfg = app_config.load()
        except Exception as exc:
            print(f"[VisionAssist] Config load error: {exc} — using defaults")
            self._cfg = app_config._DEFAULT_CONFIG.copy()

        # ── App state (demo mode flags) ────────────────────────────────────
        self.app_state: dict = {
            "slide":      1,
            "max_slides": 6,
            "demo_mode":  False,
            "paused":     False,
            "selected":   False,
            "status_msg": "Ready — show your hand",
        }

        # ── Profile manager ────────────────────────────────────────────────
        self._pm = ProfileManager(self._cfg)

        # ── Shared frame data (protected by lock) ──────────────────────────
        self._lock            = threading.Lock()
        self._current_frame:  np.ndarray | None = None
        self._gesture_label   = "UNKNOWN"
        self._last_action:    str | None = None
        self._last_action_ts: float = 0.0
        self._fps             = 0.0
        self._hand_detected   = False
        self._hold_progress:  float = 0.0

        self._build_ui()
        self._build_menu()
        self._build_floating_panel()
        self._start_processing_thread()
        self._schedule_ui_refresh()

    # ── UI construction ────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG_DARK)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Unmap>", self._on_minimize)
        self.root.bind("<Map>",   self._on_restore)

        # ── Fonts ──────────────────────────────────────────────────────────
        try:
            self._fh1   = tkfont.Font(family="Segoe UI", size=18, weight="bold")
            self._fh2   = tkfont.Font(family="Segoe UI", size=13, weight="bold")
            self._fbody = tkfont.Font(family="Segoe UI", size=11)
            self._fmono = tkfont.Font(family="Consolas",  size=10)
            self._ftiny = tkfont.Font(family="Segoe UI", size=9)
        except Exception:
            self._fh1 = self._fh2 = tkfont.Font(size=13, weight="bold")
            self._fbody = self._fmono = self._ftiny = tkfont.Font(size=10)

        # ── Header ─────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=BG_PANEL, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="👁  VisionAssist", bg=BG_PANEL, fg=ACCENT,
                 font=self._fh1).pack(side=tk.LEFT, padx=20)
        self._lbl_status_header = tk.Label(
            header, text="● INITIALISING", bg=BG_PANEL, fg=TEXT_WARN,
            font=self._fbody)
        self._lbl_status_header.pack(side=tk.RIGHT, padx=20)

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)

        # ── Body ───────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True)

        # Camera feed (left)
        cam_frame = tk.Frame(body, bg=BG_DARK, padx=10, pady=10)
        cam_frame.pack(side=tk.LEFT)
        self._cam_label = tk.Label(cam_frame, bg="black",
                                   width=PREVIEW_W, height=PREVIEW_H)
        self._cam_label.pack()

        # Sidebar (right)
        sidebar = tk.Frame(body, bg=BG_PANEL, width=300, padx=14, pady=10)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # ── Mode control ───────────────────────────────────────────────────
        self._card("Mode", sidebar)
        mode_row = tk.Frame(sidebar, bg=BG_CARD, padx=8, pady=6)
        mode_row.pack(fill=tk.X, pady=(0, 2))

        self._lbl_mode = tk.Label(mode_row, text="CONTROL",
                                   bg=BG_CARD, fg=ACCENT2, font=self._fh2,
                                   anchor="w")
        self._lbl_mode.pack(side=tk.LEFT)

        btn_mode_frame = tk.Frame(mode_row, bg=BG_CARD)
        btn_mode_frame.pack(side=tk.RIGHT)

        self._btn_pause = tk.Button(
            btn_mode_frame, text="⏸ Pause", bg=BTN_BG, fg=TEXT_WHITE,
            font=self._ftiny, bd=0, padx=6, pady=3, cursor="hand2",
            activebackground=BG_PANEL, activeforeground=ACCENT2,
            command=self._toggle_pause,
        )
        self._btn_pause.pack(side=tk.LEFT, padx=2)

        self._btn_launch_mode = tk.Button(
            btn_mode_frame, text="🚀 Launch", bg=BTN_BG, fg=TEXT_WHITE,
            font=self._ftiny, bd=0, padx=6, pady=3, cursor="hand2",
            activebackground=BG_PANEL, activeforeground=ACCENT,
            command=self._toggle_launch_mode,
        )
        self._btn_launch_mode.pack(side=tk.LEFT, padx=2)

        # ── Profile selector ───────────────────────────────────────────────
        self._card("Profile", sidebar)
        prof_frame = tk.Frame(sidebar, bg=BG_CARD, padx=8, pady=4)
        prof_frame.pack(fill=tk.X, pady=(0, 6))
        self._profile_var = tk.StringVar(value=self._pm.profile)
        prof_menu = tk.OptionMenu(
            prof_frame, self._profile_var,
            *self._pm.available_profiles(),
            command=self._on_profile_select,
        )
        prof_menu.config(bg=BTN_BG, fg=TEXT_WHITE, font=self._ftiny, bd=0,
                         activebackground=BG_PANEL, highlightthickness=0)
        prof_menu["menu"].config(bg=BTN_BG, fg=TEXT_WHITE, font=self._ftiny)
        prof_menu.pack(fill=tk.X)

        # ── Gesture detected ───────────────────────────────────────────────
        self._card("Gesture Detected", sidebar)
        self._lbl_gesture = tk.Label(sidebar, text="❓  Unknown",
                                      bg=BG_CARD, fg=ACCENT, font=self._fh2,
                                      anchor="w", padx=10, pady=6)
        self._lbl_gesture.pack(fill=tk.X, pady=(0, 2))
        # Thin hold-progress bar — fills left-to-right as gesture is held
        self._hold_canvas = tk.Canvas(
            sidebar, bg=BG_CARD, height=4, bd=0, highlightthickness=0)
        self._hold_canvas.pack(fill=tk.X, pady=(0, 6))

        # ── Action fired ───────────────────────────────────────────────────
        self._card("Last Action", sidebar)
        self._lbl_action = tk.Label(sidebar, text="—",
                                     bg=BG_CARD, fg=ACCENT2, font=self._fbody,
                                     anchor="w", padx=10, pady=4, wraplength=260)
        self._lbl_action.pack(fill=tk.X, pady=(0, 6))

        # ── Status message ─────────────────────────────────────────────────
        self._card("Status", sidebar)
        self._lbl_status_msg = tk.Label(sidebar, text="Ready — show your hand",
                                         bg=BG_CARD, fg=TEXT_WHITE, font=self._fbody,
                                         anchor="w", padx=10, pady=4, wraplength=260)
        self._lbl_status_msg.pack(fill=tk.X, pady=(0, 6))

        # ── Current mapping reference ──────────────────────────────────────
        self._card("Gesture → Action Map", sidebar)
        self._map_frame = tk.Frame(sidebar, bg=BG_CARD, padx=8, pady=4)
        self._map_frame.pack(fill=tk.X, pady=(0, 6))
        self._map_labels: list[tk.Label] = []
        self._rebuild_map_labels()

        # ── App state (demo) ───────────────────────────────────────────────
        self._card("Demo State", sidebar)
        self._lbl_state = tk.Label(sidebar, text="", bg=BG_CARD, fg=TEXT_WHITE,
                                    font=self._fmono, anchor="w", padx=10, pady=6,
                                    justify=tk.LEFT)
        self._lbl_state.pack(fill=tk.X, pady=(0, 6))

        # ── Info bar ───────────────────────────────────────────────────────
        info_bar = tk.Frame(sidebar, bg=BG_PANEL)
        info_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self._lbl_fps  = tk.Label(info_bar, text="FPS: —", bg=BG_PANEL,
                                   fg=TEXT_MUTED, font=self._ftiny, anchor="w")
        self._lbl_fps.pack(side=tk.LEFT, padx=4)
        self._lbl_hand = tk.Label(info_bar, text="Hand: None", bg=BG_PANEL,
                                   fg=TEXT_MUTED, font=self._ftiny, anchor="e")
        self._lbl_hand.pack(side=tk.RIGHT, padx=4)

        # ── Footer ─────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X)
        footer = tk.Frame(self.root, bg=BG_PANEL, pady=5)
        footer.pack(fill=tk.X)
        tk.Label(footer,
                 text="VisionAssist  ·  BCA Final Year Project  ·  Press Q or close to quit",
                 bg=BG_PANEL, fg=TEXT_MUTED, font=self._ftiny).pack()

    def _card(self, title: str, parent: tk.Widget) -> None:
        tk.Label(parent, text=title.upper(), bg=BG_PANEL, fg=TEXT_MUTED,
                 font=self._ftiny, anchor="w").pack(fill=tk.X, pady=(4, 2))

    def _rebuild_map_labels(self) -> None:
        for lbl in self._map_labels:
            lbl.destroy()
        self._map_labels.clear()
        mapping = self._pm.current_mapping_summary()
        if not mapping:
            # PAUSED mode — show a placeholder
            lbl = tk.Label(self._map_frame,
                           text="Actions disabled while paused.",
                           bg=BG_CARD, fg=TEXT_MUTED, font=self._ftiny,
                           anchor="w")
            lbl.pack(fill=tk.X, pady=2)
            self._map_labels.append(lbl)
            return
        for gesture, action_label in mapping.items():
            emoji = GESTURE_EMOJI.get(gesture, gesture)
            row = tk.Frame(self._map_frame, bg=BG_CARD)
            row.pack(fill=tk.X, pady=1)
            l1 = tk.Label(row, text=emoji, bg=BG_CARD, fg=TEXT_WHITE,
                          font=self._ftiny, width=16, anchor="w")
            l1.pack(side=tk.LEFT)
            l2 = tk.Label(row, text=action_label, bg=BG_CARD, fg=TEXT_MUTED,
                          font=self._ftiny, anchor="w")
            l2.pack(side=tk.LEFT)
            self._map_labels += [l1, l2]

    # ── Menu ───────────────────────────────────────────────────────────────
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root, bg=BG_PANEL, fg=TEXT_WHITE,
                          activebackground=BG_CARD, activeforeground=ACCENT,
                          bd=0)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0, bg=BG_PANEL, fg=TEXT_WHITE,
                            activebackground=BG_CARD, activeforeground=ACCENT)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="⚙  Settings / Apps…", command=self._open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)

        mode_menu = tk.Menu(menubar, tearoff=0, bg=BG_PANEL, fg=TEXT_WHITE,
                            activebackground=BG_CARD, activeforeground=ACCENT)
        menubar.add_cascade(label="Mode", menu=mode_menu)
        mode_menu.add_command(label="⚙  Control Mode",  command=lambda: self._set_mode(AppMode.CONTROL))
        mode_menu.add_command(label="🚀 Launch Mode",   command=lambda: self._set_mode(AppMode.LAUNCH))
        mode_menu.add_command(label="⏸  Pause",         command=self._toggle_pause)

        prof_menu = tk.Menu(menubar, tearoff=0, bg=BG_PANEL, fg=TEXT_WHITE,
                            activebackground=BG_CARD, activeforeground=ACCENT)
        menubar.add_cascade(label="Profile", menu=prof_menu)
        for p in self._pm.available_profiles():
            prof_menu.add_command(label=p, command=lambda pname=p: self._on_profile_select(pname))

    # ── Floating panel ─────────────────────────────────────────────────────
    def _build_floating_panel(self) -> None:
        self._panel = FloatingPanel(
            parent=self.root,
            on_pause_toggle=lambda _mode: self._toggle_pause(),
            on_camera_toggle=self._set_camera,
            on_show_main=self._show_main_window,
            on_profile_change=self._on_profile_select,
            profiles=self._pm.available_profiles(),
        )
        self._panel.hide()    # hidden initially

    # ── Mode / profile controls ────────────────────────────────────────────
    def _set_mode(self, mode: str) -> None:
        self._pm.set_mode(mode)
        self._sync_mode_ui()
        self._rebuild_map_labels()

    def _toggle_pause(self) -> None:
        new_mode = self._pm.toggle_pause()
        self._sync_mode_ui()

    def _toggle_launch_mode(self) -> None:
        new_mode = self._pm.toggle_launch_mode()
        self._sync_mode_ui()
        self._rebuild_map_labels()

    def _sync_mode_ui(self) -> None:
        mode = self._pm.mode
        color = MODE_COLORS.get(mode, TEXT_MUTED)
        self._lbl_mode.configure(text=mode, fg=color)
        pause_txt = "▶ Resume" if mode == AppMode.PAUSED else "⏸ Pause"
        self._btn_pause.configure(text=pause_txt)
        launch_txt = "⚙ Control" if mode == AppMode.LAUNCH else "🚀 Launch"
        self._btn_launch_mode.configure(text=launch_txt)

    def _on_profile_select(self, profile_name: str) -> None:
        self._pm.set_profile(profile_name)
        self._profile_var.set(profile_name)
        self._rebuild_map_labels()

    def _set_camera(self, camera_on: bool) -> None:
        self._camera_enabled = camera_on

    # ── Settings dialog ────────────────────────────────────────────────────
    def _open_settings(self) -> None:
        ConfigEditor(self.root, self._cfg, on_save=self._on_config_saved)

    def _on_config_saved(self, new_cfg: dict) -> None:
        self._cfg = new_cfg
        self._pm.reload_config(new_cfg)
        self._rebuild_map_labels()
        self.app_state["status_msg"] = "✅ Config saved and reloaded"

    # ── Minimize / restore ────────────────────────────────────────────────
    def _on_minimize(self, _event=None) -> None:
        # Only show floating panel when the root window is iconified
        if self.root.state() == "iconic":
            self._panel.show()

    def _on_restore(self, _event=None) -> None:
        self._panel.hide()

    def _show_main_window(self) -> None:
        self.root.deiconify()
        self.root.lift()

    # ── Background processing thread ───────────────────────────────────────
    def _start_processing_thread(self) -> None:
        t = threading.Thread(
            target=self._processing_loop,
            daemon=True,
            name="VisionAssist-Capture",
        )
        t.start()

    def _processing_loop(self) -> None:
        try:
            cam = Camera(index=0, width=PREVIEW_W, height=PREVIEW_H)
            cam.open()
        except RuntimeError as exc:
            with self._lock:
                self._gesture_label = "ERROR"
                self._last_action   = str(exc)
            return

        _start_time = _time.monotonic()

        try:
            with HandDetector(max_hands=1) as detector:
                while self.running:
                    # ── Camera-off mode: show blank frame ──────────────────
                    if not self._camera_enabled:
                        blank = np.zeros((PREVIEW_H, PREVIEW_W, 3), dtype=np.uint8)
                        cv2.putText(blank, "Camera Off", (220, 250),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                                    (80, 80, 80), 2, cv2.LINE_AA)
                        with self._lock:
                            self._current_frame = blank
                            self._gesture_label = "UNKNOWN"
                            self._hand_detected = False
                        key = cv2.waitKey(33) & 0xFF
                        if key in (ord('q'), ord('Q')):
                            self.running = False
                            self.root.after(0, self._on_close)
                            break
                        time.sleep(0.03)
                        continue

                    ok, frame = cam.read()
                    if not ok or frame is None:
                        time.sleep(0.05)
                        continue

                    frame = cv2.flip(frame, 1)
                    ts_ms = int((_time.monotonic() - _start_time) * 1000)
                    hands = detector.process(frame, ts_ms)

                    gesture_label = "UNKNOWN"
                    hand_detected = bool(hands)

                    if hands:
                        hand = hands[0]
                        draw_landmarks(frame, hand.landmarks)
                        result = classify(hand.landmarks, hand.handedness)
                        gesture_label = result.gesture
                        _overlay_gesture(frame, gesture_label, self._pm.mode)
                    else:
                        _overlay_no_hand(frame, self._pm.mode)

                    # Dispatch through ProfileManager
                    action_label, feedback = self._pm.handle_gesture(
                        gesture_label, self.app_state
                    )

                    # Compute hold progress for UI bar
                    hold_count = self._pm._controller._hold_count.get(
                        gesture_label, 0)
                    from src.action_map import HOLD_FRAMES as _HF
                    progress = min(hold_count / _HF, 1.0) if gesture_label != "UNKNOWN" else 0.0

                    now_ts = _time.monotonic()
                    with self._lock:
                        self._current_frame = frame.copy()
                        self._gesture_label = gesture_label
                        if action_label:
                            self._last_action    = action_label
                            self._last_action_ts = now_ts
                        elif now_ts - self._last_action_ts > 2.0:
                            self._last_action = None   # clear after 2 s
                        self._fps           = cam.fps
                        self._hand_detected = hand_detected
                        self._hold_progress = progress

                    # Q key exits
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord('q'), ord('Q')):
                        self.running = False
                        self.root.after(0, self._on_close)
                        break

        finally:
            cv2.destroyAllWindows()
            cam.release()

    # ── UI refresh ─────────────────────────────────────────────────────────
    def _schedule_ui_refresh(self) -> None:
        self._ui_refresh()

    def _ui_refresh(self) -> None:
        if not self.running:
            return
        try:
            self._update_ui()
        except Exception:
            pass
        self.root.after(33, self._ui_refresh)

    def _update_ui(self) -> None:
        with self._lock:
            frame    = self._current_frame
            gesture  = self._gesture_label
            action   = self._last_action
            fps      = self._fps
            hand_det = self._hand_detected
            hold_pct = self._hold_progress

        # Camera feed
        if frame is not None:
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            photo = ImageTk.PhotoImage(Image.fromarray(rgb))
            self._cam_label.configure(image=photo)
            self._cam_label._photo = photo
        else:
            placeholder = np.zeros((PREVIEW_H, PREVIEW_W, 3), dtype=np.uint8)
            cv2.putText(placeholder, "Initialising camera...",
                        (150, 240), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (100, 100, 100), 2, cv2.LINE_AA)
            photo = ImageTk.PhotoImage(Image.fromarray(placeholder))
            self._cam_label.configure(image=photo)
            self._cam_label._photo = photo

        # Gesture label
        g_text  = GESTURE_EMOJI.get(gesture, gesture)
        g_color = ACCENT if gesture not in ("UNKNOWN", "ERROR") else TEXT_MUTED
        self._lbl_gesture.configure(text=g_text, fg=g_color)

        # Hold-progress bar (thin coloured strip under gesture label)
        try:
            w = self._hold_canvas.winfo_width() or 270
            self._hold_canvas.delete("all")
            if hold_pct > 0 and gesture != "UNKNOWN":
                bar_color = ACCENT2 if hold_pct < 1.0 else ACCENT
                self._hold_canvas.create_rectangle(
                    0, 0, int(w * hold_pct), 4,
                    fill=bar_color, outline="",
                )
        except Exception:
            pass

        # Last action — persists for 2 s (clearing handled in processing thread)
        if action:
            self._lbl_action.configure(text=action, fg=ACCENT2)
        else:
            self._lbl_action.configure(text="—", fg=TEXT_MUTED)

        # Demo state
        s = self.app_state
        self._lbl_state.configure(text=(
            f"Slide : {s['slide']} / {s['max_slides']}\n"
            f"Mode  : {'Presentation' if s['demo_mode'] else 'Normal'}\n"
            f"Pause : {'Yes' if s['paused'] else 'No'}\n"
            f"Select: {'Yes' if s['selected'] else 'No'}"
        ))
        self._lbl_status_msg.configure(text=s.get("status_msg", ""))

        # FPS + hand
        self._lbl_fps.configure(text=f"FPS: {fps:.1f}")
        self._lbl_hand.configure(
            text="✅ Hand detected" if hand_det else "⬜ No hand",
            fg=ACCENT2 if hand_det else TEXT_MUTED,
        )

        # Header dot
        mode = self._pm.mode
        if gesture == "ERROR":
            self._lbl_status_header.configure(text="● ERROR",     fg=TEXT_WARN)
        elif mode == AppMode.PAUSED:
            self._lbl_status_header.configure(text="● PAUSED",    fg=TEXT_WARN)
        elif mode == AppMode.LAUNCH:
            self._lbl_status_header.configure(text="● LAUNCH",    fg=ACCENT)
        elif hand_det:
            self._lbl_status_header.configure(text="● ACTIVE",    fg=ACCENT2)
        else:
            self._lbl_status_header.configure(text="● LISTENING", fg=ACCENT)

        # Floating panel sync
        self._panel.update(
            mode=mode, profile=self._pm.profile,
            gesture=g_text, action=action,
        )

    # ── Teardown ───────────────────────────────────────────────────────────
    def _on_close(self) -> None:
        if not self.running:
            try:
                self.root.destroy()
            except Exception:
                pass
            return
        self.running = False
        time.sleep(0.15)
        cv2.destroyAllWindows()
        try:
            self.root.destroy()
        except Exception:
            pass


# ── Frame overlay helpers ──────────────────────────────────────────────────────
def _overlay_gesture(frame: np.ndarray, gesture: str, mode: str) -> None:
    mode_suffix = f" [{mode}]"
    color = {
        AppMode.CONTROL: (0, 255, 128),
        AppMode.LAUNCH:  (80, 160, 255),
        AppMode.PAUSED:  (80, 80, 80),
    }.get(mode, (200, 200, 200))
    cv2.rectangle(frame, (0, 0), (380, 44), (0, 0, 0), -1)
    cv2.putText(frame, f"{gesture}{mode_suffix}",
                (10, 30), cv2.FONT_HERSHEY_DUPLEX,
                0.72, color, 2, cv2.LINE_AA)


def _overlay_no_hand(frame: np.ndarray, mode: str) -> None:
    mode_suffix = f" [{mode}]"
    color = (80, 80, 80) if mode == AppMode.PAUSED else (120, 120, 120)
    cv2.rectangle(frame, (0, 0), (320, 44), (0, 0, 0), -1)
    cv2.putText(frame, f"No hand{mode_suffix}",
                (10, 30), cv2.FONT_HERSHEY_DUPLEX,
                0.72, color, 2, cv2.LINE_AA)


# ── Entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    root = tk.Tk()
    app  = VisionAssistUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
