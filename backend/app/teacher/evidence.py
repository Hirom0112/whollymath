"""ORM-free carriers for a student's behavioral evidence (Slices TCH.B4/B5).

The alert engine and the struggle summary are PURE and unit-tested without a DB, so they consume
these small frozen carriers rather than SQLAlchemy ``Turn`` rows. The coordinator
(``app.api.teacher_service``) builds them from ``repo.load_turns_for_learner`` — the same
decoupling ``repo.EventRow`` uses for event ingest (CLAUDE.md §7).

A ``TurnFact`` keeps only what the diagnostics read: was the answer correct, the verifier's
coarse error CATEGORY when it wasn't (``Turn.error_type`` — magnitude/operation/format/other, NOT
a named misconception; the named label is inferred separately from the weakest KC), whether a
hint was used, and when it happened. ``Turn`` carries no ``kc_id`` (only a ``problem_id`` whose
format is not a reliable KC key), so the diagnostics work at the behavioral-aggregate grain — the
honest grain for the persisted data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TurnFact:
    """One answered turn, reduced to what the teacher diagnostics read (TCH.B4/B5)."""

    correct: bool
    # The verifier's coarse error category (``Turn.error_type``) when the answer was wrong; ``None``
    # when correct. A category string (e.g. "magnitude"/"operation"), not a named misconception.
    error_category: str | None
    hint_used: bool
    # When the turn happened, as an aware UTC datetime (the coordinator coerces SQLite's naive
    # timestamps to UTC, the same fix the retention readout uses).
    created_at: datetime


__all__ = ["TurnFact"]
