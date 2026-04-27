"""APScheduler job definitions for periodic content processing across topics."""

from __future__ import annotations

import asyncio

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.agent.topic_agent import TopicAgent
from src.config import AppConfig
from src.db import repository

logger = structlog.get_logger()


class TopicScheduler:
    """Manages scheduled content discovery and posting jobs across all topics.

    Uses a concurrency semaphore to limit how many topics run simultaneously.
    """

    def __init__(
        self,
        config: AppConfig,
        agents: list[TopicAgent],
    ) -> None:
        self.config = config
        self.agents = agents
        self.scheduler = AsyncIOScheduler()
        self._semaphore = asyncio.Semaphore(config.scheduler.max_concurrent_topics)

    def setup(self) -> None:
        """Register all scheduled jobs for all topics."""
        for agent in self.agents:
            self._setup_agent_jobs(agent)

        # Global cleanup job
        self.scheduler.add_job(
            self._run_cleanup_job,
            "interval",
            hours=self.config.scheduler.cleanup_interval_hours,
            id="cleanup",
            name="Cleanup old content",
            max_instances=1,
            replace_existing=True,
        )

        logger.info(
            "scheduler.setup_complete",
            job_count=len(self.scheduler.get_jobs()),
            topics=[a.name for a in self.agents],
        )

    def _setup_agent_jobs(self, agent: TopicAgent) -> None:
        """Register jobs for a single topic agent."""
        topic = agent.name

        # Query refresh job
        self.scheduler.add_job(
            self._run_with_semaphore,
            "interval",
            hours=agent.topic_config.search.query_refresh_interval_hours,
            args=[agent.generate_queries],
            id=f"{topic}_query_refresh",
            name=f"Query refresh: {topic}",
            max_instances=1,
            replace_existing=True,
        )

        # Fetch & process job for each source
        for source in agent.sources:
            interval = agent.get_source_interval(source)
            job_id = f"{topic}_fetch_{source.source_name.lower().replace(' ', '_')}"
            self.scheduler.add_job(
                self._run_source_job,
                "interval",
                minutes=interval,
                args=[agent, source],
                id=job_id,
                name=f"Fetch: {topic} / {source.source_name}",
                max_instances=1,
                replace_existing=True,
            )

        # Posting job — check for approved content every 5 minutes
        self.scheduler.add_job(
            self._run_with_semaphore,
            "interval",
            minutes=5,
            args=[agent.post_pending],
            id=f"{topic}_posting",
            name=f"Post: {topic}",
            max_instances=1,
            replace_existing=True,
        )

        logger.info(
            "scheduler.agent_jobs_registered",
            topic=topic,
            sources=[s.source_name for s in agent.sources],
        )

    def start(self) -> None:
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("scheduler.started")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self.scheduler.shutdown(wait=False)
        logger.info("scheduler.stopped")

    async def run_all_topics_now(self) -> dict[str, dict[str, int]]:
        """Manually trigger all topics immediately. Returns topic -> source -> count."""
        results: dict[str, dict[str, int]] = {}
        for agent in self.agents:
            async with self._semaphore:
                stats = await agent.fetch_and_process()
                posted = await agent.post_pending()
                stats["_posted"] = posted
                results[agent.name] = stats
        return results

    async def _run_with_semaphore(self, coro) -> None:
        """Run a coroutine under the concurrency semaphore."""
        async with self._semaphore:
            try:
                await coro()
            except Exception:
                logger.exception("scheduler.job_failed")

    async def _run_source_job(self, agent: TopicAgent, source) -> int:
        """Job handler: fetch from source for a specific topic under semaphore."""
        async with self._semaphore:
            logger.info("job.source_start", topic=agent.name, source=source.source_name)
            try:
                count = await agent.fetch_and_process_source(source)
                logger.info(
                    "job.source_complete",
                    topic=agent.name,
                    source=source.source_name,
                    processed=count,
                )
                return count
            except Exception:
                logger.exception(
                    "job.source_failed", topic=agent.name, source=source.source_name
                )
                return 0

    async def _run_cleanup_job(self) -> None:
        """Job handler: clean up old content globally."""
        logger.info("job.cleanup_start")
        try:
            deleted = await repository.cleanup_old_content(
                retention_days=self.config.scheduler.content_retention_days,
            )
            logger.info("job.cleanup_complete", deleted=deleted)
        except Exception:
            logger.exception("job.cleanup_failed")
