# Build Tracker

> Updated: 2026-06-16
> Update status immediately when work starts/completes.
> Status: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked

---

## PHASE 0 — Foundation (Current Phase)
*Get the project scaffold, docs, and harness in place.*

- [x] Define channel philosophy and creative direction
- [x] Decide tech stack
- [x] Create project directory structure
- [x] Write CLAUDE.md harness document
- [x] Write MASTER_REFERENCE.md
- [x] Write DATA_SOURCES.md (all authoritative sources + URLs)
- [x] Write TRACKER.md (this file)
- [x] Write ARCHITECTURE.md (local+cloud diagram, DB schema, file structure)
- [x] Write .gitignore
- [x] Write .env.example (Neon + R2 + all free APIs documented)
- [x] Write requirements.txt
- [x] Decided: Dashboard = local Streamlit. DB = Neon free. Storage = R2 free 10GB.
- [ ] SETUP: Create Neon account + project → neon.tech (free, no card needed)
- [ ] SETUP: Create Cloudflare account + R2 bucket → dash.cloudflare.com (10GB free)
- [ ] SETUP: Get API keys (Pexels, Pixabay, NewsAPI, Indian Kanoon) — all free
- [ ] SETUP: Copy .env.example → .env, fill Neon DATABASE_URL + R2 credentials
- [ ] SETUP: `pip install -r requirements.txt`
- [x] BUILD: `src/db/init.sql` — full schema, 7 tables + 10 seed cases
- [x] BUILD: `src/db/models.py` — 8 SQLAlchemy ORM models, typed Mapped columns
- [x] BUILD: `src/db/session.py` — NullPool, Neon SSL handling, get_session ctx mgr, init_db
- [ ] VERIFY: `psql $DATABASE_URL -c "\dt"` — confirm Neon tables created
- [ ] VERIFY: R2 boto3 upload test — confirm storage works

---

## PHASE 1 — Data Pipeline
*Get news flowing in and case data saving to disk.*

### 1A. News Scraper
- [x] `src/scrapers/rss_monitor.py` — 10 feeds, score, dedup, DB save, raw JSON cache
- [x] `src/scrapers/news_api.py` — NewsAPI wrapper, 100/day counter, 5 crime queries, dedup
- [x] `src/scrapers/indian_kanoon.py` — API client, cache, tenacity retry, judgment downloader
- [x] Story scoring algorithm (HIGH_SCORE_KEYWORDS cap 0.60 + Indian kw + source quality + recency)
- [x] Dedup logic (exact URL + 70% title word overlap)
- [x] Save raw articles to `data/news/{source}_{date}.json`

### 1B. Case Research Agent
- [x] `src/agents/case_research_agent.py` — Indian Kanoon + NewsAPI + Wikipedia → research.json + DB
- [x] `src/scrapers/ncrb_downloader.py` — streams PDFs, pdfplumber extract_stats, skip 404
- [x] `src/scrapers/cbi_scraper.py` — daily HTML cache, 2s delay, graceful non-200 handling

### 1C. Database
- [x] `src/db/models.py` — 8 SQLAlchemy ORM models, typed Mapped columns
- [x] `src/db/init.sql` — full schema + 10 seed cases
- [x] `src/db/session.py` — NullPool, Neon SSL, get_session, init_db
- [ ] `src/pipeline/state.py` ← DONE (moved here from pipeline section)
- [x] `src/pipeline/state.py` — CaseState dataclass, CaseStatus literal, from_db_case, case_dir

---

## PHASE 2 — Script Generation
*Turn case research into documentary-quality scripts.*

### 2A. Script Agent
- [x] `src/agents/script_writer_agent.py` — Claude Sonnet + prompt caching, 9-section structure, victim-first enforced in system prompt
- [x] System prompt (105 lines) — voice/tone, tense rules, pause markers, prohibitions, cultural awareness
- [x] Structure validator (all 9 headers), word count validator (4500–6750), one retry with REVISION prefix
- [x] Fixed: research JSON key mismatch (`sources.indian_kanoon` / `sources.news_archive` / `sources.wikipedia`)

### 2B. QA Agent
- [x] `src/agents/qa_agent.py` — 5 rule-based checks, no LLM cost, max-3-retry loop, fixed word count warn-vs-fail
  - Checks: victim-first opening, no sensationalism, source citations present
  - Checks: PAUSE markers inserted, present-tense during crime sections
  - Checks: Cultural context woven in, no assumptions about audience
  - Output: pass/fail + notes → loops back to ScriptAgent if fail
- [x] Auto-fix loop (max 3 retries before human flag) — in qa_agent._update_db

### 2C. Human Review Gate
- [ ] Dashboard page: script side-by-side with research.json
- [ ] Approve / reject buttons in Streamlit
- [ ] Status flag: `APPROVED` / `NEEDS_REVISION`

---

## PHASE 3 — Audio Production
*Script → voiceover audio with timestamps.*

- [x] `src/agents/tts_agent.py` — ElevenLabs chunked (2500 char), FFmpeg merge, ffprobe timing estimation
  - Voice: George (`JBFqnCBsd6RMkjVDRZzb`), speed 0.92x, eleven_multilingual_v2
  - `[PAUSE Xs]` → SSML `<break time="Xs"/>`, [SOURCE:...] stripped
  - Single-chunk short-circuit (no FFmpeg if 1 chunk)
  - Output: `audio/voiceover.mp3` + `audio/word_timings.json`
- [x] `src/video/audio_mixer.py` — FFmpeg sidechain compress duck, SFX adelay timing, loop music to vo duration
- [x] `src/video/palette.py` — all color constants, section→music intensity map, apply_warm_grade (BGR-correct)

---

## PHASE 4 — Video Production
*Audio + B-roll + overlays → rendered video.*

### 4A. B-Roll Agent
- [x] `src/agents/broll_agent.py` — Pexels+Pixabay, DB cache, section→query lambdas, streamed download
- [x] Keyword extractor (capitalised words, INDIAN_CITIES set, CRIME_NOUNS set)
- [x] Color grade in `palette.apply_warm_grade` (BGR-aware warm grade)

### 4B. Video Templates
- [x] `src/video/templates.py` — all 8 functions: name_card, location_stamp, quote_card, title_card, timeline, vignette, ken_burns, crossfade
- [x] All colors/fonts from palette.py, no hardcoded hex, font fallback via _load_font

### 4B. Video Templates
- [ ] `src/video/templates/`
  - `name_card.py` — person introduction overlay
  - `location_stamp.py` — bottom-left location/date
  - `timeline_graphic.py` — horizontal timeline
  - `quote_card.py` — full-screen victim quote
  - `map_overlay.py` — India map with location marker
  - `title_card.py` — case title open card
