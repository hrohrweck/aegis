"""LLM prompt templates for all content processing tasks."""

from __future__ import annotations


def system_prompt(topic_name: str, topic_description: str) -> str:
    """Generate a topic-aware system prompt for the LLM."""
    return (
        f"You are a content analyst specializing in the topic: {topic_name}. "
        f"{topic_description} "
        "You evaluate content for relevance and quality, targeting the audience "
        "interested in this topic. You are always neutral, factual, and balanced. "
        "Avoid hype, superlatives, and promotional language. Present information "
        "objectively and acknowledge limitations or counter-arguments when relevant."
    )


def relevance_prompt(
    title: str,
    description: str,
    url: str,
    categories: list[dict],
    topic_name: str,
    topic_description: str,
) -> str:
    categories_text = "\n".join(
        f"- {c['name']}: {c['description']}" for c in categories
    )
    return f"""Evaluate the following content for relevance to the topic: {topic_name}.

Topic description: {topic_description}

**Content:**
- Title: {title}
- Description: {description}
- URL: {url}

**Available categories:**
{categories_text}

Respond with ONLY a JSON object (no markdown, no extra text):
{{
  "relevance_score": <integer 0-10, where 10 is extremely relevant>,
  "category": "<best matching category name from the list above>",
  "target_audiences": ["<list of relevant audience segments>"],
  "tags": ["<3-5 short topic tags>"],
  "reasoning": "<brief explanation of your relevance assessment>"
}}"""


def summary_prompt(title: str, description: str, url: str) -> str:
    return f"""Write a concise summary and a detailed description of the following content.

**Content:**
- Title: {title}
- Description: {description}
- URL: {url}

The summary should be 2-3 sentences suitable for a Discord channel post.
It should convey the key points clearly and neutrally.

The detailed description should be 2-4 paragraphs expanding on the content,
covering what it is, why it matters, and key technical details.

Respond with ONLY a JSON object (no markdown, no extra text):
{{
  "summary": "<2-3 sentence summary>",
  "detailed_description": "<2-4 paragraph detailed description>"
}}"""


def fact_check_prompt(
    title: str,
    summary: str,
    search_results: list[dict],
) -> str:
    sources_text = "\n".join(
        f"- [{s.get('title', 'Source')}]({s.get('url', '')}): {s.get('snippet', '')}"
        for s in search_results
    )
    return f"""Perform a fact-check of the following content using the provided reference sources.

**Content to verify:**
- Title: {title}
- Summary: {summary}

**Reference sources:**
{sources_text}

Assess the accuracy of the key claims. Note any confirmed facts, unverified claims,
or contradictions found in the reference sources. Be balanced and neutral.

Respond with ONLY a JSON object (no markdown, no extra text):
{{
  "fact_check": "<fact-check assessment, noting confirmed and unverified claims>",
  "confidence": "<high, medium, or low confidence in the content's accuracy>"
}}"""


def opinion_prompt(
    title: str, summary: str, category: str, topic_name: str, topic_description: str
) -> str:
    return f"""Provide a neutral, balanced assessment of the use case and relevance of the
following content within the context of {topic_name}.

Topic: {topic_name}
Topic description: {topic_description}

**Content:**
- Title: {title}
- Summary: {summary}
- Category: {category}

Write a balanced opinion covering:
1. Who would benefit most from this content
2. Practical applications or implications
3. Any limitations or considerations
4. How it fits into current trends within this topic area

Maintain a strictly neutral tone. Present multiple perspectives where relevant.
Avoid hype or dismissiveness.

Respond with ONLY a JSON object (no markdown, no extra text):
{{
  "opinion": "<2-3 paragraph neutral assessment>"
}}"""


def relation_prompt(
    new_title: str,
    new_summary: str,
    new_category: str,
    existing_content: list[dict],
) -> str:
    existing_text = "\n".join(
        f"- [ID:{c.get('id')}] \"{c.get('title')}\" (Category: {c.get('category', 'N/A')}) "
        f"Summary: {c.get('summary', 'N/A')[:150]}"
        for c in existing_content
    )
    return f"""Identify any meaningful relationships between the new content and existing content.

**New content:**
- Title: {new_title}
- Summary: {new_summary}
- Category: {new_category}

**Existing recent content:**
{existing_text}

Look for relationships like: follow-up, builds-upon, similar-topic, contradicts,
alternative, same-project, prerequisite.

Only include genuinely meaningful relationships, not superficial topic overlap.
If there are no meaningful relations, return an empty list.

Respond with ONLY a JSON object (no markdown, no extra text):
{{
  "relations": [
    {{
      "related_content_id": <integer ID from existing content>,
      "relation_type": "<type of relationship>",
      "description": "<brief description of the relationship>"
    }}
  ]
}}"""


def query_generation_prompt(
    topic_name: str,
    topic_description: str,
    source_type: str,
    count: int,
    existing_queries: list[str] | None = None,
) -> str:
    """Generate search queries for a given topic and source type."""
    existing = ""
    if existing_queries:
        existing = (
            "\nPreviously used queries (try to diversify and avoid exact duplicates):\n"
            + "\n".join(f"- {q}" for q in existing_queries)
        )

    source_guidance = {
        "youtube": (
            "For YouTube, queries should be concise (2-5 words) and optimized for video search. "
            "Focus on content that is likely to have recent video coverage."
        ),
        "web": (
            "For web search, queries can be more descriptive (5-15 words). "
            "Use natural language questions or specific topic phrases that "
            "news sites and blogs would cover."
        ),
    }

    guidance = source_guidance.get(source_type, "")

    return f"""You are a search query strategist. Given a topic, generate {count} effective
search queries for {source_type.upper()} search to discover the most relevant and recent content.

**Topic:** {topic_name}
**Topic description:** {topic_description}
{guidance}
{existing}

Requirements:
- Each query should target a different angle or sub-topic within the main topic
- Prioritize queries that would find recent or trending content
- Avoid overly broad queries that would return irrelevant results
- Queries should be in English

Respond with ONLY a JSON object (no markdown, no extra text):
{{
  "queries": ["<query 1>", "<query 2>", "..."]
}}"""
