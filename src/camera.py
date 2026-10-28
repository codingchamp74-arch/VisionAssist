"""
camera.py
---------
Thin wrapper around OpenCV VideoCapture.
Handles init errors, provides frames, and tracks FPS.
"""

from __future__ import annotations
import time
import cv2
import numpy as np


class Camera:
    """
    Context-manager-friendly webcam wrapper.

    Usage
    -----
        with Camera(index=0) as cam:
            ok, frame = cam.read()
    """

    def __init__(self, index: int = 0, width: int = 640, height: int = 480) -> None:
        self.index  = index
        self.width  = width
        self.height = height
        self._cap: cv2.VideoCapture | None = None

        # FPS tracking
        self._fps_buffer: list[float] = []
        self._last_time: float = time.monotonic()

    # ── Lifecycle ─────────────────────────────────────────────────────────
    def open(self) -> None:
        self._cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)  # CAP_DSHOW faster on Windows
        if not self._cap.isOpened():
            # Fallback: try without backend hint
            self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open webcam at index {self.index}. "
                "Check that the camera is connected and not in use by another app."
            )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, 30)

    def release(self) -> None:
        if self._cap and self._cap.isOpened():
            self._cap.release()

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.release()

    # ── Frame access ──────────────────────────────────────────────────────
    def read(self) -> tuple[bool, np.ndarray | None]:
        """Return (success, BGR frame)."""
        if self._cap is None or not self._cap.isOpened():
            return False, None
        ok, frame = self._cap.read()
        if ok:
            self._update_fps()
        return ok, frame

    # ── Metrics ───────────────────────────────────────────────────────────
    def _update_fps(self) -> None:
        now = time.monotonic()
        dt  = now - self._last_time
        self._last_time = now
        if dt > 0:
            self._fps_buffer.append(1.0 / dt)
            if len(self._fps_buffer) > 30:
                self._fps_buffer.pop(0)

    @property
    def fps(self) -> float:
        if not self._fps_buffer:
            return 0.0
        return sum(self._fps_buffer) / len(self._fps_buffer)

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()
