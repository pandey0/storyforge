from __future__ import annotations

import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from src.db.models import Case, PipelineLog
from src.db.session import get_session
from src.pipeline.state import CaseState


class PipelineOrchestrator:
    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        self._scheduler.add_job(self.job_scrape_news, IntervalTrigger(hours=6), id="scrape_news")
        self._scheduler.add_job(self.job_research_cases, CronTrigger(hour=9, minute=0), id="research")
        self._scheduler.add_job(self.job_generate_scripts, CronTrigger(hour=11, minute=0), id="scripts")
        self._scheduler.add_job(self.job_produce_videos, CronTrigger(hour=13, minute=0), id="videos")
        self._scheduler.add_job(self.job_upload_videos, CronTrigger(hour=17, minute=30), id="upload")
        self._scheduler.add_job(self.job_sync_analytics, CronTrigger(hour=2, minute=0), id="analytics")

    def start(self) -> None:
        self._scheduler.start()
        logger.info("Pipeline orchestrator started — jobs scheduled")
        try:
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            self.stop()

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Pipeline orchestrator stopped")

    def job_scrape_news(self) -> None:
        self._log_job("scrape_news", "started")
        try:
            from src.scrapers.rss_monitor import RSSMonitor
            from src.scrapers.news_api import NewsAPIClient  # noqa: F401
            with get_session() as session:
                count = RSSMonitor().run(session)
                logger.info(f"Scraped {count} new articles")
            self._log_job("scrape_news", "success", f"scraped {count} articles")
        except Exception as exc:
            logger.error(f"job_scrape_news failed: {exc}")
            self._log_job("scrape_news", "failed", str(exc))

    def job_research_cases(self) -> None:
        self._log_job("research_cases", "started")
        try:
            from src.agents.case_research_agent import CaseResearchAgent
            with get_session() as session:
                cases = self._get_cases_by_status("queued", session)
                for case in cases[:3]:
                    try:
                        state = CaseState.from_db_case(case)
                        CaseResearchAgent().run(state.slug)
                        logger.info(f"Researched case: {state.slug}")
                    except Exception as case_exc:
                        logger.error(f"Research failed for {case.slug}: {case_exc}")
                        case.status = "failed"
                        case.notes = str(case_exc)
                        session.flush()
            self._log_job("research_cases", "success")
        except Exception as exc:
            logger.error(f"job_research_cases failed: {exc}")
            self._log_job("research_cases", "failed", str(exc))

    def job_generate_scripts(self) -> None:
        self._log_job("generate_scripts", "started")
        try:
            from src.agents.script_writer_agent import ScriptWriterAgent
            from src.agents.qa_agent import QAAgent
            with get_session() as session:
                cases = self._get_cases_by_status("scripting", session)
                for case in cases[:2]:
                    try:
                        state = CaseState.from_db_case(case)
                        state.research_path = f"data/cases/{state.slug}/research.json"
                        state = ScriptWriterAgent().run(state)
                        passed, notes = QAAgent().run(state)
                        if passed:
                            logger.info(f"Script QA passed: {state.slug}")
                        else:
                            logger.warning(f"Script QA failed: {state.slug} — {notes}")
                    except Exception as case_exc:
                        logger.error(f"Script generation failed for {case.slug}: {case_exc}")
                        case.status = "failed"
                        case.notes = str(case_exc)
                        session.flush()
            self._log_job("generate_scripts", "success")
        except Exception as exc:
            logger.error(f"job_generate_scripts failed: {exc}")
            self._log_job("generate_scripts", "failed", str(exc))

    def job_produce_videos(self) -> None:
        # Only produce for human_review cases that have script_path approved.
        # (human_review means QA passed, awaiting human approval)
        # Auto-approve if qa_pass and no human intervention within 24h
        self._log_job("produce_videos", "started")
        try:
            from src.agents.video_producer_agent import VideoProducerAgent
            from datetime import datetime, timedelta, timezone
            with get_session() as session:
                cases = self._get_cases_by_status("human_review", session)
                now = datetime.now(tz=timezone.utc)
                for case in cases:
                    try:
                        if case.updated_at and (now - case.updated_at.replace(tzinfo=timezone.utc)) > timedelta(hours=24):
                            state = CaseState.from_db_case(case)
                            VideoProducerAgent().run(state)
                            logger.info(f"Video produced (auto-approved): {state.slug}")
                    except Exception as case_exc:
                        logger.error(f"Video production failed for {case.slug}: {case_exc}")
                        case.status = "failed"
                        case.notes = str(case_exc)
                        session.flush()
            self._log_job("produce_videos", "success")
        except Exception as exc:
            logger.error(f"job_produce_videos failed: {exc}")
            self._log_job("produce_videos", "failed", str(exc))

    def job_upload_videos(self) -> None:
        # Upload cases in "ready" status.
        # Schedule for 6 PM IST same day if before 5:30 PM, else next day.
        self._log_job("upload_videos", "started")
        try:
            from src.agents.publish_agent import PublishAgent
            from datetime import datetime, timezone
            import pytz
            ist = pytz.timezone("Asia/Kolkata")
            now_ist = datetime.now(tz=ist)
            with get_session() as session:
                cases = self._get_cases_by_status("ready", session)
                for case in cases:
                    try:
                        state = CaseState.from_db_case(case)
                        PublishAgent().run(state)
                        logger.info(f"Uploaded video: {state.slug}")
                    except Exception as case_exc:
                        logger.error(f"Upload failed for {case.slug}: {case_exc}")
                        case.status = "failed"
                        case.notes = str(case_exc)
                        session.flush()
            self._log_job("upload_videos", "success")
        except Exception as exc:
            logger.error(f"job_upload_videos failed: {exc}")
            self._log_job("upload_videos", "failed", str(exc))

    def job_sync_analytics(self) -> None:
        self._log_job("sync_analytics", "started")
        try:
            from src.agents.analytics_agent import AnalyticsAgent
            with get_session() as session:
                AnalyticsAgent().run(session)
                logger.info("Analytics synced")
            self._log_job("sync_analytics", "success")
        except Exception as exc:
            logger.error(f"job_sync_analytics failed: {exc}")
            self._log_job("sync_analytics", "failed", str(exc))

    def _get_cases_by_status(self, status: str, session) -> list:
        return session.query(Case).filter(Case.status == status).order_by(Case.updated_at.asc()).all()

    def _log_job(self, job_name: str, status: str, message: str = "") -> None:
        try:
            with get_session() as session:
                log = PipelineLog(
                    agent="orchestrator",
                    action=job_name,
                    status=status,
                    message=message,
                )
                session.add(log)
        except Exception as exc:
            logger.error(f"_log_job failed: {exc}")
