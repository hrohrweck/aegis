"""Tests for content source initialization and configuration."""

from __future__ import annotations

import pytest

from src.config import AppConfig, YouTubeConfig, WebSearchConfig
from src.sources.youtube_search import YouTubeSearchSource
from src.sources.youtube_channels import YouTubeChannelSource
from src.sources.web_search import BraveWebSearchSource


class TestYouTubeSearchSource:
    def test_source_name(self):
        config = YouTubeConfig(api_key="test", search_keywords=["AI"])
        source = YouTubeSearchSource(config)
        assert source.source_name == "YouTube Search"

    async def test_returns_empty_without_api_key(self):
        config = YouTubeConfig(api_key="", search_keywords=["AI"])
        source = YouTubeSearchSource(config)
        results = await source.fetch()
        assert results == []
        await source.close()


class TestYouTubeChannelSource:
    def test_source_name(self):
        config = YouTubeConfig(api_key="test")
        source = YouTubeChannelSource(config)
        assert source.source_name == "YouTube Channels"

    async def test_returns_empty_without_channels(self):
        config = YouTubeConfig(api_key="test", monitored_channels=[])
        source = YouTubeChannelSource(config)
        results = await source.fetch()
        assert results == []
        await source.close()

    async def test_returns_empty_without_api_key(self):
        config = YouTubeConfig(api_key="")
        source = YouTubeChannelSource(config)
        results = await source.fetch()
        assert results == []
        await source.close()


class TestBraveWebSearchSource:
    def test_source_name(self):
        config = WebSearchConfig(api_key="test", search_queries=["AI"])
        source = BraveWebSearchSource(config)
        assert source.source_name == "Web Search (Brave)"

    async def test_returns_empty_without_api_key(self):
        config = WebSearchConfig(api_key="", search_queries=["AI"])
        source = BraveWebSearchSource(config)
        results = await source.fetch()
        assert results == []
        await source.close()

    async def test_fact_check_returns_empty_without_key(self):
        config = WebSearchConfig(api_key="")
        source = BraveWebSearchSource(config)
        results = await source.search_for_fact_check("test query")
        assert results == []
        await source.close()
