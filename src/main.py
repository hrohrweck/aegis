"""Main entry point — wires everything together and starts the application."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from threading import Thread

import structlog
import uvicorn
from dotenv import load_dotenv

from src.agent.topic_agent import TopicAgent
from src.config import AppConfig, DiscordConfig, load_config
from src.dashboard.app import create_dashboard_app
from src.dashboard.routes import router as dashboard_router
from src.db.database import close_db, get_db
from src.discord_bot.bot import CuratorBot, create_bot
from src.llm.client import LLMClient
from src.scheduler.jobs import TopicScheduler
from src.sources.web_search import BraveWebSearchSource
from src.sources.youtube_channels import YouTubeChannelSource
from src.sources.youtube_search import YouTubeSearchSource


def setup_logging(config: AppConfig) -> None:
    """Configure structlog and stdlib logging."""
    log_level = getattr(logging, config.logging.level, logging.INFO)

    # Ensure log directory exists
    if config.logging.file:
        Path(config.logging.file).parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[
            logging.StreamHandler(sys.stdout),
            *(
                [logging.FileHandler(config.logging.file)]
                if config.logging.file
                else []
            ),
        ],
    )

    renderer = (
        structlog.dev.ConsoleRenderer()
        if sys.stdout.isatty()
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def create_shared_sources(config: AppConfig) -> tuple[
    YouTubeSearchSource | None,
    YouTubeChannelSource | None,
    BraveWebSearchSource | None,
]:
    """Initialize shared content source instances."""
    youtube_search = None
    youtube_channels = None
    web_search = None

    if config.youtube.api_key:
        youtube_search = YouTubeSearchSource(config.youtube)
        if config.youtube.monitored_channels:
            youtube_channels = YouTubeChannelSource(config.youtube)

    if config.web_search.api_key:
        web_search = BraveWebSearchSource(config.web_search)

    return youtube_search, youtube_channels, web_search


def _get_topic_discord_config(
    topic_config, default_config: DiscordConfig
) -> DiscordConfig:
    """Return the effective DiscordConfig for a topic (default or override)."""
    if topic_config.discord is None:
        return default_config
    return DiscordConfig(
        bot_token=topic_config.discord.bot_token or default_config.bot_token,
        guild_id=topic_config.discord.guild_id or default_config.guild_id,
    )


def _bot_key(config: DiscordConfig) -> str:
    """Unique key for a Discord bot configuration."""
    return f"{config.bot_token}:{config.guild_id}"


def create_topic_agents(
    config: AppConfig,
    llm: LLMClient,
    bots: dict[str, CuratorBot],
    youtube_search: YouTubeSearchSource | None,
    youtube_channels: YouTubeChannelSource | None,
    web_search: BraveWebSearchSource | None,
) -> list[TopicAgent]:
    """Create a TopicAgent for each configured topic."""
    agents: list[TopicAgent] = []

    for topic_config in config.topics:
        # Determine which sources are enabled for this topic
        yt = youtube_search if youtube_search and topic_config.search.youtube.enabled else None
        ws = web_search if web_search and topic_config.search.web.enabled else None
        ch = youtube_channels if youtube_channels else None

        # Select the appropriate bot for this topic
        discord_config = _get_topic_discord_config(topic_config, config.default_discord)
        bot = bots[_bot_key(discord_config)]

        agent = TopicAgent(
            topic_config=topic_config,
            global_config=config,
            llm=llm,
            bot=bot,
            youtube_source=yt,
            web_search_source=ws,
            channel_source=ch,
        )
        agents.append(agent)

    return agents


async def run_app(config: AppConfig) -> None:
    """Run the full application stack."""
    logger = structlog.get_logger()
    logger.info("app.starting")

    # Initialize database
    await get_db()

    # Create shared components
    llm = LLMClient(config.llm)
    youtube_search, youtube_channels, web_search = create_shared_sources(config)

    # Create Discord bots (one per unique discord config)
    bots: dict[str, CuratorBot] = {}
    discord_configs = [config.default_discord]
    for topic_config in config.topics:
        dc = _get_topic_discord_config(topic_config, config.default_discord)
        if _bot_key(dc) not in [_bot_key(c) for c in discord_configs]:
            discord_configs.append(dc)

    for dc in discord_configs:
        bots[_bot_key(dc)] = create_bot(dc)

    # Create topic agents
    agents = create_topic_agents(
        config, llm, bots, youtube_search, youtube_channels, web_search
    )

    logger.info(
        "app.agents_ready",
        topics=[a.name for a in agents],
        sources={
            "youtube_search": youtube_search is not None,
            "youtube_channels": youtube_channels is not None,
            "web_search": web_search is not None,
        },
    )

    # Create scheduler
    scheduler = TopicScheduler(config, agents)
    scheduler.setup()

    # Start dashboard in a background thread
    dashboard_thread = None
    if config.dashboard.enabled:
        dashboard_app = create_dashboard_app()
        dashboard_app.include_router(dashboard_router)

        uvicorn_config = uvicorn.Config(
            dashboard_app,
            host=config.dashboard.host,
            port=config.dashboard.port,
            log_level="warning",
        )
        server = uvicorn.Server(uvicorn_config)
        dashboard_thread = Thread(target=server.run, daemon=True)
        dashboard_thread.start()
        logger.info(
            "dashboard.started",
            url=f"http://{config.dashboard.host}:{config.dashboard.port}",
        )

    # Shutdown handler
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("app.shutdown_signal")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # Start Discord bots
    bot_tasks: list[asyncio.Task] = []
    started_bots = 0
    for key, bot in bots.items():
        if bot.config.bot_token:
            task = asyncio.create_task(bot.start(bot.config.bot_token))
            bot_tasks.append(task)
            started_bots += 1
            logger.info("discord.bot_starting", guild_id=bot.config.guild_id)
        else:
            logger.warning(
                "discord.no_token",
                guild_id=bot.config.guild_id,
                msg="Bot will not start — no token configured",
            )
    if started_bots:
        logger.info("discord.bots_started", count=started_bots)

    scheduler.start()

    # Run an initial fetch on startup
    logger.info("app.initial_fetch")
    try:
        results = await scheduler.run_all_topics_now()
        for topic_name, stats in results.items():
            logger.info("app.initial_fetch_result", topic=topic_name, stats=stats)
    except Exception:
        logger.exception("app.initial_fetch_failed")

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Cleanup
    logger.info("app.shutting_down")
    scheduler.stop()

    for task in bot_tasks:
        if not task.done():
            task.cancel()
    for bot in bots.values():
        if not bot.is_closed():
            await bot.close()

    for source in (youtube_search, youtube_channels, web_search):
        if source:
            await source.close()

    await close_db()
    logger.info("app.stopped")


def main() -> None:
    """CLI entry point."""
    load_dotenv()

    config_path = os.environ.get("CONFIG_PATH", "config/config.yaml")

    try:
        config = load_config(config_path)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {config_path}")
        print("Copy config/config.yaml and fill in your API keys.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to load config: {e}")
        sys.exit(1)

    if not config.topics:
        print("ERROR: No topics configured. Add at least one topic to config/config.yaml.")
        sys.exit(1)

    setup_logging(config)

    try:
        asyncio.run(run_app(config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
