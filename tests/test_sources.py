"""Tests for content source initialization and configuration."""

from __future__ import annotations

from src.config import WebSearchGlobalConfig, YouTubeGlobalConfig
from src.sources.web_search import BraveWebSearchSource
from src.sources.youtube_channels import YouTubeChannelSource
from src.sources.youtube_search import YouTubeSearchSource


class TestYouTubeSearchSource:
    def test_source_name(self):
        config = YouTubeGlobalConfig(api_key="test")
        source = YouTubeSearchSource(config)
        assert source.source_name == "YouTube Search"

    async def test_returns_empty_without_api_key(self):
        config = YouTubeGlobalConfig(api_key="")
        source = YouTubeSearchSource(config)
        results = await source.fetch(queries=["AI"])
        assert results == []
        await source.close()

    async def test_returns_empty_without_queries(self):
        config = YouTubeGlobalConfig(api_key="test")
        source = YouTubeSearchSource(config)
        results = await source.fetch(queries=[])
        assert results == []
        await source.close()

    async def test_returns_empty_with_none_queries(self):
        config = YouTubeGlobalConfig(api_key="test")
        source = YouTubeSearchSource(config)
        results = await source.fetch(queries=None)
        assert results == []
        await source.close()


class TestYouTubeChannelSource:
    def test_source_name(self):
        config = YouTubeGlobalConfig(api_key="test")
        source = YouTubeChannelSource(config)
        assert source.source_name == "YouTube Channels"

    async def test_returns_empty_without_channels(self):
        config = YouTubeGlobalConfig(api_key="test", monitored_channels=[])
        source = YouTubeChannelSource(config)
        results = await source.fetch()
        assert results == []
        await source.close()

    async def test_returns_empty_without_api_key(self):
        config = YouTubeGlobalConfig(api_key="")
        source = YouTubeChannelSource(config)
        results = await source.fetch()
        assert results == []
        await source.close()


class TestBraveWebSearchSource:
    def test_source_name(self):
        config = WebSearchGlobalConfig(api_key="test")
        source = BraveWebSearchSource(config)
        assert source.source_name == "Web Search (Brave)"

    async def test_returns_empty_without_api_key(self):
        config = WebSearchGlobalConfig(api_key="")
        source = BraveWebSearchSource(config)
        results = await source.fetch(queries=["AI"])
        assert results == []
        await source.close()

    async def test_returns_empty_without_queries(self):
        config = WebSearchGlobalConfig(api_key="test")
        source = BraveWebSearchSource(config)
        results = await source.fetch(queries=[])
        assert results == []
        await source.close()

    async def test_fact_check_returns_empty_without_key(self):
        config = WebSearchGlobalConfig(api_key="")
        source = BraveWebSearchSource(config)
        results = await source.search_for_fact_check("test query")
        assert results == []
        await source.close()
