"""Shared test fixtures."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.config import AppConfig, load_config


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_config() -> AppConfig:
    """Minimal config for testing (no real API keys)."""
    return AppConfig.model_validate(
        {
            "llm": {
                "base_url": "http://localhost:11434/v1",
                "api_key": "test-key",
                "model": "test-model",
            },
            "discord": {"bot_token": "test-token", "guild_id": 123456789},
            "youtube": {
                "api_key": "test-yt-key",
                "search_keywords": ["AI tools"],
                "monitored_channels": [],
            },
            "web_search": {
                "api_key": "test-brave-key",
                "search_queries": ["AI news"],
            },
            "categories": [
                {
                    "name": "AI Tools & Products",
                    "description": "AI tools",
                    "discord_channel_id": 111,
                },
                {
                    "name": "LLM Models & Research",
                    "description": "LLM research",
                    "discord_channel_id": 222,
                },
            ],
            "pipeline": {"relevance_threshold": 6},
        }
    )
