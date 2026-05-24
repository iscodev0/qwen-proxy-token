"""Authentication routes — register, login, API key management."""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status

from hubia.api.auth import create_access_token, get_current_user
from hubia.store.database import get_db
from hubia.store.users import (
    authenticate_user,
    create_user,
    generate_api_key,
    get_user_by_username,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    api_key: str | None = None


class ApiKeyResponse(BaseModel):
    api_key: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> UserResponse:
    """Register a new user account.

    Returns the user info without the password hash.  Returns ``409`` if
    the username is already taken.
    """
    user = await create_user(db, body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )
    return UserResponse(**user)


@router.post("/login")
async def login(
    body: LoginRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> TokenResponse:
    """Authenticate with username + password and receive a JWT."""
    user = await authenticate_user(db, body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(user["id"])
    return TokenResponse(access_token=token)


@router.post("/keys", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> ApiKeyResponse:
    """Generate a new API key for the authenticated user.

    The raw key is returned **once** and cannot be retrieved later.
    """
    key = await generate_api_key(db, current_user["id"])
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return ApiKeyResponse(api_key=key)


@router.get("/me")
async def me(
    current_user: dict = Depends(get_current_user),
) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        api_key=current_user.get("api_key"),
    )
