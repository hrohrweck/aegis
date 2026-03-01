"""SQLite database connection management."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import structlog

from src.db.models import SCHEMA_SQL

logger = structlog.get_logger()

_db: aiosqlite.Connection | None = None
_lock = asyncio.Lock()

DB_PATH = Path("data/aegis.db")


async def get_db() -> aiosqlite.Connection:
    """Get or create the database connection."""
    global _db
    async with _lock:
        if _db is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _db = await aiosqlite.connect(str(DB_PATH))
            _db.row_factory = aiosqlite.Row
            await _db.execute("PRAGMA journal_mode=WAL")
            await _db.execute("PRAGMA foreign_keys=ON")
            await _db.executescript(SCHEMA_SQL)
            await _db.commit()
            logger.info("database.connected", path=str(DB_PATH))
        return _db


async def close_db() -> None:
    """Close the database connection."""
    global _db
    async with _lock:
        if _db is not None:
            await _db.close()
            _db = None
            logger.info("database.closed")
