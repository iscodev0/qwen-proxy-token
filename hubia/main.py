"""Hubia FastAPI application — main entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from hubia.config import settings
from hubia.api.errors import register_error_handlers
from hubia.api.router import api_router
from hubia.core.registry import ProviderRegistry
from hubia.providers.meta_ai import MetaAIProvider
from hubia.providers.zai_web import ZaiWebProvider
from hubia.store.database import close_db, init_db

_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Return the global provider registry (initialised during lifespan)."""
    if _registry is None:
        raise RuntimeError("ProviderRegistry not initialized")
    return _registry


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialise resources on start, clean up on stop."""
    # --- Startup ---
    await init_db()

    global _registry  # noqa: PLW0603
    _registry = ProviderRegistry()
    _registry.register("meta_ai", MetaAIProvider(), ["meta-ai/"])
    _registry.register("zai_web", ZaiWebProvider(), ["zai/"])

    # Pass registry to v1 routes
    from hubia.api.v1_routes import set_registry

    set_registry(_registry)

    yield

    # --- Shutdown ---
    await close_db()


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Hubia API Hub",
    description="OpenAI-compatible API proxy for Meta AI and Z.ai",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(api_router)

# Exception handlers
register_error_handlers(app)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


# Jinja2 templates for the web UI
templates = Jinja2Templates(directory="hubia/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serve the main web UI — a single-page app for auth, credentials, and API testing."""
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/health")
async def health() -> dict:
    """Health check endpoint — returns ``{"status": "ok"}`` when running."""
    return {"status": "ok"}