- [ ] Font installation (Cormorant Garamond, Inter)
- [ ] Color palette constants (`src/video/palette.py`)

### 4C. Video Assembly
- [x] `src/video/assembler.py` — VideoCreator: cold open, per-segment clips, warm grade (BGR-aware), vignette, overlays, crossfade, FFmpeg H.264 1080p 4000kbps
- [x] Ken Burns effect (in templates.py)
- [x] Cross-dissolve transition (in templates.py)
- [x] Fixed: temp dir race condition — mixed audio now written to persistent `data/cases/{slug}/audio/`

### 4D. Thumbnail Agent
- [x] `src/agents/thumbnail_agent.py` — DALL-E 3 + Pillow overlay, 1280×720 JPG, font fallback chain, warm gradient overlay
- [x] `src/agents/video_producer_agent.py` — coordinator: TTS → B-roll → VideoCreator → Thumbnail in sequence

---

## PHASE 5 — Distribution
*Video → YouTube, scheduled.*

- [x] `src/agents/publish_agent.py` — YouTube Data API v3 OAuth2, resumable upload, thumbnail set, IST→UTC schedule, DB update
- [x] Fixed: `build_description` now extracts URLs from nested research.json sources dict
- [ ] YouTube quota manager (6 vids/day free tier) — monitor manually for now
- [ ] Playlist manager — post-launch

---

## PHASE 6 — Analytics & Dashboard
*Monitor everything. Know what's working.*

### 6A. Analytics Agent
- [x] `src/agents/analytics_agent.py` — YouTube Data API v3 stats sync, DB upsert, daily at 2 AM IST via orchestrator

### 6B. Dashboard (Streamlit)
- [x] `src/dashboard/app.py` — 7-page Streamlit app, DB-backed, 30s cache
- [x] Pages: Overview · Pipeline · Stories · Scripts · Videos · Analytics · Settings
- [x] Script approve/reject buttons in Scripts + Pipeline pages
- [x] Settings page: surgical .env line-replacement for pipeline config keys
- [ ] Human review gate for scripts (approve before TTS — currently manual via Scripts page ✓)

---

## PHASE 7 — Orchestration
*Tie everything together into a scheduled pipeline.*

- [x] `src/pipeline/orchestrator.py` — APScheduler 6 jobs, per-case error isolation, DB logging via PipelineLog
- [x] `main.py` — entry point: loads .env, init_db(), starts orchestrator
- [x] `assets/music/` + `assets/fonts/` directories created
- [x] Error handling: per-case try/except, failed cases get status="failed" + notes
- [ ] Slack/email alert on pipeline failure — post-launch

---

## PHASE 8 — First Video (Integration Test)

- [x] **Case: Jessica Lall Murder Case**
- [x] Run CaseResearchAgent → research.json
- [x] Review research quality
- [x] Run ScriptAgent → script_draft.md (Gemini 2.5 Flash, Hindi, 9-section)
- [x] Human review + approve script
- [x] Run TTS → voiceover.mp3 (20.6 min, 63 chunks, Sarvam Bulbul anushka)
- [x] Run BRollAgent → colour card fallbacks (no Pexels/Pixabay keys yet)
- [~] Run VideoAssembler → video_final.mp4 (encoding in background)
- [ ] Run ThumbnailAgent → thumbnail.jpg (needs OPENAI_API_KEY)
- [ ] Manual upload (test before automating)
- [ ] Review: script quality, audio naturalness, visual coherence
- [ ] Iterate until satisfied

---

## PHASE 9 — Quality Improvements (Round 1)
*Fixes identified from first video review.*

### 9A. TTS Pause Silence Gaps
- [x] `_split_with_pauses()` — detects `[PAUSE Xs]` markers, splits text at each
- [x] `_generate_silence_wav()` — FFmpeg `anullsrc` generates exact-duration WAV silence
- [x] `_clean_for_tts(keep_pauses=True)` — new param preserves pause markers during pre-clean
- [x] Updated `run()` — speech chunks + silence WAVs interleaved in order → merge → MP3
- [ ] Re-run TTS on Jessica Lall with pause gaps (will produce more natural audio)

### 9B. Character Image Pipeline
- [x] `CaseCharacter` DB model (`case_characters` table — name, role, image_path, image_url)
- [x] `src/agents/character_agent.py` — extracts named characters from research + script
  - Infers role (victim/accused/judge/lawyer/witness/family) from context
  - `add_image_from_url()` — downloads + saves to `data/cases/{slug}/characters/`
  - `add_image_from_file()` — copies uploaded file to characters dir
  - `get_character_image_map()` — returns {name: path} for BRollAgent
- [x] `BRollAgent` — checks character images FIRST before stock footage per segment
  - `_match_character_image()` — case-insensitive name match in segment text
- [x] `case_characters` table created in Neon
- [ ] Run CharacterAgent on Jessica Lall → extract characters
- [ ] Add character photos (Jessica Lall, Manu Sharma, Bina Ramani, etc.)

### 9C. Dashboard Pipeline Controls
- [x] Pipeline page: per-case expander with 7 step buttons (Research/Script/QA/TTS/Characters/B-Roll/Assemble)
- [x] Each button runs the step in-process, shows success/error
- [x] Characters page: view extracted characters, upload photo or paste URL per character, set role
- [x] Agent Chat page: Gemini-backed assistant, case context injected, full chat history
- [ ] Non-blocking background task support (long steps like Assemble run in thread)

---

## Agent Dependency Map

```
NewsMonitorAgent
    └─→ [DB: articles]
            └─→ CaseResearchAgent (manual trigger or scored threshold)
                    └─→ [DB: case_research] + [data/cases/{slug}/research.json]
                            └─→ ScriptWriterAgent
                                    └─→ QAAgent ──(fail)──→ ScriptWriterAgent
                                            └─(pass)──→ [HUMAN REVIEW GATE]
                                                            └─→ TTSAgent
                                                                    └─→ BRollAgent
                                                                            └─→ VideoProducerAgent
                                                                                    └─→ ThumbnailAgent
                                                                                            └─→ PublishAgent
                                                                                                    └─→ AnalyticsAgent
                                                                                                            └─→ Dashboard
```

---

---

## PHASE 10 — Next.js Control Room (Active Build)
*Replace Streamlit with Next.js + FastAPI. Add Windsurf-style active agent.*

