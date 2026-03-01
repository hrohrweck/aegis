"""Configuration loading and validation using Pydantic."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


def _resolve_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} patterns with environment variable values."""
    pattern = re.compile(r"\$\{(\w+)\}")

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


class YouTubeConfig(BaseModel):
    api_key: str = ""
    search_interval_minutes: int = 120
    channel_check_interval_minutes: int = 30
    max_results_per_search: int = 10
    search_keywords: list[str] = Field(default_factory=list)
    monitored_channels: list[MonitoredChannel] = Field(default_factory=list)


class WebSearchConfig(BaseModel):
    api_key: str = ""
    search_interval_minutes: int = 60
    max_results_per_query: int = 10
    search_queries: list[str] = Field(default_factory=list)


class CategoryConfig(BaseModel):
    name: str
    description: str
    discord_channel_id: int = 0


class PipelineConfig(BaseModel):
    relevance_threshold: int = 6
    max_content_age_hours: int = 72
    relation_lookback_days: int = 14
    max_relations: int = 5
    batch_size: int = 5


class SchedulerConfig(BaseModel):
    cleanup_interval_hours: int = 24
    content_retention_days: int = 90


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
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    categories: list[CategoryConfig] = Field(default_factory=list)
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
