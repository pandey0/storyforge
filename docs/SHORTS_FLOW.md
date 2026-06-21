# Shorts Track — Complete Flow & Edit Semantics

This document covers the shorts (vertical 9:16 reel) track end-to-end: every
step, every place an operator can intervene, exactly what happens when they
do, and which steps have NO override/validation yet (honest gaps, not implied
coverage). See `docs/TRACKER.md` Phase 19/20/21 for the build history behind
each piece referenced here.

Longform and shorts are independent tracks (`docs/SAAS_DESIGN.md` §2) — they
share only Research and Characters, then fork completely. This doc is shorts
only; see the equivalent longform steps in `TRACKER.md` Phase 21 if needed.

---

## 0. Case creation

Operator picks a **Channel Profile** (niche + language) when creating the
case — `frontend/app/shorts/new/page.tsx`. Currently one profile exists
(`indian-true-crime-hindi`), so this is a single-option dropdown today, but
the field is real (`channel_profile_id` on the `Case` row) — a second niche
is a new DB row, not a code change.

---

## 1. Research (shared with longform)

**AI does:** `case_research_agent.py` scrapes Indian Kanoon, news archive,
Wikipedia → `data/cases/{slug}/research.json`.

**Edit it:** the dashboard's Research step now has an editable JSON textarea
(not read-only). Saving writes `data/cases/{slug}/research_manual.json`,
which takes priority over the AI-generated file for **every** downstream
consumer — episode planner, episode script writer, character extraction, and
publish description all read through `src/pipeline/research_loader.py`,
which checks the manual file first.