### 10A. FastAPI Backend
- [x] `src/api/main.py` — FastAPI app, CORS, lifespan, static file mount for /files/cases
- [x] `src/api/routes/cases.py` — list, get, create, update status, file existence check
- [x] `src/api/routes/pipeline.py` — run step (background thread), job queue, approve/reject gate
- [x] `src/api/routes/logs.py` — SSE tail-then-stream, plus JSON tail endpoint
- [x] `src/api/routes/scripts.py` — get/save/delete manual override, list DB versions
- [x] `src/api/routes/characters.py` — CRUD + image URL download + multipart file upload
- [x] `src/api/routes/agent.py` — chat, status, execute action, monitor trigger
- [x] `src/api/agent/core.py` — PipelineAgent: Gemini 2.5 Flash, tool loop (max 6 iter), monitor(), execute_action()
- [x] `src/api/agent/tools.py` — 10 tools: get_all_cases, get_case_detail, get_pipeline_logs, get_script, get_file_tree, trigger_pipeline_step, read_source_file, propose_script_fix, get_recent_errors, get_all_jobs
- [x] `src/api/log_writer.py` — PipelineLogger: writes to {step}.log + pipeline.log with timestamps
- [x] `src/api/jobs.py` — thread-safe JOBS store: start_job, update_job, finish_job, get_job, get_all_jobs

### 10B. Next.js Frontend
- [x] `frontend/` — Next.js 16 App Router scaffold, TypeScript, Tailwind, shadcn/ui
- [x] Layout: Sidebar (220px fixed) + main + AgentPanel (320px fixed right)
- [x] `app/page.tsx` — Dashboard: 4 stats cards, in-production cards w/ PipelineStepper, queue list
- [x] `app/cases/page.tsx` — Cases list with status filter dropdown
- [x] `app/cases/new/page.tsx` — New case form, auto-slug from name
- [x] `app/cases/[slug]/page.tsx` — Case detail: Pipeline / Script / Characters / Audio / Video / Logs tabs
- [x] `components/LiveTerminal.tsx` — SSE streaming terminal, tail prefetch, LIVE/IDLE badge
- [x] `components/PipelineStepper.tsx` — compact (dot bar) + full (labeled dots) variants
- [x] `components/AgentPanel.tsx` — always-visible right panel: action cards + chat + tool call pills
- [x] `components/ActionCard.tsx` — severity-colored approve/dismiss cards
- [x] `components/FileStatusGrid.tsx` — 8-file artifact grid, auto-refresh 10s
- [x] `components/Sidebar.tsx` — nav + live running-jobs list (5s refresh)
- [x] Build verified: `npm run build` passes clean, 0 type errors

### 10C. Active Agent
- [x] Gemini 2.5 Flash with function calling (tool loop, not chatbot)
- [x] 10 tools including trigger_pipeline_step, read_source_file (sandboxed to src/), propose_script_fix
- [x] Proactive monitor: scans for failed cases, de-duped NOTIFICATIONS list (cap 20)
- [x] execute_action(): handles run_step + write_script_fix action types
- [x] Pending actions stored in PENDING_ACTIONS dict, exposed via /api/agent/status
- [ ] Proactive monitor scheduled loop (currently manual trigger only — POST /agent/monitor)

### 10D. Validation Gates
- [x] Human review gate banner (Pipeline tab, shown when status=human_review)
- [x] Approve/reject buttons → advance or revert pipeline status
- [ ] Gate 2: Audio review (embedded player, segment timing table)
- [ ] Gate 3: Video + thumbnail preview before publish
- [ ] Gate 4: Final publish confirmation (title/desc/tags editable)

## Servers
- FastAPI: `uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000` (from project root)
- Next.js: `npm run dev` (from frontend/) → http://localhost:3000

---

## PHASE 11 — Case Versioning ("Branch" model) + Step Workspace
*Pivot step rerun = new child case (version), not stale cascade. Each version is a fully independent pipeline.*

### Design Decision (2026-06-17)
When user reruns a pivot step (research/script/tts), instead of overwriting + cascading stale:
- Create a **child case** (slug: `{parent}-v2`, `{parent}-v3` etc.)
- Copy artifacts from parent up to the pivot point into child's data/ dir
- Child runs its own independent pipeline from the pivot step forward
- Parent case untouched — user can compare, choose which version to publish
- Non-pivot reruns (QA, characters, broll, thumbnail) just overwrite within same case

### Pivot step → what gets copied to child
| Pivot step | Copied to child | Child starts at |
|---|---|---|
| research | nothing (fresh start) | queued |
| script | research.json | research (done) |
| tts | research.json + script_draft.md | scripting (done) |

### DB changes needed
```
cases table:
  + parent_case_id  UUID NULL FK→cases.id
  + case_version    INT DEFAULT 1
  + pivot_step      VARCHAR(50) NULL  -- which step created this branch
```

### 11A. DB Migration [ ]
- [ ] Add parent_case_id, case_version, pivot_step columns to cases table
- [ ] `src/db/migrate_versioning.py` — ALTER TABLE migration script
- [ ] Update `Case` model in `src/db/models.py`

### 11B. API — Branch endpoint [ ]
- [ ] `GET /api/cases/{slug}/versions` — returns parent + all children (ordered by version)
- [ ] `POST /api/cases/{slug}/branch` — body: `{pivot_step: "script", reason?: str}`
  - Computes next version number
  - Creates child Case in DB (parent_case_id set, case_version=N, pivot_step set)
  - Copies relevant files from parent data dir into child data dir
  - Sets child case status to appropriate step
  - Returns child case dict
- [ ] Update `GET /api/cases` to group children under parents (or flag them)
- [ ] Update `GET /api/cases/{slug}` to include versions list + parent info

### 11C. Step Config Save/Load [ ]
- [ ] `src/api/routes/steps.py` — per-step config schema + save/load (JSON file per step)
- [ ] `GET /api/steps/{slug}/{step}/config`
- [ ] `PUT /api/steps/{slug}/{step}/config`
- [ ] `GET /api/steps/{slug}` — all step configs + file existence per step
- [ ] Register router in main.py

### 11D. Per-step review gates [ ]
- [ ] After each step completes → status stays at that step's name until approved
- [ ] `POST /api/steps/{slug}/{step}/approve` — advance status to next step
- [ ] `POST /api/steps/{slug}/{step}/reject` — keep status, allow rerun or branch
- [ ] Remove old `/pipeline/{slug}/approve` (was only for human_review gate)

