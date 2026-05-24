"""Top-level API router aggregating all route modules."""

from __future__ import annotations

from fastapi import APIRouter

from hubia.api.auth_routes import router as auth_router

api_router = APIRouter()
api_router.include_router(auth_router)
