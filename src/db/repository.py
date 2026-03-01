"""Database CRUD operations for content management."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import structlog

from src.db.database import get_db
from src.pipeline.content import (
    ContentEvaluation,
    ContentRelation,
    ContentStatus,
    ProcessedContent,
    RawContent,
    SourceType,
)

logger = structlog.get_logger()


async def content_exists(url_hash: str) -> bool:
    """Check if content with this URL hash already exists."""
    db = await get_db()
    cursor = await db.execute("SELECT 1 FROM content WHERE url_hash = ?", (url_hash,))
    row = await cursor.fetchone()
    return row is not None


async def fingerprint_exists(fingerprint: str) -> bool:
    """Check if content with a similar fingerprint exists."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT 1 FROM content WHERE content_fingerprint = ?", (fingerprint,)
    )
    row = await cursor.fetchone()
    return row is not None


async def insert_content(raw: RawContent) -> int:
    """Insert new raw content and return its ID."""
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO content
           (url, url_hash, content_fingerprint, title, description, author,
            source_type, thumbnail_url, published_at, raw_metadata, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            raw.url,
            raw.url_hash,
            raw.content_fingerprint,
            raw.title,
            raw.description,
            raw.author,
            raw.source_type.value,
            raw.thumbnail_url,
            raw.published_at.isoformat() if raw.published_at else None,
            json.dumps(raw.raw_metadata),
            ContentStatus.DISCOVERED.value,
        ),
    )
    await db.commit()
    content_id = cursor.lastrowid
    logger.info("content.inserted", content_id=content_id, title=raw.title[:80])
    return content_id


async def update_content_status(content_id: int, status: ContentStatus) -> None:
    """Update the status of a content item."""
    db = await get_db()
    await db.execute(
        "UPDATE content SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status.value, content_id),
    )
    await db.commit()


async def save_evaluation(content_id: int, evaluation: ContentEvaluation, model: str) -> None:
    """Save or update an LLM evaluation for content."""
    db = await get_db()
    await db.execute(
        """INSERT OR REPLACE INTO evaluations
           (content_id, relevance_score, category, summary, detailed_description,
            fact_check, opinion, target_audiences, tags, llm_model)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            content_id,
            evaluation.relevance_score,
            evaluation.category,
            evaluation.summary,
            evaluation.detailed_description,
            evaluation.fact_check,
            evaluation.opinion,
            json.dumps(evaluation.target_audiences),
            json.dumps(evaluation.tags),
            model,
        ),
    )
    await db.commit()


async def save_discord_post(
    content_id: int, channel_id: int, message_id: int, thread_id: int | None
) -> None:
    """Record a Discord post."""
    db = await get_db()
    await db.execute(
        """INSERT INTO discord_posts (content_id, channel_id, message_id, thread_id)
           VALUES (?, ?, ?, ?)""",
        (content_id, channel_id, message_id, thread_id),
    )
    await db.commit()


async def save_relation(
    content_id_a: int, content_id_b: int, relation_type: str, description: str
) -> None:
    """Save a relation between two content items."""
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR IGNORE INTO relations
               (content_id_a, content_id_b, relation_type, description)
               VALUES (?, ?, ?, ?)""",
            (content_id_a, content_id_b, relation_type, description),
        )
        await db.commit()
    except Exception:
        logger.warning("relation.save_failed", a=content_id_a, b=content_id_b)


async def get_recent_content(days: int = 14, limit: int = 50) -> list[dict]:
    """Get recent content with evaluations for relation detection."""
    db = await get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cursor = await db.execute(
        """SELECT c.id, c.url, c.title, c.description, c.source_type,
                  e.category, e.summary, e.tags
           FROM content c
           LEFT JOIN evaluations e ON c.id = e.content_id
           WHERE c.discovered_at >= ? AND c.status IN ('approved', 'posted')
           ORDER BY c.discovered_at DESC
           LIMIT ?""",
        (cutoff, limit),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_relations_for_content(content_id: int) -> list[ContentRelation]:
    """Get all relations for a content item."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT r.*, c.title as related_title, c.url as related_url
           FROM relations r
           JOIN content c ON (
               CASE WHEN r.content_id_a = ? THEN r.content_id_b ELSE r.content_id_a END = c.id
           )
           WHERE r.content_id_a = ? OR r.content_id_b = ?""",
        (content_id, content_id, content_id),
    )
    rows = await cursor.fetchall()
    relations = []
    for row in rows:
        related_id = row["content_id_b"] if row["content_id_a"] == content_id else row["content_id_a"]
        relations.append(
            ContentRelation(
                related_content_id=related_id,
                related_title=row["related_title"],
                related_url=row["related_url"],
                relation_type=row["relation_type"],
                description=row["description"],
            )
        )
    return relations


