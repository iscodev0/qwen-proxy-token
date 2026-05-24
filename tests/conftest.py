"""Shared test fixtures — database, auth, mock providers, and HTTP client."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from jose import jwt

# ---------------------------------------------------------------------------
# Test settings — modify BEFORE any hubia internal imports resolve
# ---------------------------------------------------------------------------
from hubia import config as _hubia_config

_hubia_config.settings.database_url = "sqlite+aiosqlite:///:memory:"
_hubia_config.settings.secret_key = "test-secret-key-1234567890123456"
_hubia_config.settings.encryption_key = Fernet.generate_key().decode()
_hubia_config.settings.jwt_expire_minutes = 60

# Now safe to import hubia internals
from hubia.api.auth import create_access_token
from hubia.core.provider import (
    AIProvider,
    ChatRequest,
    ChatResponse,
    ChatMessage,
    ModelInfo,
    ProviderCredentials,
    StreamChunk,
)
from hubia.core.registry import ProviderRegistry
from hubia.core.streaming import format_sse_event
from hubia.main import app
from hubia.store.database import close_db, get_connection, init_db
from hubia.store.credentials import store_credential
from hubia.store.users import create_user, generate_api_key
from hubia.api.v1_routes import set_registry

# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------


class MockMetaAIProvider(AIProvider):
    """Mock Meta AI provider returning canned responses."""

    async def chat_completion(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> ChatResponse:
        return ChatResponse(
            id="mock-meta-id",
            model=request.model,
            content="Mock Meta AI response",
            finish_reason="stop",
        )

    async def chat_completion_stream(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(content="Mock ", finish_reason=None)
        yield StreamChunk(content="response", finish_reason="stop")

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="meta-ai/llama-3", provider="meta_ai")]

    async def validate_credentials(
        self,
        credentials: ProviderCredentials,
    ) -> bool:
        return bool(credentials.data.get("datr"))


class MockZaiWebProvider(AIProvider):
    """Mock Z.ai provider returning canned responses."""

    async def chat_completion(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> ChatResponse:
        return ChatResponse(
            id="mock-zai-id",
            model=request.model,
            content="Mock Z.ai response",
            finish_reason="stop",
        )

    async def chat_completion_stream(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(content="Mock ", finish_reason=None)
        yield StreamChunk(content="zai", finish_reason="stop")

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="zai/glm-5", provider="zai_web")]

    async def validate_credentials(
        self,
        credentials: ProviderCredentials,
    ) -> bool:
        return bool(credentials.data.get("token"))


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_db():
    """Create a fresh in-memory SQLite database for each test."""
    import hubia.store.database as _db_mod

    _db_mod._db = None
    await init_db()
    yield
    await close_db()
    _db_mod._db = None


@pytest_asyncio.fixture
async def db_conn(test_db):
    """Return the shared database connection (cached by get_connection)."""
    return await get_connection()


# ---------------------------------------------------------------------------
# User + auth fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def registered_user(db_conn):
    """Create and return a registered test user."""
    user = await create_user(db_conn, "testuser", "password123")
    assert user is not None
    return user


@pytest_asyncio.fixture
async def second_user(db_conn):
    """Create a second registered user for isolation tests."""
    user = await create_user(db_conn, "user_b", "password456")
    assert user is not None
    return user


@pytest_asyncio.fixture
async def user_with_key(db_conn, registered_user):
    """Generate an API key for the registered user. Returns (user, raw_key)."""
    raw_key = await generate_api_key(db_conn, registered_user["id"])
    assert raw_key is not None
    return registered_user, raw_key


@pytest_asyncio.fixture
async def jwt_token(registered_user):
    """Create a valid JWT for the test user."""
    return create_access_token(registered_user["id"])


@pytest_asyncio.fixture
async def auth_headers(user_with_key):
    """Authorization headers with a valid API key."""
    _, raw_key = user_with_key
    return {"Authorization": f"Bearer {raw_key}"}


@pytest_asyncio.fixture
async def jwt_headers(jwt_token):
    """Authorization headers with a valid JWT."""
    return {"Authorization": f"Bearer {jwt_token}"}


# ---------------------------------------------------------------------------
# Credential fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def stored_credentials(db_conn, registered_user):
    """Store test credentials for the registered user."""
    meta_data = {"datr": "test_datr", "ecto_1_sess": "test_ecto_1_sess"}
    await store_credential(db_conn, registered_user["id"], "meta_ai", meta_data)
    zai_data = {"token": "test_zai_token_value"}
    await store_credential(db_conn, registered_user["id"], "zai_web", zai_data)
    return registered_user


# ---------------------------------------------------------------------------
# FastAPI test app + client fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_app(test_db, db_conn):
    """Set up the FastAPI app with mock providers and test DB for API tests."""
    registry = ProviderRegistry()
    registry.register("meta_ai", MockMetaAIProvider(), ["meta-ai/"])
    registry.register("zai_web", MockZaiWebProvider(), ["zai/"])
    set_registry(registry)

    from hubia.store.database import get_db

    app.dependency_overrides[get_db] = lambda: db_conn

    yield app

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_client(test_app):
    """Async HTTP client backed by the test FastAPI app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Helper: create an expired JWT
# ---------------------------------------------------------------------------


def expired_token(user_id: int = 1) -> str:
    """Return a JWT that has already expired."""
    expire = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
    }
    return jwt.encode(
        payload,
        _hubia_config.settings.secret_key,
        algorithm=_hubia_config.settings.jwt_algorithm,
    )


# ---------------------------------------------------------------------------
# Mock response helper for provider tests
# ---------------------------------------------------------------------------


def mock_response(
    status: int = 200,
    body: bytes = b"",
    headers: dict | None = None,
    content_type: str = "application/json",
) -> MagicMock:
    """Build a mock Scrapling ``Response``-like object."""
    mock = MagicMock()
    mock.status = status
    mock.body = body
    mock.headers = headers or {"Content-Type": content_type}
    mock.text = body.decode("utf-8", errors="replace")

    def sync_json() -> dict:
        return json.loads(body)

    mock.json = sync_json
    return mock
