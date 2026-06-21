import numpy as np
import cv2

# Video specs
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
VIDEO_BITRATE = "4000k"
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

# Color palette (RGB tuples)
TEXT_PRIMARY = (245, 240, 232)      # cream #F5F0E8
TEXT_ACCENT = (201, 169, 110)       # muted gold #C9A96E
CARD_BG = (20, 15, 10)             # dark warm near-black
CARD_BG_ALPHA = 217                 # 0.85 * 255

# Color grading params (apply to all B-roll)
GRADE_TEMPERATURE_SHIFT = 10        # warm shift
GRADE_SATURATION = 0.85             # -15% saturation
GRADE_SHADOW_LIFT = 26              # lift blacks (0–255)

# Typography
FONT_PRIMARY = "Cormorant-Garamond-Bold"    # case titles, victim names
FONT_SECONDARY = "Inter-Regular"             # facts, dates, stats
FONT_ITALIC = "Cormorant-Garamond-Italic"   # victim name card

# Overlay timing
NAME_CARD_DURATION = 4.0            # seconds
LOCATION_STAMP_FADE = 0.3           # fade in seconds
QUOTE_CARD_DURATION = 5.0
KEN_BURNS_ZOOM = 0.08               # 8% zoom over clip duration
CROSSFADE_DURATION = 0.5            # transition duration

# Audio levels
VOICE_VOLUME_DB = -6
MUSIC_VOLUME_DB = -24
SFX_VOLUME_DB = -18
MUSIC_TARGET_LUFS = -24

# Section → music intensity mapping
SECTION_MUSIC_INTENSITY = {
    "COLD OPEN":      "sparse",     # single instrument, very low
    "THE BREAK":      "sparse",
    "WORLD BUILDING": "silence",    # city ambience only
    "THE CRIME":      "silence",    # voice + room tone only
    "INVESTIGATION":  "low",        # low tension hum
    "LEGAL BATTLE":   "low",
    "AFTERMATH":      "sparse",
    "SYSTEMIC ANGLE": "sparse",
    "CLOSE":          "sparse",
}
MUSIC_INTENSITY_LEVELS = {
    "silence": 0.0,    # no music track
    "sparse":  0.20,   # 20% volume
    "low":     0.30,   # 30% volume
    "medium":  0.45,
}


def apply_warm_grade(frame: np.ndarray) -> np.ndarray:
    """Apply warm documentary colour grade to a video frame (numpy BGR array)."""
    graded = frame.astype(np.int32)

    # 1. Lift blacks: add shadow_lift to all channels where pixel < threshold
    threshold = 64
    mask = np.all(graded < threshold, axis=2)
    graded[mask] = np.clip(graded[mask] + GRADE_SHADOW_LIFT, 0, 255)

    graded = np.clip(graded, 0, 255).astype(np.uint8)

    # 2. Reduce saturation by converting to HSV and scaling S channel
    hsv = cv2.cvtColor(graded, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * GRADE_SATURATION, 0, 255)
    graded = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 3. Warm temperature shift: boost R slightly, reduce B slightly
    graded = graded.astype(np.int32)
    graded[:, :, 2] = np.clip(graded[:, :, 2] + GRADE_TEMPERATURE_SHIFT, 0, 255)  # R (BGR idx 2)
    graded[:, :, 0] = np.clip(graded[:, :, 0] - GRADE_TEMPERATURE_SHIFT, 0, 255)  # B (BGR idx 0)

    return graded.astype(np.uint8)
