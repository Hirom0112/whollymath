"""Contract tests for the Spanish help-mode locale seam (Slice 3.6 bilingual scaffold).

The slice routes a chosen HELP-language ("en" | "es-MX") to the turn-rendering code so banked
hints/nudges voice in Spanish, plus the deferred ``Learner.locale`` write endpoint. The locked
boundary (V2_TODO §0.3, ``Learner.locale`` docstring, CLAUDE.md §8.1): locale selects ONLY the
spoken help surface (avatar hint/nudge text + audio asset) — the on-screen problem stays English,
and locale never reaches verify/mastery/policy. So these tests assert exactly two things:

  - the HELP TEXT localizes (a banked es-MX nudge comes back in Spanish, the English path is
    byte-for-byte unchanged), and
  - ``POST /learner/locale`` persists/reads the sticky preference, 404s an unknown learner, and
    422s a locale outside {"en", "es-MX"} (the literal rejects it at the wire).

The math/verdict/next-problem path is NOT exercised here for localization — it MUST be unaffected
(the equivalence property the persistence tests pin), so we only check the help surface differs.

Run in-process against the real ASGI app (``asgi_client``) for the endpoint contract, and against
``SessionStore`` directly for the turn/hint text (the help text is a service-layer concern; driving
it through the store is the same seam the route calls). No LLM/SymPy/network: the es-MX text is the
banked offline bank, the audio lookup a cached dict read (CLAUDE.md §8.1/§9).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.app import create_app
from app.api.schemas import ActionType, SurfaceState, TurnRequest
from app.api.service import SessionStore
from app.db.engine import create_all, create_session_factory
from app.db.models import Learner
from app.tts.manifest_lookup import override_cache_dir, reset_default_cache_dir
from app.tts.spoken_bank import nudge_string_id
from app.tutor.hints import select_nudge
from app.tutor.hints_es import es_mx_text
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.api.asgi_client import post_json

# same_amount → KC_equivalence, whose nudge index 0 has a reviewed es-MX line (and, when the
# gitignored cache holds it, English audio). The number-line route lands on a different KC; we only
# need a KC with an es-MX nudge, which every renderable nudge has (the parity-tested bank).
_EQUIVALENCE_ROUTE = "same_amount"


@pytest.fixture
def empty_cache(tmp_path: Path) -> Iterator[None]:
    """Isolate the audio lookup to an empty temp cache so the help TEXT (not cached audio) is read.

    With a populated cache an English banked line captions the CANONICAL audio words verbatim (the
    SpokenAudio invariant), which would still be English text — but to assert the es-MX TEXT path
    deterministically regardless of what the real cache holds, we keep every line silent so the
    response carries the chosen-locale caption straight from the bank. es-MX audio is not rendered,
    so the Spanish path is captions-only anyway; this just makes the English side deterministic too.
    """
    override_cache_dir(tmp_path)
    try:
        yield
    finally:
        reset_default_cache_dir()


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    """A shared in-memory SQLite engine + schema, as a session factory (mirrors tests/db/)."""
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


def _hint_req(session_id: str, problem_id: str, *, locale: str = "en") -> TurnRequest:
    return TurnRequest(
        session_id=session_id,
        problem_id=problem_id,
        action=ActionType.REQUEST_HINT,
        surface_state=SurfaceState.SYMBOLIC_FOCUS,
        latency_ms=1000,
        hint_used=False,
        locale=locale,  # type: ignore[arg-type]  # the Literal narrows at the wire; "fr" is a 422-shape test elsewhere.
    )


# ── 1. The help TEXT localizes (turn/start carry locale) ─────────────────────────────────────


def test_first_hint_in_es_mx_returns_spanish_nudge_text(empty_cache: None) -> None:
    """A REQUEST_HINT with locale='es-MX' captions the banked es-MX nudge for the KC (Slice 3.6)."""
    store = SessionStore()
    started = store.start(_EQUIVALENCE_ROUTE, locale="es-MX")
    sid, pid = started.session_id, started.problem.problem_id

    result = store.process_turn(_hint_req(sid, pid, locale="es-MX"))

    kc = started.problem.kc
    expected_es = es_mx_text(nudge_string_id(kc.value, 0))
    assert expected_es is not None  # the bank has an es-MX line for every renderable nudge
    assert result.hint == expected_es
    # es-MX audio is not rendered yet → captions-only (the existing fallback), never English audio.
    assert result.hint_audio is None


def test_first_hint_default_locale_is_english_unchanged(empty_cache: None) -> None:
    """The default-locale ("en") hint is the English nudge, byte-for-byte — the English path holds.

    With no voice provider and an empty cache, the English nudge is returned verbatim (invariant 4),
    so the English hint must equal the banked English nudge and must NOT equal the es-MX line.
    """
    store = SessionStore()
    started = store.start(_EQUIVALENCE_ROUTE)  # locale defaults to "en"
    sid, pid = started.session_id, started.problem.problem_id

    result = store.process_turn(_hint_req(sid, pid))  # locale defaults to "en"

    kc = started.problem.kc
    expected_en = select_nudge(kc, index=0).text
    assert result.hint == expected_en
    assert result.hint != es_mx_text(nudge_string_id(kc.value, 0))


def test_en_and_es_hints_differ_for_same_problem(empty_cache: None) -> None:
    """The SAME first problem voiced in en vs es-MX yields different help text (localization)."""
    store = SessionStore()
    started_en = store.start(_EQUIVALENCE_ROUTE, session_id="loc-en", locale="en")
    started_es = store.start(_EQUIVALENCE_ROUTE, session_id="loc-es", locale="es-MX")

    en = store.process_turn(_hint_req(started_en.session_id, started_en.problem.problem_id))
    es = store.process_turn(
        _hint_req(started_es.session_id, started_es.problem.problem_id, locale="es-MX")
    )

    assert en.hint is not None and es.hint is not None
    assert en.hint != es.hint


# ── 2. POST /learner/locale — the deferred Learner.locale write ──────────────────────────────


def _store_with_db(session_factory: sessionmaker[OrmSession]) -> SessionStore:
    store = SessionStore(session_factory=session_factory)
    return store


def _make_learner(session_factory: sessionmaker[OrmSession], session_id: str) -> int:
    """Create a persisted learner (default locale 'en') and return its id."""
    with session_factory() as db:
        learner = Learner(session_id=session_id)
        db.add(learner)
        db.commit()
        return learner.id


def _app_with(store: SessionStore):  # type: ignore[no-untyped-def]
    app = create_app()
    app.state.session_store = store  # swap in the controlled (in-memory-DB) store
    return app


def test_set_locale_happy_path_persists_and_reads_back(
    session_factory: sessionmaker[OrmSession],
) -> None:
    """POST /learner/locale sets es-MX, echoes it, and the write is durable (read back from DB)."""
    learner_id = _make_learner(session_factory, "learner-locale-1")
    store = _store_with_db(session_factory)
    app = _app_with(store)

    status_code, body = post_json(
        app, "/learner/locale", {"learner_id": learner_id, "locale": "es-MX"}
    )

    assert status_code == 200
    assert body == {"learner_id": learner_id, "locale": "es-MX"}
    # Durable: a fresh read sees the committed value, not a transient one.
    with session_factory() as db:
        assert db.get(Learner, learner_id).locale == "es-MX"


def test_set_locale_unknown_learner_is_404(session_factory: sessionmaker[OrmSession]) -> None:
    """An unknown learner_id → 404 (set_learner_locale returns None; the handler maps it)."""
    store = _store_with_db(session_factory)
    app = _app_with(store)

    status_code, body = post_json(
        app, "/learner/locale", {"learner_id": 999_999, "locale": "es-MX"}
    )

    assert status_code == 404


def test_set_locale_invalid_value_is_422(session_factory: sessionmaker[OrmSession]) -> None:
    """A locale outside {'en','es-MX'} (e.g. 'fr') → 422 from the Literal, before the handler."""
    learner_id = _make_learner(session_factory, "learner-locale-2")
    store = _store_with_db(session_factory)
    app = _app_with(store)

    status_code, _ = post_json(
        app, "/learner/locale", {"learner_id": learner_id, "locale": "fr"}
    )

    assert status_code == 422


def test_set_locale_without_persistence_is_503() -> None:
    """No session_factory wired → 503 (the preference cannot be stored), not a misleading 404."""
    store = SessionStore()  # no factory
    app = _app_with(store)

    status_code, _ = post_json(app, "/learner/locale", {"learner_id": 1, "locale": "es-MX"})

    assert status_code == 503
