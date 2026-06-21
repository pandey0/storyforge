"""
ShortsAssemblerAgent
====================
Assembles one vertical (9:16, 1080×1920) YouTube Short per episode section.

Input (populated by ShortsScriptAgent + TTSAgent):
    data/cases/{slug}/shorts/
        ep01_who_was_the_victim.md      ← episode script
        ep01_who_was_the_victim.mp3     ← episode TTS voiceover
        ep01_who_was_the_victim_timings.json  ← optional segment timings
        ...

For each episode the agent:
  1. Blur-box crop — blur-boxed 9:16 vertical b-roll (landscape input gets a
     blurred full-frame background with a sharp center-cropped foreground).
  2. Hook frame + burned-in captions — combined single ffmpeg pass:
       - First 3 s: large bold topic title in Hindi (top area, yellow).
       - Time-gated drawtext per segment from word_timings.json (bottom quarter).
       If no font found, both overlays are skipped.
       If timings file missing, captions are skipped but hook frame still renders.
  3. Normalise audio: loudnorm=I=-16:TP=-1.5:LRA=11
  4. Final encode: grade filter + mux audio (libx264 4000k + aac 192k @ 30 fps).

Episodes whose .mp3 is missing are skipped with a warning.

State in:  state.slug, state.shorts_episode_paths (list[str] of .md paths)
State out: state.shorts_video_paths (list[str] of .mp4 output paths)

Pure-ffmpeg approach — no MoviePy.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from loguru import logger

from src.agents.broll_agent import BRollAgent, SHORTS_TOPIC_QUERY
from src.agents.scene_image_agent import SceneImageAgent
from src.pipeline.edl import get_segment_override, load_edl
from src.pipeline.state import CaseState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SHORTS_W = 1080
_SHORTS_H = 1920
_SHORTS_FPS = 30
_SHORTS_BITRATE = "4000k"
_SHORTS_CODEC = "libx264"
_AUDIO_CODEC = "aac"

# Warm grade + vignette — identical to main assembler
_GRADE_FILTER = (
    "eq=saturation=0.85:brightness=0.03,"
    "colorbalance=rs=0.04:gs=0.01:bs=-0.04,"
    "vignette=PI/5"
)

# Section slug → b-roll filename inside data/cases/{slug}/broll/
_SECTION_BROLL: dict[str, str] = {
    "cold_open":           "cold_open.mp4",
    "the_break":           "the_break.mp4",
    "world_building":      "world_building.mp4",
    "the_crime":           "the_crime.mp4",
    "investigation":       "investigation.mp4",
    "legal_battle":        "legal_battle.mp4",
    "aftermath":           "aftermath.mp4",
    "systemic_angle":      "systemic_angle.mp4",
    "close":               "close.mp4",
    # new episode slugs used by the revised shorts script agent
    "who_was_the_victim":  "who_was_the_victim.mp4",
    "the_accused":         "the_accused.mp4",
    "the_evidence":        "the_evidence.mp4",
    "the_trial":           "the_trial.mp4",
    "the_verdict":         "the_verdict.mp4",
    "where_are_they_now":  "where_are_they_now.mp4",
}

# People-focused episode slugs → character role to prefer from DB.
# None means accept any character image (no role filter).
_TOPIC_ROLE_MAP: dict[str, str | None] = {
    "who_was_the_victim": "victim",
    "the_accused":        "accused",
    "where_are_they_now": None,   # any character image
}

# System font search order for drawtext overlays
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]

# Topic slug → Hindi display text for the hook frame
_TOPIC_HINDI: dict[str, str] = {
    "who_was_the_victim": "पीड़ित कौन था?",
    "the_accused":        "आरोपी कौन था?",
    "the_evidence":       "सबूत क्या था?",
    "the_trial":          "मुकदमा कैसा रहा?",
    "the_verdict":        "फ़ैसला क्या हुआ?",
    "systemic_angle":     "सिस्टम की कमी?",
    "where_are_they_now": "अब कहाँ हैं?",
}

# Maximum caption segments to include in a single ffmpeg -vf chain
_MAX_CAPTION_SEGMENTS = 8

# Caption text max characters before truncation
_MAX_CAPTION_CHARS = 40


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Thin wrapper matching the assembler.py pattern exactly."""
    logger.debug("ffmpeg: {}", " ".join(cmd))
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def _probe_duration(path: str) -> float:
    """Return duration in seconds via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def _find_system_font() -> str | None:
    """Return path to the first available bold system font, or None."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _section_slug_from_stem(stem: str) -> str:
    """
    Extract the section slug from an episode stem.

    'ep01_cold_open'          → 'cold_open'
    'ep01_who_was_the_victim' → 'who_was_the_victim'
    'cold_open'               → 'cold_open'  (no episode prefix)
    """
    parts = stem.split("_", 1)
    if len(parts) == 2 and parts[0].startswith("ep") and parts[0][2:].isdigit():
        return parts[1]
    return stem


