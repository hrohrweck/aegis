"""APScheduler job definitions for periodic content processing."""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import AppConfig
from src.db import repository
from src.discord_bot.publisher import ContentPublisher
from src.pipeline.processor import ContentProcessor
from src.sources.base import ContentSource

logger = structlog.get_logger()


class JobManager:
    """Manages scheduled content discovery and posting jobs."""

    def __init__(
        self,
        config: AppConfig,
        processor: ContentProcessor,
        publisher: ContentPublisher,
        sources: list[ContentSource],
    ) -> None:
        self.config = config
        self.processor = processor
        self.publisher = publisher
        self.sources = sources
        self.scheduler = AsyncIOScheduler()

    def setup(self) -> None:
        """Register all scheduled jobs."""
        source_intervals = self._get_source_intervals()

        for source in self.sources:
            interval = source_intervals.get(source.source_name, 60)
            self.scheduler.add_job(
                self._run_source_job,
                "interval",
                minutes=interval,
                args=[source],
                id=f"source_{source.source_name}",
                name=f"Fetch: {source.source_name}",
                max_instances=1,
                replace_existing=True,
            )
            logger.info(
                "scheduler.job_registered",
                job=source.source_name,
                interval_minutes=interval,
            )

        # Posting job — check for approved content every 5 minutes
        self.scheduler.add_job(
            self._run_posting_job,
            "interval",
            minutes=5,
            id="posting",
            name="Post approved content",
            max_instances=1,
            replace_existing=True,
        )

        # Cleanup job
        self.scheduler.add_job(
            self._run_cleanup_job,
            "interval",
            hours=self.config.scheduler.cleanup_interval_hours,
            id="cleanup",
            name="Cleanup old content",
            max_instances=1,
            replace_existing=True,
        )

        logger.info("scheduler.setup_complete", job_count=len(self.scheduler.get_jobs()))

    def start(self) -> None:
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("scheduler.started")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self.scheduler.shutdown(wait=False)
        logger.info("scheduler.stopped")

    async def run_all_sources_now(self) -> dict[str, int]:
        """Manually trigger all sources immediately. Returns source -> count processed."""
        results = {}
        for source in self.sources:
            processed = await self._run_source_job(source)
            results[source.source_name] = processed
        return results

    async def _run_source_job(self, source: ContentSource) -> int:
        """Job handler: fetch from source, process, and return count."""
        logger.info("job.source_start", source=source.source_name)
        try:
            processed = await self.processor.process_source(source)
            count = len(processed)
            logger.info("job.source_complete", source=source.source_name, processed=count)
            return count
        except Exception:
            logger.exception("job.source_failed", source=source.source_name)
            return 0

    async def _run_posting_job(self) -> int:
        """Job handler: post approved content to Discord."""
        logger.debug("job.posting_start")
        try:
            pending = await self.processor.get_postable_content(limit=5)
            if not pending:
                return 0

            posted = await self.publisher.publish_batch(pending)
            logger.info("job.posting_complete", posted=posted, pending=len(pending))
            return posted
        except Exception:
            logger.exception("job.posting_failed")
            return 0

    async def _run_cleanup_job(self) -> None:
        """Job handler: clean up old content."""
        logger.info("job.cleanup_start")
        try:
            deleted = await repository.cleanup_old_content(
                retention_days=self.config.scheduler.content_retention_days,
            )
            logger.info("job.cleanup_complete", deleted=deleted)
        except Exception:
            logger.exception("job.cleanup_failed")

    def _get_source_intervals(self) -> dict[str, int]:
        """Map source names to their configured intervals."""
        return {
            "YouTube Search": self.config.youtube.search_interval_minutes,
            "YouTube Channels": self.config.youtube.channel_check_interval_minutes,
            "Web Search (Brave)": self.config.web_search.search_interval_minutes,
        }
