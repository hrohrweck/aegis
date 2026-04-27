"""Tests for database operations."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.db import repository
from src.db.database import close_db
from src.pipeline.content import ContentEvaluation, ContentStatus, RawContent, SourceType

TEST_TOPIC = "AI"
TEST_TOPIC_2 = "Blockchain"


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
        assert await repository.content_exists(raw.url_hash, TEST_TOPIC) is False

        # Insert
        content_id = await repository.insert_content(raw, TEST_TOPIC)
        assert content_id > 0

        # Should exist now for this topic
        assert await repository.content_exists(raw.url_hash, TEST_TOPIC) is True

        # Should NOT exist for a different topic (isolation)
        assert await repository.content_exists(raw.url_hash, TEST_TOPIC_2) is False

    async def test_fingerprint_dedup_per_topic(self):
        raw = RawContent(
            url="https://example.com/a",
            title="Same Title",
            description="Same Description",
            source_type=SourceType.WEB_SEARCH,
        )
        await repository.insert_content(raw, TEST_TOPIC)

        # Same fingerprint exists for this topic
        assert await repository.fingerprint_exists(raw.content_fingerprint, TEST_TOPIC) is True

        # But not for a different topic
        assert await repository.fingerprint_exists(raw.content_fingerprint, TEST_TOPIC_2) is False

    async def test_update_status(self):
        raw = RawContent(
            url="https://example.com/status-test",
            title="Status Test",
            source_type=SourceType.WEB_SEARCH,
        )
        content_id = await repository.insert_content(raw, TEST_TOPIC)
        await repository.update_content_status(content_id, ContentStatus.APPROVED)

        # Verify via get_all_content
        items, total = await repository.get_all_content(status="approved", topic=TEST_TOPIC)
        assert total == 1

    async def test_save_and_get_evaluation(self):
        raw = RawContent(
            url="https://example.com/eval-test",
            title="Eval Test",
            source_type=SourceType.WEB_SEARCH,
        )
        content_id = await repository.insert_content(raw, TEST_TOPIC)

        evaluation = ContentEvaluation(
            relevance_score=8,
            category="AI Tools",
            summary="A great tool",
            detailed_description="Detailed info",
            fact_check="Confirmed",
            opinion="Useful",
        )
        await repository.save_evaluation(content_id, evaluation, "test-model", TEST_TOPIC)
        await repository.update_content_status(content_id, ContentStatus.APPROVED)

        pending = await repository.get_pending_content(limit=10, topic=TEST_TOPIC)
        assert len(pending) == 1
        assert pending[0].evaluation.relevance_score == 8
        assert pending[0].evaluation.category == "AI Tools"
        assert pending[0].topic == TEST_TOPIC

    async def test_content_stats_per_topic(self):
        raw = RawContent(
            url="https://example.com/stats",
            title="Stats Test",
            source_type=SourceType.WEB_SEARCH,
        )
        await repository.insert_content(raw, TEST_TOPIC)
        await repository.insert_content(raw, TEST_TOPIC_2)

        stats_ai = await repository.get_content_stats(topic=TEST_TOPIC)
        assert stats_ai["total_content"] == 1
        assert stats_ai["last_24h"] == 1

        stats_all = await repository.get_content_stats()
        assert stats_all["total_content"] == 2

    async def test_record_search(self):
        await repository.record_search("youtube", "AI tools", 5, TEST_TOPIC)
        # No error = success

    async def test_save_relation_per_topic(self):
        raw1 = RawContent(url="https://a.com", title="A", source_type=SourceType.WEB_SEARCH)
        raw2 = RawContent(url="https://b.com", title="B", source_type=SourceType.WEB_SEARCH)
        id1 = await repository.insert_content(raw1, TEST_TOPIC)
        id2 = await repository.insert_content(raw2, TEST_TOPIC)

        await repository.save_relation(id1, id2, "similar-topic", "Both about AI", TEST_TOPIC)
        relations = await repository.get_relations_for_content(id1, TEST_TOPIC)
        assert len(relations) == 1
        assert relations[0].relation_type == "similar-topic"

    async def test_cleanup_old_content_per_topic(self):
        raw = RawContent(url="https://old.com", title="Old", source_type=SourceType.WEB_SEARCH)
        await repository.insert_content(raw, TEST_TOPIC)
        await repository.insert_content(raw, TEST_TOPIC_2)

        # Cleanup only AI topic
        deleted = await repository.cleanup_old_content(retention_days=0, topic=TEST_TOPIC)
        assert deleted == 1

        stats = await repository.get_content_stats(topic=TEST_TOPIC_2)
        assert stats["total_content"] == 1
