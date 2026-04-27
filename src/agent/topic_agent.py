"""Topic Agent — per-topic content discovery, evaluation, and publishing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from src.config import AppConfig, TopicConfig
from src.discord_bot.bot import CuratorBot
from src.discord_bot.publisher import ContentPublisher
from src.llm.client import LLMClient
from src.llm.prompts import query_generation_prompt, system_prompt
from src.pipeline.processor import ContentProcessor
from src.sources.base import ContentSource
from src.sources.web_search import BraveWebSearchSource
from src.sources.youtube_channels import YouTubeChannelSource
from src.sources.youtube_search import YouTubeSearchSource

logger = structlog.get_logger()


class TopicAgent:
    """Manages the full content lifecycle for a single topic.

    Each agent operates independently with its own:
    - Query generation and caching
    - Content sources (configured per topic)
    - Evaluation pipeline (topic-specific prompts and categories)
    - Discord publisher (topic-specific channel mappings)
    """

    def __init__(
        self,
        topic_config: TopicConfig,
        global_config: AppConfig,
        llm: LLMClient,
        bot: CuratorBot,
        youtube_source: YouTubeSearchSource | None = None,
        web_search_source: BraveWebSearchSource | None = None,
        channel_source: YouTubeChannelSource | None = None,
    ) -> None:
        self.topic_config = topic_config
        self.global_config = global_config
        self.llm = llm
        self.bot = bot
        self.name = topic_config.name

        # Query cache: {source_type: {"queries": [...], "generated_at": datetime}}
        self._query_cache: dict[str, dict] = {}

        # Build sources for this topic
        self._youtube_source = youtube_source
        self._web_search_source = web_search_source
        self._channel_source = channel_source

        self._sources: list[ContentSource] = []
        if youtube_source and topic_config.search.youtube.enabled:
            self._sources.append(youtube_source)
        if web_search_source and topic_config.search.web.enabled:
            self._sources.append(web_search_source)
        if channel_source:
            # Channel source is global, not per-topic query-based
            self._sources.append(channel_source)

        # Build processor and publisher
        self.processor = ContentProcessor(
            llm=llm,
            config=global_config,
            topic_config=topic_config,
            web_search=web_search_source,
        )
        self.publisher = ContentPublisher(bot, topic_config)

    @property
    def sources(self) -> list[ContentSource]:
        """Return the active content sources for this topic."""
        return self._sources

    def _needs_query_refresh(self, source_type: str) -> bool:
        """Check if queries for a source type need to be regenerated."""
        cache = self._query_cache.get(source_type)
        if not cache:
            return True
        generated_at = cache.get("generated_at")
        if not generated_at:
            return True
        interval = timedelta(hours=self.topic_config.search.query_refresh_interval_hours)
        return datetime.now(UTC) - generated_at > interval

    async def generate_queries(self, force: bool = False) -> dict[str, list[str]]:
        """Generate search queries for all enabled sources using the LLM.

        Returns a dict mapping source type to list of queries.
        """
        results: dict[str, list[str]] = {}
        sys = system_prompt(self.name, self.topic_config.description)

        for source_type in ("youtube", "web"):
            if not force and not self._needs_query_refresh(source_type):
                results[source_type] = self._query_cache[source_type]["queries"]
                continue

            source_config = getattr(self.topic_config.search, source_type)
            if not source_config.enabled:
                continue

            existing = self._query_cache.get(source_type, {}).get("queries")
            prompt = query_generation_prompt(
                topic_name=self.name,
                topic_description=self.topic_config.description,
                source_type=source_type,
                count=self.topic_config.search.query_count_per_source,
                existing_queries=existing,
            )

            try:
                result = await self.llm.complete_json(sys, prompt)
                queries = result.get("queries", [])
                if not queries:
                    logger.warning(
                        "agent.query_gen_empty",
                        topic=self.name,
                        source=source_type,
                    )
                    continue

                self._query_cache[source_type] = {
                    "queries": queries,
                    "generated_at": datetime.now(UTC),
                }
                results[source_type] = queries
                logger.info(
                    "agent.queries_generated",
                    topic=self.name,
                    source=source_type,
                    count=len(queries),
                )
            except Exception:
                logger.exception("agent.query_gen_failed", topic=self.name, source=source_type)
                # Fallback to cached queries if available
                if existing:
                    results[source_type] = existing

        return results

    async def fetch_and_process(self) -> dict[str, int]:
        """Run all sources, process discovered content, and return counts per source."""
        results: dict[str, int] = {}
        for source in self._sources:
            count = await self.fetch_and_process_source(source)
            results[source.source_name] = count
        return results

    async def fetch_and_process_source(self, source: ContentSource) -> int:
        """Run a single source, process discovered content, and return count processed."""
        # Ensure queries are fresh
        queries = await self.generate_queries()

        source_queries = None
        if isinstance(source, YouTubeSearchSource) and "youtube" in queries:
            source_queries = queries["youtube"]
        elif isinstance(source, BraveWebSearchSource) and "web" in queries:
            source_queries = queries["web"]
        # YouTubeChannelSource ignores queries

        try:
            raw_items = await source.fetch(source_queries)
            if raw_items:
                processed = await self.processor.process_source(source)
                return len(processed)
            return 0
        except Exception:
            logger.exception(
                "agent.fetch_process_failed",
                topic=self.name,
                source=source.source_name,
            )
            return 0

    async def post_pending(self) -> int:
        """Post approved content to Discord. Returns count posted."""
        try:
            pending = await self.processor.get_postable_content(limit=5)
            if not pending:
                return 0

            posted = await self.publisher.publish_batch(pending)
            logger.info("agent.posted", topic=self.name, posted=posted, pending=len(pending))
            return posted
        except Exception:
            logger.exception("agent.post_failed", topic=self.name)
            return 0

    async def run_cycle(self) -> dict[str, int]:
        """Run a full cycle: fetch, process, and post. Returns combined stats."""
        stats = await self.fetch_and_process()
        posted = await self.post_pending()
        stats["_posted"] = posted
        return stats

    def get_source_interval(self, source: ContentSource) -> int:
        """Get the configured interval in minutes for a source."""
        if isinstance(source, YouTubeSearchSource):
            return self.topic_config.search.youtube.interval_minutes
        if isinstance(source, BraveWebSearchSource):
            return self.topic_config.search.web.interval_minutes
        if isinstance(source, YouTubeChannelSource):
            return self.global_config.youtube.channel_check_interval_minutes
        return 60

    async def close(self) -> None:
        """Close any resources owned by this agent."""
        # Sources are shared and closed by the caller (main)
        pass
