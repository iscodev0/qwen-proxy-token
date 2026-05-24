"""Credential CRUD with Fernet-encrypted cookie storage."""

from __future__ import annotations

import json

import aiosqlite

from hubia.config import settings
from hubia.utils.crypto import decrypt_value, encrypt_value

_CRED_FIELDS = "id, user_id, provider, encrypted_cookies, created_at, updated_at, expires_at"


async def store_credential(
    db: aiosqlite.Connection,
    user_id: int,
    provider: str,
    data: dict,
    expires_at: str | None = None,
) -> dict | None:
    """Store (or update) a credential for a given user + provider.

    The *data* dict is serialised to JSON and encrypted with a per-user
    derived Fernet key before storage.  Uses ``INSERT … ON CONFLICT … DO
    UPDATE`` to handle upserts.

    Args:
        db: Database connection.
        user_id: Owning user.
        provider: Provider name (e.g. ``"meta_ai"``, ``"zai_web"``).
        data: Dict to encrypt (typically cookies / tokens).
        expires_at: Optional ISO-8601 expiry timestamp.

    Returns:
        The row dict of the stored credential, or **None** if the user
        does not exist.
    """
    plaintext = json.dumps(data, separators=(",", ":"))
    encrypted = encrypt_value(plaintext, settings.encryption_key, user_id)

    await db.execute(
        """
        INSERT INTO credentials (user_id, provider, encrypted_cookies, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, provider) DO UPDATE SET
            encrypted_cookies = excluded.encrypted_cookies,
            updated_at = CURRENT_TIMESTAMP,
            expires_at = COALESCE(excluded.expires_at, credentials.expires_at)
        """,
        (user_id, provider, encrypted, expires_at),
    )
    await db.commit()

    return await get_credential(db, user_id, provider)


async def get_credential(
    db: aiosqlite.Connection,
    user_id: int,
    provider: str,
) -> dict | None:
    """Read and decrypt a credential.

    Returns the full row dict with ``"data"`` key containing the
    decrypted dict, or **None** if no credential exists.
    """
    cursor = await db.execute(
        f"SELECT {_CRED_FIELDS} FROM credentials WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )
    row = await cursor.fetchone()
    if row is None:
        return None

    cred = dict(row)
    try:
        plaintext = decrypt_value(cred["encrypted_cookies"], settings.encryption_key, user_id)
        cred["data"] = json.loads(plaintext)
    except Exception:
        cred["data"] = None

    return cred


async def delete_credential(
    db: aiosqlite.Connection,
    user_id: int,
    provider: str,
) -> bool:
    """Delete a credential.

    Returns ``True`` if a row was deleted, ``False`` otherwise.
    """
    cursor = await db.execute(
        "DELETE FROM credentials WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )
    await db.commit()
    return cursor.rowcount > 0


async def list_credentials(
    db: aiosqlite.Connection,
    user_id: int,
) -> list[dict]:
    """List all credential meta-data (without decrypted data) for a user."""
    cursor = await db.execute(
        "SELECT id, user_id, provider, created_at, updated_at, expires_at "
        "FROM credentials WHERE user_id = ?",
        (user_id,),
    )
    return [dict(row) for row in await cursor.fetchall()]
