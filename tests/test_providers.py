"""Provider tests — MetaAI and ZaiWeb with mocked Scrapling Fetcher."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hubia.core.provider import (
    ChatMessage,
    ChatRequest,
    ModelInfo,
    ProviderCredentials,
)
from hubia.core.streaming import collect_stream


# ---------------------------------------------------------------------------
# Scrapling mock fixture — replaces broken scrapling.fetchers import chain
# (missing playwright dependency) with a mock module at sys.modules level
# so that @patch decorators on provider tests can resolve the target.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="class")
def _mock_scrapling_fetchers():
    """Replace scrapling.fetchers with a mock to bypass import failures."""
    import sys
    from unittest.mock import AsyncMock as _AsyncMock, MagicMock as _MagicMock

    mock_fetcher = _MagicMock()
    mock_fetcher.post = _AsyncMock()

    mock_fetchers_mod = _MagicMock()
    mock_fetchers_mod.AsyncFetcher = mock_fetcher

    orig = sys.modules.get("scrapling.fetchers")
    sys.modules["scrapling.fetchers"] = mock_fetchers_mod
    yield
    if orig is not None:
        sys.modules["scrapling.fetchers"] = orig
    else:
        sys.modules.pop("scrapling.fetchers", None)


# ===========================================================================
# Helpers
# ===========================================================================


def _mock_response(
    status: int = 200,
    body: bytes = b"",
    content_type: str = "application/json",
    headers: dict | None = None,
) -> MagicMock:
    """Build a Scrapling Response-like mock."""
    mock = MagicMock()
    mock.status = status
    mock.body = body
    mock.headers = headers or {"Content-Type": content_type}
    mock.text = body.decode("utf-8", errors="replace")

    def sync_json():
        return json.loads(body)

    mock.json = sync_json
    return mock


@pytest.fixture
def meta_creds():
    """Valid Meta AI credentials fixture."""
    return ProviderCredentials(
        provider="meta_ai",
        data={"datr": "test_datr", "ecto_1_sess": "test_ecto"},
    )


@pytest.fixture
def zai_creds():
    """Valid Z.ai credentials fixture."""
    return ProviderCredentials(
        provider="zai_web",
        data={"token": "eyJhbGciOiJIUzI1NiJ9.test_jwt"},
    )


@pytest.fixture
def chat_request():
    """Basic chat request fixture."""
    return ChatRequest(
        model="meta-ai/muse-spark",
        messages=[ChatMessage(role="user", content="Hello")],
    )


# ===========================================================================
# MetaAIProvider
# ===========================================================================


class TestMetaAIProvider:
    """Meta AI GraphQL provider with mocked HTTP."""

    @patch("scrapling.fetchers.AsyncFetcher.post", new_callable=AsyncMock)
    async def test_chat_completion_json(
        self, mock_post, meta_creds, chat_request
    ):
        """Non‑streaming completion with JSON response returns content."""
        mock_post.return_value = _mock_response(
            body=json.dumps({"text": "Hello from Meta AI"}).encode(),
        )

        from hubia.providers.meta_ai import MetaAIProvider

        provider = MetaAIProvider()
        response = await provider.chat_completion(chat_request, meta_creds)
        assert response.content == "Hello from Meta AI"
        assert response.finish_reason == "stop"

    @patch("scrapling.fetchers.AsyncFetcher.post", new_callable=AsyncMock)
    async def test_chat_completion_multipart(
        self, mock_post, meta_creds, chat_request
    ):
        """Multipart/mixed responses are parsed into chunks."""
        boundary = "----TestBoundary123"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"delta": {"text": "Hello "}}\r\n'
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"delta": {"text": "world"}}\r\n'
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"done": true}\r\n'
            f"--{boundary}--\r\n"
        ).encode()

        mock_post.return_value = _mock_response(
            body=body,
            content_type=f'multipart/mixed; boundary={boundary}',
        )

        from hubia.providers.meta_ai import MetaAIProvider

        provider = MetaAIProvider()
        response = await provider.chat_completion(chat_request, meta_creds)
        assert response.content == "Hello world"
        assert response.finish_reason == "stop"

    @patch("scrapling.fetchers.AsyncFetcher.post", new_callable=AsyncMock)
    async def test_session_expired(self, mock_post, meta_creds, chat_request):
        """HTTP 401 raises SessionExpiredError."""
        mock_post.return_value = _mock_response(status=401)

        from hubia.providers.meta_ai import MetaAIProvider, SessionExpiredError

        provider = MetaAIProvider()
        with pytest.raises(SessionExpiredError):
            await provider.chat_completion(chat_request, meta_creds)

    @patch("scrapling.fetchers.AsyncFetcher.post", new_callable=AsyncMock)
    async def test_invalid_cookies(self, meta_creds, chat_request):
        """Missing required cookie fields → validate_credentials returns False."""
        from hubia.providers.meta_ai import MetaAIProvider

        provider = MetaAIProvider()
        bad_creds = ProviderCredentials(provider="meta_ai", data={"datr": ""})
        valid = await provider.validate_credentials(bad_creds)
        assert valid is False

    @patch("scrapling.fetchers.AsyncFetcher.post", new_callable=AsyncMock)
    async def test_provider_error_on_500(self, mock_post, meta_creds, chat_request):
        """HTTP 500 after retries raises ProviderError."""
        from hubia.providers.meta_ai import MetaAIProvider, ProviderError

        # Retry logic: will try retries+1 times
        mock_post.return_value = _mock_response(status=500)

        provider = MetaAIProvider(retries=1)
        with pytest.raises(ProviderError):
            await provider.chat_completion(chat_request, meta_creds)
        assert mock_post.call_count >= 2

    @patch("scrapling.fetchers.AsyncFetcher.post", new_callable=AsyncMock)
    async def test_streaming_multipart(
        self, mock_post, meta_creds, chat_request
    ):
        """Streaming with multipart yields chunks."""
        boundary = "----Boundary456"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"delta": {"text": "A"}}\r\n'
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"delta": {"text": "B"}}\r\n'
            f"--{boundary}\r\n"
            "Content-Type: application/json\r\n\r\n"
            '{"done": true}\r\n'
            f"--{boundary}--\r\n"
        ).encode()

        mock_post.return_value = _mock_response(
            body=body,
            content_type=f'multipart/mixed; boundary={boundary}',
        )

        from hubia.providers.meta_ai import MetaAIProvider

        provider = MetaAIProvider()
        stream = provider.chat_completion_stream(chat_request, meta_creds)
        text = await collect_stream(stream)
        assert text == "AB"


# ===========================================================================
# ZaiWebProvider
# ===========================================================================


class TestZaiWebProvider:
    """Z.ai REST provider with mocked HTTP."""

    @patch("scrapling.fetchers.AsyncFetcher.post", new_callable=AsyncMock)
    async def test_chat_completion(
        self, mock_post, zai_creds
    ):
        """Non‑streaming completion returns content from choices."""
        request = ChatRequest(
            model="zai/glm-5",
            messages=[ChatMessage(role="user", content="Hi")],
        )
        mock_post.return_value = _mock_response(
            body=json.dumps({
                "id": "zai-123",
                "choices": [{
                    "message": {"content": "Z.ai response"},
                    "finish_reason": "stop",
                }],
            }).encode(),
        )

        from hubia.providers.zai_web import ZaiWebProvider

        provider = ZaiWebProvider()
        response = await provider.chat_completion(request, zai_creds)
        assert response.content == "Z.ai response"
        assert response.finish_reason == "stop"

    @patch("scrapling.fetchers.AsyncFetcher.post", new_callable=AsyncMock)
    async def test_streaming_sse(self, mock_post, zai_creds):
        """SSE streaming yields individual delta chunks."""
        request = ChatRequest(
            model="zai/glm-5",
            messages=[ChatMessage(role="user", content="Hi")],
            stream=True,
        )
        sse_body = (
            "data: {\"choices\": [{\"delta\": {\"content\": \"Hello\"}, \"index\": 0}]}\n\n"
            "data: {\"choices\": [{\"delta\": {\"content\": \" World\"}, \"index\": 0}]}\n\n"
            "data: [DONE]\n\n"
        ).encode()

        mock_post.return_value = _mock_response(
            body=sse_body,
            content_type="text/event-stream",
        )

        from hubia.providers.zai_web import ZaiWebProvider

        provider = ZaiWebProvider()
        stream = provider.chat_completion_stream(request, zai_creds)
        text = await collect_stream(stream)
        assert text == "Hello World"

    @patch("scrapling.fetchers.AsyncFetcher.post", new_callable=AsyncMock)
    async def test_session_expired(self, mock_post, zai_creds):
        """HTTP 401 raises SessionExpiredError."""
        request = ChatRequest(
            model="zai/glm-5",
            messages=[ChatMessage(role="user", content="Hi")],
        )
        mock_post.return_value = _mock_response(status=401)

        from hubia.providers.zai_web import ZaiWebProvider, SessionExpiredError

        provider = ZaiWebProvider()
        with pytest.raises(SessionExpiredError):
            await provider.chat_completion(request, zai_creds)

    @patch("scrapling.fetchers.AsyncFetcher.post", new_callable=AsyncMock)
    async def test_invalid_token(self, zai_creds):
        """Empty/insufficient token → validate_credentials returns False."""
        from hubia.providers.zai_web import ZaiWebProvider

        provider = ZaiWebProvider()
        bad_creds = ProviderCredentials(provider="zai_web", data={"token": "short"})
        valid = await provider.validate_credentials(bad_creds)
        assert valid is False

    async def test_model_mapping(self):
        """Model ID mapping resolves to correct Z.ai params."""
        from hubia.providers.zai_web import ZaiWebProvider

        provider = ZaiWebProvider()
        models = await provider.list_models()
        assert len(models) > 0
        ids = {m.id for m in models}
        assert "zai/glm-5" in ids
        assert "zai/glm-5-turbo" in ids
        assert "zai/glm-4.5" in ids


# ===========================================================================
# ProviderRegistry
# ===========================================================================


class TestProviderRegistry:
    """Model → provider routing."""

    async def test_register_and_resolve(self):
        """Registering a provider and resolving by prefix works."""
        from hubia.core.registry import ProviderRegistry
        from hubia.providers.meta_ai import MetaAIProvider

        registry = ProviderRegistry()
        provider = MetaAIProvider(retries=0)
        registry.register("meta_ai", provider, ["meta-ai/"])

        resolved = registry.get_provider_for_model("meta-ai/muse-spark")
        assert resolved is not None
        p, local_model = resolved
        assert p is provider
        assert local_model == "muse-spark"

    async def test_unknown_model_returns_none(self):
        """Prefix that doesn't match returns None."""
        from hubia.core.registry import ProviderRegistry

        registry = ProviderRegistry()
        resolved = registry.get_provider_for_model("unknown/model")
        assert resolved is None

    async def test_list_all_models(self):
        """Aggregating models from all registered providers."""
        from hubia.core.registry import ProviderRegistry
        from hubia.providers.zai_web import ZaiWebProvider

        registry = ProviderRegistry()
        registry.register("zai_web", ZaiWebProvider(), ["zai/"])

        models = await registry.list_all_models()
        model_ids = [m.id for m in models]
        assert "zai/glm-5" in model_ids
        assert "zai/glm-5-turbo" in model_ids
