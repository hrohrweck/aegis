"""LLM-based content evaluation, categorization, and enrichment."""

from __future__ import annotations

import structlog

from src.config import TopicConfig
from src.llm.client import LLMClient
from src.llm.prompts import (
    fact_check_prompt,
    opinion_prompt,
    relation_prompt,
    relevance_prompt,
    summary_prompt,
    system_prompt,
)
from src.pipeline.content import ContentEvaluation, ContentRelation, RawContent
from src.sources.web_search import BraveWebSearchSource

logger = structlog.get_logger()


class ContentEvaluator:
    """Evaluates and enriches content using an LLM."""

    def __init__(
        self,
        llm: LLMClient,
        topic_config: TopicConfig,
        web_search: BraveWebSearchSource | None = None,
    ) -> None:
        self.llm = llm
        self.topic_config = topic_config
        self.web_search = web_search
        self._categories = [
            {"name": c.name, "description": c.description}
            for c in topic_config.categories
        ]
        self._system = system_prompt(topic_config.name, topic_config.description)

    async def evaluate_relevance(self, raw: RawContent) -> ContentEvaluation:
        """Evaluate content relevance, categorize, and generate summary + enrichment."""
        evaluation = ContentEvaluation()

        # Step 1: Relevance scoring and categorization
        relevance_result = await self._assess_relevance(raw)
        evaluation.relevance_score = relevance_result.get("relevance_score", 0)
        evaluation.category = relevance_result.get("category", "")
        evaluation.target_audiences = relevance_result.get("target_audiences", [])
        evaluation.tags = relevance_result.get("tags", [])

        # If not relevant enough, skip expensive operations
        # Note: threshold is checked by caller (processor) using global config
        if not evaluation.category:
            logger.info(
                "evaluator.no_category",
                title=raw.title[:60],
                topic=self.topic_config.name,
            )
            return evaluation

        # Step 2: Generate summary and detailed description
        summary_result = await self._generate_summary(raw)
        evaluation.summary = summary_result.get("summary", "")
        evaluation.detailed_description = summary_result.get("detailed_description", "")

        # Step 3: Fact-check using web search
        evaluation.fact_check = await self._fact_check(raw, evaluation.summary)

        # Step 4: Generate opinion
        evaluation.opinion = await self._generate_opinion(
            raw, evaluation.summary, evaluation.category
        )

        logger.info(
            "evaluator.complete",
            title=raw.title[:60],
            score=evaluation.relevance_score,
            category=evaluation.category,
            topic=self.topic_config.name,
        )

        return evaluation

    async def detect_relations(
        self,
        raw: RawContent,
        evaluation: ContentEvaluation,
        existing_content: list[dict],
    ) -> list[ContentRelation]:
        """Find relationships between new content and existing items."""
        if not existing_content:
            return []

        prompt = relation_prompt(
            new_title=raw.title,
            new_summary=evaluation.summary,
            new_category=evaluation.category,
            existing_content=existing_content[: len(self.topic_config.categories) * 3],
        )

        result = await self.llm.complete_json(self._system, prompt)
        relations = []
        for rel in result.get("relations", []):
            try:
                relations.append(
                    ContentRelation(
                        related_content_id=int(rel["related_content_id"]),
                        relation_type=rel.get("relation_type", "related"),
                        description=rel.get("description", ""),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue

        return relations[: len(self.topic_config.categories)]

    async def _assess_relevance(self, raw: RawContent) -> dict:
        prompt = relevance_prompt(
            title=raw.title,
            description=raw.description[:500],
            url=raw.url,
            categories=self._categories,
            topic_name=self.topic_config.name,
            topic_description=self.topic_config.description,
        )
        result = await self.llm.complete_json(self._system, prompt)
        # Validate/clamp score
        score = result.get("relevance_score", 0)
        if not isinstance(score, int):
            try:
                score = int(score)
            except (ValueError, TypeError):
                score = 0
        result["relevance_score"] = max(0, min(10, score))
        return result

    async def _generate_summary(self, raw: RawContent) -> dict:
        prompt = summary_prompt(
            title=raw.title,
            description=raw.description[:1000],
            url=raw.url,
        )
        return await self.llm.complete_json(self._system, prompt)

    async def _fact_check(self, raw: RawContent, summary: str) -> str:
        """Use web search to gather sources, then LLM to fact-check."""
        search_results = []
        if self.web_search:
            search_query = f"{raw.title} fact check"
            search_results = await self.web_search.search_for_fact_check(search_query)

        if not search_results:
            return "No additional sources found for fact-checking."

        prompt = fact_check_prompt(
            title=raw.title,
            summary=summary,
            search_results=search_results,
        )
        result = await self.llm.complete_json(self._system, prompt)
        return result.get("fact_check", "Fact-check could not be completed.")

    async def _generate_opinion(
        self, raw: RawContent, summary: str, category: str
    ) -> str:
        prompt = opinion_prompt(
            title=raw.title,
            summary=summary,
            category=category,
            topic_name=self.topic_config.name,
            topic_description=self.topic_config.description,
        )
        result = await self.llm.complete_json(self._system, prompt)
        return result.get("opinion", "")
