"""
hand_detector.py
----------------
Wraps the MediaPipe Tasks HandLandmarker API (MediaPipe >= 1.0 / 1.1.x).

The legacy mp.solutions.hands API was removed in MediaPipe 1.x.
This module uses the new mediapipe.tasks.python.vision.HandLandmarker.

Model file required: models/hand_landmarker.task
Download:
    python -c "
    import urllib.request, os
    os.makedirs('models', exist_ok=True)
    urllib.request.urlretrieve(
        'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
        'models/hand_landmarker.task'
    )"
"""

from __future__ import annotations
import os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from dataclasses import dataclass
from typing import Any

# ── Default model path ────────────────────────────────────────────────────────
_HERE       = os.path.dirname(os.path.abspath(__file__))
_ROOT       = os.path.dirname(_HERE)
DEFAULT_MODEL = os.path.join(_ROOT, "models", "hand_landmarker.task")

# ── MediaPipe landmark connections (21-point hand skeleton) ───────────────────
_CONNECTIONS = [
    # Thumb
    (0,1),(1,2),(2,3),(3,4),
    # Index
    (0,5),(5,6),(6,7),(7,8),
    # Middle
    (0,9),(9,10),(10,11),(11,12),
    # Ring
    (0,13),(13,14),(14,15),(15,16),
    # Pinky
    (0,17),(17,18),(18,19),(19,20),
    # Palm
    (5,9),(9,13),(13,17),
]


@dataclass
class HandResult:
    landmarks:  list   # list of NormalizedLandmark-like objects
    handedness: str    # 'Right' or 'Left'


class HandDetector:
    """
    Detects up to `max_hands` hands per frame using MediaPipe Tasks API.

    Usage (context manager):
        with HandDetector() as detector:
            hands = detector.process(bgr_frame)
            for hand in hands:
                draw_landmarks(frame, hand.landmarks)
    """

    def __init__(
        self,
        max_hands: int = 1,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float  = 0.6,
        min_presence_confidence: float  = 0.5,
        model_path: str = DEFAULT_MODEL,
    ) -> None:
        self._max_hands    = max_hands
        self._det_conf     = min_detection_confidence
        self._trk_conf     = min_tracking_confidence
        self._pres_conf    = min_presence_confidence
        self._model_path   = model_path
        self._detector: Any = None

    # ── Lifecycle ─────────────────────────────────────────────────────────
    def open(self) -> None:
        if not os.path.exists(self._model_path):
            raise FileNotFoundError(
                f"Hand landmarker model not found: {self._model_path}\n"
                "Run the download command in hand_detector.py docstring."
            )
        base_opts = mp_python.BaseOptions(model_asset_path=self._model_path)
        opts = mp_vision.HandLandmarkerOptions(
            base_options=base_opts,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=self._max_hands,
            min_hand_detection_confidence=self._det_conf,
            min_hand_presence_confidence=self._pres_conf,
            min_tracking_confidence=self._trk_conf,
        )
        self._detector = mp_vision.HandLandmarker.create_from_options(opts)

    def close(self) -> None:
        if self._detector:
            self._detector.close()
            self._detector = None

    def __enter__(self) -> "HandDetector":
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Processing ────────────────────────────────────────────────────────
    def process(self, bgr_frame: np.ndarray, timestamp_ms: int) -> list[HandResult]:
        """
        Detect hands in a BGR frame.

        Parameters
        ----------
        bgr_frame    : OpenCV BGR frame
        timestamp_ms : monotonic timestamp in milliseconds (required for VIDEO mode)

        Returns
        -------
        List of HandResult (may be empty)
        """
        # Convert BGR → RGB for MediaPipe
        rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        detection = self._detector.detect_for_video(mp_image, timestamp_ms)

        if not detection.hand_landmarks:
            return []

        results: list[HandResult] = []
        for i, lm_list in enumerate(detection.hand_landmarks):
            # Handedness label
            side = "Right"
            if detection.handedness and i < len(detection.handedness):
                side = detection.handedness[i][0].display_name

            results.append(HandResult(landmarks=lm_list, handedness=side))
        return results


# ── Drawing utilities ─────────────────────────────────────────────────────────

def draw_landmarks(
    frame: np.ndarray,
    landmarks: list,
    color_dot:  tuple[int, int, int] = (0, 255, 128),
    color_line: tuple[int, int, int] = (255, 255, 255),
) -> None:
    """
    Draw hand skeleton (joints + connections) on `frame` in-place.

    Works with MediaPipe Tasks NormalizedLandmark objects
    (each has .x, .y attributes in [0, 1]).
    """
    h, w, _ = frame.shape

    # Build pixel coords
    pts: list[tuple[int, int]] = []
    for lm in landmarks:
        pts.append((int(lm.x * w), int(lm.y * h)))

    # Draw connections first (under dots)
    for a, b in _CONNECTIONS:
        if a < len(pts) and b < len(pts):
            cv2.line(frame, pts[a], pts[b], color_line, 2, cv2.LINE_AA)

    # Draw joint dots
    for cx, cy in pts:
        cv2.circle(frame, (cx, cy), 5, color_dot, -1)
        cv2.circle(frame, (cx, cy), 6, (0, 0, 0), 1)   # thin black outline


# Backwards-compat alias used in main.py
_draw_landmarks_from_list = draw_landmarks
