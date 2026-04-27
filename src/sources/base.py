"""Abstract base class for content sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.pipeline.content import RawContent


class ContentSource(ABC):
    """Base class for all content discovery sources."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name for this source."""

    @abstractmethod
    async def fetch(self, queries: list[str] | None = None) -> list[RawContent]:
        """Fetch new content from this source.

        Args:
            queries: Optional list of search queries to use. If not provided,
                     the source may use its own default queries.
        Returns:
            A list of raw content items.
        """

    async def close(self) -> None:
        """Cleanup resources. Override if needed."""
