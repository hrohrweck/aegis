"""YouTube channel monitoring source using YouTube Data API v3."""

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


class YouTubeChannelSource(ContentSource):
    """Monitors specific YouTube channels for new uploads."""

    def __init__(self, config: YouTubeConfig) -> None:
        self.config = config
        self._client = httpx.AsyncClient(timeout=30)

    @property
    def source_name(self) -> str:
        return "YouTube Channels"

    async def fetch(self) -> list[RawContent]:
        """Check each monitored channel for new videos."""
        if not self.config.api_key:
            logger.warning("youtube_channels.no_api_key")
            return []

        if not self.config.monitored_channels:
            logger.debug("youtube_channels.no_channels_configured")
            return []

        results: list[RawContent] = []
        published_after = (
            datetime.now(timezone.utc)
            - timedelta(minutes=self.config.channel_check_interval_minutes * 2)
        ).isoformat() + "Z"

        for channel in self.config.monitored_channels:
            try:
                items = await self._check_channel(
                    channel.channel_id, channel.name, published_after
                )
                results.extend(items)
                logger.info(
                    "youtube_channels.fetched",
                    channel=channel.name or channel.channel_id,
                    count=len(items),
                )
            except Exception:
                logger.exception(
                    "youtube_channels.failed",
                    channel=channel.channel_id,
                )

        return results

    async def _check_channel(
        self, channel_id: str, channel_name: str, published_after: str
    ) -> list[RawContent]:
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "date",
            "publishedAfter": published_after,
            "maxResults": 10,
            "key": self.config.api_key,
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
                    source_type=SourceType.YOUTUBE_CHANNEL,
                    description=snippet.get("description", ""),
                    author=snippet.get("channelTitle", "") or channel_name,
                    published_at=published_at,
                    thumbnail_url=(snippet.get("thumbnails", {}).get("high", {}).get("url", "")),
                    raw_metadata={
                        "video_id": video_id,
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                    },
                )
            )

        return items

    async def close(self) -> None:
        await self._client.aclose()
