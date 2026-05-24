"""Abstract provider interface and shared data types for AI providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: str  # "user", "assistant", "system"
    content: str


@dataclass
class ChatRequest:
    """Request payload for a chat completion."""

    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class StreamChunk:
    """A single streaming delta from a provider."""

    content: str
    finish_reason: Optional[str] = None  # "stop", "length", or None


@dataclass
class ChatResponse:
    """A complete (non-streaming) chat completion response."""

    id: str
    model: str
    content: str
    finish_reason: Optional[str] = None


@dataclass
class ModelInfo:
    """Metadata about an available model."""

    id: str
    provider: str
    description: Optional[str] = None


@dataclass
class ProviderCredentials:
    """Provider-specific credentials — cookies, tokens, etc."""

    provider: str
    data: dict  # Raw credential payload


# ---------------------------------------------------------------------------
# Abstract provider interface
# ---------------------------------------------------------------------------


class AIProvider(ABC):
    """Abstract base class for all AI providers.

    Subclasses must implement all four methods to integrate with the
    provider registry and the OpenAI-compatible API layer.
    """

    @abstractmethod
    async def chat_completion(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> ChatResponse:
        """Non‑streaming chat completion.

        Returns the complete response once all tokens have been generated.
        """

    @abstractmethod
    def chat_completion_stream(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion.

        Yields :class:`StreamChunk` instances as tokens arrive from the
        upstream provider.
        """

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return the list of models this provider offers."""

    @abstractmethod
    async def validate_credentials(
        self,
        credentials: ProviderCredentials,
    ) -> bool:
        """Check whether *credentials* are still valid (e.g. not expired).

        Returns ``True`` if the credentials can be used to make a request.
        """
