# Indian Crime Channel — Master Reference

> Last updated: 2026-06-20 (SaaS-shaped re-architecture pass)
> Source of truth for all product, technical, and creative decisions.
> Update this file whenever a decision changes.
> Architectural decisions must also satisfy `docs/SAAS_DESIGN.md`.

---

## 1. Product Vision

**What:** Automated **Hindi-language** Indian true-crime content engine producing TWO
independent product lines from the same research:

1. **Longform** — 30–45 min documentary-style YouTube videos
2. **Shorts** — 7 episodic 9:16 vertical reels per case, standalone, not condensed from longform

**Gap being filled:** No serious, well-researched Hindi-language coverage of Indian crime
with journalistic depth. Existing options are tabloid-style or shallow.

**Target audience:** 600M+ Hindi speakers — India + diaspora.

**Positioning:** "The Netflix documentary about Indian crime — in Hindi, on YouTube."

**Case/topic is data, not code.** Any case can be loaded — the pipeline, agents, and
schema carry no reference to a specific case. See `docs/SAAS_DESIGN.md` §1.

---

## 2. Creative Direction

### 2.1 Model Channels
| Channel | What We Steal |
|---------|--------------|
| MrBallen | Silence as weapon. Specificity. Never-dramatic = credible. |
| Eleanor Neale | Victim-first opening. Warmth. Emotional authenticity. |
| Nexpo | Cinematic depth. Long-form patience. Visual restraint. |

### 2.2 Format
| | Longform | Shorts |
|---|---|---|
| Length | 30–45 min | 60–90s × 7 episodes |
| Language | Hindi (Devanagari) | Hindi (Devanagari) |
| Source | `research.json` → full script | `research.json` → per-episode script (fresh, not condensed) |
| Structure | 9-section documentary arc | 7 fixed episode topics (who/accused/evidence/trial/verdict/systemic/now) |

### 2.3 Longform Script Structure
```
[COLD OPEN]      Victim as a human. Specific detail. No crime yet.
[THE BREAK]      The moment it changed. Present tense.
[WORLD BUILDING] Victim's full life, relationships, context.
[THE CRIME]      Reconstruction from evidence + reports. Present tense.
[INVESTIGATION]  Police, CBI, suspects, twists, failures.
[LEGAL BATTLE]   Courts, delays, acquittals — Indian system.
[AFTERMATH]      Families, protests, what changed.
[SYSTEMIC ANGLE] What this case reveals about India.
[CLOSE]          Unresolved questions. No tidy bow.
```

### 2.4 Shorts Episode Topics (fixed across all cases)
```
1. who_was_the_victim   — hook + humanize, no crime detail yet
2. the_accused          — who they were, why suspected
3. the_evidence         — what investigators found
4. the_trial            — courtroom, legal battle
5. the_verdict          — outcome, sentencing
6. systemic_angle       — what this reveals about the system
7. where_are_they_now   — aftermath, present day
```
Each is written fresh from `research.json` — never condensed from the longform script.
Per-topic Gemini prompt guidance + CTA teasers live in `shorts_script_agent.py` as data,
keyed by topic slug, applied identically regardless of which case is loaded.

### 2.5 Narration Voice (both tracks)
- Tone: Journalistic + storyteller hybrid, in Hindi
- Tense: Past for background. **Present tense** during crime reconstruction.
- Never: Announcer voice, melodrama, sensationalism, Hinglish, संस्कृतनिष्ठ Hindi
- Always: Source citations woven in, cultural context, self-correction when uncertain
- Silence markers: `[PAUSE 3s]` at reveals — silence is the storytelling tool

### 2.6 Visual Design Language

**Color Palette** (longform b-roll grade, shorts grade filter):
```
Grade:        eq=saturation=0.85:brightness=0.03, colorbalance warm shift, vignette
NEVER:        Bright red text, neon, horror palette, red/black combo
```

**Shorts-specific visual sourcing** (see `docs/SAAS_DESIGN.md` §3 for the priority model):
```
1. Scene-specific AI image  — DALL-E 3, generated per segment from character
                              description + that segment's narration excerpt
                              (hook + reveal + character-matched segments only,
                              capped at 4/episode for cost control)
2. Character photo          — real photo or AI portrait, DB role match
3. Topic b-roll              — Pexels, fetched per fixed topic-query map
```

**Overlays:**
```
Name card:        Once per person. 4s. Fades. Never repeated.
Location stamp:   Bottom-left. "नई दिल्ली · 2019"
Hook frame:        Shorts only — first 3s, large Hindi topic title
Captions:          Shorts only — burned-in, time-gated from word timings
```

### 2.7 Thumbnail Formula
```
Base image:   Real photo (victim, location, document) or DALL-E 3 generated
Text:         Max 5 words, Hindi, cream color
Grade:        Match video warm palette
NOT:          Shocked face, red text, crime-scene-tape graphics
```

---

## 3. Case Selection

Cases are **data, loaded through the dashboard** (`POST /cases`), not hardcoded.
Selection criteria (applied by the operator when picking what to load):
- Documented evidence available (court records, news archive)
- Victim's humanity can be centered
- Has systemic/cultural angle beyond the crime itself
- Indian legal system played a significant role
- AVOID: living minor victims, families who've asked for privacy

No fixed case list lives in code or docs — see `docs/SAAS_DESIGN.md` §1 on why.

