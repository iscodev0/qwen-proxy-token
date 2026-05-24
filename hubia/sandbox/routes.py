"""Sandbox routes — credential capture HTML interface and API endpoints.

Provides:
- HTML UI for interactive browser-based cookie capture
- REST API for starting/checking/stopping capture sessions
- Manual cookie/token input endpoints
- Credential listing and deletion
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
    capture_meta_ai_cookies_interactive,
    capture_zai_token_interactive,
    validate_meta_ai_cookies,
    validate_zai_token,
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
    provider: str  # "meta_ai" or "zai_web"
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
            if state.provider == "meta_ai":
                result = await capture_meta_ai_cookies_interactive(state.stop_event)
            elif state.provider == "zai_web":
                result = await capture_zai_token_interactive(state.stop_event)
            else:
                state.status = "error"
                state.error = f"Unknown provider: {state.provider}"
                return

            if result.get("status") == "ok":
                state.status = "ok"
                state.result = result
                # Persist to database
                if state.provider == "meta_ai":
                    cred_data: dict = result["cookies"]
                else:
                    cred_data = {"token": result["token"]}
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


class MetaAICaptureRequest(BaseModel):
    """Manual cookie input for Meta AI."""

    cookies: dict = Field(
        ...,
        description="Cookie dict with datr and ecto_1_sess values",
    )


class ZaiCaptureRequest(BaseModel):
    """Manual token input for Z.ai."""

    token: str = Field(
        ...,
        min_length=10,
        description="Z.ai session JWT token",
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
    forms for capturing Meta AI cookies and Z.ai session tokens.
    """
    creds = await list_credentials(db, current_user["id"])

    # Build status per provider
    meta_status: str = "none"
    zai_status: str = "none"
    for c in creds:
        if c["provider"] == "meta_ai":
            meta_status = "stored"
        elif c["provider"] == "zai_web":
            zai_status = "stored"

    return templates.TemplateResponse(
        request,
        "sandbox.html",
        {
            "user": current_user,
            "meta_status": meta_status,
            "zai_status": zai_status,
        },
    )


# ---------------------------------------------------------------------------
# POST /sandbox/meta-ai/capture — Manual cookie input only
# ---------------------------------------------------------------------------


@router.post("/meta-ai/capture")
async def capture_meta_ai(
    body: MetaAICaptureRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Store Meta AI cookies provided manually by the user.

    Use this endpoint when the user copies cookies from their browser's
    DevTools.  The cookies are validated before storage.
    """
    validation = await validate_meta_ai_cookies(body.cookies)
    if not validation["valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation.get("error", "Invalid cookies"),
        )

    stored = await store_credential(db, current_user["id"], "meta_ai", body.cookies)
    return {
        "status": "ok",
        "credential_id": stored["id"] if stored else None,
    }


# ---------------------------------------------------------------------------
# POST /sandbox/meta-ai/capture/start — Interactive browser capture
# ---------------------------------------------------------------------------


@router.post("/meta-ai/capture/start")
async def start_meta_ai_capture(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Start an interactive browser-based cookie capture for Meta AI.

    Opens a visible browser on the server.  The user should log in to Meta AI
    manually in that browser.  Poll the ``status`` endpoint to check progress
    or call the ``done`` endpoint to signal completion.
    """
    capture_id = uuid.uuid4().hex[:12]
    state = CaptureState(
        capture_id=capture_id,
        provider="meta_ai",
    )
    _capture_states[capture_id] = state

    _run_capture_background(state, db, current_user["id"])

    return CaptureStartResponse(
        capture_id=capture_id,
        status="started",
        message="Interactive capture started. A browser window should open on the server. "
        "Log in to Meta AI manually, then call the /done endpoint or wait for auto-detection.",
    )


# ---------------------------------------------------------------------------
# GET /sandbox/meta-ai/capture/{capture_id}/status
# ---------------------------------------------------------------------------


@router.get("/meta-ai/capture/{capture_id}/status")
async def check_meta_ai_capture_status(
    capture_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Check the status of an interactive Meta AI capture session."""
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
# POST /sandbox/meta-ai/capture/{capture_id}/done
# ---------------------------------------------------------------------------


@router.post("/meta-ai/capture/{capture_id}/done")
async def signal_meta_ai_capture_done(
    capture_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Signal that the user has finished logging in and cookies should be extracted.

    This tells the background capture task to stop waiting and extract
    whatever cookies are currently available.
    """
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
# POST /sandbox/zai/capture — Manual token input only
# ---------------------------------------------------------------------------


@router.post("/zai/capture")
async def capture_zai(
    body: ZaiCaptureRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Store a Z.ai session token provided manually by the user.

    Use this endpoint when the user copies their session token from the
    browser's DevTools (localStorage or cookies).
    """
    validation = await validate_zai_token(body.token)
    if not validation["valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation.get("error", "Invalid token"),
        )

    cred_data = {"token": body.token}
    stored = await store_credential(db, current_user["id"], "zai_web", cred_data)
    return {
        "status": "ok",
        "credential_id": stored["id"] if stored else None,
    }


# ---------------------------------------------------------------------------
# POST /sandbox/zai/capture/start — Interactive browser capture
# ---------------------------------------------------------------------------


@router.post("/zai/capture/start")
async def start_zai_capture(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Start an interactive browser-based token capture for Z.ai."""
    capture_id = uuid.uuid4().hex[:12]
    state = CaptureState(
        capture_id=capture_id,
        provider="zai_web",
    )
    _capture_states[capture_id] = state

    _run_capture_background(state, db, current_user["id"])

    return CaptureStartResponse(
        capture_id=capture_id,
        status="started",
        message="Interactive capture started. A browser window should open on the server. "
        "Log in to Z.ai manually, then call the /done endpoint or wait for auto-detection.",
    )


# ---------------------------------------------------------------------------
# GET /sandbox/zai/capture/{capture_id}/status
# ---------------------------------------------------------------------------


@router.get("/zai/capture/{capture_id}/status")
async def check_zai_capture_status(
    capture_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Check the status of an interactive Z.ai capture session."""
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
# POST /sandbox/zai/capture/{capture_id}/done
# ---------------------------------------------------------------------------


@router.post("/zai/capture/{capture_id}/done")
async def signal_zai_capture_done(
    capture_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Signal that the user has finished logging in and the token should be extracted."""
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
        "message": "Done signal sent. Token will be extracted.",
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
        provider: Provider name (e.g. ``"meta_ai"``, ``"zai_web"``).
    """
    deleted = await delete_credential(db, current_user["id"], provider)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credentials found for provider '{provider}'",
        )
    return {"status": "ok", "deleted": True}
