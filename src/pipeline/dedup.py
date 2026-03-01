"""Content deduplication logic."""

from __future__ import annotations

import structlog

from src.db import repository
from src.pipeline.content import RawContent

logger = structlog.get_logger()


async def is_duplicate(raw: RawContent) -> bool:
    """Check if content is a duplicate based on URL hash and content fingerprint.

    Returns True if the content should be skipped.
    """
    # Exact URL match
    if await repository.content_exists(raw.url_hash):
        logger.debug("dedup.url_match", url=raw.url[:80])
        return True

    # Similar content (same title + description)
    if await repository.fingerprint_exists(raw.content_fingerprint):
        logger.debug("dedup.fingerprint_match", title=raw.title[:80])
        return True

    return False


async def deduplicate_batch(items: list[RawContent]) -> list[RawContent]:
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

        # DB dedup
        if await is_duplicate(item):
            continue

        seen_urls.add(item.url_hash)
        seen_fingerprints.add(item.content_fingerprint)
        unique.append(item)

    skipped = len(items) - len(unique)
    if skipped:
        logger.info("dedup.filtered", total=len(items), unique=len(unique), skipped=skipped)

    return unique
