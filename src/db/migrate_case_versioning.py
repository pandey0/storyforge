"""Add parent_case_id, case_version, pivot_step columns to cases table."""
from sqlalchemy import text

def migrate():
    from dotenv import load_dotenv
    load_dotenv()
    from src.db.session import get_engine
    engine = get_engine()
    with engine.connect() as conn:
        # Add columns only if they don't exist
        conn.execute(text("""
            ALTER TABLE cases
            ADD COLUMN IF NOT EXISTS parent_case_id UUID REFERENCES cases(id),
            ADD COLUMN IF NOT EXISTS case_version INTEGER NOT NULL DEFAULT 1,
            ADD COLUMN IF NOT EXISTS pivot_step VARCHAR(50)
        """))
        conn.commit()
    print("Migration complete: cases table updated with versioning columns")

if __name__ == "__main__":
    migrate()
