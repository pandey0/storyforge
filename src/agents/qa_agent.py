from __future__ import annotations

import re
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from src.db.models import Case, Script
from src.db.session import get_session
from src.pipeline.state import CaseState

_SECTION_ORDER = [
    "## [COLD OPEN]",
    "## [THE BREAK]",
    "## [WORLD BUILDING]",
    "## [THE CRIME]",
    "## [INVESTIGATION]",
    "## [LEGAL BATTLE]",
    "## [AFTERMATH]",
    "## [SYSTEMIC ANGLE]",
    "## [CLOSE]",
]

_SENSATIONAL_PHRASES_EN = [
    "brutal murder", "heinous crime", "shocking", "unbelievable",
    "you won't believe", "in today's video", "in this video", "welcome back",
]
# Hindi equivalents
_SENSATIONAL_PHRASES_HI = [
    "दिल दहला देने वाला", "रोंगटे खड़े", "चौंकाने वाला",
    "आज के इस वीडियो में", "इस चैनल पर आपका स्वागत",
]

_COLD_OPEN_CRIME_WORDS_EN = re.compile(
    r"\b(murder|killed|dead|crime|death)\b", re.IGNORECASE
)
_COLD_OPEN_CRIME_WORDS_HI = re.compile(
    r"(हत्या|मारा गया|मृत्यु|अपराध|क़त्ल|कत्ल)"
)

_DATE_OPEN_EN = re.compile(r"^\s*(on\s+\w+|\s*in\s+\d{4})", re.IGNORECASE)
_DATE_OPEN_HI = re.compile(r"^\s*(\d{1,2}\s+\w+\s+\d{4}|सन्\s+\d{4}|साल\s+\d{4})")

# Devanagari Unicode range
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