def _episode_number_from_stem(stem: str) -> str:
    """
    Extract human-readable episode number from stem.

    'ep01_cold_open' → 'EP 01'
    'ep12_the_break' → 'EP 12'
    'cold_open'      → 'EP 01'  (fallback)
    """
    parts = stem.split("_", 1)
    if parts[0].startswith("ep") and parts[0][2:].isdigit():
        return f"EP {parts[0][2:].zfill(2)}"
    return "EP 01"


def _pick_broll(broll_dir: Path, section_slug: str) -> Path | None:
    """
    Choose a b-roll .mp4 for the given section slug.

    Priority:
      1. Exact match from _SECTION_BROLL map.
      2. Any .mp4 found in broll_dir.
      3. None (caller will produce a black colour card).
    """
    if not broll_dir.exists():
        logger.warning("B-roll directory does not exist: {}", broll_dir)
        return None

    # 1. Exact map lookup
    filename = _SECTION_BROLL.get(section_slug)
    if filename:
        candidate = broll_dir / filename
        if candidate.exists():
            logger.info("B-roll exact match: {} → {}", section_slug, candidate)
            return candidate
        logger.debug("Mapped b-roll '{}' not found in {}; trying fallback", filename, broll_dir)

    # 2. Any .mp4 in the directory
    for p in sorted(broll_dir.iterdir()):
        if p.is_file() and p.suffix.lower() == ".mp4":
            logger.info("B-roll fallback for section '{}': {}", section_slug, p)
            return p

    logger.warning("No .mp4 b-roll found in {} for section '{}'", broll_dir, section_slug)
    return None


def _escape_drawtext(text: str) -> str:
    """Escape special characters for ffmpeg drawtext filter value."""
    text = text.replace("\\", "\\\\")  # backslash first
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("%", "\\%")
    return text


