# Content Engine — Claude Harness

## Project Identity
General-purpose content production engine: research a subject → produce TWO
independent product lines: long-form documentaries (30–45 min) and shorts
(7 episodic 9:16 reels per case). NOT tied to one niche or language — what
genre/voice/structure/language gets produced is configured per **ChannelProfile**
(a DB row), not hardcoded in agent code. Single-operator tool, built with
SaaS-shaped internals — see `docs/SAAS_DESIGN.md`, read before designing any
new feature.

**Currently configured profile:** `indian-true-crime-hindi` — Hindi-language
Indian true crime, journalistic + warm documentary style, NOT tabloid. This is
the first and only seeded profile, not the product's identity. A second niche
(different language, different structure, different voice) is a new
`channel_profiles` row, never a code change — see "Niche Is Data Too" below.

## Two Independent Tracks
Only `research.json` (+ the shared `characters` step) is common. Past that fork,
**longform** and **shorts** never read each other's output — either must run to
completion alone. See `docs/SAAS_DESIGN.md` §2 and `frontend/lib/pipeline.ts`
(`ORDERED_PIPELINE`, `track` field) for the enforced graph.

## Case Is Data, Not Code
No case name belongs in agent logic, schema, or routing — cases are rows in the
`cases` table + files under `data/cases/{slug}/`.

## Niche Is Data Too
Genre, voice, language, section structure, and entity-role taxonomy are NOT
hardcoded constants in agent files — they live on `ChannelProfile`
(`src/db/models.py`), loaded per-case via `get_profile_for_case(slug)`
(`src/db/channel_profile.py`). Every case has a `channel_profile_id`. Agents
(`script_writer_agent.py`, `shorts_script_agent.py`, `character_agent.py`) read
`profile.voice_system_prompt`, `profile.section_headers`, `profile.shorts_topics`,
`profile.entity_roles`, etc. — never a module-level dict of niche content.
**Never add a new hardcoded niche/genre/language literal to agent code** —
add a `channel_profiles` row instead (see `src/db/seed_default_profile.py` for
the pattern). Known remaining coupling points NOT yet generalized (flagged, not
silently dropped — see `docs/SAAS_DESIGN.md` §4 "no silent caps"):
- `character_agent.py`'s `ROLE_STRONG_SIGNALS` and `_generate_ai_portrait`'s
  `_ROLE_DESC` dict — still crime-specific, not profile-driven.
- `character_agent.py`'s Hindi name-detection regex (`_DEVANAGARI_WORD`,
  `_HINDI_NAME_SUFFIXES`) — language-coupled, not niche-coupled; degrades to
  Latin extraction for non-Hindi content but isn't itself configurable per profile.
- `case_research_agent.py` — scraper logic (Indian Kanoon/CBI/NCRB) is still
  India/crime-specific Python code, not data. `ChannelProfile.research_sources`
  is seeded informationally but not yet wired into actual scraping behavior.
- No profile-picker UI in case-creation forms yet — new cases silently default
  to the one seeded profile via `get_profile_for_case`'s fallback.
- `tts_agent.py` hardcodes `target_language_code: "hi-IN"` and a fixed Sarvam
  Bulbul speaker list — not yet sourced from `profile.language`. A non-Hindi
  profile would currently still get Hindi TTS; this needs a follow-up pass.

## Voice/Philosophy Belongs to the Profile, Not This File
The crime-specific philosophy, script voice, and narration examples that used
to live here are now `indian-true-crime-hindi`'s `voice_system_prompt` field in
the DB (`src/db/seed_default_profile.py` has the readable source). Reading
that profile's content for reference:
- Victim-first, silence-over-music, journalistic citations, present-tense crime
  reconstruction, Hindi register rules — all still true for THAT profile, never
  hardcoded as universal rules a different profile must also follow.
- Shorts scripts are written FRESH from `research.json` per episode topic —
  never condensed from the longform script. This IS a structural rule
  (`shorts_script_agent.py`'s design), true across any profile.

To see or edit the current profile's exact voice text: query the `channel_profiles`
table for slug `indian-true-crime-hindi`, or read
`src/db/seed_default_profile.py`'s `VOICE_SYSTEM_PROMPT` constant (the seed
source — editing it after the row already exists requires an UPDATE, not
re-running the seed script, which skips existing rows).