### 11E. Frontend — Step Workspace page [ ]
- [ ] `/cases/[slug]/steps/[step]` — full page: config + output preview + live logs
- [ ] Config panel: dynamic form from config schema
- [ ] Output preview: step-specific (research=JSON viewer, script=text, tts=audio player, video=video player)
- [ ] Live log terminal (right panel)
- [ ] Version history bar: shows current case version + siblings (other branches)
- [ ] Run button: pivot steps show "▶ New Run (branches → v2)" with amber warning
- [ ] Non-pivot: "▶ Rerun" (overwrites in place)
- [ ] Approve/Reject buttons for post-run review

### 11F. Frontend — Branch UI [ ]
- [ ] Pipeline tab: pivot steps show "⑂ Branch" chip
- [ ] Click "Branch" → modal: "Create Version 2 branching at [Script]? Copies research from v1."
- [ ] On confirm → POST /cases/{slug}/branch → redirect to child case
- [ ] Case header: version badge (v1, v2, v3...) + parent link if child
- [ ] New "Versions" tab in case detail: list all siblings with status + which step they branched at

### 11G. Cleanup [ ]
- [ ] Remove `src/api/versions.py` (ArtifactVersion/stale-cascade model — wrong design)
- [ ] Remove `ArtifactVersion` model from `src/db/models.py`
- [ ] Remove `src/db/migrate_versions.py` migration (don't run, wrong table)
- [ ] Keep `src/api/routes/steps.py` but strip version/stale logic, keep config only

---

---

## PHASE 12 — Vertical Shorts / Reels Pipeline
*60-90s vertical clips (9:16 1080×1920) for YouTube Shorts, Instagram Reels, TikTok.*
*Fully independent production track. Only shared input: research.json raw case data.*

### Architecture Decision (2026-06-18)
**Two completely independent creative pipelines. Only shared artifact: research.json.**
- Long-form: writes 30-45 min documentary script from research → long TTS → 16:9 assembly
- Shorts: writes fresh hook-first episode scripts from research (NOT condensed from long-form) → per-episode TTS → 9:16 assembly
- Why separate scripts: long-form has transitions/context dependencies. Shorts are standalone 60-90s punches. Cannot slice or condense — must write fresh.

### Episode topics (derived from research.json, not long-form sections)
1. `who_was_the_victim` — victim's life + discovery
2. `the_accused` — who, background, motive
3. `the_evidence` — the key piece that cracked it
4. `the_trial` — most dramatic courtroom moment
5. `the_verdict` — outcome, justice or not
6. `systemic_angle` — what this reveals about India's justice system
7. `where_are_they_now` — aftermath

### Per-episode structure (120-180 Hindi words)
```
## [HOOK]     ← 10s, vivid, present tense, "आप यकीन नहीं करेंगे..."
[PAUSE 2s]
## [FACT]     ← core revelation from research, 60-80 words
## [REVEAL]   ← twist/payoff
## [CTA]      ← "Subscribe करें। अगले episode में..."
```

### 12A. ShortsScriptAgent [x]
- [x] Initial version (wrong: condensed from long-form script) — superseded
- [x] **REWRITE complete**: reads research.json directly, writes fresh episodes per topic
- [x] `_load_research()` + `_build_topic_context()` + `_topic_has_data()` helpers
- [x] 7 canonical topics: who_was_the_victim / the_accused / the_evidence / the_trial / the_verdict / systemic_angle / where_are_they_now
- [x] Gemini prompt: victim-first, hook-first, Devanagari-only, standalone per episode
- [x] Skip topics with < 40 topic-specific words in research data
- [x] Output: `data/cases/{slug}/shorts/ep01_who_was_the_victim.md` etc.

### 12B. ShortsAssemblerAgent [x]
- [x] Initial version (wrong: center-crop only, no captions) — superseded
- [x] **REWRITE complete**: blur-box crop + burned-in captions + hook frame
- [x] Blur-box: single `-filter_complex` pass — blurred 1080×1920 bg + sharp cropped fg, overlay
- [x] Hook frame: first 3s Hindi topic title (`_TOPIC_HINDI` dict), yellow, 56px, top area
- [x] Captions: time-gated drawtext per segment from `*_timings.json`, bottom quarter, capped at 8 segments
- [x] Combined overlays in single ffmpeg pass (no re-encode between hook + captions)
- [x] Font-not-found: skips all overlays gracefully (copy passthrough)
- [x] Output: `data/cases/{slug}/shorts/ep01_who_was_the_victim.mp4`
- [ ] Multi-clip pacing (2-5s rapid cuts) — deferred, single looped clip for now
- [ ] Music bed — deferred

### 12C. Pipeline Routes [x]
- [x] Old monolithic `POST /api/pipeline/{slug}/shorts` — kept for backward compat
- [x] `POST /api/pipeline/{slug}/shorts_script` — ShortsScriptAgent only
- [x] `POST /api/pipeline/{slug}/shorts_tts` — per-episode TTS + timings copy
- [x] `POST /api/pipeline/{slug}/shorts_assemble` — ShortsAssemblerAgent only
- [x] `src/api/routes/steps.py` — VALID_STEPS + STEP_CONFIGS for all 3 new steps
- [x] `src/api/routes/cases.py` `/files` — `shorts_scripts[]`, `shorts_audio[]`, `shorts_script_count`, `shorts_audio_count`
- [x] `src/api/versions.py` — STEP_FILE_MAP entries added

### 12D. ShortsScriptAgent — Per-topic nuanced prompts [x]
- [x] `_TOPIC_GUIDANCE` dict — 7 per-topic hook styles, structural rules, creative constraints
- [x] `_TOPIC_CTA` dict — each CTA teases specific next episode
- [x] `_EPISODE_PROMPT` updated to inject `{topic_guidance}` and `{topic_cta}` per call
- [x] `_write_episode()` passes topic-specific context to prompt

### 12E. Frontend — 3-step shorts pipeline [x]
- [x] `pipeline.ts`: `shorts_script` → `shorts_tts` → `shorts_assemble` chain
- [x] `countKey` added to `StepPrereq` interface — count-based prereq checking
- [x] NEXT_STEP, STEP_PREREQ, STEP_LABEL all updated for new steps
- [x] `PipelineStepCard` in `page.tsx`: `isCountKey` covers all 3 count artifact keys
- [x] Step workspace `shorts_script`: `ShortsScriptArtifact` — episode name cards
- [x] Step workspace `shorts_tts`: `ShortsAudioArtifact` — per-episode audio players
- [x] Step workspace `shorts_assemble`: existing `ShortsArtifact` portrait video cards
- [x] `prereqCountMissing` check wired in step workspace prereq logic
- [x] TypeScript: 0 errors

### 12F. TTS for Shorts [x]
- [x] `TTSAgent` reused per episode, output to `shorts/epNN_topic.mp3`
- [x] Word timings copied: `audio/word_timings.json` → `shorts/{ep_slug}_timings.json`

---

## PHASE 13 — Character Pipeline Fixes + Shorts Visual Source

### 13A. CharacterAgent fixes [x]
- [x] `_extract_from_research` now reads `people_involved[]` list (all people, not just summary.victim/perpetrator)
- [x] `_normalize_role()` helper — maps raw role strings (Hindi + English) to standard set
- [x] Script extraction no longer overwrites research findings — only adds names NOT in research
- [x] DB upsert: if character exists, update role/notes only if currently empty (no overwrite)
- [x] `characters` moved to `shared` track in `pipeline.ts` — runs after research, before fork
- [x] `STEP_PREREQ.characters` now requires `research` (not `script_draft`) — works shorts-only

### 13B. Shorts visual source [x]
- [x] `_TOPIC_ROLE_MAP` in ShortsAssemblerAgent — maps people-focused episodes to DB roles
- [x] `_pick_character_photo()` — DB lookup by role → file fallback → None
- [x] victim episode → victim's character photo; accused episode → accused photo
- [x] Portrait photos flow through existing pillarbox path in `_prepare_vertical_broll`
- [x] DB errors caught/logged — never crashes if characters dir missing

---

## PHASE 14 — Real Shorts B-Roll + Scene-Aware AI Visuals

Context: character extraction's purpose is not just "static portrait when topic = victim".
Purpose is reference material (name + role + description) to generate AI images/clips
matched to the SPECIFIC scene/commentary line playing at that moment — not just a fixed
photo reused for the whole episode.

### 14A. Real per-topic Pexels fetch for shorts [x]
- [x] `BRollAgent.fetch_for_shorts_topic(slug, topic_slug, query)` — new method, reuses
      existing `search_pexels` + `download_clip` + DB cache, saves to `broll/{topic_slug}.mp4`
- [x] `SHORTS_TOPIC_QUERY` map — one Pexels query per shorts topic slug
- [x] Fixes bug: `_pick_broll` was falling back to "any .mp4 in dir" → random leftover
      long-form clips on shorts episodes (no exact filename ever existed for new topic slugs)
- [x] Wired into `_assemble_episode` via `_ensure_topic_broll()` — fetches only if
      `broll/{topic_slug}.mp4` missing, never re-fetches

### 14B. SceneImageAgent — per-segment AI visuals [x]
- [x] New `src/agents/scene_image_agent.py`
- [x] Splits episode script into segments (timings JSON, falls back to `[PAUSE]`/sentence split)
- [x] Matches each segment against known characters (DB name match)
- [x] Builds DALL-E 3 prompt = character role/description (if matched) + scene action
      excerpt from segment text + documentary style — generates a SCENE, not a portrait
- [x] Capped at 4 generated images per episode (cost control) — hook + reveal always
      included, then earliest character-matched segments fill remaining slots
- [x] Saves to `data/cases/{slug}/scene_images/{topic}/seg_{NN}.png` + `manifest.json`
      (segment_index, start, end, image_path)

### 14C. ShortsAssembler scene-image overlay [x]
- [x] `_load_or_generate_scene_manifest()` — loads cached manifest.json or generates once
- [x] `_overlay_scene_images()` — time-gated full-screen overlay during each segment's
      [start,end] window, same `enable='between(t,...)'` technique as captions; replaces
      b-roll for that window only, leaves rest of episode on topic broll/character photo
- [x] Falls through unchanged (`shutil.copy2`) if manifest empty/missing — no regression
      when OPENAI_API_KEY unset or no character/hook/reveal segments qualify
- [x] Inserted as Step 1b, between vertical b-roll prep and hook+caption pass

---

## PHASE 15 — SaaS-Shaped Re-Architecture Pass

Pivot: single-operator tool re-architected with SaaS-shaped internals — topic/case
as data not code, longform and shorts as fully decoupled services, clean module
boundaries. No auth/billing/multi-tenant DB (explicitly out of scope for this pass).

### 15A. Clean slate [x]
- [x] Deleted `data/cases/jessica-lall-murder` + `jessica-lall-murder-v2` (847M)
- [x] Truncated DB tables: cases, case_research, scripts, videos, yt_analytics,
      case_characters, pipeline_log, broll_cache, articles
- [x] No case-specific data remains anywhere in repo or DB

### 15B. Design philosophy doc [x]
- [x] New `docs/SAAS_DESIGN.md` — Claude's own design checklist, consulted before
      every new feature: case-as-data, track independence, visual-priority
      declaration, cost-control caps, graceful degradation, per-step granularity,
      schema neutrality, 7-point feature checklist

### 15C. Context docs rewritten to match reality [x]
- [x] `docs/MASTER_REFERENCE.md` — was describing an entirely different old plan
      (English language, Streamlit, ElevenLabs, MoviePy, Claude Sonnet scripts).
      Rewritten to match actual build (Hindi, Next.js/FastAPI, Gemini, Sarvam, pure
      ffmpeg) + two-track architecture + case-selection-is-data-not-list
- [x] `docs/ARCHITECTURE.md` — same staleness, same fix. Now documents the real
      `src/`/`frontend/` tree, the two-track fork diagram, shorts visual-sourcing
      pipeline, and current env var list
- [x] `CLAUDE.md` — added "Two Independent Tracks" + "Case Is Data, Not Code"
      sections, references SAAS_DESIGN.md, rule 9 added (no case/niche literals
      in code/schema/routing), tech stack corrected to match actual build

---

## PHASE 16 — Pipeline Separation Audit + Dependency Graph

### 16A. Track separation audit [x]
- [x] Import graph checked: no longform agent imports any shorts agent; shorts only
      imports declared shared utilities (`broll_agent`, `scene_image_agent`,
      `character_agent` transitively) — no coupling violation found
- [x] Frontend confirmed to call only the 3 granular shorts routes
      (`shorts_script`/`shorts_tts`/`shorts_assemble`), never the old monolithic one
- [x] Removed dead/broken `POST /{slug}/shorts` route in `pipeline.py` — leftover
      monolithic batch route from before the granular split, unused by frontend,
      AND broken (called `ShortsAssemblerAgent().run()` which doesn't exist, only
      `.assemble()` does). Violated SAAS_DESIGN.md §6 twice over.
- [x] `VALID_STEPS` in `steps.py` confirmed clean — no stale `"shorts"` entry

### 16B. Content-ops dashboard UX research [x]
- [x] Researched 6 dimensions against real products (Opus Clip, Descript, Synthesia,
      HeyGen, n8n, Make, Deadline, Airtable, Asana): multi-stage visualization,
      parallel-track signaling, per-step granularity, cost visibility, approval
      gates, artifact browsing
- [x] Gaps identified for this dashboard: no cross-case fleet view, no per-step/
      per-case cost surfacing, approval gate not visually distinct from auto steps,
      two-track separation not obvious from UI alone (only from column position)

### 16C. Dependency graph [x]
- [x] Added Mermaid dependency graph to `docs/ARCHITECTURE.md` §1.1 — renders
      natively in GitHub/VS Code preview, no install required
- [x] Graph makes the shared-vs-track-owned edge rule visually checkable: only
      `research.json` + `characters/` (+ shared utility classes) cross into both
      subgraphs — any other cross-subgraph edge in a future diff is a violation
- [x] Recommended React Flow (not built) for a future interactive in-app DAG with
      live per-node status — same library class n8n-style workflow editors use

---

## PHASE 17 — Track-First Navigation Redesign

Pivot: user picks a TRACK first (Long-form Studio / Shorts Studio), not a case —
cases live inside the track's space, not the other way around.

### 17A. Backend per-episode scoping [x]
- [x] `ShortsScriptAgent.run_single(state, topic_slug)` — generates/regenerates
      exactly one episode, reuses existing ep-number if regenerating, assigns
      next free slot if new. Other 6 episodes untouched.
- [x] `pipeline.py` `/shorts_script`, `/shorts_tts`, `/shorts_assemble` routes —
      all accept optional `?topic=` query param; tts/assemble just narrow the
      glob pattern (`ep*_{topic}.md`/`.mp3`), no agent changes needed there
- [x] `frontend/lib/api.ts` `runStep(slug, step, topic?)` — appends `?topic=`
- [x] Removed the old monolithic-batch new-case flow assumption — per-episode
      is now a first-class operation, not just a 7-at-once batch

### 17B. New navigation tree [x]
- [x] `/` rewritten — two launch cards (Long-form Studio / Shorts Studio), case
      count aggregate, secondary link to `/cases` (kept as cross-track fleet view)
- [x] `/longform`, `/longform/new`, `/longform/[slug]` — case list, creation form,
      single-column shared+longform step workspace (reuses existing
      `/cases/[slug]/steps/[step]` for actual step execution)
- [x] `/shorts`, `/shorts/new`, `/shorts/[slug]` — case list (7-segment progress
      bar), creation form, episode-picker grid (7 topic cards, 3-dot progress)
- [x] `/shorts/[slug]/[episode]` — NEW per-episode 3-step workspace (script →
      audio → assemble for ONE topic), with artifact previews + LiveTerminal
- [x] `lib/pipeline.ts` additions: `SHORTS_TOPICS`, `SHORTS_EPISODE_STEPS`,
      `topicFileMatch()`, `longformProgress()`, `shortsProgress()`
- [x] Sidebar nav updated: Home / Long-form Studio / Shorts Studio / All Cases / Settings
- [x] Built via 2 parallel agents (disjoint file sets: longform-side vs shorts-side),
      both verified with `npx tsc --noEmit` clean

### 17C. Dead code removal [x]
- [x] Old monolithic `/{slug}/shorts` route deleted (Phase 16A) — confirmed
      unused by any new navigation path either

---

## PHASE 18 — Niche/Genre Generalization (ChannelProfile)

Corrects a scoping mistake in `docs/SAAS_DESIGN.md` §0/§1: case-as-data was
enforced, but niche/genre/voice/language were still hardcoded module constants —
meaning the app could only ever produce Hindi true-crime content. Fixed: niche is
now a DB row (`ChannelProfile`), loaded per-case. See `docs/SAAS_DESIGN.md` §0 and
`CLAUDE.md`'s "Niche Is Data Too" for the corrected principle + known remaining gaps.

### 18A. ChannelProfile schema + seed [x]
- [x] New `ChannelProfile` model (`src/db/models.py`): `voice_system_prompt`,
      `section_headers`, `case_prompt_template`, `word_count_range`,
      `words_per_minute`, `shorts_topics`, `shorts_episode_prompt_template`,
      `shorts_word_range`, `entity_roles`, `research_sources`, `language`
- [x] `Case` model generalized: dropped `victim_name`/`victim_age`/
      `victim_profession`/`perpetrator`/`case_type` columns (crime-specific).
      Added `channel_profile_id` (FK), `subject_name` (generic replacement for
      `victim_name`), `extra` (JSONB catch-all for niche-specific facts)
- [x] `src/db/migrate_channel_profiles.py` — migration, run successfully
- [x] `src/db/seed_default_profile.py` — seeds `indian-true-crime-hindi` with
      the EXACT prior hardcoded content verbatim (zero behavior change), run
      successfully (profile id confirmed in DB)
- [x] `src/db/channel_profile.py` — `get_profile_for_case(slug)` helper, falls
      back to the default profile slug if a case has no `channel_profile_id` set
- [x] Deleted dead `src/dashboard/` (old Streamlit app, superseded 2026-06-17,
      referenced none of the surviving fields, no point fixing dead code)

### 18B. Agent refactors — profile-driven, zero behavior change [x]
- [x] `script_writer_agent.py` — `SECTION_HEADERS`/`SYSTEM_PROMPT` constants
      deleted; reads `profile.voice_system_prompt`/`section_headers`/
      `case_prompt_template`/`word_count_range`/`words_per_minute`; Gemini
      model built per-call with profile's system_instruction (was per-`__init__`
      fixed instruction — had to change since instruction is now per-case)
