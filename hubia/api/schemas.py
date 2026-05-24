"""OpenAI-compatible Pydantic v2 models for the API layer."""

from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from hubia.core.provider import ChatMessage as InternalChatMessage
from hubia.core.provider import ChatRequest as InternalChatRequest
from hubia.core.provider import ChatResponse as InternalChatResponse


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single message in a chat conversation (OpenAI format)."""

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request body."""

    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None

    def to_internal(self) -> InternalChatRequest:
        """Convert to internal :class:`ChatRequest` dataclass."""
        return InternalChatRequest(
            model=self.model,
            messages=[
                InternalChatMessage(role=m.role, content=m.content) for m in self.messages
            ],
            stream=self.stream,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )


# ---------------------------------------------------------------------------
# Non-streaming response models
# ---------------------------------------------------------------------------


class Usage(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatChoice(BaseModel):
    """A single completion choice (non-streaming)."""

    index: int = 0
    message: ChatMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: Usage | None = None

    @classmethod
    def from_internal(
        cls,
        internal: InternalChatResponse,
        *,
        model: str | None = None,
    ) -> ChatCompletionResponse:
        """Build from an internal :class:`ChatResponse`."""
        return cls(
            id=internal.id,
            created=int(time.time()),
            model=model or internal.model,
            choices=[
                ChatChoice(
                    message=ChatMessage(role="assistant", content=internal.content),
                    finish_reason=internal.finish_reason,
                )
            ],
        )


# ---------------------------------------------------------------------------
# Streaming response models
# ---------------------------------------------------------------------------


class DeltaMessage(BaseModel):
    """A streaming delta (partial content update)."""

    role: str | None = None
    content: str | None = None


class ChatStreamChoice(BaseModel):
    """A single streaming choice with delta."""

    index: int = 0
    delta: DeltaMessage
    finish_reason: str | None = None


class ChatCompletionStreamResponse(BaseModel):
    """OpenAI-compatible streaming chunk (SSE event body)."""

    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChatStreamChoice]

    @classmethod
    def from_chunk(
        cls,
        content: str,
        model: str,
        *,
        finish_reason: str | None = None,
        chunk_id: str | None = None,
    ) -> ChatCompletionStreamResponse:
        """Build a streaming chunk from content text."""
        return cls(
            id=chunk_id or f"chatcmpl-{uuid.uuid4().hex[:12]}",
            created=int(time.time()),
            model=model,
            choices=[
                ChatStreamChoice(
                    delta=DeltaMessage(content=content or None, role="assistant" if content else None),
                    finish_reason=finish_reason,
                )
            ],
        )


# ---------------------------------------------------------------------------
# Model list models
# ---------------------------------------------------------------------------


class ModelObject(BaseModel):
    """A model entry in the model list."""

    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str = "hubia"


class ModelList(BaseModel):
    """OpenAI-compatible model list response."""

    object: Literal["list"] = "list"
    data: list[ModelObject]

    @classmethod
    def from_model_infos(cls, models: list) -> ModelList:
        """Build from a list of :class:`ModelInfo` instances."""
        now = int(time.time())
        return cls(
            data=[
                ModelObject(
                    id=m.id,
                    created=now,
                    owned_by=m.provider,
                )
                for m in models
            ]
        )


# ---------------------------------------------------------------------------
# Error models
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """A single error detail (OpenAI-compatible format)."""

    message: str
    type: str = "invalid_request_error"
    code: str | None = None
    param: str | None = None


class ErrorResponse(BaseModel):
    """OpenAI-compatible error response body."""

    error: ErrorDetail
