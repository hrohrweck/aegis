"""Content deduplication logic."""

from __future__ import annotations

import structlog

from src.db import repository
from src.pipeline.content import RawContent

logger = structlog.get_logger()


async def is_duplicate(raw: RawContent, topic: str) -> bool:
    """Check if content is a duplicate based on URL hash and content fingerprint.

    Returns True if the content should be skipped.
    """
    # Exact URL match within topic
    if await repository.content_exists(raw.url_hash, topic):
        logger.debug("dedup.url_match", url=raw.url[:80], topic=topic)
        return True

    # Similar content (same title + description) within topic
    if await repository.fingerprint_exists(raw.content_fingerprint, topic):
        logger.debug("dedup.fingerprint_match", title=raw.title[:80], topic=topic)
        return True

    return False


async def deduplicate_batch(items: list[RawContent], topic: str) -> list[RawContent]:
    """Filter out duplicates from a batch of raw content.

    Also deduplicates within the batch itself.
    """
    unique: list[RawContent] = []
    seen_urls: set[str] = set()
    seen_fingerprints: set[str] = set()

    for item in items:
        # Intra-batch dedup
        if item.url_hash in seen_urls or item.content_fingerprint in seen_fingerprints:
            continue

        # DB dedup (scoped to topic)
        if await is_duplicate(item, topic):
            continue

        seen_urls.add(item.url_hash)
        seen_fingerprints.add(item.content_fingerprint)
        unique.append(item)

    skipped = len(items) - len(unique)
    if skipped:
        logger.info(
            "dedup.filtered",
            total=len(items),
            unique=len(unique),
            skipped=skipped,
            topic=topic,
        )

    return unique
