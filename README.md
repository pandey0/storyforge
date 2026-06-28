# StoryForge

Automated content production engine. Research a subject → produce two independent product lines: **long-form documentaries** (30–45 min, 16:9) and **shorts** (episodic 9:16 reels, count and topics planned dynamically per case by Gemini). Not tied to one niche or language — what genre, voice, structure, and language gets produced is configured per **ChannelProfile** (a DB row), never hardcoded.

**Current seeded profile:** `indian-true-crime-hindi` — Hindi-language Indian true crime, journalistic + warm documentary style.

---

## Architecture

```
research.json  (shared — only thing both tracks read)
       │
       ├── characters  (shared, runs once)
       │     extract people → DB → photo search → AI portrait gap-fill
       │
       ├── LONGFORM TRACK (independent)
       │     script → QA → broll → TTS → assemble → thumbnail → publish
       │     → video_final.mp4 (16:9, 30–45 min)
       │
       └── SHORTS TRACK (independent, per-episode)
             episode_planner → shorts_script → TTS → scene_images → assemble
             → N× {topic}.mp4 (9:16, 60–90 s, N planned per-case by Gemini)
```

Neither track depends on the other's output. Either can run alone after `research` + `characters` complete.

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.11+ |
| Frontend | Next.js 15 + React (control room) |
| Backend API | FastAPI + SSE log streaming |
| Database | PostgreSQL (Neon) + SQLAlchemy |
| LLM (scripts) | Gemini 2.5 Flash |
| TTS | Sarvam Bulbul v2 (hi-IN) |
| Video assembly | FFmpeg (pure — no MoviePy) |
| Images | OpenRouter / Gemini Flash Image + Pillow |
| B-roll | Pexels API |
| Upload | YouTube Data API v3 |
| Storage | Local `data/` directory |

---

## Agents

| Agent | Purpose |
|---|---|
| `case_research_agent.py` | Indian Kanoon + news archive + Wikipedia → `research.json` |
| `character_agent.py` | People extraction → DB → photo search → AI portraits |
| `script_writer_agent.py` | Longform: 30–45 min Hindi script via Gemini |
| `qa_agent.py` | Tone / structure / factual QA, auto-retry loop (max 3) |
| `tts_agent.py` | Sarvam Bulbul → `audio.mp3` + `word_timings.json` |
| `broll_agent.py` | Pexels fetch + cache (longform per-section, shorts per-topic) |
| `video_producer_agent.py` | Longform FFmpeg assembly, 16:9 |
| `thumbnail_agent.py` | AI image + Pillow text overlay |
| `publish_agent.py` | YouTube Data API v3 upload + schedule |
| `analytics_agent.py` | YT analytics sync → DB |
| `episode_planner_agent.py` | Decides episode count + topics per case via Gemini (reads `research.json` + profile planner prompt) |
| `shorts_script_agent.py` | Writes each episode script from the planned episode cards |
| `scene_image_agent.py` | Per-segment AI scene images (character + narration context) |
| `shorts_assembler_agent.py` | Per-episode 9:16 assembly: blur-box, captions, scene overlay |

---

## Directory Structure

```
/
├── README.md
├── CLAUDE.md                   harness instructions for Claude
├── docs/
│   ├── SAAS_DESIGN.md          design philosophy (read before any new feature)
│   ├── MASTER_REFERENCE.md     full project bible
│   ├── TRACKER.md              build progress
│   ├── DATA_SOURCES.md         all data sources with URLs
│   └── ARCHITECTURE.md         technical diagrams + decisions
├── pipeline_defs/
│   ├── longform.yaml           longform step graph definition
│   └── shorts.yaml             shorts step graph definition
├── frontend/                   Next.js control room
│   ├── app/
│   │   ├── page.tsx            dashboard home
│   │   ├── longform/           longform cases UI
│   │   ├── shorts/             shorts cases UI
│   │   └── settings/
│   │       └── profiles/       channel profile CRUD
│   ├── components/
│   │   ├── AgentPanel.tsx      live agent log panel (collapsible)
│   │   ├── LayoutShell.tsx     layout wrapper managing panel state
│   │   └── TopicDiscovery.tsx  web search panel for new case ideas
│   └── lib/
│       ├── api.ts              typed API client
│       ├── pipeline.ts         step graph source of truth
│       └── swr-hooks.ts        SWR data hooks
├── src/
│   ├── agents/                 all agent implementations
│   ├── api/
│   │   ├── main.py             FastAPI app + router registration
│   │   └── routes/             REST endpoints (cases, pipeline, profiles, topics…)
│   ├── db/
│   │   ├── models.py           SQLAlchemy ORM models
│   │   ├── session.py          Neon connection + init_db
│   │   ├── channel_profile.py  get_profile_for_case()
│   │   └── seed_default_profile.py  seeds indian-true-crime-hindi row
│   ├── pipeline/               CaseState, orchestration, manifest, research quality
│   ├── providers/              image_gen + clip_rerank abstraction
│   └── scrapers/               Indian Kanoon, NewsAPI, RSS, archive.org, URL scraper
└── data/
    ├── cases/{slug}/           research.json, characters/, script/, audio/, broll/,
    │                           scene_images/, shorts/, output/
    ├── reports/                downloaded NCRB/CBI PDFs
    ├── news/                   cached news articles
    └── raw_judgments/          Indian Kanoon judgment text files
```

