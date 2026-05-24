"""Schema tests — Pydantic model validation and conversion methods."""

from __future__ import annotations

import pytest

from hubia.api.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamResponse,
    ChatMessage,
    DeltaMessage,
    ErrorDetail,
    ErrorResponse,
    ModelList,
    ModelObject,
    Usage,
)
from hubia.core.provider import (
    ChatRequest as InternalChatRequest,
    ChatResponse as InternalChatResponse,
    ChatMessage as InternalChatMessage,
    ModelInfo,
    StreamChunk,
)


# ===========================================================================
# ChatCompletionRequest validation
# ===========================================================================


class TestChatCompletionRequest:
    """Request validation and conversion."""

    def test_valid_request(self):
        """All required fields accepted."""
        req = ChatCompletionRequest(
            model="meta-ai/llama-3",
            messages=[ChatMessage(role="user", content="Hi")],
        )
        assert req.model == "meta-ai/llama-3"
        assert len(req.messages) == 1

    def test_optional_fields(self):
        """Optional fields default correctly."""
        req = ChatCompletionRequest(
            model="zai/glm-5",
            messages=[ChatMessage(role="user", content="Hola")],
        )
        assert req.stream is False
        assert req.temperature is None
        assert req.max_tokens is None

    def test_missing_model_fails(self):
        """Missing model field raises ValidationError."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            ChatCompletionRequest(messages=[])  # type: ignore[arg-type]

    def test_missing_messages_fails(self):
        """Missing messages field raises ValidationError."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            ChatCompletionRequest(model="m")  # type: ignore[arg-type]

    def test_to_internal(self):
        """Conversion to internal ChatRequest preserves all fields."""
        req = ChatCompletionRequest(
            model="meta-ai/llama-3",
            messages=[ChatMessage(role="user", content="Hello")],
            stream=True,
            temperature=0.7,
            max_tokens=100,
        )
        internal = req.to_internal()
        assert isinstance(internal, InternalChatRequest)
        assert internal.model == "meta-ai/llama-3"
        assert len(internal.messages) == 1
        assert internal.messages[0].content == "Hello"
        assert internal.stream is True
        assert internal.temperature == 0.7
        assert internal.max_tokens == 100


# ===========================================================================
# ChatCompletionResponse serialization
# ===========================================================================


class TestChatCompletionResponse:
    """Response model serialization."""

    def test_from_internal(self):
        """Building from internal ChatResponse."""
        internal = InternalChatResponse(
            id="resp-123",
            model="meta-ai/llama-3",
            content="Hello!",
            finish_reason="stop",
        )
        resp = ChatCompletionResponse.from_internal(internal)
        assert resp.id == "resp-123"
        assert resp.object == "chat.completion"
        assert resp.model == "meta-ai/llama-3"
        assert len(resp.choices) == 1
        assert resp.choices[0].message.content == "Hello!"
        assert resp.choices[0].finish_reason == "stop"

    def test_serialization(self):
        """Response can be serialised to JSON (for API output)."""
        internal = InternalChatResponse(
            id="resp-456", model="zai/glm-5", content="World!", finish_reason="stop"
        )
        resp = ChatCompletionResponse.from_internal(internal)
        data = resp.model_dump(mode="json")
        assert data["id"] == "resp-456"
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) == 1


# ===========================================================================
# Streaming response
# ===========================================================================


class TestStreamResponse:
    """Streaming chunk model."""

    def test_from_chunk(self):
        """Building from chunk with content."""
        chunk = StreamChunk(content="Hello", finish_reason=None)
        stream_resp = ChatCompletionStreamResponse.from_chunk(
            content=chunk.content, model="meta-ai/llama-3"
        )
        assert stream_resp.object == "chat.completion.chunk"
        assert len(stream_resp.choices) == 1
        assert stream_resp.choices[0].delta.content == "Hello"

    def test_from_chunk_with_finish(self):
        """Finish reason appears in the response."""
        stream_resp = ChatCompletionStreamResponse.from_chunk(
            content="", model="m", finish_reason="stop"
        )
        assert stream_resp.choices[0].finish_reason == "stop"

    def test_from_chunk_empty_content(self):
        """Empty content yields null delta content (OpenAI spec)."""
        stream_resp = ChatCompletionStreamResponse.from_chunk(
            content="", model="m"
        )
        assert stream_resp.choices[0].delta.content is None


# ===========================================================================
# Model list
# ===========================================================================


class TestModelList:
    """Model list response."""

    def test_from_model_infos(self):
        """Building ModelList from ModelInfo objects."""
        models = [
            ModelInfo(id="meta-ai/llama-3", provider="meta_ai"),
            ModelInfo(id="zai/glm-5", provider="zai_web"),
        ]
        ml = ModelList.from_model_infos(models)
        assert ml.object == "list"
        assert len(ml.data) == 2
        assert ml.data[0].id == "meta-ai/llama-3"
        assert ml.data[0].owned_by == "meta_ai"
        assert ml.data[1].id == "zai/glm-5"


# ===========================================================================
# Error schema
# ===========================================================================


class TestErrorSchema:
    """OpenAI-compatible error format."""

    def test_error_response(self):
        """ErrorResponse serialises to expected format."""
        err = ErrorResponse(
            error=ErrorDetail(
                message="Model not found",
                type="invalid_request_error",
                code="model_not_found",
            )
        )
        data = err.model_dump(mode="json")
        assert data["error"]["message"] == "Model not found"
        assert data["error"]["type"] == "invalid_request_error"
        assert data["error"]["code"] == "model_not_found"
        assert data["error"]["param"] is None

    def test_error_with_param(self):
        """Error can include a param field."""
        err = ErrorResponse(
            error=ErrorDetail(
                message="Bad value",
                type="invalid_request_error",
                code="invalid_param",
                param="temperature",
            )
        )
        data = err.model_dump(mode="json")
        assert data["error"]["param"] == "temperature"
