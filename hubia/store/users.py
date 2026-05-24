"""User CRUD operations — create, authenticate, API key management."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator

import aiosqlite
from passlib.hash import bcrypt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_FIELDS = "id, username, password_hash, api_key, created_at"


def _row_to_dict(row: aiosqlite.Row) -> dict | None:
    if row is None:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_user(
    db: aiosqlite.Connection,
    username: str,
    password: str,
) -> dict | None:
    """Register a new user.

    Args:
        db: Database connection.
        username: Unique username.
        password: Plain-text password (will be bcrypt-hashed).

    Returns:
        User dict without password_hash, or **None** if the username
        already exists.

    Raises:
        ValueError: If username or password is empty.
    """
    if not username or not password:
        raise ValueError("Username and password are required.")

    password_hash = bcrypt.hash(password)

    try:
        cursor = await db.execute(
            f"INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        return None  # duplicate username

    return {
        "id": cursor.lastrowid,
        "username": username,
        "api_key": None,
    }


# ---------------------------------------------------------------------------
# Authenticate
# ---------------------------------------------------------------------------

async def get_user_by_username(
    db: aiosqlite.Connection,
    username: str,
) -> dict | None:
    """Look up a user by username."""
    cursor = await db.execute(
        f"SELECT {_USER_FIELDS} FROM users WHERE username = ?",
        (username,),
    )
    return _row_to_dict(await cursor.fetchone())


async def get_user_by_id(
    db: aiosqlite.Connection,
    user_id: int,
) -> dict | None:
    """Look up a user by primary key."""
    cursor = await db.execute(
        f"SELECT {_USER_FIELDS} FROM users WHERE id = ?",
        (user_id,),
    )
    return _row_to_dict(await cursor.fetchone())


async def authenticate_user(
    db: aiosqlite.Connection,
    username: str,
    password: str,
) -> dict | None:
    """Verify credentials and return the user dict (without password_hash).

    Returns **None** if the user does not exist or the password is wrong.
    """
    user = await get_user_by_username(db, username)
    if user is None:
        return None

    stored_hash: str = user["password_hash"]
    if not bcrypt.verify(password, stored_hash):
        return None

    # Strip hash before returning
    user.pop("password_hash", None)
    return user


# ---------------------------------------------------------------------------
# API Key
# ---------------------------------------------------------------------------

async def generate_api_key(
    db: aiosqlite.Connection,
    user_id: int,
) -> str | None:
    """Generate a new API key for a user.

    The key is a 32-char hex string.  The raw key is returned **only once**
    to the caller; the stored value is bcrypt-hashed.

    Returns **None** if the user does not exist.
    """
    # Verify user exists
    existing = await get_user_by_id(db, user_id)
    if existing is None:
        return None

    raw_key = secrets.token_hex(32)  # 64 hex chars
    hashed_key = bcrypt.hash(raw_key)

    await db.execute(
        "UPDATE users SET api_key = ? WHERE id = ?",
        (hashed_key, user_id),
    )
    await db.commit()
    return raw_key


async def get_user_by_api_key(
    db: aiosqlite.Connection,
    api_key: str,
) -> dict | None:
    """Resolve a user by their API key.

    Iterates rows and verifies with bcrypt to support constant-time
    comparison on the application side.
    """
    cursor = await db.execute(
        "SELECT id, username, api_key, created_at FROM users WHERE api_key IS NOT NULL",
    )
    rows = await cursor.fetchall()
    for row in rows:
        d = dict(row)
        stored_key: str = d["api_key"]
        if bcrypt.verify(api_key, stored_key):
            return d

    return None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

async def list_users(db: aiosqlite.Connection) -> list[dict]:
    """Return all users (without password_hash)."""
    cursor = await db.execute("SELECT id, username, api_key, created_at FROM users")
    return [dict(row) for row in await cursor.fetchall()]