def _load_plan_card(slug: str, section_slug: str) -> dict | None:
    """
    Return this episode's card from the dynamically-planned shorts_plan.json,
    or None if no plan exists / the slug isn't in it (e.g. legacy episodes
    written before Phase 20). Callers fall back to the old fixed dicts below.
    """
    plan_path = Path(f"data/cases/{slug}/shorts_plan.json")
    if not plan_path.exists():
        return None
    try:
        cards = json.loads(plan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return next((c for c in cards if c.get("slug") == section_slug), None)


def _topic_hindi_label(slug: str, section_slug: str) -> str:
    """
    Return the display label for the hook frame.

    Prefers the dynamically-planned card's `hook_text` (in whatever language
    the channel profile specifies). Falls back to the legacy fixed-slug dict
    for episodes written before Phase 20, then to a title-cased slug.
    """
    card = _load_plan_card(slug, section_slug)
    if card and card.get("hook_text"):
        return card["hook_text"]
    if section_slug in _TOPIC_HINDI:
        return _TOPIC_HINDI[section_slug]
    return section_slug.replace("_", " ").title()


def _find_timings_file(md_path: Path) -> Path | None:
    """
    Locate the word timings JSON file for an episode.

    Checks two naming conventions:
      1. ep01_who_was_the_victim_timings.json   (stem + '_timings')
      2. ep01_who_was_the_victim.json            (same stem, .json ext)

    Returns the first that exists, or None.
    """
    stem = md_path.stem
    parent = md_path.parent

    candidate_1 = parent / f"{stem}_timings.json"
    if candidate_1.exists():
        logger.debug("Timings file found (pattern 1): {}", candidate_1)
        return candidate_1

    candidate_2 = parent / f"{stem}.json"
    if candidate_2.exists():
        logger.debug("Timings file found (pattern 2): {}", candidate_2)
        return candidate_2

    logger.warning(
        "No timings file found for episode '{}' — captions will be skipped", stem
    )
    return None


def _load_timings(timings_path: Path) -> list[dict]:
    """Load and validate segment timings from JSON. Returns list (may be empty)."""
    try:
        with timings_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            logger.warning("Timings file is not a JSON list: {}", timings_path)
            return []
        return data
    except Exception as exc:
        logger.warning("Failed to read timings file {}: {}", timings_path, exc)
        return []


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

class ShortsAssemblerAgent:
    """
    Assembles one vertical YouTube Short per episode.

    Usage:
        agent = ShortsAssemblerAgent()
        state = agent.assemble(state)
    """

    def assemble(self, state: CaseState) -> CaseState:
        logger.info(
            "ShortsAssemblerAgent.assemble: slug={} episodes={}",
            state.slug,
            len(state.shorts_episode_paths),
        )

        if not state.shorts_episode_paths:
            logger.warning("No shorts_episode_paths on state — nothing to assemble")
            return state

        broll_dir = Path(f"data/cases/{state.slug}/broll")
        produced: list[str] = []

        for md_path_str in state.shorts_episode_paths:
            md_path = Path(md_path_str)
            mp3_path = md_path.with_suffix(".mp3")

            if not mp3_path.exists():
                logger.warning(
                    "Skipping episode {} — TTS audio not found: {}",
                    md_path.stem,
                    mp3_path,
                )
                continue

            output_path = md_path.with_suffix(".mp4")
            try:
                self._assemble_episode(
                    md_path=md_path,
                    mp3_path=mp3_path,
                    output_path=output_path,
                    broll_dir=broll_dir,
                    case_name=state.name,
                )
                produced.append(str(output_path))
                logger.info("Episode assembled: {}", output_path)
            except Exception as exc:
                logger.error(
                    "Failed to assemble episode {}: {}",
                    md_path.stem,
                    exc,
                )

        state.shorts_video_paths = produced
        logger.info(
            "ShortsAssemblerAgent complete: {}/{} episodes produced",
            len(produced),
            len(state.shorts_episode_paths),
        )
        return state

    # ------------------------------------------------------------------
    # Per-episode orchestration
    # ------------------------------------------------------------------

    def _assemble_episode(
        self,
        md_path: Path,
        mp3_path: Path,
        output_path: Path,
        broll_dir: Path,
        case_name: str,
    ) -> None:
        """Full 5-step assembly for a single episode."""
        stem = md_path.stem
        section_slug = _section_slug_from_stem(stem)
        ep_label = _episode_number_from_stem(stem)

        logger.info(
            "Assembling episode: stem={} section={} ep={}",
            stem, section_slug, ep_label,
        )

        audio_dur = _probe_duration(str(mp3_path))
        logger.info("Audio duration: {:.2f}s", audio_dur)

        slug = broll_dir.parent.name
        characters_dir = broll_dir.parent / "characters"

        # Real per-topic Pexels fetch — replaces the old "grab any leftover .mp4" fallback
        self._ensure_topic_broll(slug, section_slug, broll_dir)

        # For people-focused episodes, prefer character photos over stock footage
        char_photo = self._pick_character_photo(characters_dir, section_slug, slug)
        broll_clip = char_photo or _pick_broll(broll_dir, section_slug)

        # Resolve caption timings (optional)
        timings_path = _find_timings_file(md_path)
        timings: list[dict] = []
        if timings_path is not None:
            timings = _load_timings(timings_path)

        # Scene-specific AI images — generated once per episode, cached to disk
        scene_manifest = self._load_or_generate_scene_manifest(slug, section_slug)
        edl = load_edl(slug, "shorts", topic=section_slug)
        scene_manifest = self._apply_edl_overrides(scene_manifest, edl, slug)

        tmp_dir = Path(tempfile.mkdtemp(prefix=f"shorts_ep_{stem}_"))
        try:
            # Step 1: vertical b-roll — blur-box crop + scale + loop
            vertical_broll = str(tmp_dir / "vertical_broll.mp4")
            self._prepare_vertical_broll(broll_clip, vertical_broll, audio_dur)

            # Step 1b: overlay scene-specific AI images during their segment windows
            with_scenes = str(tmp_dir / "with_scenes.mp4")
            self._overlay_scene_images(vertical_broll, with_scenes, scene_manifest, audio_dur)

            # Steps 2+3 combined: hook frame (first 3 s) + burned-in captions
            with_overlays = str(tmp_dir / "with_overlays.mp4")
            self._add_hook_and_captions(
                src=with_scenes,
                out=with_overlays,
                case_name=case_name,
                ep_label=ep_label,
                section_slug=section_slug,
                timings=timings,
                audio_dur=audio_dur,
                slug=slug,
            )

            # Step 4: normalise audio
            norm_audio = str(tmp_dir / "norm_audio.mp3")
            self._normalize_audio(str(mp3_path), norm_audio)

            # Step 5: final encode — grade filter + mux audio
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._final_encode(with_overlays, norm_audio, str(output_path), audio_dur)

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Step 1 — Blur-box crop + scale + loop b-roll to 1080×1920
    # ------------------------------------------------------------------

    def _prepare_vertical_broll(
        self,
        broll_clip: Path | None,
        out: str,
        duration: float,
    ) -> None:
        """
        Produce a 1080×1920 looped clip of `duration` seconds.

        Landscape input (w > h) → blur-box / portrait-boxing technique:
            - Full frame scaled to 1080×1920 + heavy blur  → background layer
            - Center-cropped 9:16 portion scaled to 1080×1920 → foreground layer
            - Foreground overlaid centred on blurred background
          Single-pass filtergraph (no temp files):
            [0:v]split=2[bg][fg];
            [bg]scale=1080:1920,boxblur=20:5[blurred];
            [fg]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920[sharp];
            [blurred][sharp]overlay=(W-w)/2:(H-h)/2,setsar=1

        Already 9:16 input → scale to 1080×1920 directly.
        Portrait/square (h >= w) → scale-with-pad (pillarbox).
        No clip → black colour card.
        """
        if broll_clip is None or not broll_clip.exists():
            logger.info("No b-roll — generating black card ({:.2f}s)", duration)
            self._black_card(out, duration)
            return

        # Detect orientation via ffprobe
        r = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                str(broll_clip),
            ],
            check=True, capture_output=True, text=True,
        )
        probe = json.loads(r.stdout)
        video_streams = [
            s for s in probe.get("streams", [])
            if s.get("codec_type") == "video"
        ]
        if not video_streams:
            logger.warning(
                "ffprobe found no video stream in {} — using black card", broll_clip
            )
            self._black_card(out, duration)
            return

        vs = video_streams[0]
        src_w = int(vs.get("width", 1920))
        src_h = int(vs.get("height", 1080))

        # Determine aspect ratio category
        ratio = src_w / src_h if src_h > 0 else 1.0
        target_ratio = _SHORTS_W / _SHORTS_H  # 1080/1920 ≈ 0.5625

        if abs(ratio - target_ratio) < 0.02:
            # Already 9:16 — just scale
            logger.debug("B-roll is already 9:16 — scaling directly")
            vf = f"scale={_SHORTS_W}:{_SHORTS_H}"
        elif src_w > src_h:
            # Landscape — blur-box technique (single-pass, no temp files)
            logger.debug("B-roll is landscape ({}×{}) — applying blur-box", src_w, src_h)
            vf = (
                f"[0:v]split=2[bg][fg];"
                f"[bg]scale={_SHORTS_W}:{_SHORTS_H},boxblur=20:5[blurred];"
                f"[fg]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale={_SHORTS_W}:{_SHORTS_H}[sharp];"
                f"[blurred][sharp]overlay=(W-w)/2:(H-h)/2,setsar=1"
            )
        else:
            # Portrait or square — scale with pillarbox padding
            logger.debug("B-roll is portrait/square ({}×{}) — scale+pad", src_w, src_h)
            vf = (
                f"scale={_SHORTS_W}:{_SHORTS_H}:force_original_aspect_ratio=decrease,"
                f"pad={_SHORTS_W}:{_SHORTS_H}:(ow-iw)/2:(oh-ih)/2"
            )

        # Build ffmpeg command — filtergraph flag differs for complex vs simple filters
        is_complex = src_w > src_h and abs(ratio - target_ratio) >= 0.02
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(broll_clip),
            "-t", str(duration),
        ]
        if is_complex:
            cmd += ["-filter_complex", vf]
        else:
            cmd += ["-vf", vf]
        cmd += [
            "-r", str(_SHORTS_FPS),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-an",
            out,
        ]
        _run(cmd)

    def _black_card(self, out: str, duration: float) -> None:
        _run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s={_SHORTS_W}x{_SHORTS_H}:r={_SHORTS_FPS}:d={duration}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-an",
            out,
        ])

    # ------------------------------------------------------------------
    # Step 1b — scene-specific AI image overlay (time-gated, like captions)
    # ------------------------------------------------------------------

    def _ensure_topic_broll(self, slug: str, section_slug: str, broll_dir: Path) -> None:
        """Fetch real Pexels footage for this topic if not already cached on disk."""
        card = _load_plan_card(slug, section_slug)
        query = (card or {}).get("broll_query") or SHORTS_TOPIC_QUERY.get(section_slug)
        if not query:
            return
        dest = broll_dir / f"{section_slug}.mp4"
        if dest.exists():
            return
        try:
            BRollAgent().fetch_for_shorts_topic(slug, section_slug, query)
        except Exception as exc:
            logger.warning("Topic b-roll fetch failed for {}/{}: {}", slug, section_slug, exc)

    def _load_or_generate_scene_manifest(self, slug: str, section_slug: str) -> list[dict]:
        """Load cached scene-image manifest, or generate it once via SceneImageAgent."""
        manifest_path = Path(f"data/cases/{slug}/scene_images/{section_slug}/manifest.json")
        if manifest_path.exists():
            try:
                return json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to read scene manifest {}: {}", manifest_path, exc)
                return []
        try:
            return SceneImageAgent().run(slug, section_slug)
        except Exception as exc:
            logger.warning("SceneImageAgent failed for {}/{}: {}", slug, section_slug, exc)
            return []

    def _apply_edl_overrides(
        self,
        manifest: list[dict],
        edl,
        slug: str,
    ) -> list[dict]:
        """Apply manual EDL overrides onto the auto-generated scene manifest, per segment_index."""
        if edl is None:
            return manifest

        overridden: list[dict] = []
        for entry in manifest:
            segment_id = str(entry.get("segment_index"))
            override = get_segment_override(edl, segment_id)
            if override is None:
                overridden.append(entry)
                continue
            if override.source_type == "broll":
                logger.warning(
                    "EDL override for segment {} is source_type='broll' — cannot apply to "
                    "still-image overlay path; leaving segment on its automatic source",
                    segment_id,
                )
                overridden.append(entry)
                continue
            new_entry = dict(entry)
            new_entry["image_path"] = f"data/cases/{slug}/{override.source_path}"
            overridden.append(new_entry)
        return overridden

    def _overlay_scene_images(
        self,
        src: str,
        out: str,
        manifest: list[dict],
        audio_dur: float,
    ) -> None:
        """
        Overlay scene-specific AI images full-screen during their segment window,
        replacing the b-roll for that window only — same time-gated technique as
        captions (`enable='between(t,start,end)'`). Falls through unchanged if no
        valid manifest entries (missing images, missing start/end).
        """
        valid = [
            m for m in manifest
            if m.get("image_path") and Path(m["image_path"]).exists()
            and m.get("start") is not None and m.get("end") is not None
        ][:_MAX_CAPTION_SEGMENTS]

        if not valid:
            shutil.copy2(src, out)
            return

        cmd = ["ffmpeg", "-y", "-i", src]
        filter_parts = []
        last_label = "0:v"
        for i, m in enumerate(valid):
            dur = max(0.1, float(m["end"]) - float(m["start"]))
            cmd += ["-loop", "1", "-framerate", str(_SHORTS_FPS), "-t", str(dur), "-i", m["image_path"]]
            img_idx = i + 1
            scaled = f"img{i}"
            filter_parts.append(
                f"[{img_idx}:v]scale={_SHORTS_W}:{_SHORTS_H}:force_original_aspect_ratio=increase,"
                f"crop={_SHORTS_W}:{_SHORTS_H},setsar=1[{scaled}]"
            )
            out_label = f"v{i}" if i < len(valid) - 1 else "vout"
            filter_parts.append(
                f"[{last_label}][{scaled}]overlay=0:0:enable='between(t,{m['start']},{m['end']})'[{out_label}]"
            )
            last_label = out_label

        cmd += [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[{last_label}]",
            "-t", str(audio_dur),
            "-r", str(_SHORTS_FPS),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-an",
            out,
        ]
        _run(cmd)

    # ------------------------------------------------------------------
    # Character photo lookup (people-focused episodes)
    # ------------------------------------------------------------------

    def _pick_character_photo(
        self,
        characters_dir: Path,
        section_slug: str,
        slug: str,
    ) -> Path | None:
        """
        For people-focused episodes, find a character photo from DB by role.
        Falls back to any image in characters_dir if no role match.
        Returns None if characters_dir doesn't exist or has no images.
        """
        card = _load_plan_card(slug, section_slug)
        has_role_hint = card is not None and card.get("role_hint")
        if not has_role_hint and section_slug not in _TOPIC_ROLE_MAP:
            return None
        if not characters_dir.exists():
            return None

        # Dynamically-planned episodes give a person's NAME, not a role bucket —
        # more precise when multiple people share a role.
        target_name = card.get("role_hint") if has_role_hint else None
        target_role = None if target_name else _TOPIC_ROLE_MAP.get(section_slug)

        try:
            from src.db.models import Case, CaseCharacter
            from src.db.session import get_session
            with get_session() as session:
                case = session.query(Case).filter_by(slug=slug).first()
                if case:
                    query = session.query(CaseCharacter).filter_by(case_id=case.id)
                    if target_name:
                        query = query.filter(CaseCharacter.name.ilike(f"%{target_name}%"))
                    elif target_role:
                        query = query.filter_by(role=target_role)
                    for char in query.all():
                        if char.image_path and Path(char.image_path).exists():
                            logger.info(
                                "Character photo found: {} ({}) for episode {}",
                                char.name, char.role, section_slug,
                            )
                            return Path(char.image_path)
        except Exception as e:
            logger.warning("DB lookup for character photo failed: {}", e)

        # Fallback: any image file in characters_dir
        img_exts = {".jpg", ".jpeg", ".png", ".webp"}
        for p in sorted(characters_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in img_exts:
                logger.info("Character photo fallback: {}", p)
                return p

        return None

    # ------------------------------------------------------------------
    # Steps 2+3 combined — Hook frame + burned-in captions (single pass)
    # ------------------------------------------------------------------

    def _add_hook_and_captions(
        self,
        src: str,
        out: str,
        case_name: str,
        ep_label: str,
        section_slug: str,
        timings: list[dict],
        audio_dur: float,
        slug: str,
    ) -> None:
        """
        Single ffmpeg pass that burns in:
          1. Hook frame: large bold Hindi topic title, top area, first 3 seconds.
          2. Case name + episode label (permanent, as before).
          3. Time-gated caption segments from timings (bottom quarter).

        If no system font is found, all text overlays are skipped and the
        video is stream-copied unchanged — the pipeline never crashes on a
        missing font.
        """
        font = _find_system_font()
        if font is None:
            logger.warning(
                "No system font found — skipping all text overlays; stream-copying"
            )
            _run(["ffmpeg", "-y", "-i", src, "-c", "copy", out])
            return

        filter_parts: list[str] = []

        # --- Permanent overlays: case name (top) + episode label (bottom-left) ---
        safe_name = _escape_drawtext(case_name)
        safe_ep = _escape_drawtext(ep_label)

        filter_parts.append(
            f"drawtext=fontfile='{font}':"
            f"text='{safe_name}':"
            f"fontsize=48:fontcolor=white:"
            f"x=(w-text_w)/2:y=80:"
            f"box=1:boxcolor=black@0.45:boxborderw=10"
        )
        filter_parts.append(
            f"drawtext=fontfile='{font}':"
            f"text='{safe_ep}':"
            f"fontsize=36:fontcolor=white:"
            f"x=40:y=h-80:"
            f"box=1:boxcolor=black@0.45:boxborderw=8"
        )

        # --- Hook frame: Hindi topic title, first 3 seconds, top area ---
        hook_text = _escape_drawtext(_topic_hindi_label(slug, section_slug))
        filter_parts.append(
            f"drawtext=fontfile='{font}':"
            f"text='{hook_text}':"
            f"fontsize=56:fontcolor=yellow:"
            f"x=(w-text_w)/2:y=h*0.15:"
            f"box=1:boxcolor=black@0.7:boxborderw=12:"
            f"enable='between(t,0,3)'"
        )

        # --- Time-gated caption segments (bottom quarter) ---
        if timings:
            segments = timings[:_MAX_CAPTION_SEGMENTS]
            for seg in segments:
                try:
                    start = float(seg.get("start_sec", 0.0))
                    end = float(seg.get("end_sec", start + 1.0))
                    raw_text = str(seg.get("text_preview", "")).strip()
                except (TypeError, ValueError) as exc:
                    logger.warning("Skipping malformed timing segment {}: {}", seg, exc)
                    continue

                if not raw_text:
                    continue

                # Truncate at max chars
                if len(raw_text) > _MAX_CAPTION_CHARS:
                    raw_text = raw_text[:_MAX_CAPTION_CHARS]

                safe_text = _escape_drawtext(raw_text)

                filter_parts.append(
                    f"drawtext=fontfile='{font}':"
                    f"text='{safe_text}':"
                    f"fontsize=42:fontcolor=white:"
                    f"x=(w-text_w)/2:y=h*0.75:"
                    f"box=1:boxcolor=black@0.6:boxborderw=8:"
                    f"enable='between(t,{start},{end})'"
                )
        else:
            logger.info("No caption timings — hook frame and permanent labels only")

        vf = ",".join(filter_parts)

        _run([
            "ffmpeg", "-y",
            "-i", src,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-an",
            out,
        ])

    # ------------------------------------------------------------------
    # Step 4 — Audio normalisation
    # ------------------------------------------------------------------

    def _normalize_audio(self, src: str, out: str) -> None:
        _run([
            "ffmpeg", "-y",
            "-i", src,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            out,
        ])

    # ------------------------------------------------------------------
    # Step 5 — Final encode: grade filter + mux audio
    # ------------------------------------------------------------------

    def _final_encode(
        self,
        video_path: str,
        audio_path: str,
        out: str,
        audio_dur: float,
    ) -> None:
        """
        Combine graded video + normalised audio, trimmed to audio_dur.
        Output: libx264 @ 4000k, aac @ 192k, 1080×1920 @ 30 fps.
        """
        _run([
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-t", str(audio_dur),
            "-vf", _GRADE_FILTER,
            "-c:v", _SHORTS_CODEC, "-b:v", _SHORTS_BITRATE,
            "-c:a", _AUDIO_CODEC, "-b:a", "192k",
            "-r", str(_SHORTS_FPS),
            "-threads", "4",
            out,
        ])