## Manual Script Override
If you write a script manually, save it to:
`data/cases/{case_slug}/script_manual.md`
The pipeline prefers this file over the AI-generated draft when it exists.
See `src/agents/script_writer_agent.py` — `_load_script()` checks manual path first.

## Tech Stack
- Language: Python 3.11+
- Frontend: Next.js + React (control room) — `frontend/`
- Backend: FastAPI — `src/api/` (REST + SSE log streaming)
- DB: PostgreSQL (Neon) + SQLAlchemy
- LLM: Gemini 2.5 Flash — scripts (longform + shorts), prompted per `ChannelProfile`
- TTS: Sarvam Bulbul v2 (currently hardcoded hi-IN — see gap list above)
- Video: Pure FFmpeg (no MoviePy)
- Images: DALL-E 3 + Pillow — thumbnails, character portraits, per-segment scene images
- B-roll: Pexels API
- Upload: YouTube Data API v3
- Storage: Local `data/` directory

## Agent Architecture
```
case_research_agent.py     research.json: Indian Kanoon + news archive + Wikipedia
character_agent.py         shared: people extraction → DB → photo search → DALL-E portraits
script_writer_agent.py     longform: 30-45 min Hindi script
qa_agent.py                longform: tone/structure/factual QA
tts_agent.py                Sarvam Bulbul → audio + word timings
broll_agent.py              Pexels fetch+cache, longform (per-section) + shorts (per-topic)
video_producer_agent.py     longform: ffmpeg assembly, 16:9
thumbnail_agent.py          DALL-E 3 + Pillow overlay
publish_agent.py            YouTube upload + schedule
analytics_agent.py          YT analytics → DB sync
shorts_script_agent.py      shorts: 7 standalone episode scripts from research.json
shorts_assembler_agent.py   shorts: per-episode 9:16 assembly (blur-box, captions, scene overlay)
scene_image_agent.py        shorts: per-segment DALL-E scene images (character + narration context)
```

## Data Sources (Authoritative)
See docs/DATA_SOURCES.md for full list.
Primary: Indian Kanoon (judgments), NCRB reports, CBI press releases, LiveLaw, NDTV Crime RSS.

## Directory Structure
```
/
├── CLAUDE.md                 ← this file, always read first
├── docs/
│   ├── SAAS_DESIGN.md        ← design philosophy — read before any new feature
│   ├── MASTER_REFERENCE.md   ← full project bible
│   ├── TRACKER.md            ← build progress tracker (update constantly)
│   ├── DATA_SOURCES.md       ← all data sources with exact URLs
│   └── ARCHITECTURE.md       ← technical diagrams + decisions
├── data/
│   ├── cases/{slug}/         ← research.json, characters/, script/, audio/, broll/,
│   │                            scene_images/, shorts/, output/ — see ARCHITECTURE.md §4.6
│   ├── reports/              ← downloaded PDFs: NCRB, CBI reports
│   ├── news/                 ← cached news articles (avoid re-scraping)
│   └── raw_judgments/        ← Indian Kanoon judgment text files
├── frontend/                 ← Next.js control room (lib/pipeline.ts = step graph source of truth)
└── src/
    ├── agents/               ← agent implementations (see Agent Architecture above)
    ├── api/                  ← FastAPI routes, background jobs, ops agent
    ├── pipeline/             ← CaseState, orchestration
    ├── db/                   ← SQLAlchemy models + session
    └── scrapers/              ← source-specific scrapers
```

## Current Build Phase
See docs/TRACKER.md — updated in real time.

## Rules for Claude Working in This Project
1. Always check TRACKER.md before starting work — don't duplicate completed tasks
2. Any new architectural decision → update MASTER_REFERENCE.md + TRACKER.md, and
   confirm it satisfies docs/SAAS_DESIGN.md (track independence, case-as-data, etc.)
3. Any new data source discovered → add to DATA_SOURCES.md immediately
4. Scripts written → save to data/cases/{case_id}/script.md
5. Case research → save to data/cases/{case_id}/research.json
6. Never hardcode API keys — use .env + python-dotenv
7. Never commit secrets — .env is in .gitignore
8. Video quality > automation speed. Review before publish for first 50 videos.
9. Never hardcode a case name, niche, or language literal into agent logic, schema,
   or routing — case is data. Content-format constants (topic lists, section
   structures) are fine; they apply identically to every case.
