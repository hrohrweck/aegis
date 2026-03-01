"""Database schema definitions."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL UNIQUE,
    content_fingerprint TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    author TEXT DEFAULT '',
    source_type TEXT NOT NULL,
    thumbnail_url TEXT DEFAULT '',
    published_at TEXT,
    raw_metadata TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'discovered',
    discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_content_url_hash ON content(url_hash);
CREATE INDEX IF NOT EXISTS idx_content_fingerprint ON content(content_fingerprint);
CREATE INDEX IF NOT EXISTS idx_content_status ON content(status);
CREATE INDEX IF NOT EXISTS idx_content_discovered_at ON content(discovered_at);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL UNIQUE,
    relevance_score INTEGER NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    detailed_description TEXT NOT NULL DEFAULT '',
    fact_check TEXT NOT NULL DEFAULT '',
    opinion TEXT NOT NULL DEFAULT '',
    target_audiences TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    llm_model TEXT DEFAULT '',
    evaluated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_evaluations_content_id ON evaluations(content_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_category ON evaluations(category);

CREATE TABLE IF NOT EXISTS discord_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    thread_id INTEGER,
    posted_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_discord_posts_content_id ON discord_posts(content_id);

CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id_a INTEGER NOT NULL,
    content_id_b INTEGER NOT NULL,
    relation_type TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (content_id_a) REFERENCES content(id) ON DELETE CASCADE,
    FOREIGN KEY (content_id_b) REFERENCES content(id) ON DELETE CASCADE,
    UNIQUE(content_id_a, content_id_b)
);

CREATE INDEX IF NOT EXISTS idx_relations_a ON relations(content_id_a);
CREATE INDEX IF NOT EXISTS idx_relations_b ON relations(content_id_b);

CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    last_run TEXT NOT NULL DEFAULT (datetime('now')),
    results_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_search_history_source ON search_history(source_type);
"""