- [x] `shorts_script_agent.py` — `_TOPICS`/`_TOPIC_GUIDANCE`/`_TOPIC_CTA`/
      `_EPISODE_PROMPT` deleted; reads `profile.shorts_topics`/
      `shorts_episode_prompt_template`; `run_single` (17A) also updated to
      look up topic from `profile.shorts_topics` instead of the old list
- [x] `character_agent.py` — `ROLE_KEYWORDS` deleted; `_normalize_role`/
      `_infer_role`/extraction methods take `entity_roles: list[dict]` threaded
      from `profile.entity_roles`. `ROLE_STRONG_SIGNALS` + Hindi name-detection
      regex deliberately left hardcoded (logged as known gaps, not silently
      dropped — see CLAUDE.md gap list)

### 18C. Field-rename ripple (victim_name → subject_name, mechanical) [x]
- [x] Backend: `src/api/routes/cases.py` (CaseCreate model + `_case_to_dict`,
      backward-compat flattened keys from `extra`), `src/api/agent/tools.py`,
      `src/agents/publish_agent.py`, `src/agents/thumbnail_agent.py`,
      `src/agents/case_research_agent.py`
- [x] Frontend: `lib/api.ts` (`Case.subject_name`), all 3 `*/new/page.tsx`
      forms (label → "Subject Name", genre-neutral placeholder), all list/detail
      pages displaying the field — 10 files total, all via 1 parallel agent
