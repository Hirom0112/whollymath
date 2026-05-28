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

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.routes import router
from app.api.service import SessionStore
from app.helpneed.artifact import load_predictor
from app.persona_surface.hint_renderer import default_hint_provider
from app.persona_surface.tutor_voice import default_voice_provider

# Load the local .env at process startup so server-side secrets (ANTHROPIC_API_KEY for the
# mascot voice, DATABASE_URL) are in the environment (CLAUDE.md §10: python-dotenv in dev,
# Secrets Manager in prod). The .env lives at the repo root (one level above backend/); in
# prod there is no file and this is a silent no-op. override=False so a real env wins.
load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def create_app() -> FastAPI:
    """Build and return the FastAPI app with the turn-loop routes mounted.

    Each app owns one in-memory ``SessionStore`` (on ``app.state``), resolved by the
    routes via the ``get_session_store`` dependency. One store per app keeps live
    sessions isolated between app instances — which is what lets tests construct a
    fresh, empty app each time (no cross-test session leakage).

    The committed HelpNeed artifact is loaded ONCE here (Slice 4.4.1) and injected into
    the store, so every turn scores observe-only without a per-request load and the
    deployed image needs no network fetch on the boot path (artifact.py). Loading once
    at boot is what keeps the turn loop sub-100ms (§8.1).
    """
    app = FastAPI(
        title="WhollyMath API",
        # The turn loop is the v1 surface; version tracks the backend package.
        version="0.1.0",
        summary="Turn-loop API for the adaptive fraction tutor (ARCHITECTURE.md §10).",
    )
    app.state.session_store = SessionStore(
        predictor=load_predictor(),
        # Enable the mascot's voice on help moments (Slice 5.5.2); lazily creates the
        # Anthropic client on first help turn. Falls back to pre-written text if unavailable.
        voice_provider=default_voice_provider(),
        # Warm the escalated partial_step / worked_step hints through the LLM behind the
        # SymPy numeric gate (Slice 5.6 pipeline); falls back to canonical text if unavailable.
        hint_provider=default_hint_provider(),
    )
    app.include_router(router)
    return app


# Module-level instance for the ASGI server (uvicorn app.api.app:app).
app = create_app()
