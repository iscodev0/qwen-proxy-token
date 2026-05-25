"""Meta AI provider — using Playwright for browser automation.

Note: Scrapling was evaluated but it's designed for scraping (extracting data),
not for browser automation (typing, clicking, etc.). Meta AI requires real
browser interaction, so we use Playwright directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from playwright.async_api import async_playwright

from hubia.config import settings
from hubia.core.provider import (
    AIProvider,
    ChatMessage,
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
    """Raised when Meta AI credentials (cookies) are stale or expired."""


class ProviderError(Exception):
    """Raised on upstream API errors after retries are exhausted."""


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class MetaAIProvider(AIProvider):
    """Provider for Meta AI using Playwright browser automation.

    Uses Playwright to interact with Meta AI through a headless browser.
    Meta AI requires real browser interaction (typing, clicking), which
    cannot be done with HTTP requests alone.

    Credentials must contain ``datr`` and ``ecto_1_sess`` cookies.
    """

    def __init__(self, timeout: int = 30) -> None:
        self._timeout = timeout
        self._browser = None
        self._playwright = None

    # ------------------------------------------------------------------
    # Browser management
    # ------------------------------------------------------------------

    async def _ensure_browser(self):
        """Ensure browser is launched."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            logger.info("Playwright browser launched")

    async def _cleanup(self):
        """Cleanup browser resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            logger.info("Playwright browser closed")

    # ------------------------------------------------------------------
    # Chat interaction
    # ------------------------------------------------------------------

    async def _send_message_and_get_response(
        self,
        credentials: ProviderCredentials,
        message: str,
    ) -> str:
        """Send a message to Meta AI and extract the response using Playwright."""
        try:
            await self._ensure_browser()
            
            logger.info(f"Sending message to Meta AI: {message[:50]}...")
            
            # Convert cookies dict to list format expected by Playwright
            cookies_list = [
                {'name': name, 'value': value, 'domain': '.meta.ai', 'path': '/'}
                for name, value in credentials.data.items()
            ]
            
            # Create a new context with cookies
            context = await self._browser.new_context()
            await context.add_cookies(cookies_list)
            
            # Create a new page
            page = await context.new_page()
            
            try:
                # Navigate to Meta AI
                await page.goto('https://www.meta.ai/', wait_until='networkidle', timeout=self._timeout * 1000)
                
                # Check if we're logged in
                if 'login' in page.url.lower():
                    raise SessionExpiredError("Session expired or invalid cookies - redirected to login")
                
                # Find and interact with the chat input
                # Look for the textarea with placeholder containing "Ask"
                textarea = await page.query_selector('textarea[placeholder*="Ask"]')
                if not textarea:
                    # Try alternative selectors
                    textarea = await page.query_selector('[role="textbox"]')
                
                if not textarea:
                    logger.error("Could not find chat input")
                    raise ProviderError("Could not find chat input on Meta AI page")
                
                # Type the message
                logger.info("Typing message...")
                await textarea.type(message, delay=10)
                await asyncio.sleep(0.5)
                
                # Take screenshot before sending
                await page.screenshot(path='/tmp/meta_ai_before_send.png')
                logger.info("Screenshot saved: /tmp/meta_ai_before_send.png")
                
                # Press Enter to send
                logger.info("Pressing Enter to send...")
                await textarea.press('Enter')
                logger.info("Enter pressed")
                
                # Wait for response to appear
                logger.info("Waiting for response...")
                await asyncio.sleep(3)
                
                # Take screenshot after sending
                try:
                    await page.screenshot(path='/tmp/meta_ai_after_send.png')
                    logger.info("Screenshot saved: /tmp/meta_ai_after_send.png")
                except Exception as e:
                    logger.error(f"Failed to take after_send screenshot: {e}")
                
                # Log current URL to see if we navigated
                logger.info(f"Current URL: {page.url}")
                
                # Poll for the response
                max_attempts = 30
                for attempt in range(max_attempts):
                    # Look for assistant messages
                    messages = await page.query_selector_all('[data-testid="assistant-message"]')
                    if not messages:
                        messages = await page.query_selector_all('[data-testid="message-text"]')
                    if not messages:
                        messages = await page.query_selector_all('[role="article"]')
                    
                    logger.info(f"Attempt {attempt}: Found {len(messages)} message elements")
                    
                    if messages:
                        # Get all message texts
                        all_texts = []
                        for msg in messages:
                            text = await msg.inner_text()
                            text = text.strip()
                            if text:
                                all_texts.append(text)
                                logger.debug(f"  Message text: {text[:100]}...")
                        
                        logger.info(f"Attempt {attempt}: Extracted {len(all_texts)} text messages")
                        if all_texts:
                            # Log first few messages for debugging
                            for i, text in enumerate(all_texts[:3]):
                                logger.info(f"  Message {i}: {text[:80]}...")
                        
                        if all_texts:
                            # Filter out status messages
                            status_indicators = [
                                "thinking", "finalizing", "generating", "processing", "working",
                                "providing", "preparing", "crafting", "answering", "responding",
                                "composing", "writing", "considering", "analyzing", "adding",
                                "creating", "searching", "finding", "looking", "checking",
                                "reviewing", "summarizing", "exploring", "investigating",
                                "simple", "math", "calculation", "arithmetic"
                            ]
                            
                            real_responses = []
                            for text in all_texts:
                                text_lower = text.lower()
                                is_status = any(status in text_lower for status in status_indicators)
                                is_too_short = len(text) < 30  # Increased from 20
                                words = text.split()
                                looks_real = len(words) >= 5 or any(p in text for p in ['.', '!', '?', ':'])
                                
                                # Additional check: if it's very short and has no punctuation, it's likely a status
                                if len(text) < 50 and not any(p in text for p in ['.', '!', '?', ':', ',']):
                                    is_status = True
                                
                                if not is_status and not is_too_short and looks_real:
                                    real_responses.append(text)
                            
                            if real_responses:
                                response_text = real_responses[-1]
                                logger.info(f"Extracted response (attempt {attempt}): {response_text[:100]}...")
                                return response_text
                    
                    await asyncio.sleep(0.8)
                
                logger.warning("Timeout waiting for response")
                return "I couldn't extract a response from Meta AI within the timeout period."
            
            finally:
                # Always close the context
                await context.close()
            
        except SessionExpiredError:
            raise
        except ProviderError:
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "session" in error_msg or "login" in error_msg or "expired" in error_msg:
                raise SessionExpiredError(str(e)) from e
            raise ProviderError(f"Failed to interact with Meta AI: {e}") from e

    # ------------------------------------------------------------------
    # AIProvider interface
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> ChatResponse:
        """Non‑streaming chat completion via Meta AI with Playwright."""
        # Extract the last user message
        message = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                message = msg.content
                break
        if not message and request.messages:
            message = request.messages[-1].content
        
        # Send message and get response
        response_text = await self._send_message_and_get_response(credentials, message)
        
        return ChatResponse(
            id=str(uuid.uuid4()),
            model=request.model,
            content=response_text,
            finish_reason="stop",
        )

    async def chat_completion_stream(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion via Meta AI with Playwright.
        
        Note: This is a simplified implementation that yields the full response
        as chunks. True streaming would require monitoring DOM changes in real-time.
        """
        # Get the full response
        response = await self.chat_completion(request, credentials)
        
        # Split into smaller chunks for streaming effect
        words = response.content.split()
        chunk_size = 5
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)
            if i > 0:
                chunk_text = ' ' + chunk_text
            yield StreamChunk(content=chunk_text, finish_reason=None)
        
        # Final chunk
        yield StreamChunk(content="", finish_reason="stop")

    async def list_models(self) -> list[ModelInfo]:
        """Return Meta AI models configured for this instance."""
        models: list[ModelInfo] = []
        for name in settings.meta_ai_doc_ids.keys():
            models.append(
                ModelInfo(
                    id=f"meta-ai/{name}",
                    provider="meta_ai",
                    description=f"Meta AI {name} model (Muse Spark via Playwright)",
                )
            )
        return models

    async def validate_credentials(
        self,
        credentials: ProviderCredentials,
    ) -> bool:
        """Check if cookies contain the required fields and are valid."""
        data = credentials.data
        required = {"datr", "ecto_1_sess"}
        if not required.issubset(data.keys()):
            return False
        if not data.get("datr") or not data.get("ecto_1_sess"):
            return False
        
        # Try to load the page to validate
        try:
            await self._ensure_browser()
            
            # Convert cookies dict to list format expected by Playwright
            cookies_list = [
                {'name': name, 'value': value, 'domain': '.meta.ai', 'path': '/'}
                for name, value in data.items()
            ]
            
            context = await self._browser.new_context()
            await context.add_cookies(cookies_list)
            page = await context.new_page()
            
            try:
                await page.goto('https://www.meta.ai/', wait_until='domcontentloaded', timeout=10000)
                # If we're not redirected to login, cookies are valid
                return 'login' not in page.url.lower()
            finally:
                await context.close()
        except Exception as e:
            logger.error(f"Credential validation failed: {e}")
            return False

    def __del__(self):
        """Cleanup on deletion."""
        # Note: This is a best-effort cleanup. For proper cleanup, use async context manager.
        if self._browser:
            try:
                asyncio.run(self._cleanup())
            except Exception:
                pass
