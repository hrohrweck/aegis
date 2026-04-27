"""Tests for Discord publishing utilities."""

from __future__ import annotations

from src.discord_bot.publisher import _category_color, _split_message, _truncate


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
    def test_returns_deterministic_color(self):
        color1 = _category_color("Test Category")
        color2 = _category_color("Test Category")
        assert color1 == color2
        assert isinstance(color1, int)
        assert color1 > 0

    def test_different_categories_get_different_colors(self):
        color1 = _category_color("Category A")
        color2 = _category_color("Category B")
        # They might occasionally collide, but it's unlikely
        assert color1 != color2

    def test_color_not_too_dark(self):
        color = _category_color("Any Category")
        assert color >= 0x333333
