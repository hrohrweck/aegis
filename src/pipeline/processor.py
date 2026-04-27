"""Content processing pipeline orchestration."""

from __future__ import annotations

import structlog

from src.config import AppConfig, TopicConfig
from src.db import repository
from src.llm.client import LLMClient
from src.pipeline.categorizer import ContentEvaluator
from src.pipeline.content import ContentStatus, ProcessedContent, RawContent
from src.pipeline.dedup import deduplicate_batch
from src.sources.base import ContentSource
from src.sources.web_search import BraveWebSearchSource

logger = structlog.get_logger()


class ContentProcessor:
    """Orchestrates the full content processing pipeline for a single topic."""

    def __init__(
        self,
        llm: LLMClient,
        config: AppConfig,
        topic_config: TopicConfig,
        web_search: BraveWebSearchSource | None = None,
    ) -> None:
        self.llm = llm
        self.config = config
        self.topic_config = topic_config
        self.evaluator = ContentEvaluator(llm, topic_config, web_search)
        self.topic = topic_config.name

    async def process_source(self, source: ContentSource) -> list[ProcessedContent]:
        """Fetch from a source and process all new content through the pipeline."""
        logger.info("pipeline.fetch_start", source=source.source_name, topic=self.topic)

        try:
            raw_items = await source.fetch()
        except Exception:
            logger.exception("pipeline.fetch_failed", source=source.source_name, topic=self.topic)
            return []

        if not raw_items:
            logger.info("pipeline.no_new_content", source=source.source_name, topic=self.topic)
            return []

        # Record the search
        await repository.record_search(
            source_type=source.source_name,
            query="batch",
            results_count=len(raw_items),
            topic=self.topic,
        )

        # Deduplicate (scoped to topic)
        unique_items = await deduplicate_batch(raw_items, self.topic)
        if not unique_items:
            logger.info("pipeline.all_duplicates", source=source.source_name, topic=self.topic)
            return []

        # Process in batches
        processed: list[ProcessedContent] = []
        batch_size = self.config.pipeline.batch_size

        for i in range(0, len(unique_items), batch_size):
            batch = unique_items[i : i + batch_size]
            for raw in batch:
                try:
                    result = await self._process_single(raw)
                    if result:
                        processed.append(result)
                except Exception:
                    logger.exception(
                        "pipeline.process_failed",
                        title=raw.title[:60],
                        topic=self.topic,
                    )

        logger.info(
            "pipeline.complete",
            source=source.source_name,
            topic=self.topic,
            fetched=len(raw_items),
            unique=len(unique_items),
            processed=len(processed),
            approved=sum(1 for p in processed if p.status == ContentStatus.APPROVED),
        )

        return processed

    async def _process_single(self, raw: RawContent) -> ProcessedContent | None:
        """Process a single content item through the full pipeline."""
        # Insert into DB
        content_id = await repository.insert_content(raw, self.topic)
        await repository.update_content_status(content_id, ContentStatus.EVALUATING)

        # Evaluate relevance and generate enrichment
        evaluation = await self.evaluator.evaluate_relevance(raw)

        # Save evaluation
        await repository.save_evaluation(content_id, evaluation, self.llm.model, self.topic)

        # Determine status based on relevance
        if evaluation.relevance_score >= self.config.pipeline.relevance_threshold:
            status = ContentStatus.APPROVED
        else:
            status = ContentStatus.REJECTED

        await repository.update_content_status(content_id, status)

        # Detect relations for approved content
        relations = []
        if status == ContentStatus.APPROVED:
            existing = await repository.get_recent_content(
                days=self.config.pipeline.relation_lookback_days,
                topic=self.topic,
            )
            relations = await self.evaluator.detect_relations(raw, evaluation, existing)

            # Save relations
            for rel in relations:
                await repository.save_relation(
                    content_id_a=content_id,
                    content_id_b=rel.related_content_id,
                    relation_type=rel.relation_type,
                    description=rel.description,
                    topic=self.topic,
                )

        return ProcessedContent(
            id=content_id,
            topic=self.topic,
            raw=raw,
            evaluation=evaluation,
            relations=relations,
            status=status,
        )

    async def get_postable_content(self, limit: int = 10) -> list[ProcessedContent]:
        """Get content that's been approved and ready to post."""
        return await repository.get_pending_content(limit=limit, topic=self.topic)
