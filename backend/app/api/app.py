"""FastAPI application factory for the WhollyMath turn loop (Slice 1.9).

TECH_STACK §3 locks FastAPI as the backend: async turn loop, Pydantic-typed
boundary, auto-generated OpenAPI. This module assembles the app and mounts the
turn-loop router. It is intentionally minimal at this slice — no middleware, no
DB lifespan, no auth (TECH_STACK §9: v1 uses session-id identification, no auth;
CLAUDE.md §8.6: no premature infrastructure).

A factory function (``create_app``) rather than a module-level singleton, so
tests construct a fresh app and future config (settings, DB lifespan) has one
obvious place to be injected. ``app`` is also exported at module level for the
uvicorn entrypoint (``uvicorn app.api.app:app``) used in local dev (CLAUDE.md
§10).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router


def create_app() -> FastAPI:
    """Build and return the FastAPI app with the turn-loop routes mounted."""
    app = FastAPI(
        title="WhollyMath API",
        # The turn loop is the v1 surface; version tracks the backend package.
        version="0.1.0",
        summary="Turn-loop API for the adaptive fraction tutor (ARCHITECTURE.md §10).",
    )
    app.include_router(router)
    return app


# Module-level instance for the ASGI server (uvicorn app.api.app:app).
app = create_app()
