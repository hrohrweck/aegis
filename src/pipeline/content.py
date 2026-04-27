"""Content data models used throughout the pipeline."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class SourceType(StrEnum):
    YOUTUBE_SEARCH = "youtube_search"
    YOUTUBE_CHANNEL = "youtube_channel"
    WEB_SEARCH = "web_search"


class ContentStatus(StrEnum):
    DISCOVERED = "discovered"
    EVALUATING = "evaluating"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"
    FAILED = "failed"


@dataclass
class RawContent:
    """Content as discovered from a source, before processing."""

    url: str
    title: str
    source_type: SourceType
    description: str = ""
    author: str = ""
    published_at: datetime | None = None
    thumbnail_url: str = ""
    raw_metadata: dict = field(default_factory=dict)

    @property
    def url_hash(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()

    @property
    def content_fingerprint(self) -> str:
        """Hash of title + description for fuzzy dedup."""
        text = f"{self.title.lower().strip()}{self.description[:200].lower().strip()}"
        return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class ContentEvaluation:
    """LLM evaluation of a piece of content."""

    relevance_score: int = 0  # 0-10
    category: str = ""
    summary: str = ""
    detailed_description: str = ""
    fact_check: str = ""
    opinion: str = ""
    target_audiences: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class ContentRelation:
    """A relationship between two pieces of content."""

    related_content_id: int = 0
    related_title: str = ""
    related_url: str = ""
    relation_type: str = ""  # e.g., "follow-up", "similar-topic", "contradicts", "builds-upon"
    description: str = ""


@dataclass
class ProcessedContent:
    """Fully processed content ready for posting."""

    id: int | None = None
    topic: str = ""
    raw: RawContent | None = None
    evaluation: ContentEvaluation = field(default_factory=ContentEvaluation)
    relations: list[ContentRelation] = field(default_factory=list)
    status: ContentStatus = ContentStatus.DISCOVERED
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    posted_at: datetime | None = None
    discord_message_id: int | None = None
    discord_thread_id: int | None = None

    @property
    def should_post(self) -> bool:
        return (
            self.status == ContentStatus.APPROVED
            and self.evaluation.relevance_score > 0
            and bool(self.evaluation.category)
        )