- [x] Repo-wide grep confirms zero remaining `.victim_name`/`.victim_age`/
      `.victim_profession`/`case.perpetrator`/`case.case_type` references
- [x] Full integration check: all touched Python modules import together,
      FastAPI app boots, `npx tsc --noEmit` clean across whole frontend

### 18D. Known gaps — explicitly deferred, not silently dropped [ ]
- [ ] `tts_agent.py` hardcodes `target_language_code: "hi-IN"` + fixed Sarvam
      speaker list — not sourced from `profile.language`
- [ ] `case_research_agent.py` scraper sources (Indian Kanoon/CBI/NCRB) still
      India/crime-specific code; `profile.research_sources` seeded but unused
- [ ] `character_agent.py`'s `ROLE_STRONG_SIGNALS` + AI-portrait `_ROLE_DESC`
      dict still crime-specific
- [ ] No profile-picker UI in case-creation forms — silently defaults to the
      one seeded profile
- [ ] Frontend role-color dicts (`ROLE_COLORS` in case/step pages) still keyed
      to the crime taxonomy — a custom profile's roles fall back to gray, not broken
- [ ] Not yet smoke-tested end-to-end with a real case created + run through
      both tracks since this migration (DB was empty going in; only import/compile
      checks done, not a live pipeline run)

