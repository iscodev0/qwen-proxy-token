"""Z.ai Web provider — REST client using Scrapling Fetcher."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from hubia.core.provider import (
    AIProvider,
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderCredentials,
    StreamChunk,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class SessionExpiredError(Exception):
    """Raised when the Z.ai session token is expired."""


class ProviderError(Exception):
    """Raised on upstream API errors after retries are exhausted."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZAI_BASE_URL = "https://chat.z.ai"
ZAI_API_URL = f"{ZAI_BASE_URL}/api"

# Local model ID → Z.ai internal model parameter mapping
MODEL_MAP: dict[str, str] = {
    "glm-5": "glm-5",
    "glm-5.1": "glm-5.1",
    "glm-5-turbo": "glm-5-turbo",
    "glm-5v-turbo": "glm-5v-turbo",
    "glm-5-code": "glm-5-code",
    "glm-4.5": "glm-4.5",
    "glm-4.6": "glm-4.6",
    "glm-4.7": "glm-4.7",
}

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/event-stream",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": ZAI_BASE_URL,
    "Referer": f"{ZAI_BASE_URL}/",
}


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class ZaiWebProvider(AIProvider):
    """Provider for Z.ai's web chat API.

    Uses :class:`scrapling.fetchers.AsyncFetcher` for HTTP requests with
    TLS fingerprint impersonation.

    Credentials must contain a ``token``, ``jwt``, or ``session_token``
    field for authentication.
    """

    def __init__(self, retries: int = 2) -> None:
        self._retries = retries

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_model_list() -> list[ModelInfo]:
        models: list[ModelInfo] = []
        for model_id in MODEL_MAP:
            models.append(
                ModelInfo(
                    id=f"zai/{model_id}",
                    provider="zai_web",
                    description=f"Z.ai model: {model_id}",
                )
            )
        return models

    @staticmethod
    def _resolve_model(model_id: str) -> str:
        """Map a local model ID (e.g. ``\"glm-5-turbo\"``) to Z.ai param.

        Falls back to ``\"glm-5\"`` when the model is not recognised.
        """
        return MODEL_MAP.get(model_id, "glm-5")

    async def _request(
        self,
        endpoint: str,
        json_payload: dict[str, Any],
        credentials: ProviderCredentials,
    ) -> Any:
        """Execute a REST request with retry logic.

        Returns the Scrapling ``Response`` object on success.

        Raises:
            SessionExpiredError: On HTTP 401 (expired token).
            ProviderError: On repeated failures.
        """
        from scrapling.fetchers import AsyncFetcher

        data = credentials.data
        token = data.get("token") or data.get("jwt") or data.get("session_token", "")

        headers = dict(_DEFAULT_HEADERS)
        headers["Authorization"] = f"Bearer {token}"

        last_error: Exception | None = None

        for attempt in range(1, self._retries + 2):
            try:
                response = await AsyncFetcher.post(
                    f"{ZAI_API_URL}/{endpoint}",
                    json=json_payload,
                    headers=headers,
                    impersonate="chrome133",
                    timeout=60,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Z.ai request failed (attempt %d/%d): %s",
                    attempt,
                    self._retries + 1,
                    exc,
                )
                if attempt <= self._retries:
                    continue
                raise ProviderError(f"Request failed after retries: {exc}") from exc

            if response.status == 401:
                raise SessionExpiredError(
                    "Z.ai session token expired. "
                    "Please re-capture your token via /sandbox/zai."
                )

            if response.status >= 500:
                last_error = ProviderError(
                    f"Z.ai returned HTTP {response.status}"
                )
                if attempt <= self._retries:
                    continue
                raise last_error

            if response.status != 200:
                raise ProviderError(
                    f"Z.ai returned HTTP {response.status}: "
                    f"{getattr(response, 'text', '')[:500]}"
                )

            return response

        raise ProviderError(f"Request failed: {last_error}")

    # ------------------------------------------------------------------
    # AIProvider interface
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> ChatResponse:
        """Non‑streaming chat completion via Z.ai API.

        The request is sent to ``POST /api/chat/completions`` with an
        OpenAI-compatible payload.
        """
        local_model = self._resolve_model(request.model)
        messages = [
            {"role": m.role, "content": m.content}
            for m in request.messages
        ]

        payload: dict[str, Any] = {
            "model": local_model,
            "messages": messages,
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        response = await self._request("chat/completions", payload, credentials)

        try:
            data = response.json()
        except Exception:
            return ChatResponse(
                id=str(uuid.uuid4()),
                model=request.model,
                content=getattr(response, "text", "")[:500],
                finish_reason="stop",
            )

        content = ""
        finish_reason: str | None = None

        choices = data.get("choices") if isinstance(data, dict) else None
        if choices:
            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            finish_reason = choice.get("finish_reason", "stop")
        elif isinstance(data, dict):
            content = (
                data.get("response")
                or data.get("text")
                or json.dumps(data)
            )

        return ChatResponse(
            id=data.get("id", str(uuid.uuid4())) if isinstance(data, dict) else str(uuid.uuid4()),
            model=request.model,
            content=content,
            finish_reason=finish_reason or "stop",
        )

    async def chat_completion_stream(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion via Z.ai API.

        The upstream SSE stream is parsed and re-packaged as OpenAI SSE
        ``StreamChunk``\\ s.
        """
        local_model = self._resolve_model(request.model)
        messages = [
            {"role": m.role, "content": m.content}
            for m in request.messages
        ]

        payload: dict[str, Any] = {
            "model": local_model,
            "messages": messages,
            "stream": True,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        response = await self._request("chat/completions", payload, credentials)

        content_type = response.headers.get("Content-Type", "")
        body_text = getattr(response, "text", "")

        if "text/event-stream" in content_type:
            # Parse Z.ai SSE → OpenAI SSE chunks
            for line in body_text.split("\n"):
                line = line.strip()
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        yield StreamChunk(content="", finish_reason="stop")
                        return
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            finish = choices[0].get("finish_reason")
                            if content:
                                yield StreamChunk(content=content, finish_reason=None)
                            if finish:
                                yield StreamChunk(content="", finish_reason=finish)
                                return
                    except json.JSONDecodeError:
                        continue
        else:
            # Non-SSE response — parse as JSON and yield once
            try:
                data = json.loads(body_text)
            except json.JSONDecodeError:
                yield StreamChunk(content=body_text[:500], finish_reason="stop")
                return

            choices = data.get("choices", []) if isinstance(data, dict) else []
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content", "")
                yield StreamChunk(content=content, finish_reason="stop")
            elif isinstance(data, dict):
                content = data.get("response") or data.get("text") or body_text[:500]
                yield StreamChunk(content=content, finish_reason="stop")
            else:
                yield StreamChunk(content=body_text[:500], finish_reason="stop")

    async def list_models(self) -> list[ModelInfo]:
        """Return Z.ai models available through this provider."""
        return self._build_model_list()

    async def validate_credentials(
        self,
        credentials: ProviderCredentials,
    ) -> bool:
        """Check if credentials contain a valid-looking token."""
        data = credentials.data
        token = data.get("token") or data.get("jwt") or data.get("session_token", "")
        if not token:
            return False
        if not isinstance(token, str) or len(token) < 10:
            return False
        return True
