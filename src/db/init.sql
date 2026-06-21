-- Indian Crime Channel — Database Schema
-- Run against Neon PostgreSQL: psql $DATABASE_URL -f src/db/init.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── CASES ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            VARCHAR(150) UNIQUE NOT NULL,   -- 'jessica-lall-murder-case'
    name            TEXT NOT NULL,                   -- 'Jessica Lall Murder Case'
    year_of_crime   INTEGER,
    location        VARCHAR(200),
    victim_name     VARCHAR(200),
    victim_age      INTEGER,
    victim_profession VARCHAR(200),
    perpetrator     TEXT,
    case_type       VARCHAR(100),                    -- 'murder'/'fraud'/'rape'/'scam'
    tier            INTEGER DEFAULT 2,               -- 1=priority, 2=standard
    status          VARCHAR(50) DEFAULT 'queued',
    -- status flow: queued → research → scripting → qa_review → human_review
    --              → tts → broll → video → thumbnail → ready → published
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── ARTICLES (scraped news) ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          VARCHAR(100),                    -- 'ndtv'/'toi'/'livelaw' etc.
    title           TEXT NOT NULL,
    content         TEXT,
    url             VARCHAR(1000) UNIQUE,
    published_at    TIMESTAMPTZ,
    story_score     FLOAT DEFAULT 0,                 -- 0.0–1.0, higher = better
    case_id         UUID REFERENCES cases(id),
    scraped_at      TIMESTAMPTZ DEFAULT NOW(),
    processed       BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_articles_score ON articles(story_score DESC);
CREATE INDEX IF NOT EXISTS idx_articles_processed ON articles(processed);

-- ── CASE RESEARCH ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS case_research (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID REFERENCES cases(id) NOT NULL,
    source_type     VARCHAR(50),
    -- 'indian_kanoon' / 'cbi_press' / 'ncrb' / 'news_archive' / 'wikipedia' / 'rss'
    source_url      VARCHAR(1000),
    source_name     VARCHAR(200),
    content         TEXT,
    judgment_date   DATE,
    saved_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_case ON case_research(case_id);

-- ── SCRIPTS ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS scripts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID REFERENCES cases(id) NOT NULL,
    version         INTEGER DEFAULT 1,               -- increments on each regeneration
    script_text     TEXT,
    word_count      INTEGER,
    duration_est_min FLOAT,                          -- estimated minutes at 150wpm
    status          VARCHAR(50) DEFAULT 'draft',
    -- draft → qa_pass → qa_fail → approved → rejected
    qa_notes        TEXT,
    qa_attempts     INTEGER DEFAULT 0,
    approved_by     VARCHAR(100) DEFAULT 'human',    -- 'human' or 'auto'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    approved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_scripts_case ON scripts(case_id);
CREATE INDEX IF NOT EXISTS idx_scripts_status ON scripts(status);

-- ── VIDEOS ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS videos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID REFERENCES cases(id) NOT NULL,
    script_id       UUID REFERENCES scripts(id),
    -- local paths
    video_path      VARCHAR(500),
    thumbnail_path  VARCHAR(500),
    audio_path      VARCHAR(500),
    -- R2 paths (after upload)
    r2_video_key    VARCHAR(500),
    r2_thumb_key    VARCHAR(500),
    -- render
    render_status   VARCHAR(50) DEFAULT 'pending',
    -- pending → rendering → done → failed
    render_started  TIMESTAMPTZ,
    render_ended    TIMESTAMPTZ,
    duration_sec    FLOAT,
    file_size_mb    FLOAT,
    -- youtube
    yt_video_id     VARCHAR(20),
    yt_url          VARCHAR(200),
    yt_title        TEXT,
    yt_description  TEXT,
    yt_tags         TEXT[],
    scheduled_at    TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_videos_case ON videos(case_id);
CREATE INDEX IF NOT EXISTS idx_videos_render ON videos(render_status);

-- ── YOUTUBE ANALYTICS ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS yt_analytics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id        UUID REFERENCES videos(id) NOT NULL,
    date            DATE NOT NULL,
    views           INTEGER DEFAULT 0,
    watch_time_hrs  FLOAT DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    comments        INTEGER DEFAULT 0,
    shares          INTEGER DEFAULT 0,
    ctr             FLOAT DEFAULT 0,                 -- click-through rate %
    avg_view_pct    FLOAT DEFAULT 0,                 -- avg % of video watched
    impressions     INTEGER DEFAULT 0,
    subscribers_gained INTEGER DEFAULT 0,
    revenue_usd     FLOAT DEFAULT 0,
    synced_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(video_id, date)
);

