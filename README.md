# Aegis

Topic-aware content discovery and curation bot for Discord. Aegis runs independent **topic agents** that continuously discover content from YouTube and the web, evaluate relevance and quality using an LLM, and post curated summaries to categorized Discord channels with detailed discussion threads.

Each agent is fully configurable: you describe what you're looking for, and the LLM generates the search queries. Add as many topics as you need — AI, blockchain, gaming, science, or anything else.

## Features

- **Multi-topic architecture** — Run independent content curation agents for any number of topics, each with their own categories, search configuration, and Discord channels
- **LLM-generated search queries** — Describe your topic once; the LLM automatically generates effective YouTube and web search queries, refreshing them daily
- **Multi-source content discovery** — YouTube keyword search, YouTube channel monitoring, and Brave Search API for web content
- **LLM-powered evaluation pipeline** — Relevance scoring, automatic categorization, summary generation, fact-checking against external sources, and neutral use-case assessment
- **Content memory** — SQLite-backed deduplication (URL hash + content fingerprint) scoped per topic, with cross-reference detection between related content within the same topic
- **Discord integration** — Posts rich embeds to category-specific channels and creates threads containing detailed descriptions, fact-checks, opinions, and links to related content
- **Per-topic Discord overrides** — Each topic posts to channels in the default server, or you can override the server per topic
- **Parallel execution with concurrency limits** — Topics run independently with a configurable maximum number of concurrent agents
- **Monitoring dashboard** — FastAPI + htmx web UI with per-topic content stats, filtering, and auto-refresh
- **Configurable LLM backend** — Any OpenAI-compatible API (OpenAI, Ollama, vLLM, LM Studio, Azure OpenAI, etc.)

## Architecture

```
Topic Agents (independent, parallel with concurrency limit)
  ├── Topic: "Artificial Intelligence"
  │     ├── LLM Query Generation (daily refresh)
  │     ├── YouTube Search ─────┐
  │     ├── YouTube Channels ───┤
  │     └── Web Search (Brave) ─┘
  │                              ▼
  │                     Content Pipeline (topic-scoped)
  │                     ├── Deduplication (URL hash + fingerprint)
  │                     ├── LLM Relevance Scoring & Categorization
  │                     ├── Summary Generation
  ���                     ├── Fact-Check (web search + LLM cross-reference)
  │                     ├── Use-Case & Relevance Opinion (neutral tone)
  │                     └── Relation Detection (against recent DB entries)
  │                              ▼
  │                     Discord Publisher
  │                     ├── Channel embed (summary + tags + score + link)
  │                     └── Thread (detail, fact-check, opinion, related content)
  │
  └── Topic: "Blockchain & Web3"
        └── ... (same pipeline, independent data)

  SQLite DB (topic-scoped tables)
  FastAPI Dashboard (per-topic monitoring, stats)
```

## Prerequisites

