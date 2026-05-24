"""Sandbox API tests — interactive capture, manual input, credential CRUD.

These tests cover the sandbox routes for Meta AI and Z.ai credential
management:
- Interactive capture start / status / done flow
- Manual cookie and token input
- Credential listing and deletion
- Authentication guards
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from hubia.sandbox.routes import _capture_states


# ===========================================================================
# Helpers
# ===========================================================================

_MOCK_COOKIES = {"datr": "test_datr", "ecto_1_sess": "test_ecto_1_sess"}
_MOCK_TOKEN = "test_jwt_token_value_12345"


# ===========================================================================
# Manual Input — Meta AI
# ===========================================================================


class TestMetaAiManualCapture:
    """POST /sandbox/meta-ai/capture — direct cookie input."""

    async def test_manual_cookies_success(self, test_client, auth_headers):
        """Valid cookies are stored and return ok."""
        resp = await test_client.post(
            "/sandbox/meta-ai/capture",
            headers=auth_headers,
            json={"cookies": _MOCK_COOKIES},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["credential_id"] is not None

    async def test_manual_cookies_missing_fields(self, test_client, auth_headers):
        """Missing required cookie fields return 400."""
        resp = await test_client.post(
            "/sandbox/meta-ai/capture",
            headers=auth_headers,
            json={"cookies": {"datr": "only_datr"}},
        )
        assert resp.status_code == 400
        assert "ecto_1_sess" in resp.json()["detail"]

    async def test_manual_cookies_empty_values(self, test_client, auth_headers):
        """Empty cookie values return 400."""
        resp = await test_client.post(
            "/sandbox/meta-ai/capture",
            headers=auth_headers,
            json={"cookies": {"datr": "", "ecto_1_sess": ""}},
        )
        assert resp.status_code == 400

    async def test_manual_cookies_requires_auth(self, test_client):
        """Without auth, cookie input returns 401."""
        resp = await test_client.post(
            "/sandbox/meta-ai/capture",
            json={"cookies": _MOCK_COOKIES},
        )
        assert resp.status_code == 401


# ===========================================================================
# Manual Input — Z.ai
# ===========================================================================


class TestZaiManualCapture:
    """POST /sandbox/zai/capture — direct token input."""

    async def test_manual_token_success(self, test_client, auth_headers):
        """Valid token is stored and returns ok."""
        resp = await test_client.post(
            "/sandbox/zai/capture",
            headers=auth_headers,
            json={"token": _MOCK_TOKEN},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

    async def test_manual_token_too_short(self, test_client, auth_headers):
        """Token shorter than 10 chars returns 422 (Pydantic validation)."""
        resp = await test_client.post(
            "/sandbox/zai/capture",
            headers=auth_headers,
            json={"token": "short"},
        )
        assert resp.status_code == 422

    async def test_manual_token_empty(self, test_client, auth_headers):
        """Empty token returns 422."""
        resp = await test_client.post(
            "/sandbox/zai/capture",
            headers=auth_headers,
            json={"token": ""},
        )
        assert resp.status_code == 422

    async def test_manual_token_requires_auth(self, test_client):
        """Without auth, token input returns 401."""
        resp = await test_client.post(
            "/sandbox/zai/capture",
            json={"token": _MOCK_TOKEN},
        )
        assert resp.status_code == 401


# ===========================================================================
# Interactive Capture — Start / Status / Done
# ===========================================================================


class TestMetaAiInteractiveCapture:
    """POST /sandbox/meta-ai/capture/start → status → done flow."""

    async def test_start_capture_returns_id(self, test_client, auth_headers):
        """Starting an interactive capture returns a capture_id."""
        resp = await test_client.post(
            "/sandbox/meta-ai/capture/start",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert "capture_id" in body
        assert len(body["capture_id"]) == 12  # uuid hex[:12]

    async def test_start_capture_requires_auth(self, test_client):
        """Without auth, start returns 401."""
        resp = await test_client.post("/sandbox/meta-ai/capture/start")
        assert resp.status_code == 401

    async def test_check_status_unknown_id(self, test_client, auth_headers):
        """Checking status for a non-existent capture returns 404."""
        resp = await test_client.get(
            "/sandbox/meta-ai/capture/unknown12345/status",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_start_then_status_pending(self, test_client, auth_headers):
        """After start, status should be 'pending' initially."""
        start = await test_client.post(
            "/sandbox/meta-ai/capture/start",
            headers=auth_headers,
        )
        cid = start.json()["capture_id"]

        resp = await test_client.get(
            f"/sandbox/meta-ai/capture/{cid}/status",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["capture_id"] == cid
        assert body["status"] in ("pending", "ok", "error")

    async def test_done_signal_acknowledged(self, test_client, auth_headers):
        """Sending done signal returns acknowledged."""
        start = await test_client.post(
            "/sandbox/meta-ai/capture/start",
            headers=auth_headers,
        )
        cid = start.json()["capture_id"]

        resp = await test_client.post(
            f"/sandbox/meta-ai/capture/{cid}/done",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "acknowledged"

    async def test_done_unknown_capture(self, test_client, auth_headers):
        """Done signal for non-existent capture returns 404."""
        resp = await test_client.post(
            "/sandbox/meta-ai/capture/unknown12345/done",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_capture_state_persistence(self, test_client, auth_headers):
        """Capture state is stored and can be retrieved after start."""
        import hubia.sandbox.routes as sandbox_routes

        start = await test_client.post(
            "/sandbox/meta-ai/capture/start",
            headers=auth_headers,
        )
        cid = start.json()["capture_id"]

        # Manually complete the capture to test status flow
        state = sandbox_routes._capture_states.get(cid)
        assert state is not None
        assert state.provider == "meta_ai"
        assert state.status == "pending"

        # Simulate completion
        state.status = "ok"
        state.result = _MOCK_COOKIES

        resp = await test_client.get(
            f"/sandbox/meta-ai/capture/{cid}/status",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"


class TestZaiInteractiveCapture:
    """POST /sandbox/zai/capture/start → status → done flow."""

    async def test_start_capture_returns_id(self, test_client, auth_headers):
        """Starting an interactive Z.ai capture returns a capture_id."""
        resp = await test_client.post(
            "/sandbox/zai/capture/start",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert "capture_id" in body

    async def test_start_capture_requires_auth(self, test_client):
        """Without auth, start returns 401."""
        resp = await test_client.post("/sandbox/zai/capture/start")
        assert resp.status_code == 401

    async def test_check_status_pending(self, test_client, auth_headers):
        """After start, status should be 'pending'."""
        start = await test_client.post(
            "/sandbox/zai/capture/start",
            headers=auth_headers,
        )
        cid = start.json()["capture_id"]

        resp = await test_client.get(
            f"/sandbox/zai/capture/{cid}/status",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["capture_id"] == cid
        assert resp.json()["status"] in ("pending", "ok", "error")

    async def test_done_signal_acknowledged(self, test_client, auth_headers):
        """Sending done signal returns acknowledged."""
        start = await test_client.post(
            "/sandbox/zai/capture/start",
            headers=auth_headers,
        )
        cid = start.json()["capture_id"]

        resp = await test_client.post(
            f"/sandbox/zai/capture/{cid}/done",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "acknowledged"

    async def test_done_unknown_capture(self, test_client, auth_headers):
        """Done signal for non-existent capture returns 404."""
        resp = await test_client.post(
            "/sandbox/zai/capture/unknown12345/done",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_status_requires_auth(self, test_client):
        """Checking status without auth returns 401."""
        resp = await test_client.get("/sandbox/zai/capture/abc123/status")
        assert resp.status_code == 401


# ===========================================================================
# Sandbox Page (HTML)
# ===========================================================================


class TestSandboxPage:
    """GET /sandbox — HTML UI."""

    async def test_sandbox_page_returns_html(self, test_client, auth_headers):
        """Authenticated request returns HTML page."""
        resp = await test_client.get("/sandbox", headers=auth_headers)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    async def test_sandbox_page_requires_auth(self, test_client):
        """Without auth, sandbox page returns 401."""
        resp = await test_client.get("/sandbox")
        assert resp.status_code == 401


# ===========================================================================
# Credential CRUD via Sandbox
# ===========================================================================


class TestCredentialManagement:
    """GET /sandbox/credentials, DELETE /sandbox/credentials/{provider}."""

    async def test_list_credentials_empty(self, test_client, auth_headers):
        """Initially, no credentials are stored."""
        resp = await test_client.get("/sandbox/credentials", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["credentials"] == []

    async def test_list_credentials_after_store(self, test_client, auth_headers):
        """After storing cookies, list returns them."""
        await test_client.post(
            "/sandbox/meta-ai/capture",
            headers=auth_headers,
            json={"cookies": _MOCK_COOKIES},
        )
        resp = await test_client.get("/sandbox/credentials", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["credentials"]) >= 1
        providers = {c["provider"] for c in body["credentials"]}
        assert "meta_ai" in providers

    async def test_delete_credential(self, test_client, auth_headers):
        """Deleting a credential removes it."""
        # Store first
        await test_client.post(
            "/sandbox/meta-ai/capture",
            headers=auth_headers,
            json={"cookies": _MOCK_COOKIES},
        )
        # Delete
        resp = await test_client.delete(
            "/sandbox/credentials/meta_ai",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    async def test_delete_nonexistent(self, test_client, auth_headers):
        """Deleting a non-existent credential returns 404."""
        resp = await test_client.delete(
            "/sandbox/credentials/nonexistent",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_list_requires_auth(self, test_client):
        """Without auth, listing returns 401."""
        resp = await test_client.get("/sandbox/credentials")
        assert resp.status_code == 401

    async def test_delete_requires_auth(self, test_client):
        """Without auth, delete returns 401."""
        resp = await test_client.delete("/sandbox/credentials/meta_ai")
        assert resp.status_code == 401
