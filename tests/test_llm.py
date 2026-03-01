"""Tests for LLM prompt generation."""

from __future__ import annotations

from src.llm.prompts import (
    relevance_prompt,
    summary_prompt,
    fact_check_prompt,
    opinion_prompt,
    relation_prompt,
)


class TestPrompts:
    def test_relevance_prompt_includes_content(self):
        prompt = relevance_prompt(
            title="New LLM Model Released",
            description="A new open-source language model",
            url="https://example.com",
            categories=[
                {"name": "LLM Models", "description": "Language model releases"},
                {"name": "AI Tools", "description": "AI tool releases"},
            ],
        )
        assert "New LLM Model Released" in prompt
        assert "LLM Models" in prompt
        assert "AI Tools" in prompt
        assert "JSON" in prompt

    def test_summary_prompt_includes_content(self):
        prompt = summary_prompt(
            title="Test Title",
            description="Test description of content",
            url="https://example.com",
        )
        assert "Test Title" in prompt
        assert "Discord" in prompt
        assert "JSON" in prompt

    def test_fact_check_prompt_includes_sources(self):
        sources = [
            {"title": "Source 1", "url": "https://s1.com", "snippet": "Fact 1"},
            {"title": "Source 2", "url": "https://s2.com", "snippet": "Fact 2"},
        ]
        prompt = fact_check_prompt(
            title="Claim Title",
            summary="Some claims made",
            search_results=sources,
        )
        assert "Source 1" in prompt
        assert "Source 2" in prompt
        assert "neutral" in prompt.lower() or "balanced" in prompt.lower()

    def test_opinion_prompt_requests_neutrality(self):
        prompt = opinion_prompt(
            title="Some AI Tool",
            summary="A tool that does X",
            category="AI Tools",
        )
        assert "neutral" in prompt.lower()
        assert "JSON" in prompt

    def test_relation_prompt_includes_existing(self):
        existing = [
            {"id": 1, "title": "Related Post", "category": "AI", "summary": "About AI"},
            {"id": 2, "title": "Other Post", "category": "ML", "summary": "About ML"},
        ]
        prompt = relation_prompt(
            new_title="New Content",
            new_summary="Summary of new",
            new_category="AI",
            existing_content=existing,
        )
        assert "Related Post" in prompt
        assert "Other Post" in prompt
        assert "ID:1" in prompt
