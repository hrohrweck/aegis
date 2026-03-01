# Aegis

AI content discovery and curation bot for Discord. Aegis continuously discovers AI-related content from YouTube and the web, evaluates relevance and quality using an LLM, and posts curated summaries to categorized Discord channels with detailed discussion threads.

Designed for communities of **AI power users**, **software engineers**, and **DevOps professionals**.

## Features

- **Multi-source content discovery** — YouTube keyword search, YouTube channel monitoring, and Brave Search API for web content
- **LLM-powered evaluation pipeline** — Relevance scoring, automatic categorization, summary generation, fact-checking against external sources, and neutral use-case assessment
- **Content memory** — SQLite-backed deduplication (URL hash + content fingerprint) and cross-reference detection between related content
- **Discord integration** — Posts rich embeds to category-specific channels and creates threads containing detailed descriptions, fact-checks, opinions, and links to related content
- **Configurable categories** — Categories with descriptions and Discord channel mappings are defined in a single YAML file; adding a new category requires no code changes
- **Monitoring dashboard** — FastAPI + htmx web UI with content stats, filtering, and auto-refresh
- **Configurable LLM backend** — Any OpenAI-compatible API (OpenAI, Ollama, vLLM, LM Studio, Azure OpenAI, etc.)

## Architecture

```
Scheduler (APScheduler)
  ├── YouTube Search ─────┐
  ├── YouTube Channels ───┤
  └── Web Search (Brave) ─┘
                           ▼
                  Content Pipeline
                  ├── Deduplication (URL hash + fingerprint)
                  ├── LLM Relevance Scoring & Categorization
                  ├── Summary Generation
                  ├── Fact-Check (web search + LLM cross-reference)
                  ├── Use-Case & Relevance Opinion (neutral tone)
                  └── Relation Detection (against recent DB entries)
                           ▼
                  Discord Publisher
                  ├── Channel embed (summary + tags + score + link)
                  └── Thread (detail, fact-check, opinion, related content)

  SQLite DB (memory, dedup, relations)
  FastAPI Dashboard (monitoring, stats)
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

- `discord.guild_id` — your Discord server ID
- `categories[*].discord_channel_id` — the channel ID for each category
- Optionally adjust search keywords, intervals, and pipeline thresholds

### 4. Run

```bash
python -m src.main
```

The application starts as a long-running daemon. It will:
1. Initialize the SQLite database
2. Start the Discord bot
3. Run an initial content fetch from all sources
4. Begin the scheduled fetch/process/post loop
5. Serve the monitoring dashboard at `http://localhost:8080`

### Docker

```bash
cp .env.example .env   # fill in your keys
docker compose up -d
```

The dashboard is exposed on port `8080`. Data and logs are persisted via volume mounts.

## Configuration

All configuration lives in `config/config.yaml`. Values containing `${VAR_NAME}` are resolved from environment variables at startup, so secrets can be kept in `.env` or your container orchestrator.

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
discord:
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
  search_interval_minutes: 120         # How often to run keyword searches
  channel_check_interval_minutes: 30   # How often to check monitored channels
  max_results_per_search: 10
  search_keywords:
    - "AI tools for developers"
    - "large language models"
    - "AI coding assistant"
    # Add your own keywords
  monitored_channels:
    - channel_id: "UCxxxxxxxxxxxxxxxxxxxxxxxx"
      name: "Two Minute Papers"
    - channel_id: "UCxxxxxxxxxxxxxxxxxxxxxxxx"
      name: "Yannic Kilcher"
```

To get a YouTube API key, create a project in [Google Cloud Console](https://console.cloud.google.com/), enable the YouTube Data API v3, and create an API key.

### Web Search (Brave)

```yaml
web_search:
  api_key: "${BRAVE_SEARCH_API_KEY}"
  search_interval_minutes: 60
  max_results_per_query: 10
  search_queries:
    - "latest AI tools for software engineers"
    - "new LLM models released"
    # Add your own queries
```

Get a Brave Search API key at [brave.com/search/api](https://brave.com/search/api/). The free tier provides 2,000 queries/month.

### Categories

Each category maps to a Discord channel. The LLM uses the `description` field to classify content.

```yaml
categories:
  - name: "LLM Models & Research"
    description: "New language models, model releases, benchmarks, research papers"
    discord_channel_id: 123456789012345678

  - name: "AI Tools & Products"
    description: "New AI-powered tools, products, platforms for developers"
    discord_channel_id: 234567890123456789

  # Add as many categories as you need
```

To add a category: add an entry to this list, create the corresponding Discord channel, and set its ID. No code changes required.

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
```

### Dashboard

```yaml
dashboard:
  enabled: true
  host: "0.0.0.0"
  port: 8080
```

## How It Works

### Content Pipeline

For each piece of discovered content, the pipeline runs these steps in order:

1. **Deduplication** — Check URL hash and content fingerprint against the SQLite database. Skip if already seen.
2. **Relevance scoring** — The LLM scores the content 0-10 for the target audience and assigns a category.
3. **Filtering** — Content below the `relevance_threshold` is recorded but not processed further.
4. **Summary generation** — The LLM produces a short summary (for the Discord embed) and a detailed description (for the thread).
5. **Fact-check** — The Brave Search API runs a verification search. The LLM cross-references the content's claims against those results.
6. **Opinion** — The LLM writes a neutral assessment of the content's use case, relevance, limitations, and how it fits current trends.
7. **Relation detection** — The LLM compares the new content against recent entries in the database and identifies meaningful relationships (follow-up, similar-topic, builds-upon, contradicts, etc.).
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

Two layers prevent duplicate posts:

- **URL hash** — SHA-256 of the full URL. Catches exact re-encounters of the same page.
- **Content fingerprint** — SHA-256 of `lowercase(title) + first 200 chars of lowercase(description)`. Catches the same content reposted at different URLs.

Both checks run against the SQLite database before any LLM processing, keeping API costs low.

## Project Structure

```
aegis/
├── config/
│   └── config.yaml              # Main configuration
├── src/
│   ├── main.py                  # Entry point, app lifecycle
│   ├── config.py                # Pydantic config with env var resolution
│   ├── sources/
│   │   ├── base.py              # Abstract ContentSource interface
│   │   ├── youtube_search.py    # YouTube keyword search
│   │   ├── youtube_channels.py  # YouTube channel monitoring
│   │   └── web_search.py        # Brave Search API
│   ├── pipeline/
│   │   ├── content.py           # Data models
│   │   ├── dedup.py             # Deduplication logic
│   │   ├── categorizer.py       # LLM evaluation & enrichment
│   │   └── processor.py         # Pipeline orchestration
│   ├── llm/
│   │   ├── client.py            # OpenAI-compatible async client
│   │   └── prompts.py           # Prompt templates
│   ├── discord_bot/
│   │   ├── bot.py               # Discord client setup
│   │   └── publisher.py         # Post & thread creation
│   ├── db/
│   │   ├── database.py          # aiosqlite connection (WAL mode)
│   │   ├── models.py            # SQL schema
│   │   └── repository.py        # CRUD operations
│   ├── scheduler/
│   │   └── jobs.py              # APScheduler job definitions
│   └── dashboard/
│       ├── app.py               # FastAPI app factory
│       ├── routes.py            # HTML + JSON API routes
│       └── templates/           # Jinja2 + htmx templates
├── tests/                       # 42 tests
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