- **Python 3.11+**
- **API keys** (see [Configuration](#configuration)):
  - An OpenAI-compatible LLM API key
  - A Discord bot token
  - A YouTube Data API v3 key
  - A Brave Search API key

## Quick Start

### 1. Clone and install

```bash
git clone <repo-url> && cd aegis
python -m venv .venv && source .venv/bin/activate
pip install .
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:

```
LLM_API_KEY=sk-your-key-here
DISCORD_BOT_TOKEN=your-discord-bot-token
YOUTUBE_API_KEY=your-youtube-api-key
BRAVE_SEARCH_API_KEY=your-brave-search-key
```

### 3. Configure the application

Edit `config/config.yaml`. At minimum, set:

- `default_discord.guild_id` — your Discord server ID
- For each topic, set `categories[*].discord_channel_id` — the channel ID for each category
- Optionally adjust topic descriptions, search settings, and pipeline thresholds

### 4. Run

```bash
python -m src.main
```

The application starts as a long-running daemon. It will:
1. Initialize the SQLite database
2. Start the Discord bot
3. Generate initial search queries for each topic via LLM
4. Run an initial content fetch from all sources for all topics
5. Begin the scheduled fetch/process/post loop
6. Serve the monitoring dashboard at `http://localhost:8080`

### Docker

```bash
cp .env.example .env   # fill in your keys
docker compose up -d
```

The dashboard is exposed on port `8080`. Data and logs are persisted via volume mounts.

## Configuration

All configuration lives in `config/config.yaml`. Values containing `${VAR_NAME}` are resolved from environment variables at startup, so secrets can be kept in `.env` or your container orchestrator.

### Topics

Topics are the core of Aegis. Each topic is an independent agent with its own description, categories, search settings, and Discord channels.

```yaml
topics:
  - name: "Artificial Intelligence"
    description: >
      Latest developments in artificial intelligence, large language models,
      AI coding assistants, and machine learning infrastructure.
    search:
      youtube:
        enabled: true
        max_results: 10
        interval_minutes: 120
      web:
        enabled: true
        max_results: 10
        interval_minutes: 60
      query_count_per_source: 5
      query_refresh_interval_hours: 24
    categories:
      - name: "LLM Models & Research"
        description: "New language models, benchmarks, research papers"
        discord_channel_id: 123456789012345678
      - name: "AI Tools & Products"
        description: "New AI-powered tools and platforms"
        discord_channel_id: 234567890123456789

  - name: "Blockchain & Web3"
    description: "Blockchain technology, smart contracts, and DeFi"
    search:
      youtube: { enabled: false }
      web: { enabled: true, interval_minutes: 120 }
    categories:
      - name: "DeFi & Protocols"
        description: "Decentralized finance platforms"
        discord_channel_id: 345678901234567890
```

**How query generation works:**
- The LLM reads your topic `name` and `description`
- It generates `query_count_per_source` effective search queries for each enabled source
- Queries are cached and reused until `query_refresh_interval_hours` passes, then regenerated
- You never need to manually write search keywords

**Per-topic Discord override:**
```yaml
topics:
  - name: "Gaming News"
    description: "Video game releases and industry news"
    discord:
      guild_id: 987654321098765432  # Override default server for this topic
    categories:
      - name: "New Releases"
        discord_channel_id: 555555555555555555
```

### LLM

```yaml
llm:
  base_url: "https://api.openai.com/v1"   # Any OpenAI-compatible endpoint
  api_key: "${LLM_API_KEY}"
  model: "gpt-4o-mini"
  temperature: 0.3
  max_tokens: 4096
  timeout: 60
  max_retries: 3
```

**Using a local model (e.g. Ollama):**

```yaml
llm:
  base_url: "http://localhost:11434/v1"
  api_key: "ollama"
  model: "llama3.1"
```

### Discord

```yaml
default_discord:
  bot_token: "${DISCORD_BOT_TOKEN}"
  guild_id: 123456789012345678       # Right-click server → Copy Server ID
```

The bot requires the following permissions (use Discord's OAuth2 URL generator):
- `Send Messages`
- `Create Public Threads`
- `Send Messages in Threads`
- `Embed Links`
- `Read Message History`

Recommended bot permission integer: `326417525760`

### YouTube

```yaml
youtube:
  api_key: "${YOUTUBE_API_KEY}"
  channel_check_interval_minutes: 30   # How often to check monitored channels
  max_results_per_search: 10
  monitored_channels: []
    # - channel_id: "UCxxxxxx"
    #   name: "Example Channel"
```

Monitored channels are global — they apply to all topics that have YouTube search enabled.

### Web Search (Brave)

```yaml
web_search:
  api_key: "${BRAVE_SEARCH_API_KEY}"
  max_results_per_query: 10
```

Get a Brave Search API key at [brave.com/search/api](https://brave.com/search/api/). The free tier provides 2,000 queries/month.

### Categories

Each category maps to a Discord channel within a topic. The LLM uses the `description` field to classify content into the best matching category.

To add a category: add an entry to the topic's `categories` list, create the corresponding Discord channel, and set its ID. No code changes required.

### Pipeline

```yaml
pipeline:
  relevance_threshold: 6        # 0-10, content scoring below this is not posted
  max_content_age_hours: 72     # Ignore content older than this
  relation_lookback_days: 14    # How far back to look for related content
  max_relations: 5              # Max related items shown per post
  batch_size: 5                 # Items processed concurrently
```

### Scheduler

```yaml
scheduler:
  cleanup_interval_hours: 24    # How often to prune old DB entries
  content_retention_days: 90    # Keep content in DB for this long
  max_concurrent_topics: 3      # Max topics running simultaneously
```

### Dashboard

```yaml
dashboard:
  enabled: true
  host: "0.0.0.0"
  port: 8080
```

## How It Works

### Query Generation

Each topic agent periodically asks the LLM to generate search queries based on the topic description. For example, if your topic is "Artificial Intelligence" described as "latest developments in AI and LLMs for developers", the LLM might generate queries like:
- `latest large language model releases`
- `AI coding assistant updates 2024`
- `new machine learning frameworks`

These queries are cached and refreshed automatically.

### Content Pipeline

For each piece of discovered content, the pipeline runs these steps in order:

1. **Deduplication** — Check URL hash and content fingerprint against the SQLite database, scoped to the topic. Skip if already seen.
2. **Relevance scoring** — The LLM scores the content 0-10 for the topic and assigns a category.
3. **Filtering** — Content below the `relevance_threshold` is recorded but not processed further.
4. **Summary generation** — The LLM produces a short summary (for the Discord embed) and a detailed description (for the thread).
5. **Fact-check** — The Brave Search API runs a verification search. The LLM cross-references the content's claims against those results.
6. **Opinion** — The LLM writes a neutral assessment of the content's use case, relevance, limitations, and how it fits current trends within the topic.
7. **Relation detection** — The LLM compares the new content against recent entries in the topic's database and identifies meaningful relationships (follow-up, similar-topic, builds-upon, contradicts, etc.).
8. **Discord posting** — An embed is posted to the category's channel. A thread is created containing the detailed description, fact-check, opinion, and related content links.

### Discord Posts

**Channel message (embed):**
- Title with link to source
- 2-3 sentence summary
- Tags, relevance score, source author
- Links to related content (if any)

**Thread (auto-created under the message):**
- Detailed description (2-4 paragraphs)
- Fact-check section with source references
- Use case and relevance assessment (neutral tone)
- Related content links with relationship descriptions

### Deduplication Strategy

Two layers prevent duplicate posts within each topic:

- **URL hash** — SHA-256 of the full URL. Catches exact re-encounters of the same page.
- **Content fingerprint** — SHA-256 of `lowercase(title) + first 200 chars of lowercase(description)`. Catches the same content reposted at different URLs.

Both checks run against the topic-scoped SQLite database before any LLM processing, keeping API costs low. The same URL can exist independently across different topics.

## Project Structure

```
aegis/
├── config/
│   └── config.yaml              # Main configuration (topic-centric)
├── src/
│   ├── main.py                  # Entry point, app lifecycle
│   ├── config.py                # Pydantic config with env var resolution
│   ├── agent/
│   │   ├── topic_agent.py       # Per-topic content curation agent
│   │   └── __init__.py
│   ├── sources/
│   │   ├── base.py              # Abstract ContentSource interface
│   │   ├── youtube_search.py    # YouTube keyword search (dynamic queries)
│   │   ├── youtube_channels.py  # YouTube channel monitoring
│   │   └── web_search.py        # Brave Search API (dynamic queries)
│   ├── pipeline/
│   │   ├── content.py           # Data models
│   │   ├── dedup.py             # Topic-scoped deduplication logic
│   │   ├── categorizer.py       # LLM evaluation & enrichment (topic-aware)
│   │   └── processor.py         # Pipeline orchestration (per-topic)
│   ├── llm/
│   │   ├── client.py            # OpenAI-compatible async client
│   │   └── prompts.py           # Topic-aware prompt templates
│   ├── discord_bot/
│   │   ├── bot.py               # Discord client setup
│   │   └── publisher.py         # Post & thread creation (topic-aware)
│   ├── db/
│   │   ├── database.py          # aiosqlite connection (WAL mode)
│   │   ├── models.py            # SQL schema (with topic columns)
│   │   └── repository.py        # CRUD operations (topic-scoped)
│   ├── scheduler/
│   │   └── jobs.py              # TopicScheduler with concurrency limiting
│   └── dashboard/
│       ├── app.py               # FastAPI app factory
│       ├── routes.py            # HTML + JSON API routes (topic filtering)
│       └── templates/           # Jinja2 + htmx templates
├── tests/                       # 52 tests
├── pyproject.toml
├── Dockerfile
├── docker-compose.yaml
├── .env.example
└── .gitignore
```

## Development

### Install dev dependencies

```bash
pip install -e ".[dev]"
```

### Run tests

```bash
pytest -v
```

### Lint

```bash
ruff check src/ tests/
```

## API Key Setup Guide

### Discord Bot Token

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click "New Application", give it a name
3. Go to "Bot" in the sidebar, click "Reset Token", and copy the token
4. Under "Privileged Gateway Intents", enable "Message Content Intent" if you plan to extend the bot with command handling
5. Go to "OAuth2" > "URL Generator", select `bot` scope, then select the permissions listed above
6. Use the generated URL to invite the bot to your server

### YouTube Data API v3

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Go to "APIs & Services" > "Library", search for "YouTube Data API v3", and enable it
4. Go to "APIs & Services" > "Credentials", click "Create Credentials" > "API key"
5. Copy the key

### Brave Search API

1. Go to [brave.com/search/api](https://brave.com/search/api/)
2. Sign up for the free plan (2,000 queries/month)
3. Copy the API key from the dashboard

### Getting Discord IDs

Enable Developer Mode in Discord (User Settings > Advanced > Developer Mode). Then:

- **Server (Guild) ID** — Right-click the server name > "Copy Server ID"
- **Channel ID** — Right-click a channel > "Copy Channel ID"
- **YouTube Channel ID** — Go to the channel page on YouTube. The URL contains the channel ID (`UC...`), or use [commentpicker.com/youtube-channel-id.php](https://commentpicker.com/youtube-channel-id.php)

## License

MIT
