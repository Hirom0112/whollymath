"""Build a per-skill homework set — anchored to the just-learned skill, plus spaced review.

PROJECT.md §3.4 "Two-star model" + RD.0.4/0.9: the set is "mostly the new skill, mixed with
spaced review of earlier UNLOCKED skills" — NOT a blocked run of one problem (the mastery model
rejects blocked practice, §3.4 rule 4) and NOT teacher-assigned for v1. Reviews pull only from
EARLIER spine skills (`SPINE_ORDER`), so a set never tests something not yet taught.

This module only ASSEMBLES problems (reusing the Layer-1 ``generate_problem`` — never a second
problem source) and records which is the anchor. Correctness/grading is ``grading.py``'s job
(SymPy verifier); reading the photo is ``scanner.py``'s job. Deterministic: a fixed
``(target_kc, seed_base)`` yields the same set every call (seeded generator), so a session can
rebuild its assignment on resume.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.prerequisites import SPINE_ORDER
from app.domain.problem_generators import Problem, generate_problem

# v1 set shape (tunable): how many anchored target-skill items + how many spaced-review items.
# The target count is what the ≥0.8 ★★ gate is scored over (grading.py); reviews are evidence +
# interleaving, not part of the gate threshold.
DEFAULT_TARGET_COUNT = 5
DEFAULT_REVIEW_COUNT = 2


@dataclass(frozen=True)
class AssignmentProblem:
    """One problem in a homework set: the ``Problem`` and whether it is the anchored target skill.

    Frozen — an assigned item is a fact. ``is_target`` marks the just-learned skill (scored by the
    ★★ gate); ``False`` marks a spaced-review item from an earlier spine skill (evidence only).
    """

    problem: Problem
    is_target: bool


@dataclass(frozen=True)
class Assignment:
    """One generated homework set for one skill (PROJECT.md §3.4 two-star model).

    Frozen. ``target_kc`` is the just-learned skill the set is anchored to; ``problems`` are the
    items in presentation order (target items first, then spaced review). The expected answer for
    each is its ``problem.correct_value`` (SymPy) — grading reads it from there, so the answer key
    never has to be stored separately.
    """

    target_kc: KnowledgeComponentId
    problems: tuple[AssignmentProblem, ...]

    @property
    def target_problems(self) -> tuple[AssignmentProblem, ...]:
        """The anchored target-skill items — the set the ★★ pass threshold is scored over."""
        return tuple(p for p in self.problems if p.is_target)


def _earlier_spine_skills(target_kc: KnowledgeComponentId) -> list[KnowledgeComponentId]:
    """The skills taught BEFORE ``target_kc`` in spine order — the pool spaced review pulls from."""
    if target_kc not in SPINE_ORDER:
        return []
    index = SPINE_ORDER.index(target_kc)
    return list(SPINE_ORDER[:index])


def build_assignment(
    target_kc: KnowledgeComponentId,
    *,
    target_count: int = DEFAULT_TARGET_COUNT,
    review_count: int = DEFAULT_REVIEW_COUNT,
    seed_base: int = 0,
) -> Assignment:
    """Build the homework set for ``target_kc``: ``target_count`` anchored items + up to
    ``review_count`` spaced-review items from earlier spine skills.

    Deterministic from ``seed_base`` (the generator is seeded). Review items are drawn from the
    spine skills immediately PRECEDING the target (the closest earlier skills, most worth keeping
    warm); when the target is the first spine skill (number line) there are none, so the set is
    target-only. Each item uses the KC's default representation — a paper worksheet is a single
    static surface, so representation diversity is the in-lesson tutor's job (§3.4 rule 2), not the
    homework's.
    """
    items: list[AssignmentProblem] = []

    for i in range(target_count):
        problem = generate_problem(target_kc, seed=seed_base + i + 1)
        items.append(AssignmentProblem(problem=problem, is_target=True))

    # Spaced review: the closest earlier spine skills, one item each, most-recent-first so the
    # skill just below the target is reviewed before older ones. Number-line PLACEMENT is excluded:
    # scanned homework needs a WRITTEN answer to read off the photo, and a placement item's "answer"
    # is a mark on a line (its on-screen "drag the marker" wording makes no sense on paper, and the
    # scanner/verifier has no value to grade). Number-line practice stays the in-app lesson task.
    earlier = [
        kc
        for kc in _earlier_spine_skills(target_kc)
        if kc is not KnowledgeComponentId.NUMBER_LINE_PLACEMENT
    ]
    review_kcs = list(reversed(earlier))[:review_count]
    for j, review_kc in enumerate(review_kcs):
        problem = generate_problem(review_kc, seed=seed_base + 100 + j)
        items.append(AssignmentProblem(problem=problem, is_target=False))

    return Assignment(target_kc=target_kc, problems=tuple(items))


__all__ = [
    "DEFAULT_REVIEW_COUNT",
    "DEFAULT_TARGET_COUNT",
    "Assignment",
    "AssignmentProblem",
    "build_assignment",
]
