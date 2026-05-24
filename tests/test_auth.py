"""Auth API tests — register, login, JWT, API key, /auth/me."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from hubia.config import settings as _s


# ===========================================================================
# Registration
# ===========================================================================


class TestRegister:
    """POST /auth/register behaviour."""

    async def test_register_success(self, test_client, test_db):
        """Valid registration returns 201 with user info."""
        resp = await test_client.post(
            "/auth/register",
            json={"username": "newuser", "password": "securePass1"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "newuser"
        assert "id" in body
        assert "password" not in body  # never leak hash

    async def test_register_duplicate(self, test_client, test_db, registered_user):
        """Duplicate username returns 409."""
        resp = await test_client.post(
            "/auth/register",
            json={"username": "testuser", "password": "anotherPass1"},
        )
        assert resp.status_code == 409
        assert "detail" in resp.json()

    async def test_register_short_password(self, test_client, test_db):
        """Password shorter than 8 chars returns 422."""
        resp = await test_client.post(
            "/auth/register",
            json={"username": "shortpwd", "password": "abc"},
        )
        assert resp.status_code == 422


# ===========================================================================
# Login
# ===========================================================================


class TestLogin:
    """POST /auth/login behaviour."""

    async def test_login_success(self, test_client, test_db, registered_user):
        """Correct credentials return a JWT."""
        resp = await test_client.post(
            "/auth/login",
            json={"username": "testuser", "password": "password123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password(self, test_client, test_db, registered_user):
        """Wrong password returns 401."""
        resp = await test_client.post(
            "/auth/login",
            json={"username": "testuser", "password": "wrongPassword!"},
        )
        assert resp.status_code == 401

    async def test_login_nonexistent(self, test_client, test_db):
        """Non‑existent user returns 401."""
        resp = await test_client.post(
            "/auth/login",
            json={"username": "nobody", "password": "anyPassword1"},
        )
        assert resp.status_code == 401


# ===========================================================================
# API Key
# ===========================================================================


class TestApiKey:
    """POST /auth/keys — API key generation."""

    async def test_generate_key(self, test_client, auth_headers):
        """Authenticated user can generate an API key."""
        resp = await test_client.post("/auth/keys", headers=auth_headers)
        assert resp.status_code == 201
        body = resp.json()
        assert "api_key" in body
        assert len(body["api_key"]) == 64  # 32 bytes → 64 hex chars

    async def test_generate_key_unauthenticated(self, test_client):
        """Without auth, key generation returns 401."""
        resp = await test_client.post("/auth/keys")
        assert resp.status_code == 401


# ===========================================================================
# /auth/me
# ===========================================================================


class TestMe:
    """GET /auth/me — current user profile."""

    async def test_me_authenticated(self, test_client, auth_headers):
        """Authenticated request returns user info."""
        resp = await test_client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "testuser"
        assert "id" in body

    async def test_me_jwt(self, test_client, jwt_headers):
        """Valid JWT also works for /auth/me."""
        resp = await test_client.get("/auth/me", headers=jwt_headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == "testuser"

    async def test_me_unauthenticated(self, test_client):
        """No auth header returns 401."""
        resp = await test_client.get("/auth/me")
        assert resp.status_code == 401


# ===========================================================================
# JWT validation
# ===========================================================================


class TestJWT:
    """JWT token lifecycle tests."""

    async def test_expired_token(self, test_client, test_db, registered_user):
        """An expired JWT returns 401."""
        from tests.conftest import expired_token

        token = expired_token(registered_user["id"])
        headers = {"Authorization": f"Bearer {token}"}
        resp = await test_client.get("/auth/me", headers=headers)
        assert resp.status_code == 401

    async def test_invalid_token(self, test_client):
        """A malformed or incorrectly signed token returns 401."""
        token = jwt.encode(
            {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "wrong-secret-key",
            algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}
        resp = await test_client.get("/auth/me", headers=headers)
        assert resp.status_code == 401
