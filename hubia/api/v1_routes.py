"""OpenAI-compatible /v1 routes — models list and chat completions."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import aiosqlite
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from hubia.api.auth import get_current_user
from hubia.api.errors import (
    CredentialMissingError,
    HubiaError,
    ModelNotFoundError,
    ProviderError as ApiProviderError,
    SessionExpiredError as ApiSessionExpiredError,
)
from hubia.api.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamResponse,
    ModelList,
)
from hubia.core.provider import ChatRequest as InternalChatRequest
from hubia.core.provider import ProviderCredentials, StreamChunk
from hubia.core.registry import ProviderRegistry
from hubia.core.streaming import format_sse_done, format_sse_event
from hubia.store.credentials import get_credential
from hubia.store.database import get_db

router = APIRouter(prefix="/v1", tags=["v1"])

# Will be set during app startup via set_registry()
_registry: ProviderRegistry | None = None


def set_registry(registry: ProviderRegistry) -> None:
    """Inject the provider registry (called during app lifespan startup)."""
    global _registry  # noqa: PLW0603
    _registry = registry


def _get_registry() -> ProviderRegistry:
    if _registry is None:
        raise RuntimeError("ProviderRegistry not initialized")
    return _registry


# ---------------------------------------------------------------------------
# GET /v1/models
# ---------------------------------------------------------------------------


@router.get("/models")
async def list_models(
    current_user: dict = Depends(get_current_user),
) -> ModelList:
    """List all available models from all registered providers.

    Requires a valid JWT or API key in the ``Authorization`` header.
    """
    registry = _get_registry()
    models = await registry.list_all_models()
    return ModelList.from_model_infos(models)


# ---------------------------------------------------------------------------
# POST /v1/chat/completions
# ---------------------------------------------------------------------------


@router.post("/chat/completions")
async def chat_completion(
    body: ChatCompletionRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Chat completion — standard (JSON) or streaming (SSE).

    Set ``stream: true`` in the request body to receive a Server-Sent Events
    stream.  Both modes require valid authentication and stored provider
    credentials.
    """
    # Resolve provider from model ID
    registry = _get_registry()
    resolved = registry.get_provider_for_model(body.model)
    if resolved is None:
        raise ModelNotFoundError(body.model)

    provider, local_model = resolved

    # Determine provider name for credential lookup
    provider_name = "meta_ai" if "meta-ai" in body.model else "zai_web"

    # Fetch user's stored credentials for this provider
    cred_row = await get_credential(db, current_user["id"], provider_name)
    if cred_row is None or cred_row.get("data") is None:
        raise CredentialMissingError(provider_name)

    credentials = ProviderCredentials(provider=provider_name, data=cred_row["data"])

    # Convert request to internal format
    internal_request: InternalChatRequest = body.to_internal()

    if body.stream:
        return await _handle_stream(provider, internal_request, credentials, body.model)
    else:
        return await _handle_standard(provider, internal_request, credentials, body.model)


async def _handle_standard(
    provider,
    request: InternalChatRequest,
    credentials: ProviderCredentials,
    model: str,
) -> ChatCompletionResponse:
    """Non-streaming chat completion — returns a single JSON response."""
    try:
        response = await provider.chat_completion(request, credentials)
    except Exception as exc:
        _reraise_as_api_error(exc)
    return ChatCompletionResponse.from_internal(response, model=model)


async def _handle_stream(
    provider,
    request: InternalChatRequest,
    credentials: ProviderCredentials,
    model: str,
) -> StreamingResponse:
    """Streaming chat completion — returns an SSE ``StreamingResponse``."""

    async def event_stream() -> AsyncIterator[str]:
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        try:
            async for chunk in provider.chat_completion_stream(request, credentials):
                sse_event = _chunk_to_sse(chunk, model, chunk_id)
                if sse_event:
                    yield sse_event
            yield format_sse_done()
        except Exception as exc:
            error_event = _error_to_sse(exc)
            if error_event:
                yield error_event
            yield format_sse_done()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _chunk_to_sse(chunk: StreamChunk, model: str, chunk_id: str) -> str | None:
    """Convert a :class:`StreamChunk` to an OpenAI SSE event string."""
    response = ChatCompletionStreamResponse.from_chunk(
        content=chunk.content,
        model=model,
        finish_reason=chunk.finish_reason,
        chunk_id=chunk_id,
    )
    return format_sse_event(response.model_dump_json(by_alias=True))


def _error_to_sse(exc: Exception) -> str | None:
    """Convert an exception to an SSE error event."""
    if isinstance(exc, HubiaError):
        error_data = json.dumps(
            {
                "error": {
                    "message": exc.message,
                    "type": exc.type_,
                    "code": exc.code,
                }
            },
            separators=(",", ":"),
        )
    else:
        error_data = json.dumps(
            {
                "error": {
                    "message": "Provider request failed",
                    "type": "api_error",
                    "code": "provider_error",
                }
            },
            separators=(",", ":"),
        )
    return format_sse_event(error_data)


def _reraise_as_api_error(exc: Exception) -> None:
    """Convert provider-level exceptions to API-layer exceptions.

    Provider modules define their own ``SessionExpiredError`` and
    ``ProviderError`` — this helper maps them to the centralised API
    exception classes.
    """
    from hubia.providers.meta_ai import (
        ProviderError as MetaProviderError,
        SessionExpiredError as MetaSessionExpired,
    )
    from hubia.providers.zai_web import (
        ProviderError as ZaiProviderError,
        SessionExpiredError as ZaiSessionExpired,
    )

    if isinstance(exc, (MetaSessionExpired, ZaiSessionExpired)):
        raise ApiSessionExpiredError(str(exc)) from exc
    if isinstance(exc, (MetaProviderError, ZaiProviderError)):
        raise ApiProviderError(str(exc)) from exc
    if isinstance(exc, HubiaError):
        raise exc
    # Unknown exception — wrap in a generic ProviderError
    raise ApiProviderError(str(exc)) from exc
