"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.config import AppConfig, load_config


class TestConfigLoading:
    def test_load_minimal_config(self, tmp_path: Path):
        """A minimal YAML file should produce a valid config with defaults."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"llm": {"api_key": "sk-test"}}))

        config = load_config(config_file)
        assert config.llm.api_key == "sk-test"
        assert config.llm.model == "gpt-4o-mini"  # default
        assert config.pipeline.relevance_threshold == 6  # default
        assert config.topics == []  # default

    def test_load_topic_based_config(self, tmp_path: Path):
        """Topic-based config should parse correctly."""
        data = {
            "llm": {"base_url": "http://localhost:11434/v1", "api_key": "key", "model": "llama3"},
            "default_discord": {"bot_token": "token", "guild_id": 999},
            "youtube": {"api_key": "yt-key"},
            "topics": [
                {
                    "name": "AI",
                    "description": "AI content",
                    "categories": [
                        {"name": "Tools", "description": "AI tools", "discord_channel_id": 111}
                    ],
                    "search": {
                        "query_count_per_source": 5,
                        "query_refresh_interval_hours": 12,
                    },
                }
            ],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(data))

        config = load_config(config_file)
        assert config.llm.model == "llama3"
        assert config.default_discord.guild_id == 999
        assert len(config.topics) == 1
        assert config.topics[0].name == "AI"
        assert config.topics[0].search.query_count_per_source == 5
        assert len(config.topics[0].categories) == 1
        assert config.topics[0].categories[0].discord_channel_id == 111

    def test_env_var_resolution(self, tmp_path: Path, monkeypatch):
        """Environment variables in ${VAR} syntax should be resolved."""
        monkeypatch.setenv("TEST_API_KEY", "resolved-key")
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"llm": {"api_key": "${TEST_API_KEY}"}}))

        config = load_config(config_file)
        assert config.llm.api_key == "resolved-key"

    def test_missing_config_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path.yaml")

    def test_empty_config_file(self, tmp_path: Path):
        """An empty YAML file should produce defaults."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        config = load_config(config_file)
        assert isinstance(config, AppConfig)

    def test_invalid_log_level(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"logging": {"level": "BANANA"}}))
        with pytest.raises(Exception):
            load_config(config_file)

    def test_topic_discord_override(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        data = {
            "topics": [
                {
                    "name": "Test",
                    "description": "Test topic",
                    "discord": {"guild_id": 987654321},
                    "categories": [],
                }
            ]
        }
        config_file.write_text(yaml.dump(data))
        config = load_config(config_file)
        assert config.topics[0].discord.guild_id == 987654321