---

## 4. Technical Architecture

### 4.1 Two Independent Tracks

```
research.json (shared — the ONLY thing both tracks read)
        │
        ├──► characters step (shared, runs once)
        │      extract people → DB → real photo search → DALL-E 3 portrait gap-fill
        │
        ├──► LONGFORM TRACK (independent)
        │      script → human_review gate → broll → tts → assemble → thumbnail
        │      → video_final.mp4 (16:9, 30-45min)
        │
        └──► SHORTS TRACK (independent, per-episode)
               shorts_script → shorts_tts → shorts_assemble
               → 7× {topic}.mp4 (9:16, 60-90s)
```

Neither track depends on the other's output. Either can run alone, in any order,
after `research` + `characters` complete. See `frontend/lib/pipeline.ts` `ORDERED_PIPELINE`
for the authoritative step graph and `docs/SAAS_DESIGN.md` §2 for why this separation
is enforced at the architecture level, not just convention.

### 4.2 Agents (`src/agents/`)
```
case_research_agent.py     research.json from Indian Kanoon + news + Wikipedia
character_agent.py         people extraction → DB → photo search → DALL-E 3 portraits
script_writer_agent.py     Longform: 30-45 min Hindi script (Gemini)
qa_agent.py                Script QA: tone, structure, factual flags
tts_agent.py                Sarvam Bulbul v2 → audio.mp3 + word_timings.json
broll_agent.py              Pexels fetch + cache, longform (per-section) + shorts (per-topic)
video_producer_agent.py     Longform assembly (ffmpeg)
thumbnail_agent.py          DALL-E 3 + Pillow overlay
publish_agent.py            YouTube Data API v3 upload + schedule
analytics_agent.py          YT analytics sync → DB
shorts_script_agent.py      7 standalone episode scripts from research.json (Gemini)
shorts_assembler_agent.py   Per-episode 9:16 assembly: blur-box, captions, scene overlay
scene_image_agent.py        Per-segment DALL-E 3 scene images (character + narration context)
```

### 4.3 Infrastructure Model
- Dashboard + pipeline: local machine, no server bill
- DB: Neon (Postgres, free tier, cloud-hosted, survives machine changes)
- Files: local `data/` folder
- Frontend: Next.js (control room UI)
- Backend: FastAPI (`src/api/`) — REST + SSE log streaming

### 4.4 Tech Stack
| Layer | Tool |
|-------|------|
| Language | Python 3.11+ |
| Frontend | Next.js + React |
| Backend API | FastAPI |
| DB | PostgreSQL (Neon) + SQLAlchemy |
| LLM (scripts) | Gemini 2.5 Flash |
| TTS | Sarvam Bulbul v2 (hi-IN) |
| Video | Pure FFmpeg (no MoviePy) |
| Thumbnails / portraits / scene images | DALL-E 3 + Pillow |
| B-roll | Pexels API |
| Upload | YouTube Data API v3 |

### 4.5 Database Schema (current — see `src/db/models.py` for authoritative source)
```sql
cases            id, slug, name, year_of_crime, location, victim_name, victim_age,
                 victim_profession, perpetrator, case_type, tier, parent_case_id,
                 case_version, pivot_step, status, notes
articles         id, source, title, content, url, story_score, case_id, processed
case_research    id, case_id, source_type, source_url, source_name, content, judgment_date
scripts          id, case_id, version, script_text, word_count, duration_est_min,
                 status, qa_notes, qa_attempts, approved_by
videos           id, case_id, script_id, video_path, thumbnail_path, audio_path,
                 render_status, yt_video_id, yt_url, scheduled_at, published_at
yt_analytics     id, video_id, date, views, watch_time_hrs, likes, comments, ctr, ...
case_characters  id, case_id, name, role, image_path, image_url, notes
broll_cache      id, query, file_path, source, license, duration_sec
pipeline_log     id, case_id, agent, action, status, message, duration_sec
```
`cases.parent_case_id` + `case_version` support branching a case (re-research, re-script)
without losing prior versions — see Phase 11 in `docs/TRACKER.md`.

### 4.6 Data Storage Structure
```
data/cases/{case_slug}/
├── research.json              ← shared by both tracks
├── characters/                ← shared: real photos + AI portraits
├── script_draft.md / script.md          ← longform track
├── audio/voiceover.mp3 + word_timings.json
├── broll/                     ← longform: {section}.mp4, shorts: {topic}.mp4
├── scene_images/{topic}/      ← shorts: per-segment DALL-E images + manifest.json
├── shorts/{topic}.md / .mp3 / _timings.json / .mp4   ← shorts track, per episode
└── output/video_final.mp4 + thumbnail.jpg            ← longform track
```

---

## 5. Revenue Strategy
- Primary: YouTube AdSense
- Mitigation: legal/educational framing, victim-first, no glorification
- Secondary: sponsorships from legal education platforms
- Shorts track exists specifically to drive discovery/subscriber funnel into longform

---

## 6. Key Risks
| Risk | Mitigation |
|------|-----------|
| Demonetization | Educational framing, victim-first, no sensationalism |
| Copyright strikes | Pexels for b-roll, DALL-E for generated imagery, no news footage |
| Script quality drift | QA Agent + human review gate before audio production |
| Cost creep on AI visuals | Scene images capped at 4/episode, cached after first generation |
