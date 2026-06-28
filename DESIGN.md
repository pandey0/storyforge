---
name: StoryForge — Video Design System
description: Visual identity for documentary videos and 9:16 shorts. Warm, desaturated, journalistic. Source of truth for FFmpeg overlay colors, typography, and color grading.
version: alpha

colors:
  text-primary: "#F5F0E8"
  text-accent: "#C9A96E"
  card-bg: "#140F0A"
  overlay-bg: "rgba(20, 15, 10, 0.85)"
  grade-shadow: "#1A0F0A"
  vignette: "rgba(0,0,0,0.4)"
  caption-bg: "rgba(0,0,0,0.75)"
  caption-text: "#F5F0E8"

typography:
  title:
    fontFamily: Cormorant Garamond
    fontWeight: "700"
    fontSize: 72px
    lineHeight: 84px
    letterSpacing: -0.02em
    note: "Case title cards, victim name overlays. Devanagari fallback: Noto Serif Devanagari Bold."
  title-italic:
    fontFamily: Cormorant Garamond
    fontWeight: "400"
    fontStyle: italic
    fontSize: 54px
    lineHeight: 64px
    note: "Victim name card in longform cold open."
  body:
    fontFamily: Inter
    fontWeight: "400"
    fontSize: 36px
    lineHeight: 48px
    note: "Facts, dates, statistics, location stamps."
  caption:
    fontFamily: Noto Sans Devanagari
    fontWeight: "400"
    fontSize: 42px
    lineHeight: 54px
    note: "Shorts subtitle/caption track. Must render Devanagari. 9:16 safe zone bottom third."
  label:
    fontFamily: Inter
    fontWeight: "500"
    fontSize: 28px
    lineHeight: 36px
    letterSpacing: 0.04em
    note: "Source attribution, timestamp stamps, lower-thirds."

spacing:
  unit: 8px
  safe-margin-16x9: 80px
  safe-margin-9x16: 60px
  name-card-top: 560px
  caption-bottom: 120px
  lower-third-bottom: 140px

components:
  name-card:
    backgroundColor: "{colors.overlay-bg}"
    textColor: "{colors.text-primary}"
    accentColor: "{colors.text-accent}"
    typography: "{typography.title-italic}"
    duration: 4.0s
    position: "centered, lower third"
  location-stamp:
    textColor: "{colors.text-accent}"
    typography: "{typography.label}"
    fadeIn: 0.3s
    position: "bottom-left, above lower-third"
  caption-bar:
    backgroundColor: "{colors.caption-bg}"
    textColor: "{colors.caption-text}"
    typography: "{typography.caption}"
    position: "bottom 120px, 9:16 safe zone"
  quote-card:
    backgroundColor: "{colors.overlay-bg}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body}"
    duration: 5.0s
  source-label:
    textColor: "{colors.text-accent}"
    typography: "{typography.label}"
    position: "bottom-right corner"
---

## Overview

These are the video output design tokens — they govern what FFmpeg renders into the actual MP4 files, not the control room UI. See `frontend/DESIGN.md` for the control room.

The aesthetic is **warm documentary film**: desaturated, lifted blacks, amber tones. Influenced by Indian photojournalism and documentary series like Sanjay Kak's work. Anti-sensational, anti-tabloid. Every visual choice should feel like a serious Indian news documentary, not a true-crime YouTube thumbnail.

Managed in code: `src/video/palette.py` (Python constants) and `src/video/templates.py` (overlay drawing).

## Colors

**Video palette is warm-shifted from neutral:**
- Text: cream `#F5F0E8` — not pure white, reduces harshness against dark backgrounds
- Accent: muted gold `#C9A96E` — used for victim names, location stamps, source labels. NOT yellow, NOT orange. Muted.
- Card background: dark warm near-black `#140F0A` — warmer than pure black, matches color grade
- Overlay: 85% opacity (`rgba(20, 15, 10, 0.85)`) for name cards and quote cards

**Color grading applied to all B-roll clips:**
- Warm temperature shift: `+10` to red channel, `-10` to blue
- Saturation reduction: `×0.85` (15% desaturation)
- Shadow lift: `+26` to all channels below threshold 64 — lifts blacks, reduces crush
- Apply via `src/video/palette.apply_warm_grade(frame)`

All B-roll goes through this grade before compositing. Never use raw ungraded footage in the final video.

## Typography

Two typefaces in the video:
- **Cormorant Garamond** — editorial, authoritative. Case titles, victim names. Loaded from `/usr/share/fonts/` on the render host.
- **Inter** — neutral, readable at motion. Facts, stats, lower-thirds.
- **Noto Sans Devanagari** — Hindi captions in shorts. Must be present for shorts_assembler_agent to render caption text correctly.

Font size guide (1920×1080 render):
- Title cards: 72px
- Name cards: 54px italic
- Lower-thirds body: 36px
- Labels/stamps: 28px

Shorts (1080×1920) use same sizes — the narrower frame means text fills more horizontal width; do not scale down.

## Video Specs

**Longform:**
- Resolution: 1920×1080 (16:9)
- FPS: 30
- Codec: libx264 / AAC
- Bitrate: 4000k video
- Container: MP4

**Shorts (per episode):**
- Resolution: 1080×1920 (9:16)
- FPS: 30
- Codec: libx264 / AAC
- Container: MP4
- Blur-box technique: 16:9 source blurred and stretched to fill 9:16 background; original 16:9 clip centered as foreground

## Audio Levels

Voice-over sits at `-6 dBFS`. Music is a support layer, never foreground:

| Section | Music level |
|---|---|
| COLD OPEN | sparse (20%) |
| THE CRIME | silence — voice + room tone only |
| INVESTIGATION | low (30%) |
| AFTERMATH | sparse (20%) |
| CLOSE | sparse (20%) |

Music target: `-24 LUFS`. Never let music compete with narration. When in doubt, less music.

## Overlay Timing

- Name card duration: 4.0s
- Quote card duration: 5.0s
- Location stamp fade: 0.3s
- Ken Burns zoom: 8% over clip duration
- Crossfade between clips: 0.5s

## Do's and Don'ts

**Do:**
- Apply warm grade to every B-roll clip before compositing
- Use cream + gold palette for all overlays — never white text on dark
- Keep name cards in the lower third, never centered vertically
- Show source attribution (location, date) where factually grounded
- Use silence intentionally — THE CRIME section has no music by design

**Don't:**
- Use pure white text (`#FFFFFF`) — use cream `#F5F0E8`
- Use bright saturated colors anywhere in overlays
- Add music during crime reconstruction sections
- Use jump cuts — minimum crossfade 0.5s
- Add watermarks, channel logos, or subscribe buttons in the produced video (those go on YouTube post-upload)
