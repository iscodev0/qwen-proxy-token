"""Store layer tests — user CRUD, credential CRUD, encryption, isolation."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from hubia.config import settings
from hubia.store.credentials import (
    delete_credential,
    get_credential,
    list_credentials,
    store_credential,
)
from hubia.store.users import (
    authenticate_user,
    create_user,
    generate_api_key,
    get_user_by_api_key,
    get_user_by_id,
    get_user_by_username,
    list_users,
)
from hubia.utils.crypto import decrypt_value, encrypt_value


# ===========================================================================
# Database initialisation
# ===========================================================================


class TestDatabaseInit:
    """Verify database tables and WAL mode."""

    async def test_tables_created(self, db_conn):
        """Users + credentials tables exist after init_db()."""
        cursor = await db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row["name"] async for row in cursor]
        assert "users" in tables
        assert "credentials" in tables

    async def test_wal_mode(self, db_conn):
        """WAL journal mode is enabled (MEMORY for in-memory DB)."""
        cursor = await db_conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        mode = row[0] if row else ""
        # In-memory SQLite uses MEMORY mode; file-based uses WAL
        assert mode.upper() in ("WAL", "MEMORY")

    async def test_foreign_keys_on(self, db_conn):
        """Foreign key enforcement is enabled."""
        cursor = await db_conn.execute("PRAGMA foreign_keys")
        row = await cursor.fetchone()
        assert row[0] == 1


# ===========================================================================
# User CRUD
# ===========================================================================


class TestUserCRUD:
    """Create, read, authenticate, and manage users."""

    async def test_create_user(self, db_conn):
        """Creating a valid user returns user dict."""
        user = await create_user(db_conn, "alice", "securePass1")
        assert user is not None
        assert user["username"] == "alice"
        assert "password_hash" not in user  # stripped from return
        assert user["id"] is not None

    async def test_get_by_username(self, db_conn):
        """Lookup by username returns the correct user."""
        await create_user(db_conn, "bob", "bobPass123")
        user = await get_user_by_username(db_conn, "bob")
        assert user is not None
        assert user["username"] == "bob"

    async def test_duplicate_username(self, db_conn):
        """Creating a user with an existing username returns None."""
        await create_user(db_conn, "dup", "dupPass123")
        result = await create_user(db_conn, "dup", "otherPass456")
        assert result is None

    async def test_get_user_by_id(self, db_conn):
        """Lookup by primary key."""
        created = await create_user(db_conn, "charlie", "charliePass")
        user = await get_user_by_id(db_conn, created["id"])
        assert user is not None
        assert user["username"] == "charlie"

    async def test_authenticate_success(self, db_conn):
        """Correct credentials return user dict."""
        await create_user(db_conn, "dave", "davePass123")
        user = await authenticate_user(db_conn, "dave", "davePass123")
        assert user is not None
        assert user["username"] == "dave"

    async def test_authenticate_wrong_password(self, db_conn):
        """Wrong password returns None."""
        await create_user(db_conn, "eve", "evePass123")
        user = await authenticate_user(db_conn, "eve", "wrongPass!")
        assert user is None

    async def test_authenticate_nonexistent_user(self, db_conn):
        """Non‑existent user returns None."""
        user = await authenticate_user(db_conn, "nobody", "anyPass")
        assert user is None

    async def test_generate_api_key(self, db_conn):
        """Generating an API key returns the raw key string."""
        created = await create_user(db_conn, "frank", "frankPass")
        raw_key = await generate_api_key(db_conn, created["id"])
        assert raw_key is not None
        assert len(raw_key) == 64  # 32 bytes → 64 hex chars

    async def test_get_user_by_api_key(self, db_conn):
        """Resolve a user via their API key."""
        created = await create_user(db_conn, "grace", "gracePass")
        raw_key = await generate_api_key(db_conn, created["id"])
        user = await get_user_by_api_key(db_conn, raw_key)
        assert user is not None
        assert user["username"] == "grace"

    async def test_list_users(self, db_conn):
        """list_users returns all registered users."""
        await create_user(db_conn, "u1", "pass1")
        await create_user(db_conn, "u2", "pass2")
        users = await list_users(db_conn)
        assert len(users) >= 2


# ===========================================================================
# Credential CRUD
# ===========================================================================


class TestCredentialCRUD:
    """Encrypted credential storage operations."""

    async def test_store_and_get(self, db_conn, registered_user):
        """Storing a credential and reading it back returns decrypted data."""
        data = {"datr": "abc123", "ecto_1_sess": "xyz789"}
        stored = await store_credential(db_conn, registered_user["id"], "meta_ai", data)
        assert stored is not None
        assert stored["provider"] == "meta_ai"
        assert stored["data"] == data  # decrypted on read

    async def test_encryption_roundtrip(self, db_conn, registered_user):
        """Encrypted blob differs from plaintext; decryption recovers it."""
        data = {"secret": "sensitive_value"}
        await store_credential(db_conn, registered_user["id"], "zai_web", data)

        # Read raw encrypted value from DB
        cursor = await db_conn.execute(
            "SELECT encrypted_cookies FROM credentials WHERE user_id=? AND provider=?",
            (registered_user["id"], "zai_web"),
        )
        row = await cursor.fetchone()
        encrypted = row["encrypted_cookies"] if row else ""

        # Encrypted value should NOT contain the plaintext
        assert "sensitive_value" not in encrypted

        # Decrypt manually and verify
        user_id = registered_user["id"]
        plaintext = decrypt_value(encrypted, settings.encryption_key, user_id)
        assert json.loads(plaintext) == data

    async def test_upsert_updates_existing(self, db_conn, registered_user):
        """Storing again for the same user+provider updates the row."""
        data1 = {"token": "first"}
        data2 = {"token": "updated"}
        await store_credential(db_conn, registered_user["id"], "zai_web", data1)
        await store_credential(db_conn, registered_user["id"], "zai_web", data2)

        cred = await get_credential(db_conn, registered_user["id"], "zai_web")
        assert cred is not None
        assert cred["data"]["token"] == "updated"

    async def test_delete(self, db_conn, registered_user):
        """Deleting a credential removes the row."""
        await store_credential(db_conn, registered_user["id"], "meta_ai", {"k": "v"})
        deleted = await delete_credential(db_conn, registered_user["id"], "meta_ai")
        assert deleted is True

        # Verify it's gone
        cred = await get_credential(db_conn, registered_user["id"], "meta_ai")
        assert cred is None

    async def test_list_credentials(self, db_conn, registered_user):
        """Listing returns metadata for all of a user's credentials."""
        await store_credential(db_conn, registered_user["id"], "meta_ai", {"a": "1"})
        await store_credential(db_conn, registered_user["id"], "zai_web", {"b": "2"})
        creds = await list_credentials(db_conn, registered_user["id"])
        assert len(creds) == 2
        providers = {c["provider"] for c in creds}
        assert providers == {"meta_ai", "zai_web"}


# ===========================================================================
# User isolation
# ===========================================================================


class TestUserIsolation:
    """Users must not be able to see each other's credentials."""

    async def test_isolation(self, db_conn, registered_user, second_user):
        """User A's credentials are invisible to User B."""
        await store_credential(
            db_conn, registered_user["id"], "meta_ai", {"datr": "alice_data"}
        )
        await store_credential(
            db_conn, second_user["id"], "meta_ai", {"datr": "bob_data"}
        )

        # User A sees their own
        alice_cred = await get_credential(
            db_conn, registered_user["id"], "meta_ai"
        )
        assert alice_cred["data"]["datr"] == "alice_data"

        # User B should not see User A's credential — B has their own
        bob_cred = await get_credential(db_conn, second_user["id"], "meta_ai")
        assert bob_cred["data"]["datr"] == "bob_data"

        # User A listing does not include User B's credentials
        alice_list = await list_credentials(db_conn, registered_user["id"])
        assert len(alice_list) == 1
        assert alice_list[0]["provider"] == "meta_ai"
