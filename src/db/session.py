from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

load_dotenv()

_raw_url = os.environ.get("DATABASE_URL", "")

# Neon URLs may carry ?sslmode=require; SQLAlchemy needs it as connect_arg not query param
# Strip it and pass via connect_args instead to avoid driver conflicts
_connect_args: dict = {}
if "?" in _raw_url:
    # Strip all query params from URL — pass ssl via connect_args instead
    _database_url, _qs = _raw_url.split("?", 1)
    if "sslmode=require" in _qs or "sslmode" in _qs:
        _connect_args["sslmode"] = "require"
else:
    _database_url = _raw_url

engine = create_engine(
    _database_url,
    poolclass=NullPool,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine():
    return engine


def init_db() -> None:
    from .models import Base

    with engine.connect() as conn:
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        conn.commit()

    Base.metadata.create_all(bind=engine)


__all__ = ["engine", "SessionLocal", "get_session", "get_engine", "init_db"]