---

## Setup

### 1. Prerequisites

- Python 3.11+
- Node.js 18+
- FFmpeg installed and on PATH (`ffmpeg -version`)
- PostgreSQL via [Neon](https://neon.tech) (free tier)

### 2. Clone and install

```bash
git clone https://github.com/pandey0/storyforge.git
cd storyforge

# Python deps
pip install -r requirements.txt

# Frontend deps
cd frontend && npm install && cd ..
```

### 3. Environment

```bash
cp .env.example .env   # .env.example documents every variable
```

Fill in `.env`:

| Variable | Where to get it | Required |
|---|---|---|
| `DATABASE_URL` | [neon.tech](https://neon.tech) → Connection string | Yes |
| `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com) → Get API Key | Yes |
| `SARVAM_API_KEY` | [sarvam.ai](https://sarvam.ai) → API | Yes |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) | Yes (scene images) |
| `PEXELS_API_KEY` | [pexels.com/api](https://www.pexels.com/api/) | Yes (b-roll) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) | Optional (thumbnails) |
| `YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN` | Google Cloud Console → YouTube Data API v3 | Optional (publish) |

### 4. Database init + seed

```bash
python -c "from src.db.session import init_db; init_db()"
python src/db/seed_default_profile.py
```

### 5. Start

```bash
# Backend (terminal 1)
uvicorn src.api.main:app --reload --port 8000

# Frontend (terminal 2)
cd frontend && npm run dev
```

Control room: [http://localhost:3000](http://localhost:3000)  
API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Core Concepts

### Case is data, not code

No case name belongs in agent logic, schema, or routing. Cases are rows in the `cases` table + files under `data/cases/{slug}/`. Create a case via the dashboard or `POST /api/cases`.

### Niche is data too

Genre, voice, language, section structure, and entity-role taxonomy live on `ChannelProfile` (a DB row), not in Python files. Agents read `profile.voice_system_prompt`, `profile.section_headers`, `profile.shorts_topics`, etc. via `get_profile_for_case(slug)`. A second niche (different language, different structure, different voice) is a new `channel_profiles` row — never a code change.

### Track independence

Only `research.json` + `characters` output is shared. Past that fork, longform and shorts never read each other's output. Either must run to completion alone.

### Manual script override

Save a manually-written script to `data/cases/{slug}/script_manual.md`. The pipeline prefers it over the AI draft when it exists.

---

## API Reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/cases` | List cases. `?track=longform\|shorts` to filter. |
| `POST` | `/api/cases` | Create case. Pass `extra: {case_type: "longform"\|"shorts"}`. |
| `GET` | `/api/cases/{slug}` | Case detail |
| `GET` | `/api/profiles` | List channel profiles |
| `POST` | `/api/profiles` | Create profile |
| `PUT` | `/api/profiles/{slug}` | Update profile |
| `DELETE` | `/api/profiles/{slug}` | Delete profile (blocked if cases reference it) |
| `POST` | `/api/pipeline/{slug}/run` | Run pipeline step |
| `GET` | `/api/pipeline/{slug}/status` | Step status |
| `GET` | `/api/logs/{slug}/stream` | SSE log stream |
| `GET` | `/api/topics/search` | Search web for topic ideas (`?q=&language=&limit=`) |

Full interactive docs at `/docs` (Swagger UI) when the backend is running.

---

## Adding a New Niche

1. Create a row in `channel_profiles`:

```python
# src/db/seed_default_profile.py is the pattern to follow
profile = ChannelProfile(
    slug="english-tech-docs",
    name="English Tech Documentaries",
    language="en",
    voice_system_prompt="...",
    section_headers=["HOOK", "BACKGROUND", "RISE", "FALL", "LESSONS"],
    shorts_topics=[...],
    entity_roles=[...],
    ...
)
```

2. Set `channel_profile_id` on new cases to the new profile's ID.

No Python agent files need editing.

---

## Design Principles

- **Cost control** — paid API calls are capped, cached, and idempotent. Re-running a step costs ~$0 for already-processed content.
- **Graceful degradation** — missing API keys log a warning and return `[]`/`None`. Never crash the pipeline.
- **Per-step granularity** — every step is independently runnable and re-runnable.
- **No silent caps** — when a cost cap drops content, it is logged explicitly.

See `docs/SAAS_DESIGN.md` for the full design checklist applied before any new feature.

---

## License

Private repository. All rights reserved.