class QAAgent:
    def run(self, state: CaseState) -> tuple[bool, str]:
        script = self._load_script(state)

        all_failures: list[str] = []

        structure_fails = self._check_structure(script)
        if structure_fails:
            logger.warning(f"QA check_structure: FAIL — {structure_fails}")
            all_failures.extend(structure_fails)
        else:
            logger.info("QA check_structure: PASS")

        voice_fails = self._check_voice(script)
        if voice_fails:
            logger.warning(f"QA check_voice: FAIL — {voice_fails}")
            all_failures.extend(voice_fails)
        else:
            logger.info("QA check_voice: PASS")

        wc_fails = self._check_word_count(script)
        if wc_fails:
            logger.warning(f"QA check_word_count: FAIL — {wc_fails}")
            all_failures.extend(wc_fails)
        else:
            logger.info("QA check_word_count: PASS")

        pause_fails = self._check_pause_markers(script)
        if pause_fails:
            logger.warning(f"QA check_pause_markers: FAIL — {pause_fails}")
            all_failures.extend(pause_fails)
        else:
            logger.info("QA check_pause_markers: PASS")

        victim_fails = self._check_victim_first(script)
        if victim_fails:
            logger.warning(f"QA check_victim_first: FAIL — {victim_fails}")
            all_failures.extend(victim_fails)
        else:
            logger.info("QA check_victim_first: PASS")

        n = len(all_failures)
        passed = n == 0
        notes = "; ".join(all_failures) if all_failures else "All checks passed"

        logger.info(f"QA RESULT: {'PASS' if passed else 'FAIL'} — {n} issues found")

        with get_session() as session:
            self._update_db(state, passed, notes, session)

        return passed, notes

    def _load_script(self, state: CaseState) -> str:
        path = state.draft_script_path
        if not path:
            raise ValueError(f"draft_script_path not set on state for slug={state.slug}")
        return Path(path).read_text(encoding="utf-8")

    def _check_structure(self, script: str) -> list[str]:
        failures: list[str] = []

        missing = [h for h in _SECTION_ORDER if h not in script]
        if missing:
            failures.append(f"Missing section headers: {missing}")

        positions = []
        for header in _SECTION_ORDER:
            idx = script.find(header)
            if idx != -1:
                positions.append((idx, header))

        if len(positions) > 1:
            for i in range(1, len(positions)):
                if positions[i][0] < positions[i - 1][0]:
                    failures.append(
                        f"Section out of order: {positions[i][1]!r} appears before {positions[i-1][1]!r}"
                    )

        return failures

    def _check_voice(self, script: str) -> list[str]:
        failures: list[str] = []
        lower = script.lower()
        is_hindi = bool(_DEVANAGARI.search(script))

        phrases = _SENSATIONAL_PHRASES_HI if is_hindi else _SENSATIONAL_PHRASES_EN
        for phrase in phrases:
            if phrase in script:
                failures.append(f"Sensationalism phrase found: {phrase!r}")

        close_start = script.find("## [CLOSE]")
        like_pos = lower.find("like and subscribe") if not is_hindi else script.find("subscribe करें")
        if like_pos != -1:
            if close_start == -1 or like_pos < close_start:
                failures.append("Subscribe call-to-action found outside ## [CLOSE]")

        cold_open_start = script.find("## [COLD OPEN]")
        the_break_start = script.find("## [THE BREAK]")
        if cold_open_start != -1:
            cold_open_end = the_break_start if the_break_start != -1 else cold_open_start + 500
            cold_open_text = script[cold_open_start:cold_open_end]
            first_500 = cold_open_text[:500]
            crime_re = _COLD_OPEN_CRIME_WORDS_HI if is_hindi else _COLD_OPEN_CRIME_WORDS_EN
            if crime_re.search(first_500):
                failures.append(
                    "COLD OPEN mentions crime/death in first 500 chars (should introduce victim as human first)"
                )

        if "[SOURCE:" not in script:
            failures.append("No source citations [SOURCE: found in script")

        return failures

    def _check_pause_markers(self, script: str) -> list[str]:
        failures: list[str] = []
        count = script.count("[PAUSE")
        if count == 0:
            failures.append("Zero [PAUSE markers found — FAIL")
        elif count < 3:
            failures.append(f"Only {count} [PAUSE marker(s) found — WARN (fewer than 3)")
        return failures

    def _check_victim_first(self, script: str) -> list[str]:
        failures: list[str] = []

        cold_open_start = script.find("## [COLD OPEN]")
        the_break_start = script.find("## [THE BREAK]")

        if cold_open_start == -1:
            return failures

        cold_open_end = the_break_start if the_break_start != -1 else len(script)
        cold_open_text = script[cold_open_start + len("## [COLD OPEN]"):cold_open_end].strip()

        if not cold_open_text:
            failures.append("COLD OPEN is empty")
            return failures

        is_hindi = bool(_DEVANAGARI.search(cold_open_text))

        if is_hindi:
            # Hindi: check COLD OPEN is non-empty and doesn't open with a date
            date_match = _DATE_OPEN_HI.match(cold_open_text)
            if date_match:
                failures.append("COLD OPEN (Hindi) opens with a date — victim should come first")
        else:
            # English: look for proper name pattern
            victim_pattern = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")
            victim_match = victim_pattern.search(cold_open_text)
            if not victim_match:
                failures.append("COLD OPEN does not contain victim's name (no proper name found)")

            date_match = _DATE_OPEN_EN.match(cold_open_text)
            if date_match:
                failures.append("COLD OPEN opens with a date before victim intro")

        return failures

    def _check_word_count(self, script: str) -> list[str]:
        failures: list[str] = []

        header_re = re.compile(r"^##\s+\[.*?\]\s*$", re.MULTILINE)
        cleaned = header_re.sub("", script)
        words = cleaned.split()
        count = len(words)

        if count < 4000:
            failures.append(f"Word count {count} < 4000 — too short")
        elif count > 8000:
            failures.append(f"Word count {count} > 8000 — definitely too long")
        elif count > 7000:
            # warn only — don't block production
            logger.warning(f"Word count {count} > 7000 — may be long but within tolerance")

        return failures

    def _update_db(self, state: CaseState, passed: bool, notes: str, session: Session) -> None:
        script_row: Script | None = (
            session.query(Script)
            .filter(Script.case_id == state.case_id)
            .order_by(Script.version.desc())
            .first()
        )
        case_row: Case | None = session.query(Case).filter(Case.id == state.case_id).first()

        if passed:
            if script_row:
                script_row.status = "qa_pass"
                script_row.qa_notes = notes
            if case_row:
                case_row.status = "human_review"
        else:
            attempts = (script_row.qa_attempts or 0) if script_row else 0
            if script_row:
                script_row.status = "qa_fail"
                script_row.qa_notes = notes
            if attempts < 3:
                if script_row:
                    script_row.qa_attempts = attempts + 1
                if case_row:
                    case_row.status = "scripting"
            else:
                if case_row:
                    case_row.status = "human_review"
                    existing_notes = case_row.notes or ""
                    case_row.notes = (
                        existing_notes + "\nMax QA retries — human needed"
                    ).strip()
