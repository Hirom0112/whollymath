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

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.api.routes import router
from app.api.service import SessionStore
from app.db.engine import create_db_engine, create_session_factory, database_url_from_env
from app.helpneed.artifact import load_predictor
from app.persona_surface.hint_renderer import default_hint_provider
from app.persona_surface.tutor_voice import default_voice_provider

_log = logging.getLogger(__name__)

# Load the local .env at process startup so server-side secrets (ANTHROPIC_API_KEY for the
# mascot voice, DATABASE_URL) are in the environment (CLAUDE.md §10: python-dotenv in dev,
# Secrets Manager in prod). The .env lives at the repo root (one level above backend/); in
# prod there is no file and this is a silent no-op. override=False so a real env wins.
load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def _build_session_factory() -> sessionmaker[OrmSession] | None:
    """Build the persistence factory from ``DATABASE_URL`` — or ``None`` if no DB is reachable.

    Persistence is OFF the decision path and strictly optional (Slice PL.1, ARCHITECTURE.md
    §14 invariant 7): the live demo must boot even with no Postgres. So engine creation is
    wrapped in try/except — a missing ``DATABASE_URL`` (``database_url_from_env`` raises) or an
    engine that cannot be built is logged and skipped, and the app runs in-memory only. We do a
    cheap ``connect()`` to surface an unreachable DB at boot rather than on the first turn;
    note SQLAlchemy ``create_engine`` is lazy, so without this probe a dead DB would only fail
    later (and harmlessly, since turn-time persistence failures are already swallowed).
    """
    try:
        url = database_url_from_env()
        engine = create_db_engine(url)
        with engine.connect():
            pass
        return create_session_factory(engine)
    except Exception:  # noqa: BLE001 — no DB ⇒ in-memory only; the demo still boots (invariant 7).
        _log.warning("no database reachable; running in-memory (no session/mastery persistence)")
        return None


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
        # Persist sessions/mastery when a DB is reachable (Slice PL.1) — None ⇒ in-memory only,
        # so the app boots with no Postgres. Writes are off the decision path (invariant 7).
        session_factory=_build_session_factory(),
    )
    app.include_router(router)
    return app


# Module-level instance for the ASGI server (uvicorn app.api.app:app).
app = create_app()
