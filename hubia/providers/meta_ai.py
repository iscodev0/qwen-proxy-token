"""Meta AI provider — using Playwright for reliable browser automation."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

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

    Uses a real browser (Chromium) to interact with Meta AI, which is more
    reliable than HTTP requests because Meta's anti-bot detection is bypassed.

    Credentials must contain ``datr`` and ``ecto_1_sess`` cookies.
    
    OPTIMIZATIONS:
    - Persistent browser instance (reused across requests)
    - Persistent context with user profile
    - Optimized selectors and waits
    """

    _shared_browser = None
    _shared_context = None
    _shared_page = None
    _lock = asyncio.Lock()

    def __init__(self, headless: bool = True, timeout: int = 60) -> None:
        self._headless = headless
        self._timeout = timeout * 1000  # Convert to milliseconds
        self._browser = None
        self._context = None

    # ------------------------------------------------------------------
    # Browser management (OPTIMIZED - shared instance)
    # ------------------------------------------------------------------

    @classmethod
    async def _get_shared_browser(cls, headless: bool = True) -> Any:
        """Get or create a shared Playwright browser instance."""
        async with cls._lock:
            if cls._shared_browser is None:
                from playwright.async_api import async_playwright
                
                cls._playwright = await async_playwright().start()
                cls._shared_browser = await cls._playwright.chromium.launch(
                    headless=headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                    ]
                )
                logger.info("Launched shared Playwright browser (headless=%s)", headless)
            
            return cls._shared_browser

    @classmethod
    async def _get_shared_context(cls, credentials: ProviderCredentials, headless: bool = True) -> Any:
        """Create a browser context with the provided cookies (reuses browser)."""
        browser = await cls._get_shared_browser(headless)
        
        # Convert cookies dict to Playwright format
        cookies_list = []
        for name, value in credentials.data.items():
            cookies_list.append({
                'name': name,
                'value': value,
                'domain': '.meta.ai',
                'path': '/',
            })
        
        # Create new context with cookies (each user gets their own context)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        await context.add_cookies(cookies_list)
        
        return context

    @classmethod
    async def cleanup_shared_browser(cls) -> None:
        """Close the shared browser instance."""
        async with cls._lock:
            if cls._shared_context:
                await cls._shared_context.close()
                cls._shared_context = None
            if cls._shared_browser:
                await cls._shared_browser.close()
                cls._shared_browser = None
            if hasattr(cls, '_playwright') and cls._playwright:
                await cls._playwright.stop()
                cls._playwright = None
            logger.info("Closed shared Playwright browser")

    async def _get_browser(self) -> Any:
        """Get or create a Playwright browser instance (uses shared instance)."""
        return await self._get_shared_browser(self._headless)

    async def _get_context(self, credentials: ProviderCredentials) -> Any:
        """Create a browser context with the provided cookies (uses shared browser)."""
        return await self._get_shared_context(credentials, self._headless)

    async def _cleanup(self) -> None:
        """Close browser and cleanup resources."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if hasattr(self, '_playwright') and self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ------------------------------------------------------------------
    # Chat interaction (OPTIMIZED)
    # ------------------------------------------------------------------

    async def _send_message_and_get_response(
        self,
        context: Any,
        message: str,
    ) -> str:
        """Send a message to Meta AI and extract the response (OPTIMIZED)."""
        page = await context.new_page()
        
        try:
            # Navigate to Meta AI (reduced timeout)
            logger.info("Navigating to meta.ai...")
            await page.goto('https://www.meta.ai/', timeout=30000, wait_until='domcontentloaded')
            
            # Wait for page to be interactive (shorter wait)
            await page.wait_for_timeout(2000)
            
            # Check if we're on a conversation page and need to start a new chat
            current_url = page.url
            if '/prompt/' in current_url or '/chat/' in current_url:
                logger.info("On conversation page, starting new chat...")
                # Look for "New chat" button
                new_chat_selectors = [
                    'button:has-text("New chat")',
                    'button[aria-label*="New chat"]',
                    'a[href="/"]',
                ]
                for selector in new_chat_selectors:
                    try:
                        btn = page.locator(selector).first
                        if await btn.count() > 0 and await btn.is_visible():
                            await btn.click()
                            await page.wait_for_timeout(1500)
                            logger.info(f"Clicked new chat button: {selector}")
                            break
                    except Exception:
                        continue
            
            # Find chat input quickly with optimized selectors
            chat_input = None
            selectors = [
                '[role="textbox"]',  # Most likely to be visible
                'textarea[data-testid="composer-input"]',
                'textarea[placeholder*="Ask"]',
            ]
            
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    count = await element.count()
                    if count > 0:
                        visible = await element.is_visible()
                        if visible:
                            chat_input = element
                            logger.info(f"Found visible chat input with selector: {selector}")
                            break
                        else:
                            # Try to make it visible
                            await element.scroll_into_view_if_needed(timeout=2000)
                            await page.wait_for_timeout(300)
                            if await element.is_visible():
                                chat_input = element
                                logger.info(f"Made chat input visible with selector: {selector}")
                                break
                except Exception:
                    continue
            
            if not chat_input:
                raise SessionExpiredError(
                    "Could not find chat input on Meta AI page. "
                    "Session may be expired or cookies are invalid."
                )
            
            # Fill and send message (optimized)
            logger.info(f"Sending message: {message[:50]}...")
            
            # Try clicking with force to avoid visibility issues
            try:
                await chat_input.click(force=True, timeout=5000)
                await page.wait_for_timeout(500)
                # Use type() instead of fill() for dynamic elements
                await chat_input.type(message, delay=10, timeout=10000)
            except Exception as e:
                logger.warning(f"Click/type failed, trying JavaScript: {e}")
                # Fallback: use JavaScript to set value and trigger events
                await page.evaluate(f'''(msg) => {{
                    const textarea = document.querySelector('textarea[placeholder*="Ask"]');
                    if (textarea) {{
                        textarea.value = msg;
                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}''', message)
                await page.wait_for_timeout(500)
            
            await page.wait_for_timeout(300)
            await chat_input.press('Enter')
            
            # Wait for response (optimized polling)
            logger.info("Waiting for response...")
            await page.wait_for_timeout(3000)  # Initial wait
            
            # Take screenshot after sending message
            try:
                await page.screenshot(path='/tmp/meta_ai_after_send.png')
                logger.debug("Screenshot saved: /tmp/meta_ai_after_send.png")
            except Exception:
                pass
            
            # Poll for response with shorter intervals
            max_attempts = 35
            for attempt in range(max_attempts):
                # Check if response is ready
                try:
                    response_selectors = [
                        '[data-testid="assistant-message"]',
                        '[data-testid="message-text"]',
                        '[role="article"]',
                    ]
                    
                    for selector in response_selectors:
                        messages = await page.locator(selector).all()
                        if messages:
                            # Get ALL messages and find the last real one
                            all_texts = []
                            for msg in messages:
                                try:
                                    text = await msg.inner_text()
                                    if text and text.strip():
                                        all_texts.append(text.strip())
                                except Exception:
                                    continue
                            
                            if all_texts:
                                # Filter out status messages
                                status_indicators = [
                                    "thinking", "finalizing", "generating", "processing", "working",
                                    "providing the answer", "preparing response", "crafting response",
                                    "answering", "responding", "composing", "writing response",
                                    "let me think", "considering", "analyzing", "adding", "creating",
                                    "searching", "finding", "looking up", "checking", "crafting",
                                    "reviewing", "summarizing", "exploring", "investigating"
                                ]
                                
                                real_responses = []
                                for text in all_texts:
                                    is_status = any(status in text.lower() for status in status_indicators)
                                    is_too_short = len(text) < 20
                                    words = text.split()
                                    looks_real = len(words) >= 4 or any(p in text for p in ['.', '!', '?'])
                                    
                                    if not is_status and not is_too_short and looks_real:
                                        real_responses.append(text)
                                
                                if real_responses:
                                    # Return the last real response
                                    response_text = real_responses[-1]
                                    logger.info(f"Extracted response with selector {selector} (attempt {attempt})")
                                    logger.debug(f"Filtered {len(all_texts)} messages, found {len(real_responses)} real responses")
                                    return response_text
                                else:
                                    # Log what was filtered for debugging
                                    if all_texts:
                                        sample = all_texts[0][:100] if all_texts[0] else ""
                                        logger.debug(f"Attempt {attempt}: Found {len(all_texts)} messages but all filtered out. Sample: '{sample}...'")
                except Exception as e:
                    logger.debug(f"Attempt {attempt}: Exception while checking response: {e}")
                
                # Take screenshot every 5 attempts for debugging
                if attempt % 5 == 0 and attempt > 0:
                    try:
                        await page.screenshot(path=f'/tmp/meta_ai_attempt_{attempt}.png')
                        logger.debug(f"Screenshot saved: /tmp/meta_ai_attempt_{attempt}.png")
                    except Exception:
                        pass
                
                # Wait before next attempt
                await page.wait_for_timeout(800)
            
            # Final screenshot before timeout
            try:
                await page.screenshot(path='/tmp/meta_ai_timeout.png')
                logger.warning("Timeout waiting for response. Screenshot: /tmp/meta_ai_timeout.png")
            except Exception:
                pass
            
            # If we get here, we didn't get a response
            return "I couldn't extract a response from Meta AI within the timeout period."
            
        except Exception as e:
            error_msg = str(e).lower()
            if "session" in error_msg or "login" in error_msg or "expired" in error_msg:
                raise SessionExpiredError(str(e)) from e
            raise ProviderError(f"Failed to interact with Meta AI: {e}") from e
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # AIProvider interface
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> ChatResponse:
        """Non‑streaming chat completion via Meta AI with Playwright."""
        context = await self._get_context(credentials)
        
        try:
            # Extract the last user message
            message = ""
            for msg in reversed(request.messages):
                if msg.role == "user":
                    message = msg.content
                    break
            if not message and request.messages:
                message = request.messages[-1].content
            
            # Send message and get response
            response_text = await self._send_message_and_get_response(context, message)
            
            return ChatResponse(
                id=str(uuid.uuid4()),
                model=request.model,
                content=response_text,
                finish_reason="stop",
            )
            
        finally:
            await context.close()

    async def chat_completion_stream(
        self,
        request: ChatRequest,
        credentials: ProviderCredentials,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion via Meta AI with Playwright.
        
        Note: This is a simplified implementation that yields the full response
        as a single chunk. True streaming would require monitoring DOM changes.
        """
        # For now, just get the full response and yield it
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
                    description=f"Meta AI {name} model (Llama 3 via Playwright)",
                )
            )
        return models

    async def validate_credentials(
        self,
        credentials: ProviderCredentials,
    ) -> bool:
        """Check if cookies contain the required fields."""
        data = credentials.data
        required = {"datr", "ecto_1_sess"}
        if not required.issubset(data.keys()):
            return False
        if not data.get("datr") or not data.get("ecto_1_sess"):
            return False
        return True

    def __del__(self) -> None:
        """Cleanup on deletion."""
        # Note: This is a best-effort cleanup. For proper cleanup, use async context manager.
        pass
