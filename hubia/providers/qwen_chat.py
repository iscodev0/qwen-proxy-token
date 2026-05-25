"""Qwen Chat provider — REST client using Scrapling Fetcher.

Authenticates via browser cookies to chat.qwen.ai.
Supports SSE streaming and non-streaming chat completion.

Features:
    - Automatic chat creation for each request
    - System prompt support (OpenAI-compatible)
    - Thinking/reasoning mode
    - Web search tool
    - Code interpreter tool
    - Multiple chat modes

Chat Management:
    The provider automatically creates a new chat for each request using
    the Qwen API endpoint POST /api/v2/chats/new. This ensures that each
    request uses the correct model and avoids context pollution.
    
    If you want to reuse an existing chat (e.g., for conversation continuity),
    set the QWEN_CHAT_ID environment variable with a valid chat_id from your account.
    
    To get a chat_id manually:
    1. Go to https://chat.qwen.ai/ and send any message
    2. Run: python get_chat_id.py
    3. Copy the chat_id and set: export QWEN_CHAT_ID="your-chat-id"

System Prompts:
    The provider supports OpenAI-compatible system prompts. If the first message
    in the request has role='system', it will be used as the system prompt for
    the conversation.
    
    Example:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"}
        ]

Tools and Features:
    Configure via environment variables:
    
    - QWEN_CHAT_MODE: Chat mode ("normal", "thinking", "search", "code")
    - QWEN_ENABLE_THINKING: Enable thinking/reasoning (default: "true")
    - QWEN_ENABLE_SEARCH: Enable web search tool (default: "false")
    - QWEN_ENABLE_CODE_INTERPRETER: Enable code interpreter (default: "false")
    
    Example:
        export QWEN_ENABLE_SEARCH="true"
        export QWEN_CHAT_MODE="search"
"""

from __future__ import annotations

import json
import logging
import os
import time
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


class QwenSessionExpiredError(Exception):
    """Raised when the Qwen session cookies are expired."""


