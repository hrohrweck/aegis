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

from src.config import AppConfig, load_config
from src.dashboard.app import create_dashboard_app
from src.dashboard.routes import router as dashboard_router
from src.db.database import close_db, get_db
from src.discord_bot.bot import CuratorBot, create_bot
from src.discord_bot.publisher import ContentPublisher
from src.llm.client import LLMClient
from src.pipeline.processor import ContentProcessor
from src.scheduler.jobs import JobManager
from src.sources.base import ContentSource
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

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if sys.stdout.isatty() else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def create_sources(config: AppConfig) -> tuple[list[ContentSource], BraveWebSearchSource | None]:
    """Initialize all content sources."""
    sources: list[ContentSource] = []
    web_search: BraveWebSearchSource | None = None

    # YouTube search
    if config.youtube.api_key and config.youtube.search_keywords:
        sources.append(YouTubeSearchSource(config.youtube))

    # YouTube channel monitoring
    if config.youtube.api_key and config.youtube.monitored_channels:
        sources.append(YouTubeChannelSource(config.youtube))

    # Web search (Brave)
    if config.web_search.api_key and config.web_search.search_queries:
        web_search = BraveWebSearchSource(config.web_search)
        sources.append(web_search)

    return sources, web_search


async def run_app(config: AppConfig) -> None:
    """Run the full application stack."""
    logger = structlog.get_logger()
    logger.info("app.starting")

    # Initialize database
    await get_db()

    # Create components
    llm = LLMClient(config.llm)
    sources, web_search = create_sources(config)
    processor = ContentProcessor(llm, config, web_search)
    bot = create_bot(config.discord)
    publisher = ContentPublisher(bot, config)
    job_manager = JobManager(config, processor, publisher, sources)

    logger.info(
        "app.components_ready",
        sources=[s.source_name for s in sources],
        categories=[c.name for c in config.categories],
    )

    # Setup scheduler
    job_manager.setup()

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

    # Start Discord bot + scheduler
    bot_task = None
    if config.discord.bot_token:
        bot_task = asyncio.create_task(bot.start(config.discord.bot_token))
        logger.info("discord.bot_starting")
    else:
        logger.warning("discord.no_token", msg="Bot will not start — no token configured")

    job_manager.start()

    # Run an initial fetch on startup
    logger.info("app.initial_fetch")
    try:
        results = await job_manager.run_all_sources_now()
        for source_name, count in results.items():
            logger.info("app.initial_fetch_result", source=source_name, count=count)
    except Exception:
        logger.exception("app.initial_fetch_failed")

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Cleanup
    logger.info("app.shutting_down")
    job_manager.stop()

    if bot_task and not bot_task.done():
        await bot.close()

    for source in sources:
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

    setup_logging(config)

    try:
        asyncio.run(run_app(config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
