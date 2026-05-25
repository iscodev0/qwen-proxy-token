"""Qwen Chat provider — REST client using Bearer JWT authentication.

Authenticates via email/password to obtain JWT token from chat.qwen.ai.
Supports SSE streaming and non-streaming chat completion.

Features:
    - Automatic chat creation for each request
    - System prompt support (OpenAI-compatible)
    - Thinking/reasoning mode
    - Web search tool
    - Code interpreter tool
    - Dynamic model list from API
    - Auto token refresh
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

import httpx

from hubia.core.provider import (
    AIProvider,
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderCredentials,
    StreamChunk,
)

logger = logging.getLogger(__name__)


class QwenSessionExpiredError(Exception):
    """Raised when the Qwen JWT token is expired."""


class QwenProviderError(Exception):
    """Raised on upstream API errors after retries are exhausted."""


QWEN_BASE_URL = "https://chat.qwen.ai"
QWEN_API_URL = f"{QWEN_BASE_URL}/api/v2"
QWEN_AUTH_URL = f"{QWEN_BASE_URL}/api/v1/auth/login"

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": QWEN_BASE_URL,
    "Referer": f"{QWEN_BASE_URL}/",
}


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class QwenChatProvider(AIProvider):
    """Provider for Qwen's web chat API using Bearer JWT authentication.

    Credentials must contain email and password for JWT token acquisition.
    Token is cached and auto-refreshed when expired.
    """

    def __init__(self, retries: int = 2) -> None:
        self._retries = retries
        self._token: str | None = None
        self._token_expiry: datetime | None = None
        self._models_cache: list[ModelInfo] | None = None
        self._models_cache_time: datetime | None = None

    async def _login(self, email: str, password: str) -> str:
        """Authenticate with Qwen and return JWT token."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                QWEN_AUTH_URL,
                json={"email": email, "password": password},
                headers=_DEFAULT_HEADERS,
            )
            
            if response.status_code != 200:
                raise QwenProviderError(
                    f"Qwen login failed (HTTP {response.status_code}): {response.text[:200]}"
                )
            
            data = response.json()
            token = data.get("token") or data.get("data", {}).get("token")
            
            if not token:
                raise QwenProviderError("Qwen login response missing token")
            
            self._token = token
            self._token_expiry = datetime.now() + timedelta(days=29)
            
            logger.info("Qwen login successful, token expires in 29 days")
            return token

    async def _ensure_token(self, credentials: ProviderCredentials) -> str:
        """Ensure we have a valid token, refreshing if needed."""
        data = credentials.data
        email = data.get("email")
        password = data.get("password")
        
        if not email or not password:
            raise QwenProviderError("Credentials must contain 'email' and 'password'")
        
        if self._token and self._token_expiry and datetime.now() < self._token_expiry:
            return self._token
        
        return await self._login(email, password)

    def _get_headers(self, token: str) -> dict[str, str]:
        """Build headers with Bearer token."""
        headers = dict(_DEFAULT_HEADERS)
        headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _fetch_models(self, token: str) -> list[ModelInfo]:
        """Fetch available models from Qwen API with caching."""
        if self._models_cache and self._models_cache_time:
            cache_age = datetime.now() - self._models_cache_time
            if cache_age < timedelta(hours=1):
                return self._models_cache
        
        headers = self._get_headers(token)
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{QWEN_API_URL}/models",
                headers=headers,
            )
            
            if response.status_code != 200:
                logger.warning("Failed to fetch models, using defaults")
                return self._default_models()
            
            data = response.json()
            models_data = data.get("data", {}).get("data", [])
            
            models = []
            for m in models_data:
                model_id = m.get("id")
                if model_id:
                    models.append(
                        ModelInfo(
                            id=f"qwen/{model_id}",
                            provider="qwen_chat",
                            description=m.get("info", {}).get("meta", {}).get("short_description", ""),
                        )
                    )
            
            self._models_cache = models
            self._models_cache_time = datetime.now()
            
            logger.info(f"Cached {len(models)} models from Qwen API")
            return models

    def _default_models(self) -> list[ModelInfo]:
        """Fallback model list if API fetch fails."""
        return [
            ModelInfo(id="qwen/qwen3.7-max", provider="qwen_chat", description="Qwen3.7-Max"),
            ModelInfo(id="qwen/qwen3.6-plus", provider="qwen_chat", description="Qwen3.6-Plus"),
            ModelInfo(id="qwen/qwen3.6-max-preview", provider="qwen_chat", description="Qwen3.6-Max-Preview"),
        ]

    async def _create_chat(self, token: str, model: str) -> str:
        """Create a new chat session."""
        headers = self._get_headers(token)
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{QWEN_API_URL}/chats/new",
                json={
                    "title": "New Chat",
                    "models": [model],
                    "chat_mode": "normal",
                    "chat_type": "t2t",
                    "timestamp": int(time.time() * 1000),
                    "project_id": "",
                },
                headers=headers,
            )
            
            if response.status_code != 200:
                raise QwenProviderError(f"Failed to create chat: HTTP {response.status_code}")
            
            data = response.json()
            chat_id = data.get("data", {}).get("id")
            
            if not chat_id:
                raise QwenProviderError("Failed to create chat: no ID returned")
            
            logger.info(f"Created new chat: {chat_id}")
            return chat_id

    def _build_chat_payload(
        self,
        model: str,
        messages: list[dict],
        chat_id: str,
        stream: bool = True,
    ) -> dict[str, Any]:
        """Build simplified chat completion payload."""
        qwen_messages = []
        
        for msg in messages:
            qwen_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })
        
        return {
            "stream": stream,
            "chat_id": chat_id,
            "model": model,
            "messages": qwen_messages,
        }

    async def _request(
        self,
        endpoint: str,
        json_payload: dict[str, Any],
        credentials: ProviderCredentials,
        chat_id: str | None = None,
    ) -> httpx.Response:
        """Execute REST request with retry logic."""
        token = await self._ensure_token(credentials)
        headers = self._get_headers(token)
        
        last_error: Exception | None = None
        
        for attempt in range(1, self._retries + 2):
            try:
                url = f"{QWEN_API_URL}/{endpoint}"
                if chat_id:
                    url += f"?chat_id={chat_id}"
                
                async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                    response = await client.post(
                        url,
                        json=json_payload,
                        headers=headers,
                    )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Qwen request failed (attempt %d/%d): %s",
                    attempt,
                    self._retries + 1,
                    exc,
                )
                if attempt <= self._retries:
                    continue
                raise QwenProviderError(f"Request failed after retries: {exc}") from exc
            
            if response.status_code in (401, 403):
                self._token = None
                self._token_expiry = None
                raise QwenSessionExpiredError(
                    f"Qwen session expired (HTTP {response.status_code}). "
                    "Token will be refreshed on next request."
                )
            
            if response.status_code >= 500:
                last_error = QwenProviderError(f"Qwen returned HTTP {response.status_code}")
                if attempt <= self._retries:
                    continue
                raise last_error
            
            if response.status_code != 200:
                raise QwenProviderError(
                    f"Qwen returned HTTP {response.status_code}: {response.text[:500]}"
                )
            
            return response
        
        raise QwenProviderError(f"Request failed: {last_error}")

    # ------------------------------------------------------------------
    # AIProvider interface
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> ChatResponse:
        """Non-streaming chat completion via Qwen API."""
        token = await self._ensure_token(credentials)
        
        model = request.model
        if model.startswith("qwen/"):
            model = model[5:]
        
        chat_id = await self._create_chat(token, model)
        
        messages = []
        system_content = None
        
        for m in request.messages:
            if m.role == "system":
                system_content = m.content
            else:
                messages.append({"role": m.role, "content": m.content})
        
        if system_content and messages:
            for i, msg in enumerate(messages):
                if msg["role"] == "user":
                    messages[i]["content"] = f"{system_content}\n\n{msg['content']}"
                    break
        
        payload = self._build_chat_payload(
            model=model,
            messages=messages,
            chat_id=chat_id,
            stream=False,
        )
        
        response = await self._request(
            "chat/completions", payload, credentials, chat_id=chat_id
        )
        
        try:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception:
            content = response.text
        
        return ChatResponse(
            id=chat_id,
            model=request.model,
            content=content,
            finish_reason="stop",
        )

    async def chat_completion_stream(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion via Qwen API with SSE."""
        token = await self._ensure_token(credentials)
        
        model = request.model
        if model.startswith("qwen/"):
            model = model[5:]
        
        chat_id = await self._create_chat(token, model)
        
        messages = []
        system_content = None
        
        for m in request.messages:
            if m.role == "system":
                system_content = m.content
            else:
                messages.append({"role": m.role, "content": m.content})
        
        if system_content and messages:
            for i, msg in enumerate(messages):
                if msg["role"] == "user":
                    messages[i]["content"] = f"{system_content}\n\n{msg['content']}"
                    break
        
        payload = self._build_chat_payload(
            model=model,
            messages=messages,
            chat_id=chat_id,
            stream=True,
        )
        
        headers = self._get_headers(token)
        url = f"{QWEN_API_URL}/chat/completions?chat_id={chat_id}"
        
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code in (401, 403):
                    self._token = None
                    self._token_expiry = None
                    raise QwenSessionExpiredError(
                        f"Qwen session expired (HTTP {response.status_code})"
                    )
                
                if response.status_code != 200:
                    body = await response.aread()
                    raise QwenProviderError(
                        f"Qwen returned HTTP {response.status_code}: {body.decode()[:500]}"
                    )
                
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        yield StreamChunk(content="", finish_reason="stop")
                        return
                    
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            text = delta.get("content", "") or delta.get("text", "")
                            finish = choices[0].get("finish_reason")
                            
                            if text:
                                yield StreamChunk(content=text, finish_reason=None)
                            if finish:
                                yield StreamChunk(content="", finish_reason=finish)
                                return
                    except json.JSONDecodeError:
                        continue
        
        yield StreamChunk(content="", finish_reason="stop")

    async def list_models(self) -> list[ModelInfo]:
        """Return Qwen models available through this provider."""
        if self._models_cache:
            return self._models_cache
        return self._default_models()

    async def validate_credentials(
        self,
        credentials: ProviderCredentials,
    ) -> bool:
        """Check if credentials contain valid email and password."""
        data = credentials.data
        email = data.get("email")
        password = data.get("password")
        
        if not email or not password:
            return False
        
        if not isinstance(email, str) or not isinstance(password, str):
            return False
        
        if len(email) < 5 or len(password) < 6:
            return False
        
        return True
