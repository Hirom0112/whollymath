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
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.api.auth_routes import auth_router
from app.api.course_routes import course_router
from app.api.routes import router
from app.api.service import SessionStore
from app.api.units_routes import units_router
from app.db.engine import (
    create_all,
    create_db_engine,
    create_session_factory,
    database_url_from_env,
)
from app.db.seed import seed_curriculum
from app.helpneed.artifact import load_predictor
from app.homework.scanner import MathpixScanner, MockScanner
from app.homework.session import HomeworkStore
from app.llm.tracing import traced
from app.persona_surface.hint_renderer import default_hint_provider
from app.persona_surface.tutor_voice import default_voice_provider

_log = logging.getLogger(__name__)

# Load the local .env at process startup so server-side secrets (ANTHROPIC_API_KEY for the
# mascot voice, DATABASE_URL) are in the environment (CLAUDE.md §10: python-dotenv in dev,
# Secrets Manager in prod). The .env lives at the repo root (one level above backend/); in
# prod there is no file and this is a silent no-op. override=False so a real env wins.
load_dotenv(Path(__file__).resolve().parents[3] / ".env")


# The default durable store when no ``DATABASE_URL`` is configured (Slice AR.2). An on-disk
# SQLite file under the gitignored ``backend/data/`` dir, so the DEFAULT running app persists —
# a passed transfer probe writes ``confirmed=true`` to ``mastery_state`` and the 1★ survives a
# restart (AUDIT.md §6 blocker 2) — WITHOUT requiring a Postgres to be stood up first. SQLite is
# already a first-class backend here (the test suite and ``create_db_engine`` both use it); prod
# still points ``DATABASE_URL`` at RDS Postgres and that path is unchanged. The file lives next
# to this package's repo root (``backend/data/whollymath.db``); ``backend/data/`` is gitignored.
_DEFAULT_SQLITE_PATH = Path(__file__).resolve().parents[2] / "data" / "whollymath.db"


def _build_session_factory() -> sessionmaker[OrmSession] | None:
    """Build the persistence factory — durable by DEFAULT, ``None`` only on an explicit-DB failure.

    Persistence is OFF the decision path and strictly optional (Slice PL.1, ARCHITECTURE.md §14
    invariant 7): a turn's response is identical with or without a factory, and a write failure
    is swallowed. But the DEFAULT running app MUST persist so the first mastery star is durable
    (AUDIT.md §6 blocker 2; PROJECT.md §3.4 "mastered means CONFIRMED"). Resolution order:

      1. ``DATABASE_URL`` set ⇒ use it (prod RDS Postgres, or a local docker-compose Postgres).
         We probe with a cheap ``connect()`` so an UNREACHABLE explicitly-configured DB surfaces
         at boot, not on the first turn (``create_engine`` is lazy). If that explicit DB cannot
         be reached we fall back to ``None`` (in-memory only) rather than silently writing to a
         different store than the operator configured — the demo still boots (invariant 7).
      2. No ``DATABASE_URL`` ⇒ default to a durable on-disk SQLite file (``backend/data/``),
         materializing the schema on first boot via ``create_all`` (SQLite has no migration
         runner wired; prod Postgres uses Alembic). This is what makes the out-of-the-box app
         persist the 1★ across a restart with no Postgres required.

    Only a genuinely-unusable filesystem for the default SQLite path degrades to ``None``.
    """
    try:
        url = database_url_from_env()
    except RuntimeError:
        # No DATABASE_URL: default to a durable on-disk SQLite store so the app persists by
        # default (Slice AR.2). create_all is idempotent, so re-boot over an existing file is a
        # no-op; it materializes the schema on the very first boot (no Alembic for SQLite here).
        try:
            _DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
            engine = create_db_engine(f"sqlite:///{_DEFAULT_SQLITE_PATH}")
            create_all(engine)
            factory = create_session_factory(engine)
            # Seed the curriculum catalog so a fresh default SQLite app boots with populated
            # unit/lesson tables (DAT.4 bootstrap half). Prod Postgres is seeded by the Alembic
            # migration, but this SQLite default path has no migration runner, so seed here.
            # seed_curriculum upserts and is idempotent: re-boot over an existing file is a no-op.
            # Best-effort like the rest of this path (ARCHITECTURE.md §14 invariant 7) — a seed
            # failure must not break persistence, which is off the decision path.
            try:
                with factory() as seed_session:
                    seed_curriculum(seed_session)
                    seed_session.commit()
            except Exception:  # noqa: BLE001 — seeding is best-effort; persistence still works.
                _log.warning("could not seed curriculum into default SQLite store")
            _log.info("no DATABASE_URL; persisting to default SQLite at %s", _DEFAULT_SQLITE_PATH)
            return factory
        except Exception:  # noqa: BLE001 — even the default store is best-effort (invariant 7).
            _log.warning("could not open default SQLite store; running in-memory (no persistence)")
            return None
    try:
        engine = create_db_engine(url)
        with engine.connect():
            pass
        return create_session_factory(engine)
    except Exception:  # noqa: BLE001 — configured DB unreachable ⇒ in-memory; the demo still boots.
        _log.warning("configured DATABASE_URL is unreachable; running in-memory (no persistence)")
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
        # Wrapped in LangSmith tracing (Slice PL.0): a no-op passthrough unless
        # LANGSMITH_TRACING is set, so the default behavior is unchanged.
        voice_provider=traced(default_voice_provider()),
        # Warm the escalated partial_step / worked_step hints through the LLM behind the
        # SymPy numeric gate (Slice 5.6 pipeline); falls back to canonical text if unavailable.
        hint_provider=traced(default_hint_provider()),
        # Persist sessions/mastery when a DB is reachable (Slice PL.1) — None ⇒ in-memory only,
        # so the app boots with no Postgres. Writes are off the decision path (invariant 7).
        session_factory=_build_session_factory(),
    )
    # The homework scan flow's store (PROJECT.md §3.4 two-star model): one per app instance, like
    # the turn-loop store, so runs are isolated between apps. Real Mathpix OCR when MATHPIX_APP_KEY
    # is configured, else the deterministic MockScanner (no key needed) — same flow either way.
    homework_scanner = MathpixScanner() if os.environ.get("MATHPIX_APP_KEY") else MockScanner()
    app.state.homework_store = HomeworkStore(scanner=homework_scanner)
    app.include_router(router)
    # The Google-OIDC account endpoints (Slice PL.3), additive and independent of the turn loop:
    # mounting this router adds /me without touching the turn endpoints' (identity-free) contract.
    app.include_router(auth_router)
    # The course-product endpoints (Slice CP.A.1) — also additive and on the authenticated path:
    # /course derives the learning-path home from existing engine state, off the turn loop.
    app.include_router(course_router)
    # The unit-product endpoints (Slices DAT.8/DAT.9/DAT.10) — additive and on the same optional-
    # auth path as /course: /units and /unit/{slug} derive the unit/lesson shell from the catalog
    # + the course map, off the turn loop, surfacing the teacher-assigned unit for a signed-in
    # learner (DAT.10).
    app.include_router(units_router)
    return app


# Module-level instance for the ASGI server (uvicorn app.api.app:app).
app = create_app()
