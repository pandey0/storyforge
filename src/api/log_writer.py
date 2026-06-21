from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


class PipelineLogger:
    """Writes log lines to per-step log AND to a combined pipeline.log."""

    def __init__(self, slug: str, step: str) -> None:
        self.slug = slug
        self.step = step
        log_dir = Path(f"data/cases/{slug}/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        self._step_log = log_dir / f"{step}.log"
        self._pipeline_log = log_dir / "pipeline.log"

    def _write(self, level: str, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {level} | {msg}\n"
        try:
            with open(self._step_log, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass
        try:
            with open(self._pipeline_log, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    def info(self, msg: str) -> None:
        self._write("INFO   ", msg)

    def warning(self, msg: str) -> None:
        self._write("WARNING", msg)

    def error(self, msg: str) -> None:
        self._write("ERROR  ", msg)