class QwenProviderError(Exception):
    """Raised on upstream API errors after retries are exhausted."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QWEN_BASE_URL = "https://chat.qwen.ai"
QWEN_API_URL = f"{QWEN_BASE_URL}/api/v2"

# Local model ID → Qwen internal model parameter mapping
MODEL_MAP: dict[str, str] = {
    "qwen3.7-max": "qwen3.7-max",
    "qwen3.6-plus": "qwen3.6-plus",
    "qwen3.6-max-preview": "qwen3.6-max-preview",
}

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/event-stream, application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": QWEN_BASE_URL,
    "Referer": f"{QWEN_BASE_URL}/",
}


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class QwenChatProvider(AIProvider):
    """Provider for Qwen's web chat API.

    Uses :class:`scrapling.fetchers.AsyncFetcher` for HTTP requests with
    TLS fingerprint impersonation.

    Credentials must contain a ``cookies`` dict with all browser cookies
    (token, acw_tc, aui, cna, etc.) for cookie-based authentication.
    """

    def __init__(self, retries: int = 2) -> None:
        self._retries = retries

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_cookie_header(cookies: dict) -> str:
        """Build Cookie header from cookies dict."""
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    @staticmethod
    def _get_cookies(credentials: ProviderCredentials) -> dict:
        """Extract cookies from credentials data."""
        data = credentials.data
        # Support both {cookies: {...}} and flat {token: ..., acw_tc: ...} formats
        if "cookies" in data and isinstance(data["cookies"], dict):
            return data["cookies"]
        # Flat format — all keys are cookies
        return {k: v for k, v in data.items() if isinstance(v, str)}

    @staticmethod
    def _build_model_list() -> list[ModelInfo]:
        models: list[ModelInfo] = []
        for model_id in MODEL_MAP:
            models.append(
                ModelInfo(
                    id=f"qwen/{model_id}",
                    provider="qwen_chat",
                    description=f"Qwen model: {model_id}",
                )
            )
        return models

    @staticmethod
    def _resolve_model(model_id: str) -> str:
        """Map a local model ID to Qwen's internal model parameter.

        Falls back to ``"qwen3.6-plus"`` when the model is not recognised.
        """
        return MODEL_MAP.get(model_id, "qwen3.6-plus")

    def _build_chat_payload(
        self,
        model: str,
        messages: list[dict],
        chat_id: str,
        stream: bool = True,
        system_prompt: str | None = None,
        enable_thinking: bool = True,
        enable_search: bool = False,
        enable_code_interpreter: bool = False,
        chat_mode: str = "normal",
    ) -> dict[str, Any]:
        """Build the Qwen chat completion payload.

        Based on reverse-engineered request format from chat.qwen.ai.
        
        Args:
            model: Model ID (e.g., "qwen3.7-max")
            messages: List of message dicts with 'role' and 'content'
            chat_id: Chat session ID
            stream: Whether to stream the response
            system_prompt: Optional system prompt to prepend
            enable_thinking: Enable thinking/reasoning mode
            enable_search: Enable web search tool
            enable_code_interpreter: Enable code interpreter tool
            chat_mode: Chat mode ("normal", "thinking", "search", "code")
        
        Returns:
            Formatted payload dict for Qwen API
        """
        # Build message objects with Qwen's expected structure
        qwen_messages = []
        parent_id = None
        
        # Add system prompt if provided
        if system_prompt:
            fid = str(uuid.uuid4())
            system_msg: dict[str, Any] = {
                "fid": fid,
                "parentId": None,
                "childrenIds": [],
                "role": "system",
                "content": system_prompt,
                "user_action": "system",
                "files": [],
                "timestamp": int(time.time()),
                "models": [],
                "chat_type": "t2t",
                "feature_config": self._build_feature_config(
                    enable_thinking, enable_search, enable_code_interpreter, chat_mode
                ),
                "extra": {"meta": {"subChatType": "t2t"}},
                "sub_chat_type": "t2t",
                "parent_id": None,
            }
            qwen_messages.append(system_msg)
            parent_id = fid

        # Process user and assistant messages
        for i, msg in enumerate(messages):
            fid = str(uuid.uuid4())
            next_fid = str(uuid.uuid4()) if i < len(messages) - 1 else None
            
            # Update parent's childrenIds
            if qwen_messages:
                qwen_messages[-1]["childrenIds"] = [fid]

            qwen_msg: dict[str, Any] = {
                "fid": fid,
                "parentId": parent_id,
                "childrenIds": [next_fid] if next_fid else [],
                "role": msg["role"],
                "content": msg["content"],
                "user_action": "chat" if msg["role"] == "user" else "assistant",
                "files": [],
                "timestamp": int(time.time()),
                "models": [model] if msg["role"] == "user" else [],
                "chat_type": "t2t",
                "feature_config": self._build_feature_config(
                    enable_thinking, enable_search, enable_code_interpreter, chat_mode
                ),
                "extra": {"meta": {"subChatType": "t2t"}},
                "sub_chat_type": "t2t",
                "parent_id": parent_id,
            }
            qwen_messages.append(qwen_msg)
            parent_id = fid

        # Build tools list based on enabled features
        tools = self._build_tools_list(enable_search, enable_code_interpreter)

        payload: dict[str, Any] = {
            "stream": stream,
            "version": "2.1",
            "incremental_output": True,
            "chat_id": chat_id,
            "chat_mode": chat_mode,
            "model": model,
            "parent_id": None,
            "messages": qwen_messages,
            "timestamp": int(time.time()),
        }
        
        # Add tools if any are enabled
        if tools:
            payload["tools"] = tools

        return payload
    
    def _build_feature_config(
        self,
        enable_thinking: bool,
        enable_search: bool,
        enable_code_interpreter: bool,
        chat_mode: str,
    ) -> dict[str, Any]:
        """Build feature configuration based on enabled tools.
        
        Args:
            enable_thinking: Enable thinking/reasoning mode
            enable_search: Enable web search
            enable_code_interpreter: Enable code interpreter
            chat_mode: Chat mode string
        
        Returns:
            Feature config dict
        """
        config = {
            "thinking_enabled": enable_thinking,
            "output_schema": "phase",
            "research_mode": "normal",
            "auto_thinking": enable_thinking,
            "thinking_mode": "Auto" if enable_thinking else "Off",
            "thinking_format": "summary",
            "auto_search": enable_search,
        }
        
        # Add tool-specific configs
        if enable_code_interpreter:
            config["code_interpreter_enabled"] = True
        
        return config
    
    def _build_tools_list(
        self,
        enable_search: bool,
        enable_code_interpreter: bool,
    ) -> list[dict[str, Any]]:
        """Build tools list for Qwen API.
        
        Args:
            enable_search: Enable web search tool
            enable_code_interpreter: Enable code interpreter tool
        
        Returns:
            List of tool definitions
        """
        tools = []
        
        if enable_search:
            tools.append({
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            }
                        },
                        "required": ["query"]
                    }
                }
            })
        
        if enable_code_interpreter:
            tools.append({
                "type": "function",
                "function": {
                    "name": "code_interpreter",
                    "description": "Execute Python code",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Python code to execute"
                            }
                        },
                        "required": ["code"]
                    }
                }
            })
        
        return tools

    async def _get_or_create_chat_id(
        self,
        credentials: ProviderCredentials,
        model: str = "qwen3.6-plus",
    ) -> str:
        """Create a new chat or get an existing one.
        
        This method automatically creates a new chat for each request using
        the Qwen API endpoint POST /api/v2/chats/new. This ensures that each
        request uses the correct model and avoids context pollution from
        previous conversations.
        
        Priority:
        1. QWEN_CHAT_ID environment variable (if set, reuses existing chat)
        2. Create a new chat via API (default behavior)
        3. Fall back to most recent chat if creation fails
        
        Args:
            credentials: User's Qwen cookies
            model: Model to use for the new chat (e.g., "qwen3.7-max")
        
        Returns:
            A valid chat_id to use for the request
        """
        # First, check if QWEN_CHAT_ID is set in environment
        env_chat_id = os.environ.get("QWEN_CHAT_ID")
        if env_chat_id:
            logger.info("Using QWEN_CHAT_ID from environment: %s", env_chat_id)
            return env_chat_id
        
        # Try to create a new chat
        from scrapling.fetchers import AsyncFetcher

        cookies = self._get_cookies(credentials)
        headers = dict(_DEFAULT_HEADERS)
        headers["Cookie"] = self._build_cookie_header(cookies)

        # Create new chat
        try:
            create_payload = {
                "title": "Nuevo Chat",
                "models": [model],
                "chat_mode": "normal",
                "chat_type": "t2t",
                "timestamp": int(time.time() * 1000),  # milliseconds
                "project_id": "",
            }
            
            response = await AsyncFetcher.post(
                f"{QWEN_API_URL}/chats/new",
                json=create_payload,
                headers=headers,
                impersonate="chrome131",
                timeout=30,
            )
            
            if response.status == 200:
                data = response.json()
                if data.get("success") and data.get("data", {}).get("id"):
                    chat_id = data["data"]["id"]
                    logger.info("Created new chat with id: %s", chat_id)
                    return chat_id
        except Exception as exc:
            logger.warning("Failed to create chat: %s", exc)

        # Fall back to listing existing chats
        try:
            response = await AsyncFetcher.get(
                f"{QWEN_API_URL}/chats/",
                headers=headers,
                impersonate="chrome131",
                timeout=30,
            )
            
            if response.status == 200:
                data = response.json()
                chats = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(chats, list) and chats:
                    chat_id = chats[0].get("id")
                    if chat_id:
                        logger.info("Using most recent chat_id: %s", chat_id)
                        return chat_id
        except Exception as exc:
            logger.warning("Failed to list chats: %s", exc)

        # No chats found and couldn't create one
        raise QwenProviderError(
            "Failed to create or find a chat.\n\n"
            "Please create a chat manually at https://chat.qwen.ai/ and set:\n"
            "export QWEN_CHAT_ID='your-chat-id'"
        )

    async def _request(
        self,
        endpoint: str,
        json_payload: dict[str, Any],
        credentials: ProviderCredentials,
        chat_id: str | None = None,
    ) -> Any:
        """Execute a REST request with retry logic using httpx for SSE support.

        Returns a response object with .status, .headers, and .text attributes.

        Raises:
            QwenSessionExpiredError: On HTTP 401 or 403 (expired cookies).
            QwenProviderError: On repeated failures.
        """
        import httpx

        cookies = self._get_cookies(credentials)
        headers = dict(_DEFAULT_HEADERS)
        headers["Cookie"] = self._build_cookie_header(cookies)

        last_error: Exception | None = None

        for attempt in range(1, self._retries + 2):
            try:
                # Build URL with query params if chat_id is present
                url = f"{QWEN_API_URL}/{endpoint}"
                if chat_id:
                    url += f"?chat_id={chat_id}"

                async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                    response = await client.post(
                        url,
                        json=json_payload,
                        headers=headers,
                        cookies=cookies,
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
                raise QwenProviderError(
                    f"Request failed after retries: {exc}"
                ) from exc

            if response.status_code in (401, 403):
                raise QwenSessionExpiredError(
                    "Qwen session expired (HTTP %d). "
                    "Please re-capture your cookies via /sandbox/qwen."
                    % response.status_code
                )

            if response.status_code >= 500:
                last_error = QwenProviderError(
                    f"Qwen returned HTTP {response.status_code}"
                )
                if attempt <= self._retries:
                    continue
                raise last_error

            if response.status_code != 200:
                raise QwenProviderError(
                    f"Qwen returned HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )

            # Wrap httpx response to match Scrapling interface
            class ResponseWrapper:
                def __init__(self, resp):
                    self.status = resp.status_code
                    self.headers = dict(resp.headers)
                    self.text = resp.text
                    
                def json(self):
                    return json.loads(self.text)
            
            return ResponseWrapper(response)

        raise QwenProviderError(f"Request failed: {last_error}")

    # ------------------------------------------------------------------
    # AIProvider interface
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> ChatResponse:
        """Non-streaming chat completion via Qwen API.

        Internally uses streaming and collects the full response.
        
        Supports system prompts: if the first message has role='system',
        it will be used as the system prompt for the conversation.
        """
        local_model = self._resolve_model(request.model)
        chat_id = await self._get_or_create_chat_id(credentials, local_model)

        # Extract system prompt if present
        system_prompt = None
        messages = []
        
        for m in request.messages:
            if m.role == "system":
                system_prompt = m.content
            else:
                messages.append({"role": m.role, "content": m.content})

        # Get chat mode from environment or default to "normal"
        chat_mode = os.environ.get("QWEN_CHAT_MODE", "normal")
        enable_thinking = os.environ.get("QWEN_ENABLE_THINKING", "true").lower() == "true"
        enable_search = os.environ.get("QWEN_ENABLE_SEARCH", "false").lower() == "true"
        enable_code_interpreter = os.environ.get("QWEN_ENABLE_CODE_INTERPRETER", "false").lower() == "true"

        payload = self._build_chat_payload(
            model=local_model,
            messages=messages,
            chat_id=chat_id,
            stream=True,  # Always use streaming
            system_prompt=system_prompt,
            enable_thinking=enable_thinking,
            enable_search=enable_search,
            enable_code_interpreter=enable_code_interpreter,
            chat_mode=chat_mode,
        )

        response = await self._request(
            "chat/completions", payload, credentials, chat_id=chat_id
        )

        # Parse SSE response and collect full content
        body_text = getattr(response, "text", "")
        full_content = self._parse_sse_response(body_text)

        return ChatResponse(
            id=chat_id,
            model=request.model,
            content=full_content,
            finish_reason="stop",
        )

    async def chat_completion_stream(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion via Qwen API.

        The upstream SSE stream is parsed and re-packaged as OpenAI SSE
        ``StreamChunk``\\ s.
        
        Supports system prompts: if the first message has role='system',
        it will be used as the system prompt for the conversation.
        """
        local_model = self._resolve_model(request.model)
        chat_id = await self._get_or_create_chat_id(credentials, local_model)

        # Extract system prompt if present
        system_prompt = None
        messages = []
        
        for m in request.messages:
            if m.role == "system":
                system_prompt = m.content
            else:
                messages.append({"role": m.role, "content": m.content})

        # Get chat mode from environment or default to "normal"
        chat_mode = os.environ.get("QWEN_CHAT_MODE", "normal")
        enable_thinking = os.environ.get("QWEN_ENABLE_THINKING", "true").lower() == "true"
        enable_search = os.environ.get("QWEN_ENABLE_SEARCH", "false").lower() == "true"
        enable_code_interpreter = os.environ.get("QWEN_ENABLE_CODE_INTERPRETER", "false").lower() == "true"

        payload = self._build_chat_payload(
            model=local_model,
            messages=messages,
            chat_id=chat_id,
            stream=True,
            system_prompt=system_prompt,
            enable_thinking=enable_thinking,
            enable_search=enable_search,
            enable_code_interpreter=enable_code_interpreter,
            chat_mode=chat_mode,
        )

        response = await self._request(
            "chat/completions", payload, credentials, chat_id=chat_id
        )

        body_text = getattr(response, "text", "")

        # Parse SSE and yield chunks
        for chunk in self._iter_sse_chunks(body_text):
            yield chunk

    def _parse_sse_response(self, body_text: str) -> str:
        """Parse SSE response and return full content."""
        content_parts = []

        for line in body_text.split("\n"):
            line = line.strip()
            if not line.startswith("data: "):
                continue

            data_str = line[6:]
            if data_str == "[DONE]":
                break

            try:
                data = json.loads(data_str)
                # Qwen SSE format: {"choices": [{"delta": {"content": "..."}}]}
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        content_parts.append(text)
            except json.JSONDecodeError:
                continue

        return "".join(content_parts)

    def _iter_sse_chunks(self, body_text: str) -> AsyncIterator[StreamChunk]:
        """Parse SSE response and yield StreamChunks."""
        for line in body_text.split("\n"):
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
                    text = delta.get("content", "")
                    finish = choices[0].get("finish_reason")
                    if text:
                        yield StreamChunk(content=text, finish_reason=None)
                    if finish:
                        yield StreamChunk(content="", finish_reason=finish)
                        return
            except json.JSONDecodeError:
                continue

        # If we get here without [DONE], yield stop
        yield StreamChunk(content="", finish_reason="stop")

    async def list_models(self) -> list[ModelInfo]:
        """Return Qwen models available through this provider."""
        return self._build_model_list()

    async def validate_credentials(
        self,
        credentials: ProviderCredentials,
    ) -> bool:
        """Check if credentials contain valid-looking cookies.

        Validates that the cookies dict has a 'token' field with reasonable length.
        """
        cookies = self._get_cookies(credentials)
        if not cookies:
            return False
        token = cookies.get("token", "")
        if not token or not isinstance(token, str) or len(token) < 20:
            return False
        return True
