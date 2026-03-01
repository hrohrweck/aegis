"""YouTube keyword search content source using YouTube Data API v3."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import structlog

from src.config import YouTubeConfig
from src.pipeline.content import RawContent, SourceType
from src.sources.base import ContentSource

logger = structlog.get_logger()

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEO_URL = "https://www.youtube.com/watch?v="


class YouTubeSearchSource(ContentSource):
    """Searches YouTube for AI-related content using keyword queries."""

    def __init__(self, config: YouTubeConfig) -> None:
        self.config = config
        self._client = httpx.AsyncClient(timeout=30)

    @property
    def source_name(self) -> str:
        return "YouTube Search"

    async def fetch(self) -> list[RawContent]:
        """Search YouTube for each configured keyword."""
        if not self.config.api_key:
            logger.warning("youtube_search.no_api_key")
            return []

        results: list[RawContent] = []
        # Search for content published in the last N hours
        published_after = (
            datetime.now(timezone.utc) - timedelta(hours=self.config.search_interval_minutes * 2 / 60)
        ).isoformat() + "Z"

        for keyword in self.config.search_keywords:
            try:
                items = await self._search(keyword, published_after)
                results.extend(items)
                logger.info(
                    "youtube_search.fetched",
                    keyword=keyword,
                    count=len(items),
                )
            except Exception:
                logger.exception("youtube_search.failed", keyword=keyword)

        return results

    async def _search(self, keyword: str, published_after: str) -> list[RawContent]:
        params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "order": "date",
            "publishedAfter": published_after,
            "maxResults": self.config.max_results_per_search,
            "key": self.config.api_key,
            "relevanceLanguage": "en",
        }

        response = await self._client.get(YOUTUBE_SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()

        items = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue

            published_at = None
            if pub_str := snippet.get("publishedAt"):
                try:
                    published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            items.append(
                RawContent(
                    url=f"{YOUTUBE_VIDEO_URL}{video_id}",
                    title=snippet.get("title", ""),
                    source_type=SourceType.YOUTUBE_SEARCH,
                    description=snippet.get("description", ""),
                    author=snippet.get("channelTitle", ""),
                    published_at=published_at,
                    thumbnail_url=(snippet.get("thumbnails", {}).get("high", {}).get("url", "")),
                    raw_metadata={"video_id": video_id, "keyword": keyword},
                )
            )

        return items

    async def close(self) -> None:
        await self._client.aclose()
