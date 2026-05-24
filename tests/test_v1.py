"""API v1 tests — /v1/models and /v1/chat/completions."""

from __future__ import annotations

import json

import pytest


# ===========================================================================
# GET /v1/models
# ===========================================================================


class TestModels:
    """Model listing endpoint."""

    async def test_list_models(self, test_client, auth_headers):
        """Authenticated request returns model list from all providers."""
        resp = await test_client.get("/v1/models", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "list"
        assert len(body["data"]) >= 2
        model_ids = {m["id"] for m in body["data"]}
        assert "meta-ai/llama-3" in model_ids
        assert "zai/glm-5" in model_ids

    async def test_models_requires_auth(self, test_client):
        """Without auth, model list returns 401."""
        resp = await test_client.get("/v1/models")
        assert resp.status_code == 401


# ===========================================================================
# POST /v1/chat/completions — standard (non-streaming)
# ===========================================================================


class TestChatCompletions:
    """Standard (non‑streaming) chat completions."""

    async def test_chat_completion_success(
        self, test_client, auth_headers, stored_credentials
    ):
        """Standard request returns an OpenAI-compatible response."""
        resp = await test_client.post(
            "/v1/chat/completions",
            headers=auth_headers,
            json={
                "model": "meta-ai/llama-3",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "chat.completion"
        assert body["model"] == "meta-ai/llama-3"
        assert len(body["choices"]) > 0
        assert body["choices"][0]["message"]["role"] == "assistant"
        assert "content" in body["choices"][0]["message"]
        assert "id" in body
        assert "created" in body

    async def test_chat_completion_requires_auth(self, test_client):
        """Without auth, completion returns 401."""
        resp = await test_client.post(
            "/v1/chat/completions",
            json={
                "model": "meta-ai/llama-3",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
        assert resp.status_code == 401

    async def test_unknown_model(self, test_client, auth_headers):
        """Unknown model returns 404 with OpenAI-compatible error."""
        resp = await test_client.post(
            "/v1/chat/completions",
            headers=auth_headers,
            json={
                "model": "nonexistent/model",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "model_not_found"

    async def test_missing_credentials(self, test_client, auth_headers):
        """No stored credentials for a provider returns 403."""
        resp = await test_client.post(
            "/v1/chat/completions",
            headers=auth_headers,
            json={
                "model": "meta-ai/llama-3",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
        assert resp.status_code == 403
        body = resp.json()
        assert "error" in body

    async def test_invalid_json_body(self, test_client, auth_headers):
        """Malformed JSON returns 422."""
        resp = await test_client.post(
            "/v1/chat/completions",
            headers=auth_headers,
            content=b"not-json",
        )
        assert resp.status_code == 422


# ===========================================================================
# POST /v1/chat/completions — streaming
# ===========================================================================


class TestStreaming:
    """Streaming chat completions (SSE)."""

    async def test_stream_chunks(
        self, test_client, auth_headers, stored_credentials
    ):
        """stream=true returns text/event-stream with delta chunks."""
        resp = await test_client.post(
            "/v1/chat/completions",
            headers=auth_headers,
            json={
                "model": "meta-ai/llama-3",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        body = resp.text
        assert "data:" in body
        # Should contain delta content
        assert "Mock" in body
        # Should end with [DONE]
        assert "data: [DONE]" in body

    async def test_stream_includes_openai_format(
        self, test_client, auth_headers, stored_credentials
    ):
        """SSE events follow OpenAI delta format."""
        resp = await test_client.post(
            "/v1/chat/completions",
            headers=auth_headers,
            json={
                "model": "meta-ai/llama-3",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
            },
        )
        lines = resp.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data: ")]
        assert len(data_lines) >= 2  # at least one content + DONE

        # Parse first data line as JSON
        first_data = data_lines[0][6:]  # strip "data: "
        if first_data != "[DONE]":
            payload = json.loads(first_data)
            assert "choices" in payload
            assert "delta" in payload["choices"][0]
