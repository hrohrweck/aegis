"""Shared test fixtures."""

from __future__ import annotations

import asyncio

import pytest

from src.config import AppConfig


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
            "default_discord": {"bot_token": "test-token", "guild_id": 123456789},
            "youtube": {
                "api_key": "test-yt-key",
                "monitored_channels": [],
            },
            "web_search": {
                "api_key": "test-brave-key",
            },
            "topics": [
                {
                    "name": "AI",
                    "description": "Artificial intelligence content",
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
                    "search": {
                        "youtube": {"enabled": True, "interval_minutes": 120},
                        "web": {"enabled": True, "interval_minutes": 60},
                        "query_count_per_source": 3,
                        "query_refresh_interval_hours": 24,
                    },
                },
                {
                    "name": "Blockchain",
                    "description": "Blockchain and crypto content",
                    "categories": [
                        {
                            "name": "DeFi",
                            "description": "Decentralized finance",
                            "discord_channel_id": 333,
                        },
                    ],
                    "search": {
                        "youtube": {"enabled": False},
                        "web": {"enabled": True, "interval_minutes": 120},
                        "query_count_per_source": 3,
                        "query_refresh_interval_hours": 24,
                    },
                },
            ],
            "pipeline": {"relevance_threshold": 6},
        }
    )
