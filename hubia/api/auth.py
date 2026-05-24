"""JWT creation / verification and FastAPI auth dependencies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from hubia.config import settings
from hubia.store.database import get_db
from hubia.store.users import get_user_by_api_key, get_user_by_id

import aiosqlite

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user_id: int) -> str:
    """Create a signed JWT containing the user id in the ``sub`` claim."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT.

    Returns the payload dict on success, or **None** if the token is
    expired, malformed, or the signature is invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    authorization: str | None = Header(None),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """Resolve the current user from a JWT or API key Bearer token.

    Authentication order:
        1. Try to decode the token as a JWT (``sub`` claim → user id).
        2. If that fails, try to look up the token as an API key.

    Raises ``401`` if neither method succeeds.
    """
    token = _extract_token(credentials, authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Try JWT
    payload = decode_token(token)
    if payload is not None:
        user_id = int(payload["sub"])
        user = await get_user_by_id(db, user_id)
        if user is not None:
            return user

    # 2. Try API key
    user = await get_user_by_api_key(db, token)
    if user is not None:
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None,
    authorization: str | None,
) -> str | None:
    """Extract the Bearer token from either the scheme or raw header."""
    if credentials is not None:
        return credentials.credentials
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ")
    return None
