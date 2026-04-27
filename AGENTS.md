# Agent Guidance for Aegis

This file contains context, conventions, and workflows specifically for coding agents working on the Aegis codebase.

## Project Overview

Aegis is a **topic-centric content curation bot for Discord**. It runs independent "topic agents" that discover content from YouTube and the web, evaluate it with an LLM, and post curated summaries to Discord channels.

Key architectural principle: **everything is scoped per-topic**. Topics are independent — they have their own search queries, categories, database records, and Discord channels. There is no cross-topic deduplication.

## Tech Stack

- **Python 3.11+** — strictly typed with `from __future__ import annotations`
- **Pydantic 2.x** — configuration validation
- **aiosqlite** — async SQLite (WAL mode)
- **discord.py 2.x** — Discord bot client
- **OpenAI-compatible LLM APIs** — via `openai` async client
- **APScheduler** — periodic job scheduling
- **FastAPI + Jinja2 + htmx** — monitoring dashboard
- **pytest + pytest-asyncio** — testing
- **ruff** — linting and import sorting

## Development Environment Setup

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest -v

# Run linter (must pass before committing)
ruff check src/ tests/

# Run the application
python -m src.main
```

## Coding Conventions

### Type Hints
- Use `from __future__ import annotations` in every file
- Use `str | None` instead of `Optional[str]`
- Use `list[str]` instead of `List[str]`
- Annotate all function parameters and return types

### Imports
- Group: stdlib → third-party → local
- Ruff will auto-sort; run `ruff check --fix` if imports are out of order

### Async Patterns
- All I/O is async (database, HTTP, Discord)
- Use `async def` for all methods that do I/O
- Database uses a global singleton connection with `asyncio.Lock`

### Structlog
- Use `structlog.get_logger()` for all logging
- Log with kwargs: `logger.info("event.name", key=value)`
- Never use f-strings in log messages

### Error Handling
- Use `logger.exception("event.name", ...)` inside `except` blocks (includes traceback)
- Never silently swallow exceptions
- Return empty lists / None for recoverable errors, don't crash the pipeline

## Project Structure

```
src/
├── config.py              # Pydantic models, env var resolution
├── main.py                # Entry point, bot lifecycle, signal handling
├── agent/
│   └── topic_agent.py     # Per-topic agent (query gen, fetch, process, post)
├── sources/
│   ├── base.py            # ContentSource abstract class
│   ├── youtube_search.py  # YouTube Data API v3 keyword search
│   ├── youtube_channels.py# YouTube channel monitoring
│   └── web_search.py      # Brave Search API
├── pipeline/
│   ├── content.py         # Dataclasses: RawContent, ContentEvaluation, etc.
│   ├── dedup.py           # Topic-scoped URL + fingerprint deduplication
│   ├── categorizer.py     # LLM-based evaluation (topic-aware prompts)
│   └── processor.py       # Orchestrates fetch → dedup → evaluate → relations
├── llm/
│   ├── client.py          # OpenAI-compatible async client with JSON parsing
│   └── prompts.py         # All LLM prompt templates (topic-aware)
├── discord_bot/
│   ├── bot.py             # Minimal discord.Client subclass
│   └── publisher.py       # Embeds + thread creation
├── db/
│   ├── database.py        # aiosqlite connection singleton
│   ├── models.py          # SQL schema (with topic columns)
│   └── repository.py      # All CRUD operations (topic-scoped)
├── scheduler/
│   └── jobs.py            # TopicScheduler with concurrency semaphore
└── dashboard/
    ├── app.py             # FastAPI factory
    ├── routes.py          # HTML + JSON endpoints
    └── templates/         # Jinja2 + htmx
```

## Critical Design Patterns

### Topic Scoping
Every database table has a `topic` column. All repository functions accept `topic: str | None` and filter accordingly. Deduplication is per-topic — the same URL can exist in multiple topics independently.

### Query Generation
Topics do NOT have hardcoded search keywords. The LLM generates them dynamically from the topic description. The `TopicAgent` caches queries and refreshes them based on `query_refresh_interval_hours`.

### Shared vs Per-Topic Resources
- **Shared:** LLM client, database connection, source instances (YouTubeSearchSource, BraveWebSearchSource)
- **Per-topic:** TopicAgent, ContentProcessor, ContentPublisher, query cache, category map
- **Per-unique-discord-config:** CuratorBot instances (when topics override the default Discord server)

### Discord Bot Lifecycle
- One bot per unique Discord configuration (token + guild_id)
- Bots are started concurrently in `run_app()`
- All bots are closed gracefully on shutdown
- The publisher uses `bot.get_channel(channel_id)` — channels can be on different guilds

## Testing Guidelines

### Test Structure
- Tests live in `tests/` with `test_*.py` naming
- Use `pytest-asyncio` mode = auto (configured in pyproject.toml)
- Use the `sample_config` fixture from `conftest.py` for config-dependent tests

### Database Tests
- Use the `setup_test_db` fixture (autouse) which patches `DB_PATH` to a temp file
- The fixture resets the global `_db` connection before each test
- Always pass `topic` parameter to repository functions

### Mocking External APIs
- Tests should NOT call real YouTube, Brave, Discord, or LLM APIs
- Test the "no API key" paths (sources return `[]` when unconfigured)
- Test the query generation prompt strings, not actual LLM calls

## Common Pitfalls

1. **Forgetting topic parameter in repository calls** — Always pass `topic` to dedup, insert, search, etc.
2. **Not passing queries to source.fetch()** — Query-based sources return empty if `queries=None`.
3. **Using Python's `hash()` for persistence** — It's randomized per process. Use `hashlib` for deterministic hashing.
4. **htmx `hx-swap="none"`** — This discards the response. Use `innerHTML` or `outerHTML` with an HTML endpoint.
5. **Single bot assumption** — Topics can have different Discord configs. Check `main.py` bot creation logic.

## Configuration File

`config/config.yaml` is the single source of truth. It uses `${ENV_VAR}` syntax for secrets. Environment variables are resolved at load time by `load_config()`.

Key sections:
- `llm` — API endpoint, model, temperature
- `default_discord` — Default bot token and guild ID
- `topics` — List of topic agents (the core of the application)
- `youtube` / `web_search` — Global API keys and settings
- `pipeline` — Relevance threshold, batch size, etc.
- `scheduler` — Intervals and concurrency limit
- `dashboard` — FastAPI host/port

## CI/CD

GitHub Actions runs on every PR:
- Python 3.11 and 3.12
- `ruff check src/ tests/` (must pass)
- `pytest -v` (must pass)

Workflow file: `.github/workflows/ci.yml`

## Adding a New Feature

1. **Start with config** — If the feature needs configuration, add it to `src/config.py` first
2. **Update schema if needed** — Database changes go in `src/db/models.py`
3. **Implement the feature** — Follow existing patterns in the relevant module
4. **Add tests** — Cover success paths, error paths, and edge cases
5. **Run linter** — `ruff check --fix src/ tests/`
6. **Run tests** — `pytest -v`
7. **Update this file** — If you changed conventions or added new patterns

## Questions?

If something isn't covered here, check:
1. `README.md` for user-facing documentation
2. `config/config.yaml` for configuration examples
3. The test files for usage examples
