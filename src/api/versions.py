"""Pivot step constants for case-level branching."""

# Steps where rerun creates a new child case instead of overwriting
PIVOT_STEPS = {"research", "script", "tts"}

# What to copy from parent to child at each pivot
PIVOT_COPY_MAP = {
    "research": [],  # nothing — fresh start
    "script": ["research.json"],
    "tts": ["research.json", "script_draft.md", "script_manual.md", "audio/word_timings.json"],
}

# Canonical output file per step (for file existence checks)
STEP_FILE_MAP = {
    "research":  "research.json",
    "script":    "script_draft.md",
    "tts":       "audio/voiceover.mp3",
    "broll":          None,
    "shorts":         None,  # episodic — multiple files in shorts/ dir, not one canonical file
    "shorts_plan":    "shorts_plan.json",
    "shorts_script":  None,  # episodic — files in shorts/*.md
    "shorts_tts":     None,  # episodic — files in shorts/*.mp3
    "shorts_assemble": None,  # episodic — files in shorts/*.mp4
    "video":     "output/video_final.mp4",
    "thumbnail": "output/thumbnail.jpg",
}

# Status to set on child case after branching (child starts from this step)
PIVOT_CHILD_STATUS = {
    "research": "queued",
    "script":   "research",   # research already done
    "tts":      "scripting",  # script already done
}
