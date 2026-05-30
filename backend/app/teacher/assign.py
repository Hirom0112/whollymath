"""Assign-next-unit write service (Slice TCH.B7).

The one teacher WRITE: hand a unit to a student. Guards first (a teacher may only act on their
OWN roster — the ``get_student_if_on_roster`` authorization primitive, TCH.B1), resolves the unit
slug to its row, then upserts the assignment idempotently (``repo.assign_unit`` keys on
(student, unit), so re-assigning is a touch, not a duplicate). The two failure modes raise typed
errors the route maps to HTTP — a foreign/unknown student is a 404 (the teacher must not learn
whether the id exists at all), an unknown unit is a 400 (the request named a bad unit).

The caller owns the unit of work (commit), per CLAUDE.md §7; ``now`` is passed so the write stays
clock-free and deterministic.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session as OrmSession

from app.db import repositories as repo
from app.db.models import Assignment


class StudentNotOnRosterError(Exception):
    """Raised when the target student is not on the acting teacher's roster (→ 404)."""


class UnknownUnitError(Exception):
    """Raised when the requested unit slug matches no catalog unit (→ 400)."""


def assign_next_unit(
    db: OrmSession,
    *,
    teacher_id: int,
    student_id: int,
    unit_slug: str,
    now: datetime,
) -> Assignment:
    """Assign ``unit_slug`` to ``student_id`` on behalf of ``teacher_id``; return the assignment.

    Raises ``StudentNotOnRosterError`` if the student is not on this teacher's roster (the owns
    guard) and ``UnknownUnitError`` if the slug resolves to no unit. A teacher may assign a unit
    whose prereqs are not yet met — availability is advisory, the teacher's judgment overrides the
    gate (TCH.Q5). Idempotent: re-assigning the same unit touches the existing row.
    """
    if repo.get_student_if_on_roster(db, teacher_id, student_id) is None:
        raise StudentNotOnRosterError(student_id)
    unit = repo.get_unit(db, unit_slug)
    if unit is None:
        raise UnknownUnitError(unit_slug)
    return repo.assign_unit(
        db, teacher_id=teacher_id, student_id=student_id, unit_id=unit.id, now=now
    )


__all__ = ["StudentNotOnRosterError", "UnknownUnitError", "assign_next_unit"]
