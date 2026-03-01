"""Brave Search API content source for web-based AI content discovery."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import structlog

from src.config import WebSearchConfig
from src.pipeline.content import RawContent, SourceType
from src.sources.base import ContentSource

logger = structlog.get_logger()

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveWebSearchSource(ContentSource):
    """Searches the web for AI content using Brave Search API."""

    def __init__(self, config: WebSearchConfig) -> None:
        self.config = config
        self._client = httpx.AsyncClient(timeout=30)

    @property
    def source_name(self) -> str:
        return "Web Search (Brave)"

    async def fetch(self) -> list[RawContent]:
        """Run all configured search queries."""
        if not self.config.api_key:
            logger.warning("web_search.no_api_key")
            return []

        results: list[RawContent] = []
        seen_urls: set[str] = set()

        for query in self.config.search_queries:
            try:
                items = await self._search(query)
                # Deduplicate within this batch
                for item in items:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        results.append(item)
                logger.info("web_search.fetched", query=query, count=len(items))
            except Exception:
                logger.exception("web_search.failed", query=query)

        return results

    async def _search(self, query: str) -> list[RawContent]:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.config.api_key,
        }
        params = {
            "q": query,
            "count": self.config.max_results_per_query,
            "freshness": "pw",  # Past week
            "text_decorations": False,
            "search_lang": "en",
        }

        response = await self._client.get(
            BRAVE_SEARCH_URL, headers=headers, params=params
        )
        response.raise_for_status()
        data = response.json()

        items = []
        for result in data.get("web", {}).get("results", []):
            url = result.get("url", "")
            if not url:
                continue

            published_at = None
            if age := result.get("age"):
                # Brave returns age like "2 days ago" - we approximate
                published_at = datetime.now(timezone.utc)

            items.append(
                RawContent(
                    url=url,
                    title=result.get("title", ""),
                    source_type=SourceType.WEB_SEARCH,
                    description=result.get("description", ""),
                    author=result.get("profile", {}).get("name", ""),
                    published_at=published_at,
                    thumbnail_url=result.get("thumbnail", {}).get("src", ""),
                    raw_metadata={
                        "query": query,
                        "age": result.get("age", ""),
                        "language": result.get("language", ""),
                        "family_friendly": result.get("family_friendly", True),
                    },
                )
            )

        return items

    async def search_for_fact_check(self, query: str, count: int = 5) -> list[dict]:
        """Run a targeted search for fact-checking purposes. Returns simplified results."""
        if not self.config.api_key:
            return []

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.config.api_key,
        }
        params = {
            "q": query,
            "count": count,
            "text_decorations": False,
            "search_lang": "en",
        }

        try:
            response = await self._client.get(
                BRAVE_SEARCH_URL, headers=headers, params=params
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.exception("web_search.fact_check_failed", query=query)
            return []

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
            }
            for r in data.get("web", {}).get("results", [])
        ]

    async def close(self) -> None:
        await self._client.aclose()
