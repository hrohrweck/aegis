"""Configuration loading and validation using Pydantic."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


def _resolve_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} patterns with environment variable values."""
    pattern = re.compile(r"\$\{(\w+)}")

    def replacer(match: re.Match) -> str:
        env_var = match.group(1)
        return os.environ.get(env_var, match.group(0))

    return pattern.sub(replacer, value)


def _resolve_env_recursive(obj: object) -> object:
    """Recursively resolve environment variables in a data structure."""
    if isinstance(obj, str):
        return _resolve_env_vars(obj)
    if isinstance(obj, dict):
        return {k: _resolve_env_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_recursive(item) for item in obj]
    return obj


class LLMConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 60
    max_retries: int = 3


class DiscordConfig(BaseModel):
    bot_token: str = ""
    guild_id: int = 0


class MonitoredChannel(BaseModel):
    channel_id: str
    name: str = ""


class YouTubeGlobalConfig(BaseModel):
    api_key: str = ""
    channel_check_interval_minutes: int = 30
    max_results_per_search: int = 10
    monitored_channels: list[MonitoredChannel] = Field(default_factory=list)


class WebSearchGlobalConfig(BaseModel):
    api_key: str = ""
    max_results_per_query: int = 10


class TopicSearchSourceConfig(BaseModel):
    enabled: bool = True
    max_results: int = 10
    interval_minutes: int = 60


class TopicSearchConfig(BaseModel):
    youtube: TopicSearchSourceConfig = Field(
        default_factory=lambda: TopicSearchSourceConfig(enabled=True, interval_minutes=120)
    )
    web: TopicSearchSourceConfig = Field(
        default_factory=lambda: TopicSearchSourceConfig(enabled=True, interval_minutes=60)
    )
    query_count_per_source: int = 5
    query_refresh_interval_hours: int = 24


class TopicCategoryConfig(BaseModel):
    name: str
    description: str
    discord_channel_id: int = 0


class TopicDiscordOverride(BaseModel):
    bot_token: str | None = None
    guild_id: int | None = None


class TopicConfig(BaseModel):
    name: str
    description: str
    categories: list[TopicCategoryConfig] = Field(default_factory=list)
    search: TopicSearchConfig = Field(default_factory=TopicSearchConfig)
    discord: TopicDiscordOverride | None = None


class PipelineConfig(BaseModel):
    relevance_threshold: int = 6
    max_content_age_hours: int = 72
    relation_lookback_days: int = 14
    max_relations: int = 5
    batch_size: int = 5


class SchedulerConfig(BaseModel):
    cleanup_interval_hours: int = 24
    content_retention_days: int = 90
    max_concurrent_topics: int = 3


class DashboardConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str | None = "logs/aegis.log"

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            msg = f"Invalid log level: {v}. Must be one of {valid}"
            raise ValueError(msg)
        return v.upper()


class AppConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    default_discord: DiscordConfig = Field(default_factory=DiscordConfig)
    topics: list[TopicConfig] = Field(default_factory=list)
    youtube: YouTubeGlobalConfig = Field(default_factory=YouTubeGlobalConfig)
    web_search: WebSearchGlobalConfig = Field(default_factory=WebSearchGlobalConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load configuration from YAML file with environment variable resolution."""
    if config_path is None:
        config_path = Path("config/config.yaml")
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    resolved = _resolve_env_recursive(raw)
    return AppConfig.model_validate(resolved)