**What happens when you edit it:**
1. Save → checkpoint `research` flips to `human_edited`.
2. A structural sanity check always runs (case name present, at least one
   real content field non-empty). If the edit was human-made, an additional
   Gemini coherence check runs too ("does this still look like real case
   research, not corrupted/spam"). Checkpoint flips to `ai_validated` or
   `ai_flagged`.
3. Operator can Approve/Reject via the checkpoint badge. **This does not
   block anything downstream** — it's a visible status, not a gate. Nothing
   re-runs automatically.
4. **No cascade**: if you edit research *after* the Episode Plan already
   ran, the plan does NOT regenerate automatically. You must manually re-run
   the Episode Plan step to pick up the research edit. Same for any
   already-written episode scripts.

Revert: delete the manual override (button next to Save) to fall back to
the AI-generated `research.json`.

---

## 2. Characters (shared with longform)

**AI does:** `character_agent.py` extracts named people from research +
script, infers a role, generates a DALL-E portrait if no real photo found.

**Edit it:** full CRUD already existed before this phase (add/edit
role+notes/delete/swap photo) — `/cases/{slug}` Characters tab.

**What happens when you edit it:**
1. Any add/edit → checkpoint `characters` flips to `human_edited`.
2. "Validate characters" button runs a Gemini check: does each person's role
   still plausibly fit what's in the research? Flags mismatches but never
   blocks.
3. Approve/Reject is **advisory only**. If you skip approval entirely,
   `scene_image_agent.py` and `shorts_assembler_agent.py`'s character-photo
   matching still work exactly as before — they just log a warning
   ("Using unapproved character set for {slug}...") instead of refusing to
   run. True-crime accuracy matters, but one unverified character shouldn't
   halt episode production.

---

## 3. Episode Plan (shorts only — no longform equivalent)

**AI does:** `episode_planner_agent.py` reads the *entire* research file and
decides, from scratch, how many episodes this case supports and what each
covers. No fixed menu, no fixed count — a thin case might get 3 episodes, a
rich one 8+. Output: `data/cases/{slug}/shorts_plan.json`, an array of cards:
`{slug, label, hook_text, angle, broll_query, role_hint, cta}`.

**Edit it:** **none yet.** This is the one major step in the shorts track
with no manual-override file, no editor UI, no validator, no checkpoint at
all — unlike Research, the plan can only be regenerated wholesale by
re-running the step, not hand-edited. (If you need to tweak one episode's
angle, the closest workaround today is editing that specific episode's
script after the fact — see step 4 — since the script step doesn't re-read
the plan card on every run, only at generation time.)

**What happens when you re-run it:** the entire `shorts_plan.json` is
overwritten. Any already-written episode scripts/audio/video for episodes
that no longer exist in the new plan become orphaned files (not auto-deleted,
not auto-relinked) — check the Episodes grid against the new plan before
assuming an old episode still applies.

---

## 4. Episode Script (one per planned episode)

**AI does:** `shorts_script_agent.py` writes a fresh standalone 120-180 word
script per plan card — HOOK / FACT / REVEAL / CTA — using the full research
context plus that card's specific `angle`. Each episode is written
independently; later episodes are told explicitly not to re-narrate earlier
plot points already covered by an earlier episode's angle.

**Edit it:** you can re-run a single episode (`run_single`) without touching
the others. There is **no manual text-override file** for episode scripts
(unlike the longform script's `script_manual.md`) and **no QA agent runs on
shorts scripts at all** — `qa_agent.py` only validates the longform script.
There is no checkpoint for this step either.

**What happens when you re-run one episode:** only that episode's `.md` file
is overwritten (`ep{NN}_{slug}.md`); the episode numbering is preserved by
matching the existing filename, so re-running doesn't shuffle other episodes.

---

## 5. Episode Audio (TTS, per episode)

**AI does:** Sarvam Bulbul v2 per episode script → `ep{NN}_{slug}.mp3` +
`ep{NN}_{slug}_timings.json`. Voice/pace/pitch/loudness are configurable per
case (not per episode) via the step config panel — reachable from each
episode page via "⚙ Voice, pace, pitch & loudness settings".

**What happens after every generation (automatic, not optional):**
1. `audio_validator.py` runs three deterministic checks — no LLM, just
   ffprobe/ffmpeg: duration sanity (30-150s range for shorts), silence gaps
   over 5s, loudness outside -35dB to -5dB.
2. Result recorded against checkpoint `shorts_tts_{episode_slug}` — **one
   checkpoint per episode**, not shared across the case (this was a real bug
   in the first cut of this feature — locking in episode 1 was silently also
   approving episode 2-4's unrelated audio; fixed before this doc was
   written).
3. Advisory only — a flagged result never blocks anything, just shows on the
   episode's audio checkpoint badge.

**Edit it:** per-segment replace. `word_timings.json` segments are
paragraph/section-level (not word-level). Each episode page lists its
segments with a file-upload "Replace" control. Uploading a clip:
1. Splices the new clip into that segment's `[start_sec, end_sec)` window
   via ffmpeg (trim-before + new clip + trim-after + concat).
2. **Shifts every subsequent segment's timing** by the duration delta, so
   captions in the assembled video stay in sync with the new audio length.
3. Re-runs the same three deterministic checks automatically, records
   against the same per-episode checkpoint.

---

## 6. Episode Assemble (final 9:16 render, per episode)

**AI does:** `shorts_assembler_agent.py` — blur-box vertical crop, hook frame
(card's `hook_text`, first 3s), burned-in captions from timings, b-roll
(card's `broll_query`, Pexels) or character photo (card's `role_hint`,
matched by name against `CaseCharacter` rows) per the priority chain,
loudness normalize, final encode.

**Edit it (EDL — Edit Decision List):** per-segment override of which b-roll
clip / character photo / scene image plays. Two ways to set a source: pick
from existing assets already on disk, or **upload a new one directly**
(file input next to the picker).

**What happens when you edit + save:**
1. Saving (`PUT /api/edl/{slug}`) writes the override to disk immediately,
   but **it is not yet active**. Checkpoint `edl_shorts_{episode_slug}`
   flips to `human_edited`.
2. "Run advisory check" (optional, informational only): image overrides get
   a Gemini Vision description + a fit-check against the segment; video
   overrides just get an ffprobe validity check (no per-frame content
   check — too expensive/unreliable to do cheaply). Never blocks the next
   step.
3. **"Lock In Overrides"** — a separate explicit action
   (`POST /api/checkpoints/{slug}/edl_shorts_{episode_slug}/approve`). Until
   you click this, the assembler ignores everything you saved and falls back
   to its normal automatic selection — saved is not the same as active.
4. This checkpoint is **per episode**, same fix as the audio one above —
   locking episode 1's overrides has zero effect on episode 2's.
5. Editing the EDL again after locking resets the checkpoint to
   `human_edited` — you must re-lock after any further change, it doesn't
   stay silently approved forever.

A case that never opens the EDL editor at all pays zero cost for this
feature — the very first check in `get_segment_override` is "is there a
saved EDL file at all", and if not, it returns immediately before any
database/checkpoint lookup happens.

---

## 7. After assembly — what's NOT built yet

- **No publish step for shorts.** `publish_agent.py` (YouTube upload) is
  longform-only in `ORDERED_PIPELINE` — finished shorts episodes are
  uploaded manually outside this dashboard today.
- **No full video patch-editing.** If you need to fix something in an
  already-assembled episode beyond what EDL covers, you re-run the whole
  assemble step for that episode — there's no cheap way to patch one piece
  of the rendered mp4 (the ffmpeg-concat assembly architecture doesn't
  support that cheaply; flagged as real future work, not attempted).

---

## Quick reference — checkpoint step names used by the shorts track

| Step | Checkpoint step name | Scope |
|---|---|---|
| Research | `research` | per case (shared) |
| Characters | `characters` | per case (shared) |
| Episode Plan | *(none)* | — |
| Episode Script | *(none)* | — |
| Episode Audio | `shorts_tts_{episode_slug}` | **per episode** |
| Episode Assemble / EDL | `edl_shorts_{episode_slug}` | **per episode** |

All of these live in one shared table (`step_checkpoints`,
`src/pipeline/checkpoints.py`) — every step plugs into the same
`ai_generated → human_edited → ai_validated/ai_flagged → human_approved/rejected`
state machine instead of inventing its own.
