"""Tests for configuration loading and validation."""

from __future__ import annotations

import os
import tempfile
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

    def test_load_full_config(self, tmp_path: Path):
        """All fields should be parsed correctly."""
        data = {
            "llm": {"base_url": "http://localhost:11434/v1", "api_key": "key", "model": "llama3"},
            "discord": {"bot_token": "token", "guild_id": 999},
            "youtube": {
                "api_key": "yt-key",
                "search_keywords": ["AI", "ML"],
                "monitored_channels": [{"channel_id": "UC123", "name": "TestCh"}],
            },
            "categories": [
                {"name": "Cat1", "description": "Desc1", "discord_channel_id": 111}
            ],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(data))

        config = load_config(config_file)
        assert config.llm.model == "llama3"
        assert config.discord.guild_id == 999
        assert len(config.youtube.search_keywords) == 2
        assert config.youtube.monitored_channels[0].channel_id == "UC123"
        assert len(config.categories) == 1

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
