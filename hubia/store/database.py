"""Async SQLite database setup and connection management."""

from __future__ import annotations

from collections.abc import AsyncIterator

import aiosqlite

from hubia.config import settings

# Module-level connection for simple access patterns
_db: aiosqlite.Connection | None = None


async def get_connection() -> aiosqlite.Connection:
    """Return the shared database connection, creating it if necessary."""
    global _db  # noqa: PLW0603
    if _db is None:
        path = settings.database_url.replace("sqlite+aiosqlite:///", "")
        _db = await aiosqlite.connect(path)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL;")
        await _db.execute("PRAGMA foreign_keys=ON;")
    return _db


async def init_db() -> None:
    """Create tables if they do not exist.

    Schema:
        - **users**: id, username (unique), password_hash, api_key (unique),
          created_at
        - **credentials**: id, user_id (FK), provider (meta_ai | zai_web),
          encrypted_cookies, created_at, updated_at, expires_at, unique(user_id,
          provider)
    """
    db = await get_connection()

    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    UNIQUE NOT NULL,
            password_hash   TEXT    NOT NULL,
            api_key         TEXT    UNIQUE,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS credentials (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL REFERENCES users(id),
            provider          TEXT    NOT NULL,
            encrypted_cookies TEXT    NOT NULL,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at        TIMESTAMP,
            UNIQUE(user_id, provider)
        );
    """)
    await db.commit()


async def close_db() -> None:
    """Close the shared database connection if open."""
    global _db  # noqa: PLW0603
    if _db is not None:
        await _db.close()
        _db = None


async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """FastAPI-compatible dependency yielding the database connection.

    Usage::

        async def my_endpoint(db: aiosqlite.Connection = Depends(get_db)):
            ...
    """
    db = await get_connection()
    yield db
