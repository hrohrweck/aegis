"""Tests for pipeline content models and deduplication."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.pipeline.content import (
    ContentEvaluation,
    ContentStatus,
    ProcessedContent,
    RawContent,
    SourceType,
)


class TestRawContent:
    def test_url_hash_deterministic(self):
        rc = RawContent(
            url="https://example.com/test",
            title="Test",
            source_type=SourceType.WEB_SEARCH,
        )
        assert rc.url_hash == rc.url_hash  # Same object, same hash
        rc2 = RawContent(
            url="https://example.com/test",
            title="Different Title",
            source_type=SourceType.YOUTUBE_SEARCH,
        )
        assert rc.url_hash == rc2.url_hash  # Same URL = same hash

    def test_url_hash_different_for_different_urls(self):
        rc1 = RawContent(url="https://a.com", title="A", source_type=SourceType.WEB_SEARCH)
        rc2 = RawContent(url="https://b.com", title="B", source_type=SourceType.WEB_SEARCH)
        assert rc1.url_hash != rc2.url_hash

    def test_content_fingerprint(self):
        rc1 = RawContent(
            url="https://a.com",
            title="Test Title",
            description="Some desc",
            source_type=SourceType.WEB_SEARCH,
        )
        rc2 = RawContent(
            url="https://b.com",
            title="test title",  # Case-insensitive
            description="Some desc",
            source_type=SourceType.YOUTUBE_SEARCH,
        )
        assert rc1.content_fingerprint == rc2.content_fingerprint

    def test_fingerprint_differs_on_different_content(self):
        rc1 = RawContent(url="https://a.com", title="Foo", source_type=SourceType.WEB_SEARCH)
        rc2 = RawContent(url="https://a.com", title="Bar", source_type=SourceType.WEB_SEARCH)
        assert rc1.content_fingerprint != rc2.content_fingerprint


class TestProcessedContent:
    def test_should_post_when_approved(self):
        pc = ProcessedContent(
            id=1,
            status=ContentStatus.APPROVED,
            evaluation=ContentEvaluation(relevance_score=8, category="AI Tools"),
        )
        assert pc.should_post is True

    def test_should_not_post_when_rejected(self):
        pc = ProcessedContent(
            id=1,
            status=ContentStatus.REJECTED,
            evaluation=ContentEvaluation(relevance_score=3, category="AI Tools"),
        )
        assert pc.should_post is False

    def test_should_not_post_without_category(self):
        pc = ProcessedContent(
            id=1,
            status=ContentStatus.APPROVED,
            evaluation=ContentEvaluation(relevance_score=8, category=""),
        )
        assert pc.should_post is False

    def test_should_not_post_with_zero_score(self):
        pc = ProcessedContent(
            id=1,
            status=ContentStatus.APPROVED,
            evaluation=ContentEvaluation(relevance_score=0, category="AI Tools"),
        )
        assert pc.should_post is False
