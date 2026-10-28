"""
config.py
---------
Central configuration for VisionAssist.
Edit this file to tune thresholds without touching core logic.
"""

# ── Camera settings ──────────────────────────────────────────────────────────
CAMERA_INDEX  = 0          # 0 = default webcam; change to 1 for external
CAMERA_WIDTH  = 640
CAMERA_HEIGHT = 480
CAMERA_FPS    = 30

# ── Hand detection ────────────────────────────────────────────────────────────
MAX_HANDS                 = 1     # detect at most 1 hand
MIN_DETECTION_CONFIDENCE  = 0.70  # lower → more detections, noisier
MIN_TRACKING_CONFIDENCE   = 0.60  # lower → loses hand less often

# ── Gesture stability ─────────────────────────────────────────────────────────
HOLD_FRAMES  = 8    # consecutive frames a gesture must be held to fire
COOLDOWN_SEC = 1.5  # seconds between repeated firings of the same gesture

# ── Demo parameters ───────────────────────────────────────────────────────────
MAX_SLIDES = 6
