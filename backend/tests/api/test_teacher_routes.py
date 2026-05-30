"""Contract tests for the teacher dashboard routes (Slice TCH.B8).

Drives the real DB-backed app: seeds a demo teacher + a roster of students with persisted mastery
and turn history, then exercises GET /teacher/roster, GET /teacher/student/{id}, and POST
/teacher/student/{id}/assign-unit through the in-process ASGI client. Pins the auth gate
(401/404), the diagnostics surfacing on real data, the owns-roster isolation, and the idempotent
assign. The student id on the wire is the student's external key (Learner.session_id).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.api.app import create_app
from app.db import repositories as repo
from app.db.engine import create_all, create_session_factory
from app.db.seed import seed_curriculum
from app.domain.curriculum import all_units
from app.domain.knowledge_components import KnowledgeComponentId
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.api.asgi_client import get, post_json

_EQ = KnowledgeComponentId.EQUIVALENCE
_A_UNIT_SLUG = all_units()[0].slug  # a real, catalog-seeded unit a teacher can assign


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[OrmSession]]:
    engine: Engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def app(session_factory: sessionmaker[OrmSession]) -> FastAPI:
    application = create_app()
    application.state.session_store.session_factory = session_factory
    with session_factory() as db:
        seed_curriculum(db)  # units must exist for assign + assigned-unit resolution
        db.commit()
    return application


def _persist_answers(
    db: OrmSession, learner_id: int, outcomes: list[tuple[bool, str | None]]
) -> None:
    session = repo.create_session(db, learner_id=learner_id, route_key="equivalence")
    db.flush()
    for i, (correct, err) in enumerate(outcomes):
        repo.persist_turn(
            db,
            session_id=session.id,
            turn_index=i,
            problem_id=f"p{i}",
            action="answer",
            correct=correct,
            error_type=err,
            surface_state="symbolic",
            state_transition=None,
            latency_ms=3000,
            hint_used=False,
        )


def _seed(app: FastAPI) -> tuple[int, str]:
    """Seed a demo teacher + a struggling student (Maya), an on-track student (Sam), and a
    non-rostered student (Ghost). Returns (teacher_id, demo_bearer_token)."""
    _, login = post_json(app, "/teacher/demo-login", {})
    teacher_id, token = login["learner_id"], login["token"]
    sf = app.state.session_store.session_factory
    with sf() as db:
        maya = repo.get_or_create_learner(db, "stu-maya")
        maya.email = "maya@example.com"
        db.flush()
        repo.add_student_to_roster(db, teacher_id, maya.id)
        repo.upsert_mastery_state(
            db,
            learner_id=maya.id,
            kc_id=_EQ.value,
            bkt_probability=0.2,
            attempt_count=5,
            hint_count=2,
            unscaffolded_correct_count=0,
            confirmed=False,
        )
        # A trailing run of wrong answers → STUCK (urgent) → struggling.
        _persist_answers(
            db,
            maya.id,
            [(True, None), (False, "magnitude"), (False, "magnitude"), (False, "magnitude")],
        )

        sam = repo.get_or_create_learner(db, "stu-sam")
        db.flush()
        repo.add_student_to_roster(db, teacher_id, sam.id)
        repo.upsert_mastery_state(
            db,
            learner_id=sam.id,
            kc_id=_EQ.value,
            bkt_probability=0.95,
            attempt_count=4,
            hint_count=0,
            unscaffolded_correct_count=4,
            confirmed=True,
        )

        repo.get_or_create_learner(db, "stu-ghost")  # exists but NOT on the roster
        db.commit()
    return teacher_id, token


def _auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def _assign(app: FastAPI, token: str | None, student_id: str, unit_id: str) -> tuple[int, object]:
    headers = _auth(token) if token is not None else None
    return post_json(
        app, f"/teacher/student/{student_id}/assign-unit", {"unit_id": unit_id}, headers=headers
    )


def test_roster_requires_teacher_auth(app: FastAPI) -> None:
    assert get(app, "/teacher/roster")[0] == 401


def test_roster_lists_ranked_students(app: FastAPI) -> None:
    _, token = _seed(app)
    code, body = get(app, "/teacher/roster", headers=_auth(token))
    assert code == 200, body
    assert body["class_name"] == "Demo Class"
    by_id = {s["student_id"]: s for s in body["students"]}
    assert set(by_id) == {"stu-maya", "stu-sam"}  # only THIS teacher's roster
    assert by_id["stu-maya"]["category"] == "struggling"
    assert by_id["stu-sam"]["category"] == "on_track"
    # The struggling student carries an urgent alert that drove the bucket.
    assert any(a["severity"] == "urgent" for a in by_id["stu-maya"]["alerts"])


def test_student_drill_in_surfaces_diagnostics(app: FastAPI) -> None:
    _, token = _seed(app)
    code, body = get(app, "/teacher/student/stu-maya", headers=_auth(token))
    assert code == 200, body
    assert body["student_id"] == "stu-maya"
    assert body["category"] == "struggling"
    # Equivalence is a weakness and the bank maps it to a named misconception.
    assert any(w["kc_id"] == _EQ.value for w in body["weaknesses"])
    assert body["struggle"]["matched_misconception"] is not None
    assert any(a["kind"] == "STUCK" for a in body["alerts"])
    assert body["assigned_unit_id"] is None
    # Every catalog unit is offered for assignment.
    assert len(body["assignable_units"]) == len(all_units())


def test_student_not_on_roster_is_404(app: FastAPI) -> None:
    _, token = _seed(app)
    assert get(app, "/teacher/student/stu-ghost", headers=_auth(token))[0] == 404


def test_unknown_student_is_404(app: FastAPI) -> None:
    _, token = _seed(app)
    assert get(app, "/teacher/student/stu-nobody", headers=_auth(token))[0] == 404


def test_assign_unit_sets_assigned_and_is_idempotent(app: FastAPI) -> None:
    _, token = _seed(app)
    code, body = _assign(app, token, "stu-maya", _A_UNIT_SLUG)
    assert code == 200, body
    assert body["student"]["assigned_unit_id"] == _A_UNIT_SLUG  # type: ignore[index]

    # Re-assigning the same unit is idempotent (no duplicate, still assigned).
    code2, body2 = _assign(app, token, "stu-maya", _A_UNIT_SLUG)
    assert code2 == 200
    assert body2["student"]["assigned_unit_id"] == _A_UNIT_SLUG  # type: ignore[index]


def test_assign_unknown_unit_is_400(app: FastAPI) -> None:
    _, token = _seed(app)
    code, _ = _assign(app, token, "stu-maya", "not-a-real-unit")
    assert code == 400


def test_assign_foreign_student_is_404(app: FastAPI) -> None:
    _, token = _seed(app)
    code, _ = _assign(app, token, "stu-ghost", _A_UNIT_SLUG)
    assert code == 404


def test_assign_requires_teacher_auth(app: FastAPI) -> None:
    _seed(app)
    code, _ = _assign(app, None, "stu-maya", _A_UNIT_SLUG)
    assert code == 401
