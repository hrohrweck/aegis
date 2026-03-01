"""Discord content publishing — posts summaries to channels and creates threads."""

from __future__ import annotations

import discord
import structlog

from src.config import AppConfig
from src.db import repository
from src.discord_bot.bot import CuratorBot
from src.pipeline.content import ContentStatus, ProcessedContent

logger = structlog.get_logger()

# Discord message length limits
MAX_MESSAGE_LENGTH = 2000
MAX_EMBED_DESCRIPTION = 4096
MAX_THREAD_NAME = 100


class ContentPublisher:
    """Publishes processed content to Discord channels with threads."""

    def __init__(self, bot: CuratorBot, config: AppConfig) -> None:
        self.bot = bot
        self.config = config
        self._channel_map: dict[str, int] = {
            cat.name: cat.discord_channel_id for cat in config.categories
        }

    async def publish(self, content: ProcessedContent) -> bool:
        """Publish a single content item to the appropriate Discord channel.

        Creates a summary message and a thread with detailed information.
        Returns True if posted successfully.
        """
        if not self.bot.is_ready_to_post:
            logger.warning("publisher.bot_not_ready")
            return False

        if not content.raw or not content.evaluation.category:
            logger.warning("publisher.invalid_content", content_id=content.id)
            return False

        # Resolve channel
        channel_id = self._channel_map.get(content.evaluation.category)
        if not channel_id:
            logger.warning(
                "publisher.no_channel",
                category=content.evaluation.category,
            )
            return False

        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                "publisher.channel_not_found",
                channel_id=channel_id,
                category=content.evaluation.category,
            )
            return False

        try:
            # Post the main summary message
            message = await self._post_summary(channel, content)

            # Create a thread with detailed information
            thread = await self._create_thread(message, content)

            # Record in database
            await repository.save_discord_post(
                content_id=content.id,
                channel_id=channel_id,
                message_id=message.id,
                thread_id=thread.id if thread else None,
            )
            await repository.update_content_status(content.id, ContentStatus.POSTED)

            logger.info(
                "publisher.posted",
                content_id=content.id,
                channel=channel.name,
                thread=thread.name if thread else None,
            )
            return True

        except discord.HTTPException:
            logger.exception(
                "publisher.discord_error",
                content_id=content.id,
                channel_id=channel_id,
            )
            await repository.update_content_status(content.id, ContentStatus.FAILED)
            return False

    async def publish_batch(self, items: list[ProcessedContent]) -> int:
        """Publish a batch of content items. Returns count of successful posts."""
        posted = 0
        for content in items:
            if await self.publish(content):
                posted += 1
        return posted

    async def _post_summary(
        self, channel: discord.TextChannel, content: ProcessedContent
    ) -> discord.Message:
        """Post the main summary embed to a channel."""
        raw = content.raw
        evaluation = content.evaluation

        # Build embed
        embed = discord.Embed(
            title=_truncate(raw.title, 256),
            url=raw.url,
            description=_truncate(evaluation.summary, MAX_EMBED_DESCRIPTION),
            color=_category_color(evaluation.category),
        )

        # Add metadata fields
        if evaluation.tags:
            embed.add_field(
                name="Tags",
                value=" ".join(f"`{tag}`" for tag in evaluation.tags[:5]),
                inline=True,
            )

        embed.add_field(
            name="Relevance",
            value=f"{'★' * evaluation.relevance_score}{'☆' * (10 - evaluation.relevance_score)} ({evaluation.relevance_score}/10)",
            inline=True,
        )

        if raw.author:
            embed.add_field(name="Source", value=raw.author, inline=True)

        embed.set_footer(text=f"{evaluation.category} • {raw.source_type.value}")

        if raw.thumbnail_url:
            embed.set_thumbnail(url=raw.thumbnail_url)

        # Add relation mentions in message text
        relation_text = ""
        if content.relations:
            relation_lines = []
            for rel in content.relations[:3]:
                if rel.related_title and rel.related_url:
                    relation_lines.append(
                        f"🔗 **{rel.relation_type}**: [{_truncate(rel.related_title, 60)}]({rel.related_url})"
                    )
            if relation_lines:
                relation_text = "\n".join(relation_lines)

        message_text = relation_text if relation_text else ""
        return await channel.send(content=message_text or None, embed=embed)

    async def _create_thread(
        self, message: discord.Message, content: ProcessedContent
    ) -> discord.Thread | None:
        """Create a thread on the message with detailed information."""
        evaluation = content.evaluation
        thread_name = _truncate(f"📋 {content.raw.title}", MAX_THREAD_NAME)

        try:
            thread = await message.create_thread(name=thread_name)
        except discord.HTTPException:
            logger.exception("publisher.thread_create_failed")
            return None

        # Post detailed description
        if evaluation.detailed_description:
            desc_text = f"## 📝 Detailed Description\n\n{evaluation.detailed_description}"
            for chunk in _split_message(desc_text):
                await thread.send(chunk)

        # Post fact check
        if evaluation.fact_check:
            fc_text = f"## ✅ Fact Check\n\n{evaluation.fact_check}"
            for chunk in _split_message(fc_text):
                await thread.send(chunk)

        # Post opinion / use case assessment
        if evaluation.opinion:
            op_text = f"## 💡 Use Case & Relevance Assessment\n\n{evaluation.opinion}"
            for chunk in _split_message(op_text):
                await thread.send(chunk)

        # Post relations
        if content.relations:
            rel_lines = ["## 🔗 Related Content\n"]
            for rel in content.relations:
                title_display = rel.related_title or f"Content #{rel.related_content_id}"
                url_part = f" — {rel.related_url}" if rel.related_url else ""
                rel_lines.append(
                    f"- **{rel.relation_type}**: {title_display}{url_part}\n  {rel.description}"
                )
            rel_text = "\n".join(rel_lines)
            for chunk in _split_message(rel_text):
                await thread.send(chunk)

        return thread


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _split_message(text: str, max_len: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split a long message into chunks respecting Discord's limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Find a good split point
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1 or split_at < max_len // 2:
            split_at = text.rfind(" ", 0, max_len)
        if split_at == -1:
            split_at = max_len

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()

    return chunks


def _category_color(category: str) -> int:
    """Assign a color to a category for visual distinction in embeds."""
    colors = {
        "LLM Models & Research": 0x7289DA,  # Blurple
        "AI Tools & Products": 0x43B581,    # Green
        "AI Coding & Development": 0xFAA61A, # Orange
        "MLOps & Infrastructure": 0xF04747,  # Red
        "AI Agents & Automation": 0x9B59B6,  # Purple
        "Industry News & Analysis": 0x3498DB, # Blue
    }
    return colors.get(category, 0x99AAB5)  # Default grey
