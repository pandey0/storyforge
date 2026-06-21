"""Run once to add artifact_versions table."""
from src.db.session import get_engine
from src.db.models import Base, ArtifactVersion


def migrate():
    engine = get_engine()
    ArtifactVersion.__table__.create(engine, checkfirst=True)
    print("artifact_versions table created")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    migrate()
