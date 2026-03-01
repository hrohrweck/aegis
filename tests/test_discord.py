"""Tests for Discord publishing utilities."""

from __future__ import annotations

from src.discord_bot.publisher import _truncate, _split_message, _category_color


class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("hello", 10) == "hello"

    def test_long_text_truncated(self):
        result = _truncate("a" * 300, 256)
        assert len(result) == 256
        assert result.endswith("...")

    def test_exact_length_unchanged(self):
        text = "a" * 100
        assert _truncate(text, 100) == text


class TestSplitMessage:
    def test_short_message_not_split(self):
        assert _split_message("hello") == ["hello"]

    def test_long_message_split(self):
        text = "word " * 500  # ~2500 chars
        chunks = _split_message(text, max_len=2000)
        assert len(chunks) > 1
        assert all(len(c) <= 2000 for c in chunks)

    def test_split_preserves_content(self):
        text = "line one\nline two\nline three"
        chunks = _split_message(text, max_len=20)
        combined = " ".join(c.strip() for c in chunks)
        # All words should be present
        for word in ["line", "one", "two", "three"]:
            assert word in combined


class TestCategoryColor:
    def test_known_category(self):
        assert _category_color("LLM Models & Research") == 0x7289DA

    def test_unknown_category_returns_default(self):
        assert _category_color("Unknown Category") == 0x99AAB5
