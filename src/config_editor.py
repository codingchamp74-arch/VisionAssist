"""
src/config_editor.py
--------------------
Tkinter dialog for editing VisionAssist user configuration:
  • Add / remove registered apps and websites
  • Browse button (native Windows file picker) to select executables
  • Assign launch gestures to each entry
  • Duplicate gesture conflict detection with clear explanation
  • Enable / disable individual entries
  • Save to disk

Opened via the main window's Settings menu.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font as tkfont
from typing import Callable, Any

from src import app_config

BG_DARK    = "#0d1117"
BG_PANEL   = "#161b22"
BG_CARD    = "#21262d"
ACCENT     = "#58a6ff"
ACCENT2    = "#3fb950"
TEXT_WHITE = "#f0f6fc"
TEXT_MUTED = "#8b949e"
TEXT_WARN  = "#f85149"
BORDER     = "#30363d"

GESTURE_OPTIONS = ["", "OPEN_PALM", "FIST", "THUMBS_UP", "POINTING", "PEACE"]
TYPE_OPTIONS    = ["app", "website"]

# Human-readable labels for gesture names shown in conflict messages
GESTURE_LABELS = {
    "OPEN_PALM": "Open Palm 🖐",
    "FIST":      "Fist ✊",
    "THUMBS_UP": "Thumbs Up 👍",
    "POINTING":  "Pointing ☝",
    "PEACE":     "Peace ✌",
}


class ConfigEditor(tk.Toplevel):
    """
    Modal-style config editor window.

    Parameters
    ----------
    parent       : Tk root
    cfg          : current config dict
    on_save      : callback(new_cfg: dict) called after successful save
    """

    def __init__(
        self,
        parent: tk.Misc,
        cfg: dict[str, Any],
        on_save: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__(parent)
        self._cfg     = cfg
        self._on_save = on_save
        self._apps    = list(cfg.get("registered_apps", []))   # working copy

        self.title("VisionAssist — Settings")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)
        self.minsize(640, 460)
        self.grab_set()   # modal

        try:
            self._fb  = tkfont.Font(family="Segoe UI", size=10, weight="bold")
            self._fn  = tkfont.Font(family="Segoe UI", size=10)
            self._fh  = tkfont.Font(family="Segoe UI", size=12, weight="bold")
            self._fty = tkfont.Font(family="Segoe UI", size=9)
        except Exception:
            self._fb = self._fn = self._fh = self._fty = tkfont.Font(size=10)

        self._build()
        self._refresh_list()

    # ── Build ─────────────────────────────────────────────────────────────
    def _build(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=BG_PANEL, pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Registered Apps & Websites",
                 bg=BG_PANEL, fg=ACCENT, font=self._fh).pack(side=tk.LEFT, padx=14)

        # Hint
        tk.Label(
            self,
            text=(
                "Add apps (exe name or full path) and websites (http/https URL). "
                "Assign a unique Launch Gesture per entry to open it in Launch Mode."
            ),
            bg=BG_DARK, fg=TEXT_MUTED, font=self._fty,
            wraplength=600, justify=tk.LEFT,
        ).pack(fill=tk.X, padx=14, pady=(6, 2))

        tk.Frame(self, bg=BORDER, height=1).pack(fill=tk.X)

        # ── App list (Treeview) ────────────────────────────────────────────
        list_frame = tk.Frame(self, bg=BG_DARK)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        cols = ("Enabled", "Name", "Type", "Path / URL", "Launch Gesture")
        self._tree = ttk.Treeview(list_frame, columns=cols,
                                   show="headings", height=8)
        for col, w in zip(cols, (60, 120, 65, 240, 120)):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w",
                               stretch=(col == "Path / URL"))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                        background=BG_CARD, fieldbackground=BG_CARD,
                        foreground=TEXT_WHITE, rowheight=22, font=self._fn)
        style.configure("Treeview.Heading",
                        background=BG_PANEL, foreground=TEXT_MUTED,
                        font=self._fty)
        style.map("Treeview", background=[("selected", BG_PANEL)])

        vsb = ttk.Scrollbar(list_frame, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── Edit form ─────────────────────────────────────────────────────
        form = tk.Frame(self, bg=BG_PANEL, padx=12, pady=8)
        form.pack(fill=tk.X, padx=10, pady=(0, 4))

        def _label(text, row, col):
            tk.Label(form, text=text, bg=BG_PANEL, fg=TEXT_MUTED,
                     font=self._fty, anchor="e", width=14).grid(
                row=row, column=col * 2, sticky="e", padx=(4, 2), pady=3)

        # Row 0: Name + Type
        _label("Name", 0, 0)
        self._var_name = tk.StringVar()
        tk.Entry(form, textvariable=self._var_name, bg=BG_CARD, fg=TEXT_WHITE,
                 font=self._fn, width=20, insertbackground=TEXT_WHITE,
                 ).grid(row=0, column=1, sticky="ew", padx=(0, 12))

        _label("Type", 0, 1)
        self._var_type = tk.StringVar(value="app")
        om_type = tk.OptionMenu(form, self._var_type, *TYPE_OPTIONS,
                                command=self._on_type_change)
        om_type.config(bg=BG_CARD, fg=TEXT_WHITE, font=self._fty, bd=0,
                       activebackground=BG_PANEL, highlightthickness=0)
        om_type["menu"].config(bg=BG_CARD, fg=TEXT_WHITE, font=self._fty)
        om_type.grid(row=0, column=3, sticky="ew", padx=(0, 4))

        # Row 1: Path + Browse button + Gesture
        _label("Path / URL", 1, 0)
        path_row = tk.Frame(form, bg=BG_PANEL)
        path_row.grid(row=1, column=1, sticky="ew", padx=(0, 12))
        self._var_path = tk.StringVar()
        self._entry_path = tk.Entry(
            path_row, textvariable=self._var_path,
            bg=BG_CARD, fg=TEXT_WHITE, font=self._fn,
            width=22, insertbackground=TEXT_WHITE,
        )
        self._entry_path.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._btn_browse = tk.Button(
            path_row, text="📂 Browse",
            bg=BG_CARD, fg=TEXT_WHITE, font=self._fty,
            bd=0, padx=6, pady=2, cursor="hand2",
            activebackground=BG_PANEL, activeforeground=ACCENT,
            command=self._browse_exe,
        )
        self._btn_browse.pack(side=tk.LEFT, padx=(4, 0))

        _label("Launch Gesture", 1, 1)
        self._var_gesture = tk.StringVar()
        om_gest = tk.OptionMenu(form, self._var_gesture, *GESTURE_OPTIONS)
        om_gest.config(bg=BG_CARD, fg=TEXT_WHITE, font=self._fty, bd=0,
                       activebackground=BG_PANEL, highlightthickness=0)
        om_gest["menu"].config(bg=BG_CARD, fg=TEXT_WHITE, font=self._fty)
        om_gest.grid(row=1, column=3, sticky="ew", padx=(0, 4))

        # Row 2: Enabled checkbox
        self._var_enabled = tk.BooleanVar(value=True)
        tk.Checkbutton(
            form, text="Enabled", variable=self._var_enabled,
            bg=BG_PANEL, fg=TEXT_WHITE, font=self._fty,
            activebackground=BG_PANEL, selectcolor=BG_CARD,
        ).grid(row=2, column=1, sticky="w", pady=2)

        form.columnconfigure(1, weight=2)
        form.columnconfigure(3, weight=1)

        # ── Conflict warning ───────────────────────────────────────────────
        self._lbl_conflict = tk.Label(self, text="", bg=BG_DARK,
                                       fg=TEXT_WARN, font=self._fty,
                                       wraplength=580, justify=tk.LEFT)
        self._lbl_conflict.pack(fill=tk.X, padx=14)

        # ── Action buttons ─────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=BG_DARK, padx=10, pady=6)
        btn_frame.pack(fill=tk.X)

        def _btn(text, cmd, fg=TEXT_WHITE):
            b = tk.Button(btn_frame, text=text, command=cmd,
                          bg=BG_CARD, fg=fg, font=self._fn, bd=0,
                          padx=10, pady=4, cursor="hand2",
                          activebackground=BG_PANEL, activeforeground=ACCENT)
            return b

        _btn("➕ Add / Update", self._add_or_update).pack(side=tk.LEFT, padx=4)
        _btn("🗑  Remove",      self._remove, fg=TEXT_WARN).pack(side=tk.LEFT, padx=4)
        _btn("💾 Save",         self._save, fg=ACCENT2).pack(side=tk.RIGHT, padx=4)
        _btn("✕ Cancel",       self.destroy, fg=TEXT_MUTED).pack(side=tk.RIGHT, padx=4)

        # Status label
        self._lbl_status = tk.Label(self, text="", bg=BG_DARK, fg=ACCENT2,
                                     font=self._fty)
        self._lbl_status.pack(pady=(0, 4))

    # ── Browse button ─────────────────────────────────────────────────────
    def _browse_exe(self) -> None:
        """Open native Windows file picker and fill the path entry."""
        try:
            path = filedialog.askopenfilename(
                parent=self,
                title="Select Executable",
                filetypes=[
                    ("Executable files", "*.exe"),
                    ("All files", "*.*"),
                ],
            )
        except Exception as exc:
            self._status(f"File picker error: {exc}", error=True)
            return

        if not path:
            return   # user cancelled — do nothing

        self._var_path.set(path)
        # Auto-set type to 'app' since we just browsed for an exe
        self._var_type.set("app")
        self._lbl_conflict.configure(text="")

    def _on_type_change(self, val: str) -> None:
        """Show/hide Browse button based on type."""
        if val == "website":
            self._btn_browse.configure(state=tk.DISABLED, fg=TEXT_MUTED)
        else:
            self._btn_browse.configure(state=tk.NORMAL, fg=TEXT_WHITE)

    # ── Duplicate gesture conflict detection ──────────────────────────────
    def _check_gesture_conflict(self, gesture: str, current_name: str) -> str | None:
        """
        Return a conflict explanation if `gesture` is already assigned to
        another enabled app in the working list, else return None.

        The same gesture CAN be reused if the conflicting entry is disabled.
        """
        if not gesture:
            return None
        for app in self._apps:
            if app.get("name") == current_name:
                continue   # allow updating own entry
            if app.get("launch_gesture") == gesture and app.get("enabled", True):
                label = GESTURE_LABELS.get(gesture, gesture)
                return (
                    f"⚠ Conflict: {label} is already assigned to "
                    f"'{app['name']}'. Each enabled entry must have a unique "
                    f"launch gesture. Disable the other entry or choose a "
                    f"different gesture."
                )
        return None

    # ── List management ───────────────────────────────────────────────────
    def _refresh_list(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for app in self._apps:
            self._tree.insert("", "end", values=(
                "✅" if app.get("enabled", True) else "☐",
                app.get("name", ""),
                app.get("type", "app"),
                app.get("path_or_url", ""),
                app.get("launch_gesture") or "—",
            ))

    def _on_select(self, _event=None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        app = self._apps[idx]
        self._var_name.set(app.get("name", ""))
        self._var_type.set(app.get("type", "app"))
        self._var_path.set(app.get("path_or_url", ""))
        self._var_gesture.set(app.get("launch_gesture") or "")
        self._var_enabled.set(app.get("enabled", True))
        self._lbl_conflict.configure(text="")
        self._lbl_status.configure(text="")
        # Sync browse button state
        self._on_type_change(self._var_type.get())

    def _add_or_update(self) -> None:
        name    = self._var_name.get().strip()
        kind    = self._var_type.get()
        path    = self._var_path.get().strip()
        gesture = self._var_gesture.get() or None
        enabled = self._var_enabled.get()

        if not name:
            self._status("Name cannot be empty.", error=True)
            return

        err = app_config.validate_app_entry(kind, path)
        if err:
            self._status(err, error=True)
            return

        # Gesture conflict check
        if gesture and enabled:
            conflict = self._check_gesture_conflict(gesture, name)
            if conflict:
                self._lbl_conflict.configure(text=conflict)
                self._status("Resolve the gesture conflict before adding.", error=True)
                return

        self._lbl_conflict.configure(text="")
        # Remove existing with same name, then append
        self._apps = [a for a in self._apps if a["name"] != name]
        self._apps.append({
            "name": name,
            "type": kind,
            "path_or_url": path,
            "launch_gesture": (
                gesture if gesture in app_config.VALID_GESTURES else None
            ),
            "enabled": enabled,
        })
        self._refresh_list()
        self._status(f"'{name}' added/updated.")

    def _remove(self) -> None:
        sel = self._tree.selection()
        if not sel:
            self._status("Select an entry to remove.", error=True)
            return
        idx = self._tree.index(sel[0])
        removed = self._apps.pop(idx)
        self._refresh_list()
        self._lbl_conflict.configure(text="")
        self._status(f"'{removed['name']}' removed.")

    def _save(self) -> None:
        from copy import deepcopy
        new_cfg = deepcopy(self._cfg)
        new_cfg["registered_apps"] = self._apps
        try:
            app_config.save(new_cfg)
        except Exception as exc:
            self._status(f"Save failed: {exc}", error=True)
            return
        self._on_save(new_cfg)
        self._status("Saved ✅")
        self.after(800, self.destroy)

    def _status(self, msg: str, error: bool = False) -> None:
        self._lbl_status.configure(
            text=msg,
            fg=TEXT_WARN if error else ACCENT2,
        )