CREATE INDEX IF NOT EXISTS idx_analytics_video ON yt_analytics(video_id);
CREATE INDEX IF NOT EXISTS idx_analytics_date ON yt_analytics(date DESC);

-- ── BROLL CACHE ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS broll_cache (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query           VARCHAR(300),
    file_path       VARCHAR(500),
    source          VARCHAR(50),                     -- 'pexels'/'pixabay'/'local'
    source_id       VARCHAR(100),                    -- original ID from source
    license         VARCHAR(100) DEFAULT 'CC0',
    duration_sec    FLOAT,
    resolution      VARCHAR(20),                     -- '1920x1080'
    file_size_mb    FLOAT,
    cached_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_broll_query ON broll_cache(query);

-- ── PIPELINE LOG ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pipeline_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id         UUID REFERENCES cases(id),
    agent           VARCHAR(100),                    -- which agent ran
    action          VARCHAR(200),                    -- what it did
    status          VARCHAR(50),                     -- 'success'/'error'/'retry'
    message         TEXT,
    duration_sec    FLOAT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_log_case ON pipeline_log(case_id);
CREATE INDEX IF NOT EXISTS idx_log_created ON pipeline_log(created_at DESC);

-- ── SEED: Priority Tier 1 Cases ───────────────────────────────────────────────

INSERT INTO cases (slug, name, year_of_crime, location, victim_name, case_type, tier, status) VALUES
    ('jessica-lall-murder', 'Jessica Lall Murder Case', 1999, 'New Delhi', 'Jessica Lall', 'murder', 1, 'queued'),
    ('aarushi-talwar-murder', 'Aarushi Talwar Murder Case', 2008, 'Noida, UP', 'Aarushi Talwar', 'murder', 1, 'queued'),
    ('sheena-bora-murder', 'Sheena Bora Murder Case', 2012, 'Mumbai, Maharashtra', 'Sheena Bora', 'murder', 1, 'queued'),
    ('priyadarshini-mattoo', 'Priyadarshini Mattoo Murder Case', 1996, 'New Delhi', 'Priyadarshini Mattoo', 'murder', 1, 'queued'),
    ('nithari-killings', 'Nithari Serial Killings', 2006, 'Nithari, Noida', 'Multiple victims', 'serial-murder', 1, 'queued'),
    ('nanavati-case', 'K.M. Nanavati vs State of Maharashtra', 1959, 'Mumbai, Maharashtra', 'Prem Ahuja', 'murder', 1, 'queued'),
    ('vyapam-scam', 'Vyapam Scam', 2013, 'Madhya Pradesh', 'Multiple victims', 'scam', 1, 'queued'),
    ('sunanda-pushkar', 'Sunanda Pushkar Death Case', 2014, 'New Delhi', 'Sunanda Pushkar', 'suspicious-death', 1, 'queued'),
    ('uphaar-cinema-fire', 'Uphaar Cinema Fire', 1997, 'New Delhi', 'Multiple victims (59 dead)', 'negligence', 1, 'queued'),
    ('satyam-scam', 'Satyam Computer Scam', 2009, 'Hyderabad, Telangana', 'Shareholders/Employees', 'corporate-fraud', 1, 'queued')
ON CONFLICT (slug) DO NOTHING;
