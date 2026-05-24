"""Top-level API router aggregating all route modules."""

from __future__ import annotations

from fastapi import APIRouter

from hubia.api.auth_routes import router as auth_router
from hubia.api.v1_routes import router as v1_router
from hubia.sandbox.routes import router as sandbox_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(v1_router)
api_router.include_router(sandbox_router)