---

## PHASE 19 — Lightweight Manual Override Editor (EDL)

Not a full NLE (researched and rejected — weeks of timeline/playback engineering,
wrong tool for an automated pipeline). Instead: a browser timeline UI emits a JSON
Edit Decision List; existing FFmpeg pipelines (longform `assembler.py`, shorts
`shorts_assembler_agent.py`) consume it as an OPT-IN override per segment — auto-pick
stays the default when no override exists. Library: `react-timeline-editor` (timeline
widget only, no render engine — keeps the existing free server-side FFmpeg render,
per the "browser UI, server renders" pattern real JSON-to-video products use).

### 19A. EDL schema + storage + API (foundation, built first, others depend on it) [x]
- [x] `src/pipeline/edl.py` — `EDLSegment`/`EDL` pydantic models: `segment_id`,
      `start`, `end`, `source_type` (`auto`/`broll`/`character_photo`/`scene_image`),
      `source_path` (relative to `data/cases/{slug}/`, `None` = auto/fallback)
- [x] `edl_path(slug, track, topic=None)` → `data/cases/{slug}/edl/{track}.json`
      (longform) or `edl/shorts_{topic}.json` (shorts, one EDL per episode)
- [x] `load_edl()`/`save_edl()`/`get_segment_override(edl, segment_id)` +
      `build_longform_skeleton()`/`build_shorts_skeleton()` helpers (skeleton
      segment_id is the timings-array INDEX, not section name — a section like
      "COLD OPEN" can span multiple timing segments)
- [x] `src/api/routes/edl.py` — `GET /api/edl/{slug}?track=...&topic=...` (saved
      EDL or auto skeleton), `PUT /api/edl/{slug}` to save
- [x] Wired into `src/api/main.py` router list, app boots clean

### 19B. Longform consumption [ ]
- [ ] `src/video/assembler.py` (`VideoCreator`) / `video_producer_agent.py` —
      `_load_broll_map` / `_build_segments` check for a saved EDL first; for any
      segment with a non-`auto` override, use `source_path` instead of the
      automatic per-section Pexels pick. Segments with no override (or no EDL
      file at all) fall through to current automatic behavior unchanged.

### 19C. Shorts consumption [ ]
- [x] `shorts_assembler_agent.py`'s `_assemble_episode` — EDL override check
      applied to the per-segment scene-image manifest (scoping decision: whole-
      episode char_photo/broll fallback left untouched, no segment mapping for
      it). `broll`-type override hitting a scene-image segment logs + skips
      (known limitation, not silently dropped)

