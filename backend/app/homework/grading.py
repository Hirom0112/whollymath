"""Grade a scanned homework set — SymPy decides, exactly like the live tutor.

PROJECT.md §3.4 two-star model: homework earns the SECOND star (★★) when the learner does well
on the ANCHORED target skill — "most target-skill problems correct unassisted (≈4/5)", i.e. a
target-skill score ≥ ``PASS_THRESHOLD``. Review items are graded too (they feed per-KC evidence
and the 1-on-1 walk-through), but they are NOT part of the pass threshold — the gate is the skill
the set is anchored to.

Correctness is the domain verifier's job, never this module's (CLAUDE.md §8.2): each submitted
answer is judged by ``domain.verifier.verify`` against the problem's SymPy ``correct_value`` — the
SAME oracle the live turn loop uses, so a homework "correct" means exactly what an in-lesson
"correct" means. An UNREADABLE answer (the scanner returned ``None``) is graded incorrect but
flagged ``unreadable`` so the surface can route it to the OCR-misread fix in the 1-on-1 review
rather than silently marking the child wrong.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.problem_generators import Problem
from app.domain.verifier import Submitted, verify
from app.homework.assignment import Assignment

# The ★★ pass bar over the target-skill items (RD.0.9: "most correct, ≈4/5"). Tunable.
PASS_THRESHOLD = 0.8

_BARE_INTEGER = re.compile(r"-?\d+")


def _normalize_answer(problem: Problem, answer: Submitted | None) -> Submitted | None:
    """Map a paper answer to the form the verifier expects.

    Equivalence fill-the-top ("3/4 is the same as ?/8") asks the learner to write only the missing
    TOP number (e.g. ``4``), but the verifier judges the fraction's VALUE — so a bare numerator is
    reconstructed against the given denominator (``4`` → ``4/8``). A learner who writes the full
    fraction (``4/8``) already verifies, so this only rescues the numerator-only convention. All
    other items pass through unchanged.
    """
    if problem.given_denominator is None or answer is None:
        return answer
    text = str(answer).strip()
    if _BARE_INTEGER.fullmatch(text):
        return f"{text}/{problem.given_denominator}"
    return answer


@dataclass(frozen=True)
class QuestionResult:
    """The graded outcome of one homework question — evidence the 1-on-1 review reads.

    Frozen. ``submitted`` is what the scanner read (``None`` = unreadable); ``correct`` is the SymPy
    verdict; ``unreadable`` marks a scan miss so the review can ask the learner to confirm the
    answer (the OCR-misread safety valve) instead of counting a misread as a real mistake.
    """

    index: int
    kc: KnowledgeComponentId
    statement: str
    is_target: bool
    submitted: str | None
    correct: bool
    unreadable: bool


@dataclass(frozen=True)
class GradeResult:
    """The graded homework set + the ★★ verdict (PROJECT.md §3.4 two-star model).

    Frozen. ``target_score`` is the fraction of ANCHORED target-skill items correct (the gate);
    ``passed`` is ``target_score >= PASS_THRESHOLD``. ``results`` carries every question (target and
    review) for the 1-on-1 walk-through. A failed set does NOT block other lessons — the caller
    routes a fail to "redo this lesson + a fresh set" (RD.0.9); this module only computes it.
    """

    results: tuple[QuestionResult, ...]
    target_correct: int
    target_total: int
    target_score: float
    passed: bool


def grade(assignment: Assignment, submitted: Mapping[int, Submitted | None]) -> GradeResult:
    """Grade ``submitted`` (question index → scanned answer, or ``None`` if unreadable) against
    ``assignment``. SymPy decides each item; ★★ passes when the TARGET-skill score ≥ threshold.

    The index space is the position of each item in ``assignment.problems`` (0-based), the same
    order the scanner reports against. A target with no items (should not happen) scores 0.0 and
    does not pass — we never declare a pass off an empty set.
    """
    results: list[QuestionResult] = []
    target_correct = 0
    target_total = 0

    for index, item in enumerate(assignment.problems):
        answer = submitted.get(index)
        unreadable = answer is None
        normalized = _normalize_answer(item.problem, answer)
        is_correct = (not unreadable) and verify(item.problem, normalized).is_correct
        results.append(
            QuestionResult(
                index=index,
                kc=item.problem.kc,
                statement=item.problem.statement,
                is_target=item.is_target,
                submitted=None if answer is None else str(answer),
                correct=is_correct,
                unreadable=unreadable,
            )
        )
        if item.is_target:
            target_total += 1
            if is_correct:
                target_correct += 1

    target_score = (target_correct / target_total) if target_total else 0.0
    passed = target_total > 0 and target_score >= PASS_THRESHOLD

    return GradeResult(
        results=tuple(results),
        target_correct=target_correct,
        target_total=target_total,
        target_score=target_score,
        passed=passed,
    )


__all__ = ["PASS_THRESHOLD", "GradeResult", "QuestionResult", "grade"]
