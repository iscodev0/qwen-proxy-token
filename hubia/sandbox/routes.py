"""Sandbox routes — credential capture HTML interface and API endpoints.

Provides:
- HTML UI for interactive browser-based cookie capture
- REST API for starting/checking/stopping capture sessions
- Manual cookie/token input endpoints
- Credential listing and deletion

Only Qwen provider is supported.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from hubia.api.auth import get_current_user
from hubia.sandbox.capture import (
    capture_qwen_cookies_interactive,
    validate_qwen_cookies,
)
from hubia.store.credentials import (
    delete_credential,
    get_credential,
    list_credentials,
    store_credential,
)
from hubia.store.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])
templates = Jinja2Templates(directory="hubia/sandbox/templates")


# ---------------------------------------------------------------------------
# In-memory capture state management
# ---------------------------------------------------------------------------


@dataclass
class CaptureState:
    """Tracks an interactive browser capture session."""

    capture_id: str
    provider: str  # "qwen_chat"
    status: str = "pending"  # pending | capturing | ok | error
    result: dict | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


# Global capture state store — keyed by capture_id
_capture_states: dict[str, CaptureState] = {}


def _run_capture_background(state: CaptureState, db: aiosqlite.Connection, user_id: int) -> None:
    """Launch the interactive capture as a background task.

    When the capture completes (ok or error), the result is automatically
    persisted to the database.
    """

    async def _capture_task():
        try:
            if state.provider == "qwen_chat":
                result = await capture_qwen_cookies_interactive(state.stop_event)
            else:
                state.status = "error"
                state.error = f"Unknown provider: {state.provider}"
                return

            if result.get("status") == "ok":
                state.status = "ok"
                state.result = result
                # Persist to database
                cred_data = {"cookies": result["cookies"]}
                await store_credential(db, user_id, state.provider, cred_data)
            else:
                state.status = "error"
                state.error = result.get("error", "Capture failed")
        except Exception as exc:
            logger.exception("Capture background task failed")
            state.status = "error"
            state.error = str(exc)

    state.task = asyncio.create_task(_capture_task())


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class QwenCaptureRequest(BaseModel):
    """Manual cookies input for Qwen."""

    cookies: dict = Field(
        ...,
        description="All cookies from chat.qwen.ai (token, acw_tc, aui, cna, etc.)",
    )


class CaptureStartResponse(BaseModel):
    """Response returned after starting an interactive capture."""

    capture_id: str
    status: str = "started"
    message: str


class CaptureStatusResponse(BaseModel):
    """Status of an interactive capture session."""

    capture_id: str
    status: str  # pending | capturing | ok | error
    error: str | None = None


# ---------------------------------------------------------------------------
# GET /sandbox — HTML UI
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def sandbox_page(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Serve the sandbox HTML interface for credential management.

    The page shows the current user's stored credentials status and provides
    forms for capturing Qwen cookies.
    """
    creds = await list_credentials(db, current_user["id"])

    # Build status per provider
    qwen_status: str = "none"
    for c in creds:
        if c["provider"] == "qwen_chat":
            qwen_status = "stored"

    return templates.TemplateResponse(
        request,
        "sandbox.html",
        {
            "user": current_user,
            "qwen_status": qwen_status,
        },
    )


# ---------------------------------------------------------------------------
# POST /sandbox/qwen/capture — Manual cookies input
# ---------------------------------------------------------------------------


@router.post("/qwen/capture")
async def capture_qwen(
    body: QwenCaptureRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Store Qwen cookies provided manually by the user.

    Use this endpoint when the user copies all cookies from the
    browser's DevTools (Application → Cookies → chat.qwen.ai).
    """
    validation = await validate_qwen_cookies(body.cookies)
    if not validation["valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation.get("error", "Invalid cookies"),
        )

    cred_data = {"cookies": body.cookies}
    stored = await store_credential(db, current_user["id"], "qwen_chat", cred_data)
    return {
        "status": "ok",
        "credential_id": stored["id"] if stored else None,
    }


# ---------------------------------------------------------------------------
# POST /sandbox/qwen/capture/start — Interactive browser capture
# ---------------------------------------------------------------------------


@router.post("/qwen/capture/start")
async def start_qwen_capture(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Start an interactive browser-based cookie capture for Qwen.

    Opens a visible browser on the server.  The user should log in to Qwen
    manually in that browser.  Poll the ``status`` endpoint to check progress
    or call the ``done`` endpoint to signal completion.
    """
    capture_id = uuid.uuid4().hex[:12]
    state = CaptureState(
        capture_id=capture_id,
        provider="qwen_chat",
    )
    _capture_states[capture_id] = state

    _run_capture_background(state, db, current_user["id"])

    return CaptureStartResponse(
        capture_id=capture_id,
        status="started",
        message="Interactive capture started. A browser window should open on the server. "
        "Log in to Qwen manually, then call the /done endpoint or wait for auto-detection.",
    )


# ---------------------------------------------------------------------------
# GET /sandbox/qwen/capture/{capture_id}/status
# ---------------------------------------------------------------------------


@router.get("/qwen/capture/{capture_id}/status")
async def check_qwen_capture_status(
    capture_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Check the status of an interactive Qwen capture session."""
    state = _capture_states.get(capture_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Capture session not found",
        )

    return CaptureStatusResponse(
        capture_id=capture_id,
        status=state.status,
        error=state.error,
    )


# ---------------------------------------------------------------------------
# POST /sandbox/qwen/capture/{capture_id}/done
# ---------------------------------------------------------------------------


@router.post("/qwen/capture/{capture_id}/done")
async def signal_qwen_capture_done(
    capture_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Signal that the user has finished logging in and cookies should be extracted."""
    state = _capture_states.get(capture_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Capture session not found",
        )

    if state.status != "pending":
        return {
            "status": "acknowledged",
            "capture_status": state.status,
        }

    state.stop_event.set()
    return {
        "status": "acknowledged",
        "message": "Done signal sent. Cookies will be extracted.",
    }


# ---------------------------------------------------------------------------
# GET /sandbox/credentials — list stored credentials
# ---------------------------------------------------------------------------


@router.get("/credentials")
async def list_user_credentials(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """List metadata for all stored credentials belonging to the current user.

    Returns provider, creation time, and expiry (no decrypted data).
    """
    creds = await list_credentials(db, current_user["id"])
    return {"credentials": creds}


# ---------------------------------------------------------------------------
# DELETE /sandbox/credentials/{provider}
# ---------------------------------------------------------------------------


@router.delete("/credentials/{provider}")
async def delete_user_credential(
    provider: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Delete stored credentials for a specific provider.

    Args:
        provider: Provider name (e.g. ``"qwen_chat"``).
    """
    deleted = await delete_credential(db, current_user["id"], provider)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credentials found for provider '{provider}'",
        )
    return {"status": "ok", "deleted": True}
