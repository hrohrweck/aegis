"""OpenAI-compatible LLM client with structured output support."""

from __future__ import annotations

import json
from typing import Any

import structlog
from openai import AsyncOpenAI

from src.config import LLMConfig

logger = structlog.get_logger()


class LLMClient:
    """Async LLM client using OpenAI-compatible API."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.client = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        self.model = config.model

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Send a prompt and parse the response as JSON.

        Uses response_format=json_object when available. Falls back to
        parsing JSON from the text response if the API doesn't support it.
        """
        temp = temperature if temperature is not None else self.config.temperature

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temp,
                max_tokens=self.config.max_tokens,
                response_format={"type": "json_object"},
            )
        except Exception:
            # Fallback: some providers don't support response_format
            logger.debug("llm.json_mode_fallback", model=self.model)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temp,
                max_tokens=self.config.max_tokens,
            )

        text = response.choices[0].message.content or "{}"
        text = text.strip()

        # Handle markdown-wrapped JSON
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("llm.json_parse_failed", response_preview=text[:200])
            return {}

    async def complete_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> str:
        """Send a prompt and return raw text response."""
        temp = temperature if temperature is not None else self.config.temperature

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temp,
            max_tokens=self.config.max_tokens,
        )

        return response.choices[0].message.content or ""
