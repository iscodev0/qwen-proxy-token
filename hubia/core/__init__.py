"""Core abstractions: provider interface, registry, and streaming."""

from hubia.core.provider import (
    AIProvider,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderCredentials,
    StreamChunk,
)
from hubia.core.registry import ProviderRegistry
from hubia.core.streaming import (
    chunk_to_sse,
    collect_stream,
    extract_boundary,
    format_sse_done,
    format_sse_event,
    parse_multipart_mixed,
)

__all__ = [
    "AIProvider",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ModelInfo",
    "ProviderCredentials",
    "ProviderRegistry",
    "StreamChunk",
    "chunk_to_sse",
    "collect_stream",
    "extract_boundary",
    "format_sse_done",
    "format_sse_event",
    "parse_multipart_mixed",
]
