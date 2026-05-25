"""Top-level API router aggregating all route modules."""

from __future__ import annotations

from fastapi import APIRouter

from hubia.api.v1_routes import router as v1_router

api_router = APIRouter()
api_router.include_router(v1_router)
