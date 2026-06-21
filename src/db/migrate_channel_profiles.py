"""Add channel_profiles table; generalize cases table beyond the true-crime niche."""
from sqlalchemy import text


def migrate():
    from dotenv import load_dotenv
    load_dotenv()
    from src.db.session import get_engine
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS channel_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                slug VARCHAR(100) UNIQUE NOT NULL,
                name TEXT NOT NULL,
                language VARCHAR(10) NOT NULL DEFAULT 'hi',
                voice_system_prompt TEXT NOT NULL,
                section_headers JSONB NOT NULL,
                case_prompt_template TEXT NOT NULL,
                word_count_range JSONB NOT NULL,
                words_per_minute INTEGER NOT NULL DEFAULT 125,
                shorts_topics JSONB NOT NULL,
                shorts_episode_prompt_template TEXT NOT NULL,
                shorts_word_range JSONB NOT NULL,
                entity_roles JSONB NOT NULL,
                research_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            ALTER TABLE cases
            ADD COLUMN IF NOT EXISTS channel_profile_id UUID REFERENCES channel_profiles(id),
            ADD COLUMN IF NOT EXISTS subject_name VARCHAR(200),
            ADD COLUMN IF NOT EXISTS extra JSONB NOT NULL DEFAULT '{}'::jsonb
        """))
        # Crime-specific dedicated columns retired — niche-specific facts now live
        # in cases.extra (JSONB). Safe: data/cases + these rows were wiped (Phase 15).
        conn.execute(text("""
            ALTER TABLE cases
            DROP COLUMN IF EXISTS victim_name,
            DROP COLUMN IF EXISTS victim_age,
            DROP COLUMN IF EXISTS victim_profession,
            DROP COLUMN IF EXISTS perpetrator,
            DROP COLUMN IF EXISTS case_type
        """))
        conn.commit()
    print("Migration complete: channel_profiles created; cases table generalized")


if __name__ == "__main__":
    migrate()