### 19D. Frontend timeline editor [x]
- [x] `@xzdarcy/react-timeline-editor` + `@xzdarcy/timeline-engine` installed
- [x] `components/EditDecisionListEditor.tsx` — hybrid: read-only visual
      `Timeline` strip (colored bars per segment) above a scrollable row-list
      that actually drives state/save (drag-to-discrete-source-picking wasn't
      a natural fit for the library — row-list `<select>` overrides shipped
      instead, per the brief's explicit fallback allowance)
- [x] Wired into `/longform/[slug]` and `/shorts/[slug]/[episode]` as a
      "Manual Overrides" section
- [x] `npx tsc --noEmit` + `npm run build` both clean

---

## PHASE 20 — Dynamic Episode Planning (replaces fixed 7-topic shorts menu)

User pushback, correctly: episode COUNT and IDENTITY were a fixed menu of 7
(`ChannelProfile.shorts_topics`) with skip-if-thin logic — dynamic in whether a
slot fills, not in whether the slot should exist at all. Fix: a planning step
reads the full case research and decides how many episodes (no fixed target)
and what each is about, before any script gets written. The fixed topic dicts
that drove on-screen hook text / character role preference / b-roll query per
slug get replaced by per-card LLM-generated metadata, so visual quality doesn't
regress when slugs are no longer from a known set.

Two corrections during build, both from user review — recorded so the same
mistakes don't recur:
1. First prompt draft handed the planner a "starting menu" of 7 angles
   (victim/accused/evidence/trial/verdict/systemic/aftermath) as scaffolding.
   Caught: a fixed menu inside a prompt is the same rigidity as a fixed menu
   in code — the model just anchors on it. Rewritten to derive count/identity
   purely from the case's own research, zero starting structure. `role_hint`
   also changed from a fixed role-enum to the actual person's NAME from the
   research — removes a second fixed taxonomy and is more precise.
2. First draft also hardcoded "in Hindi" into the prompt text and named a
   field `label_hindi`. Caught: language is `profile.language`, a per-niche
   user selection, not a property of the planner itself. Prompt now takes
   `{language}` as a format placeholder (ISO code, filled at call time from
   `profile.language`); field renamed `hook_text` (language-neutral name,
   content is in whatever language the profile specifies).

### 20A. ChannelProfile: planner guidance field (foundation) [x]
- [x] `channel_profiles.shorts_planner_prompt` (TEXT) — migrated + backfilled
      for the seeded profile (`indian-true-crime-hindi`). Template string with
      a `{language}` placeholder, formatted by `EpisodePlannerAgent` at call
      time from `profile.language` — see corrections above.

### 20B. EpisodePlannerAgent (foundation — schema contract others depend on) [x]
- [x] New `src/agents/episode_planner_agent.py` — Gemini call: input = full
      research.json + `profile.shorts_planner_prompt.format(language=profile.language)`.
      Output: JSON array of episode cards, each `{slug, label, hook_text,
      angle, broll_query, role_hint, cta}` (`role_hint` = a person's actual
      NAME from the research, not a role-enum bucket) — count decided by the
      model based on actual material, not a fixed target
- [x] Saved to `data/cases/{slug}/shorts_plan.json` (case data, not profile data)
- [x] Served free via existing `/files/cases/{slug}/shorts_plan.json` static
      mount — no new GET route needed

### 20C. Pipeline wiring (foundation) [x]
- [x] New step `shorts_plan` — shorts track, before `shorts_script`
- [x] `pipeline.ts` (`ORDERED_PIPELINE`, `STEP_PREREQ`, `NEXT_STEP`,
      `STEP_LABEL`) + backend `POST /api/pipeline/{slug}/shorts_plan` route
- [x] `_SHORTS_TOPICS` fixed-set validation in `pipeline.py` (3 call sites)
      replaced by `_shorts_plan_slugs(slug)` reading the case's actual plan
- [x] `cases.py` `/files` endpoint: added `shorts_plan` + `shorts_plan_count`
      keys so the dashboard can show plan status without a separate fetch

### 20D. ShortsScriptAgent rewrite [x]
- [x] Drop `profile.shorts_topics` iteration entirely; read `shorts_plan.json`
- [x] `_build_topic_context` replaced by `_research_context` — no more fixed
      if/elif per old slug; full research dump + the card's `angle` text, the
      model focuses itself instead of hand-mapped field extraction
- [x] `run_single(state, episode_slug)` looks up the plan entry by slug

### 20E. Visual layer reads per-card metadata, not fixed dicts [x]
- [x] `shorts_assembler_agent.py`: new `_load_plan_card(slug, section_slug)`
      helper; `_topic_hindi_label`/`_pick_character_photo`/`_ensure_topic_broll`
      all prefer the plan card's `hook_text`/`role_hint`/`broll_query` first,
      fall back to the legacy fixed dicts only for episodes with no plan.
      `role_hint` matched via `CaseCharacter.name.ilike()`, not a role bucket.
- [x] `broll_agent.py`'s `SHORTS_TOPIC_QUERY` untouched (still used as the
      fallback) — query now sourced from the plan card first in `_ensure_topic_broll`

### 20F. Frontend: dynamic-length episode grid [x]
- [x] New `useShortsPlan(slug)` hook (`swr-hooks.ts`) — fetches
      `shorts_plan.json` directly off the static mount
- [x] `/shorts/[slug]/page.tsx` — stopped enumerating `SHORTS_TOPICS`/
      `profile.shorts_topics`; added an "Episode Plan" step row (gates the
      grid); grid renders however many cards the plan actually contains;
      "no plan yet" message shown instead of an empty grid
- [x] `/shorts/[slug]/[episode]/page.tsx` — validates episode slug against
      the plan (`useShortsPlan`), not the old fixed list
- [x] `shortsProgress()` denominator now reads `files.shorts_plan_count`
      (falls back to the legacy constant only if no plan exists yet)
- [x] `npx tsc --noEmit` clean; backend `py_compile` + fresh-import clean;
      both servers restarted and confirmed live

---

## Decisions Log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-06-16 | Long-form 30–45 min format | Better watch time, RPM, audience loyalty vs 5–8 min |
| 2026-06-16 | ElevenLabs over Google TTS | Quality critical at 30–45 min runtime |
| 2026-06-16 | Warm documentary palette (not red/black) | Red/black = tabloid; warm = credible |
| 2026-06-16 | Artlist.io for music (not YT Audio Library) | YT Audio Library sounds identical across channels |
| 2026-06-16 | Human review gate before production | Quality > speed for first 50 videos |
| 2026-06-16 | Cormorant Garamond + Inter typography | Gravitas + readability; no horror/generic fonts |
| 2026-06-16 | Jessica Lall as first case | Clear arc, satisfying resolution, maximum cultural resonance |
| 2026-06-16 | Indian Kanoon API as primary legal source | Full judgment text, free, programmatic |
| 2026-06-16 | Character images > stock footage for real cases | Real photos = documentary credibility; Pexels stays as location/atmosphere fallback |
| 2026-06-16 | Silence WAVs via FFmpeg anullsrc for [PAUSE Xs] markers | Sarvam Bulbul has no SSML; interleave actual silence WAVs at merge time |
| 2026-06-16 | Dashboard controls all pipeline steps + Gemini agent chat | Operators need no terminal access for normal workflow |
| 2026-06-17 | Migrate from Streamlit → Next.js + FastAPI | Streamlit ceiling hit: no real-time logs, no SSE, no complex UX |
| 2026-06-17 | Active Windsurf-style agent (Gemini function calling) | Chatbot not enough — agent must observe, act, diagnose, fix |
| 2026-06-20 | Single-operator, SaaS-shaped architecture (not multi-tenant) | Clean module boundaries + topic-as-config without auth/billing overhead the project doesn't need yet |
| 2026-06-20 | Full data + DB wipe before re-architecture | Old docs/data described a different plan entirely (English/Streamlit/ElevenLabs); clean slate cheaper than reconciling |
| 2026-06-20 | docs/SAAS_DESIGN.md as standing design-review checklist | Prevents future features from re-coupling longform/shorts or hardcoding case/niche literals |
| 2026-06-20 | Track chosen first in navigation (Home → Long-form/Shorts Studio → case) | User explicitly rejected case-first nav — tracks must feel like genuinely separate products, not a tab on a case page |
| 2026-06-20 | ChannelProfile DB row replaces hardcoded niche/genre/voice constants | SAAS_DESIGN.md §0/§1 originally let content-structure stay hardcoded — wrong; app must support any niche/language without code edits |
| 2026-06-20 | Seeded exact current Hindi-crime content as first profile verbatim, no rewrite | Proves the abstraction is behavior-preserving by construction; a fabricated second example niche would add noise without proving anything code couldn't already do |
