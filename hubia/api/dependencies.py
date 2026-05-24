"""Shared FastAPI dependencies — re-exports for convenience."""

from __future__ import annotations

import aiosqlite
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from hubia.api.auth import decode_token, get_current_user
from hubia.store.database import get_db
from hubia.store.users import get_user_by_api_key, get_user_by_id

__all__ = [
    "get_current_user",
    "get_db",
    "get_current_user_jwt_or_api_key",
]

# Convenience alias
get_current_user_jwt_or_api_key = get_current_user
