"""The homework scan flow's stateful store — one run per upload token (in-memory, v1).

Ties the three homework pieces (assignment / scanner / grading) into the cross-device flow the
product needs (PROJECT.md §3.4 two-star model):

  1. ``assign``   — the desktop starts a run for a skill → a one-time ``token`` (the QR carries it).
  2. ``submit``   — the phone posts its page photos against the token → the scanner transcribes a
                    DRAFT reading (state → ``ready_for_review``). Grading does NOT happen here.
  3. ``confirm``  — the desktop sends the learner-confirmed answers (after the "I read this as 1/4 —
                    right?" read-back) → SymPy grades them → the ★★ verdict (state → ``graded``).

The read-back between submit and confirm is the OCR-misread safety valve (RD.0.9): the scanner only
transcribes; the learner confirms; only then does the verifier judge. The scanner is INJECTED (mock
by default, a Mathpix-class scanner later) — the same swap-seam as the LLM provider; the flow is
identical either way. In-memory + per-process for v1 (mirrors the turn-loop ``SessionStore``);
durable storage is a later concern (the demo flow is request-scoped).
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.verifier import Submitted
from app.homework.assignment import Assignment, build_assignment
from app.homework.grading import GradeResult, grade
from app.homework.scanner import HomeworkScanner, MockScanner

# The states a run moves through, in order. Strings (not an enum) because they cross the wire
# verbatim and the set is tiny and stable.
STATE_WAITING = "waiting"  # assigned; awaiting the phone's photos
STATE_READY_FOR_REVIEW = "ready_for_review"  # photos in, draft transcribed; awaiting the read-back
STATE_GRADED = "graded"  # learner confirmed; SymPy graded; verdict ready


@dataclass
class HwRun:
    """One homework run, keyed by its upload token (mutable: it advances waiting → review → graded).

    ``draft`` is the scanner's raw reading (question index → answer or ``None``), shown to the
    learner for the read-back; ``result`` is the SymPy verdict computed from the CONFIRMED answers
    (not the draft). Both are ``None`` until their stage runs.
    """

    token: str
    assignment: Assignment
    state: str = STATE_WAITING
    draft: dict[int, str | None] | None = None
    result: GradeResult | None = None


@dataclass
class HomeworkStore:
    """In-memory store of homework runs by token (one per app instance, like ``SessionStore``).

    ``scanner`` is injected so tests/demos use ``MockScanner`` and production swaps in a real
    math-OCR scanner with no flow change. Construct one per app in ``create_app`` and hold it on
    ``app.state`` so runs are isolated between app instances (each test gets a fresh store).
    """

    scanner: HomeworkScanner = field(default_factory=MockScanner)
    _runs: dict[str, HwRun] = field(default_factory=dict)

    def assign(self, kc: KnowledgeComponentId, *, seed_base: int = 0) -> HwRun:
        """Start a run for ``kc`` and return it (state ``waiting``); the token is the QR payload."""
        token = secrets.token_urlsafe(9)
        run = HwRun(token=token, assignment=build_assignment(kc, seed_base=seed_base))
        self._runs[token] = run
        return run

    def get(self, token: str) -> HwRun | None:
        """The run for ``token``, or ``None`` if unknown (the route maps that to a 404)."""
        return self._runs.get(token)

    def submit(self, token: str, pages: list[bytes]) -> HwRun | None:
        """Record the phone's page photos: transcribe a draft and move to ``ready_for_review``.

        ``None`` if the token is unknown. Grading deliberately does NOT happen here — the learner
        confirms the transcription first (``confirm``).
        """
        run = self._runs.get(token)
        if run is None:
            return None
        run.draft = self.scanner.scan(pages, run.assignment)
        run.state = STATE_READY_FOR_REVIEW
        return run

    def confirm(self, token: str, answers: Mapping[int, Submitted | None]) -> HwRun | None:
        """Grade the learner-CONFIRMED answers (post read-back) with SymPy; move to ``graded``.

        ``None`` if the token is unknown. ``answers`` is authoritative — it is what the learner
        confirmed/corrected in the read-back, not necessarily the raw draft.
        """
        run = self._runs.get(token)
        if run is None:
            return None
        run.result = grade(run.assignment, answers)
        run.state = STATE_GRADED
        return run


__all__ = [
    "STATE_GRADED",
    "STATE_READY_FOR_REVIEW",
    "STATE_WAITING",
    "HomeworkStore",
    "HwRun",
]
