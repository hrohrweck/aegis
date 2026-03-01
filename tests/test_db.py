"""Tests for database operations."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from src.db.database import close_db, get_db
from src.db import repository
from src.pipeline.content import ContentStatus, RawContent, SourceType, ContentEvaluation


@pytest.fixture(autouse=True)
async def setup_test_db(tmp_path):
    """Use a temporary database for each test."""
    test_db_path = tmp_path / "test.db"

    with patch("src.db.database.DB_PATH", test_db_path):
        # Reset the global connection
        import src.db.database as db_mod
        db_mod._db = None

        yield

        await close_db()
        db_mod._db = None


class TestContentRepository:
    async def test_insert_and_check_exists(self):
        raw = RawContent(
            url="https://example.com/test",
            title="Test Content",
            source_type=SourceType.WEB_SEARCH,
            description="A test",
        )

        # Should not exist yet
        assert await repository.content_exists(raw.url_hash) is False

        # Insert
        content_id = await repository.insert_content(raw)
        assert content_id > 0

        # Should exist now
        assert await repository.content_exists(raw.url_hash) is True

    async def test_fingerprint_dedup(self):
        raw = RawContent(
            url="https://example.com/a",
            title="Same Title",
            description="Same Description",
            source_type=SourceType.WEB_SEARCH,
        )
        await repository.insert_content(raw)

        # Different URL, same content
        assert await repository.fingerprint_exists(raw.content_fingerprint) is True

    async def test_update_status(self):
        raw = RawContent(
            url="https://example.com/status-test",
            title="Status Test",
            source_type=SourceType.WEB_SEARCH,
        )
        content_id = await repository.insert_content(raw)
        await repository.update_content_status(content_id, ContentStatus.APPROVED)

        # Verify via get_all_content
        items, total = await repository.get_all_content(status="approved")
        assert total == 1

    async def test_save_and_get_evaluation(self):
        raw = RawContent(
            url="https://example.com/eval-test",
            title="Eval Test",
            source_type=SourceType.WEB_SEARCH,
        )
        content_id = await repository.insert_content(raw)

        evaluation = ContentEvaluation(
            relevance_score=8,
            category="AI Tools",
            summary="A great tool",
            detailed_description="Detailed info",
            fact_check="Confirmed",
            opinion="Useful",
        )
        await repository.save_evaluation(content_id, evaluation, "test-model")
        await repository.update_content_status(content_id, ContentStatus.APPROVED)

        pending = await repository.get_pending_content(limit=10)
        assert len(pending) == 1
        assert pending[0].evaluation.relevance_score == 8
        assert pending[0].evaluation.category == "AI Tools"

    async def test_content_stats(self):
        raw = RawContent(
            url="https://example.com/stats",
            title="Stats Test",
            source_type=SourceType.WEB_SEARCH,
        )
        await repository.insert_content(raw)

        stats = await repository.get_content_stats()
        assert stats["total_content"] == 1
        assert stats["last_24h"] == 1

    async def test_record_search(self):
        await repository.record_search("youtube", "AI tools", 5)
        # No error = success. Could verify with raw query if needed.

    async def test_save_relation(self):
        raw1 = RawContent(url="https://a.com", title="A", source_type=SourceType.WEB_SEARCH)
        raw2 = RawContent(url="https://b.com", title="B", source_type=SourceType.WEB_SEARCH)
        id1 = await repository.insert_content(raw1)
        id2 = await repository.insert_content(raw2)

        await repository.save_relation(id1, id2, "similar-topic", "Both about AI")
        relations = await repository.get_relations_for_content(id1)
        assert len(relations) == 1
        assert relations[0].relation_type == "similar-topic"
