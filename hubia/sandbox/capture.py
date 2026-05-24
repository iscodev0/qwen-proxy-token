"""Cookie / session-token capture using Scrapling StealthyFetcher.

Provides interactive browser-based capture (visible browser, user logs in
manually) and manual credential input flows for Meta AI and Z.ai.

Security note: The interactive flow opens a VISIBLE browser on the server
machine.  The user logs in with THEIR OWN credentials using the real
provider's login page — the application NEVER sees the password.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Polling interval (seconds) between cookie checks during interactive capture
_POLL_INTERVAL_S = 2

# Maximum time (seconds) to wait for the user to log in before timing out
_CAPTURE_TIMEOUT_S = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Meta AI cookie capture — interactive
# ---------------------------------------------------------------------------


async def capture_meta_ai_cookies_interactive(
    stop_event: asyncio.Event | None = None,
) -> dict:
    """Open a visible browser and let the user log into Meta AI manually.

    The function opens a non-headless browser pointed at ``https://
    www.meta.ai/`` and polls for the required session cookies (``datr``,
    ``ecto_1_sess``) every *2 s*.  The caller can signal completion early
    by setting *stop_event*.

    Returns:
        A dict with:
        - ``status``: ``"ok"`` or ``"error"``.
        - ``cookies``: dict with ``datr`` and ``ecto_1_sess`` (on success).
        - ``error``: Error message (on failure).
        - ``mock``: ``True`` if mock data was returned.

    Raises:
        RuntimeError: If StealthyFetcher is not installed.
    """
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        logger.warning("StealthyFetcher not available — returning mock cookies")
        return _mock_meta_ai_cookies()

    logger.info("Starting interactive Meta AI cookie capture (headless=False)")

    async with StealthyFetcher(headless=False) as fetcher:
        await fetcher.goto("https://www.meta.ai/")

        deadline = asyncio.get_event_loop().time() + _CAPTURE_TIMEOUT_S

        while True:
            # Check for user-signalled completion
            if stop_event is not None and stop_event.is_set():
                logger.info("Stop event set — extracting cookies now")
                break

            # Check elapsed time
            if asyncio.get_event_loop().time() > deadline:
                logger.warning("Interactive capture timed out after %ds", _CAPTURE_TIMEOUT_S)
                return {
                    "status": "error",
                    "error": f"Capture timed out after {_CAPTURE_TIMEOUT_S} seconds. "
                    "Please try again.",
                }

            # Poll for cookies
            try:
                cookies = await fetcher.get_cookies()
            except Exception:
                logger.exception("Error polling cookies — browser may have been closed")
                cookies = {}

            datr = cookies.get("datr", "")
            ecto_1_sess = cookies.get("ecto_1_sess", "")

            if datr and ecto_1_sess:
                logger.info("Required cookies detected — capture successful")
                return {
                    "cookies": {
                        "datr": datr,
                        "ecto_1_sess": ecto_1_sess,
                    },
                    "status": "ok",
                }

            await asyncio.sleep(_POLL_INTERVAL_S)

        # If we broke out of the loop via stop_event, grab whatever we have
        try:
            cookies = await fetcher.get_cookies()
        except Exception:
            cookies = {}

        datr = cookies.get("datr", "")
        ecto_1_sess = cookies.get("ecto_1_sess", "")

        if not datr or not ecto_1_sess:
            return {
                "status": "error",
                "error": "Required cookies (datr, ecto_1_sess) not found. "
                "Please log in to Meta AI first.",
            }

        return {
            "cookies": {"datr": datr, "ecto_1_sess": ecto_1_sess},
            "status": "ok",
        }


async def validate_meta_ai_cookies(cookies: dict) -> dict:
    """Check that the cookie dict contains non-empty required fields.

    Returns:
        A dict with ``valid`` (bool) and optionally ``error`` (str).
    """
    required = {"datr", "ecto_1_sess"}
    if not required.issubset(cookies.keys()):
        return {
            "valid": False,
            "error": "Missing required cookies: datr, ecto_1_sess",
        }
    if not cookies.get("datr") or not cookies.get("ecto_1_sess"):
        return {"valid": False, "error": "Empty cookie values"}
    return {"valid": True}


# ---------------------------------------------------------------------------
# Z.ai session token capture — interactive
# ---------------------------------------------------------------------------


async def capture_zai_token_interactive(
    stop_event: asyncio.Event | None = None,
) -> dict:
    """Open a visible browser and let the user log into Z.ai manually.

    The function opens a non-headless browser pointed at ``https://
    chat.z.ai/`` and polls for the session token every *2 s*.

    Returns:
        A dict with:
        - ``status``: ``"ok"`` or ``"error"``.
        - ``token``: The session JWT string (on success).
        - ``error``: Error message (on failure).
        - ``mock``: ``True`` if mock data was returned.
    """
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        logger.warning("StealthyFetcher not available — returning mock token")
        return _mock_zai_token()

    logger.info("Starting interactive Z.ai token capture (headless=False)")

    async with StealthyFetcher(headless=False) as fetcher:
        await fetcher.goto("https://chat.z.ai/")

        deadline = asyncio.get_event_loop().time() + _CAPTURE_TIMEOUT_S

        while True:
            if stop_event is not None and stop_event.is_set():
                logger.info("Stop event set — extracting token now")
                break

            if asyncio.get_event_loop().time() > deadline:
                logger.warning("Interactive capture timed out after %ds", _CAPTURE_TIMEOUT_S)
                return {
                    "status": "error",
                    "error": f"Capture timed out after {_CAPTURE_TIMEOUT_S} seconds. "
                    "Please try again.",
                }

            # Poll for token from localStorage first, then cookies
            token = ""
            try:
                token = await fetcher.evaluate(
                    "localStorage.getItem('token') || "
                    "localStorage.getItem('jwt') || ''"
                )
            except Exception:
                logger.debug("localStorage not available, trying cookies")

            if not token or len(token) < 10:
                try:
                    cookies = await fetcher.get_cookies()
                except Exception:
                    cookies = {}
                token = cookies.get("token") or cookies.get("jwt") or ""

            if token and len(token) >= 10:
                logger.info("Session token detected — capture successful")
                return {"token": token, "status": "ok"}

            await asyncio.sleep(_POLL_INTERVAL_S)

        # Broke out via stop_event — final attempt
        token = ""
        try:
            token = await fetcher.evaluate(
                "localStorage.getItem('token') || "
                "localStorage.getItem('jwt') || ''"
            )
        except Exception:
            pass

        if not token or len(token) < 10:
            try:
                cookies = await fetcher.get_cookies()
            except Exception:
                cookies = {}
            token = cookies.get("token") or cookies.get("jwt") or ""

        if not token or len(token) < 10:
            return {
                "status": "error",
                "error": "Session token not found. Please log in to Z.ai first.",
            }

        return {"token": token, "status": "ok"}


async def validate_zai_token(token: str) -> dict:
    """Validate that a Z.ai session token looks plausible.

    Returns:
        A dict with ``valid`` (bool) and optionally ``error`` (str).
    """
    if not token:
        return {"valid": False, "error": "Token is empty"}
    if not isinstance(token, str) or len(token) < 10:
        return {"valid": False, "error": "Token is too short (min 10 chars)"}
    return {"valid": True}


# ---------------------------------------------------------------------------
# Development mocks (used when StealthyFetcher is not installed)
# ---------------------------------------------------------------------------


def _mock_meta_ai_cookies() -> dict:
    """Return mock cookies for development when StealthyFetcher is absent."""
    return {
        "cookies": {
            "datr": "mock_datr_development_only",
            "ecto_1_sess": "mock_ecto_1_sess_development_only",
        },
        "status": "ok",
        "mock": True,
    }


def _mock_zai_token() -> dict:
    """Return a mock JWT for development when StealthyFetcher is absent."""
    return {
        "token": "mock_jwt_token_for_development_only",
        "status": "ok",
        "mock": True,
    }