async def get_pending_content(limit: int = 10) -> list[ProcessedContent]:
    """Get content that has been approved but not yet posted."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT c.*, e.relevance_score, e.category, e.summary,
                  e.detailed_description, e.fact_check, e.opinion,
                  e.target_audiences, e.tags
           FROM content c
           JOIN evaluations e ON c.id = e.content_id
           WHERE c.status = 'approved'
           ORDER BY e.relevance_score DESC, c.discovered_at DESC
           LIMIT ?""",
        (limit,),
    )
    rows = await cursor.fetchall()
    results = []
    for row in rows:
        raw = RawContent(
            url=row["url"],
            title=row["title"],
            source_type=SourceType(row["source_type"]),
            description=row["description"],
            author=row["author"],
            thumbnail_url=row["thumbnail_url"] or "",
        )
        evaluation = ContentEvaluation(
            relevance_score=row["relevance_score"],
            category=row["category"],
            summary=row["summary"],
            detailed_description=row["detailed_description"],
            fact_check=row["fact_check"],
            opinion=row["opinion"],
            target_audiences=json.loads(row["target_audiences"] or "[]"),
            tags=json.loads(row["tags"] or "[]"),
        )
        relations = await get_relations_for_content(row["id"])
        results.append(
            ProcessedContent(
                id=row["id"],
                raw=raw,
                evaluation=evaluation,
                relations=relations,
                status=ContentStatus.APPROVED,
            )
        )
    return results


async def get_content_stats() -> dict:
    """Get content statistics for the dashboard."""
    db = await get_db()

    stats = {}

    cursor = await db.execute("SELECT COUNT(*) as total FROM content")
    row = await cursor.fetchone()
    stats["total_content"] = row["total"]

    cursor = await db.execute(
        "SELECT status, COUNT(*) as count FROM content GROUP BY status"
    )
    stats["by_status"] = {row["status"]: row["count"] for row in await cursor.fetchall()}

    cursor = await db.execute(
        """SELECT e.category, COUNT(*) as count
           FROM evaluations e
           JOIN content c ON c.id = e.content_id
           WHERE c.status IN ('approved', 'posted')
           GROUP BY e.category"""
    )
    stats["by_category"] = {row["category"]: row["count"] for row in await cursor.fetchall()}

    cursor = await db.execute(
        """SELECT source_type, COUNT(*) as count
           FROM content GROUP BY source_type"""
    )
    stats["by_source"] = {row["source_type"]: row["count"] for row in await cursor.fetchall()}

    cursor = await db.execute(
        """SELECT COUNT(*) as count FROM content
           WHERE discovered_at >= datetime('now', '-1 day')"""
    )
    row = await cursor.fetchone()
    stats["last_24h"] = row["count"]

    cursor = await db.execute("SELECT COUNT(*) as count FROM discord_posts")
    row = await cursor.fetchone()
    stats["total_posts"] = row["count"]

    return stats


async def get_all_content(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    category: str | None = None,
) -> tuple[list[dict], int]:
    """Get all content with evaluations for dashboard display."""
    db = await get_db()

    where_clauses = []
    params: list = []

    if status:
        where_clauses.append("c.status = ?")
        params.append(status)
    if category:
        where_clauses.append("e.category = ?")
        params.append(category)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    count_cursor = await db.execute(
        f"""SELECT COUNT(*) as total FROM content c
            LEFT JOIN evaluations e ON c.id = e.content_id
            {where_sql}""",
        params,
    )
    total = (await count_cursor.fetchone())["total"]

    cursor = await db.execute(
        f"""SELECT c.*, e.relevance_score, e.category, e.summary
            FROM content c
            LEFT JOIN evaluations e ON c.id = e.content_id
            {where_sql}
            ORDER BY c.discovered_at DESC
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows], total


async def record_search(source_type: str, query: str, results_count: int) -> None:
    """Record a search execution."""
    db = await get_db()
    await db.execute(
        """INSERT INTO search_history (source_type, query, results_count)
           VALUES (?, ?, ?)""",
        (source_type, query, results_count),
    )
    await db.commit()


async def cleanup_old_content(retention_days: int) -> int:
    """Delete content older than retention period. Returns count deleted."""
    db = await get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    cursor = await db.execute(
        "DELETE FROM content WHERE discovered_at < ? AND status != 'posted'",
        (cutoff,),
    )
    await db.commit()
    deleted = cursor.rowcount
    if deleted:
        logger.info("cleanup.deleted", count=deleted, retention_days=retention_days)
    return deleted
