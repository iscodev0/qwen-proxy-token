"""JWT creation / verification and FastAPI auth dependencies.

Authentication is disabled in qwen-proxy — all endpoints are open.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from hubia.config import settings

# ---------------------------------------------------------------------------
# JWT helpers (kept for backwards compatibility)
# ---------------------------------------------------------------------------


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

# Default user returned when authentication is disabled
_DEFAULT_USER = {"id": 1, "username": "user", "email": "user@localhost", "api_key": "qwen-proxy"}


async def get_current_user() -> dict:
    """Return a default user — authentication is disabled in qwen-proxy."""
    return _DEFAULT_USER
