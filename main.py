#!/usr/bin/env python3
"""Entry point. Loads .env then starts the pipeline orchestrator."""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"))

from src.db.session import init_db
from src.pipeline.orchestrator import PipelineOrchestrator
from loguru import logger


def main() -> None:
    logger.info("IndianCrimes — starting up")

    try:
        init_db()
        logger.info("DB initialised")
    except Exception as exc:
        logger.error("DB init failed: {} — check DATABASE_URL in .env", exc)
        sys.exit(1)

    orchestrator = PipelineOrchestrator()
    orchestrator.start()


if __name__ == "__main__":
    main()
