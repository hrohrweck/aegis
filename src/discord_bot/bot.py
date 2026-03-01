"""Discord bot setup and lifecycle management."""

from __future__ import annotations

import discord
import structlog

from src.config import DiscordConfig

logger = structlog.get_logger()


class CuratorBot(discord.Client):
    """Minimal Discord client for posting curated content.

    This bot doesn't handle commands — it only posts content to channels
    and creates threads. It runs alongside the scheduler.
    """

    def __init__(self, config: DiscordConfig) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        super().__init__(intents=intents)
        self.config = config
        self._ready = False

    async def on_ready(self) -> None:
        self._ready = True
        logger.info(
            "discord.ready",
            user=str(self.user),
            guild_id=self.config.guild_id,
        )

    @property
    def is_ready_to_post(self) -> bool:
        return self._ready and not self.is_closed()

    def get_guild(self) -> discord.Guild | None:
        """Get the configured guild."""
        return self.get_guild_by_id(self.config.guild_id)

    def get_guild_by_id(self, guild_id: int) -> discord.Guild | None:
        for guild in self.guilds:
            if guild.id == guild_id:
                return guild
        return None


def create_bot(config: DiscordConfig) -> CuratorBot:
    """Create and return a configured bot instance."""
    return CuratorBot(config)
