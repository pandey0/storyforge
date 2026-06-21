from __future__ import annotations

from loguru import logger

from src.pipeline.state import CaseState


class VideoProducerAgent:
    """Coordinates TTS → B-roll → Video assembly → Thumbnail in sequence."""

    def run(self, state: CaseState) -> CaseState:
        logger.info("VideoProducerAgent: starting for slug={}", state.slug)

        from src.agents.tts_agent import TTSAgent
        state = TTSAgent().run(state)
        if state.error:
            logger.error("TTS failed: {}", state.error)
            return state

        from src.agents.broll_agent import BRollAgent
        state = BRollAgent().run(state)
        if state.error:
            logger.warning("B-roll fetch failed (continuing): {}", state.error)
            state.error = None

        from src.video.assembler import VideoCreator
        state = VideoCreator().create(state)

        from src.agents.thumbnail_agent import ThumbnailAgent
        state = ThumbnailAgent().run(state)

        logger.success("VideoProducerAgent: done → status={}", state.status)
        return state
