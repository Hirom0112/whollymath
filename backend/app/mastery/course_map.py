"""The course map — one STATUS per KC for the learning-path home screen (Slice CP.A.1).

This is the first surface of the course product (PROJECT.md §3.13): an expansion BEYOND the
PRD's mastery-engine thesis, built strictly as a LAYER ON TOP of the existing engine — it adds
NO new mastery logic. The map is a pure composition of three things the engine already owns:

  - the prerequisite graph (``domain/prerequisites``) — which skills are unlocked / still locked,
    and the teaching order (``SPINE_ORDER``) the path is laid out in;
  - the persisted per-skill mastery (a ``ReviewableSkill`` projection of ``MasteryState``) —
    whether a skill has been touched and whether it is CONFIRMED; and
  - the retention model (``mastery/retention``) — whether a confirmed skill has decayed and is
    due for review (spaced repetition).

Each KC gets exactly one of five statuses, mutually exclusive and exhaustive:

  - ``LOCKED``      — a prerequisite is not yet confirmed and the learner hasn't started it.
  - ``AVAILABLE``   — prerequisites met (or it's the root), not yet started.
  - ``IN_PROGRESS`` — touched (has a mastery row) but not yet confirmed. Wins over locked: the
    cold-start route lets a learner begin any route, so actual progress beats the advisory graph.
  - ``MASTERED``    — confirmed (the S5-probe verdict) and still retained.
  - ``DUE_REVIEW``  — confirmed but decayed below the review bar (``retention.is_due_for_review``).

Pure + deterministic: no DB, no LLM, no SymPy; ``now`` is passed in, never read from the clock
here (CLAUDE.md §8.1, §4.1). The DB read + projection lives in the service, exactly as the
study planner's does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.prerequisites import SPINE_ORDER, prerequisites_of, unlocked
from app.mastery.retention import (
    DEFAULT_HALF_LIFE,
    REVIEW_THRESHOLD,
    ReviewableSkill,
    is_due_for_review,
)


class CourseNodeStatus(StrEnum):
    """A KC's status on the course map (see the module docstring for the full definition).

    ``StrEnum`` so the value serializes as its lowercase string on the wire and reads cleanly in
    the frontend (a stable union type via the generated shared types)."""

    LOCKED = "locked"
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    MASTERED = "mastered"
    DUE_REVIEW = "due_review"


@dataclass(frozen=True)
class CourseNode:
    """One KC's place on the learning path.

    ``prerequisites`` are the KCs that must be confirmed before this one is suggested (the edges
    to draw). ``probability`` is the stored BKT mastery level for a touched skill (for a progress
    indicator), or ``None`` if the learner hasn't started it yet. Frozen + ordered so the whole
    map is a deterministic value (PROJECT.md §4.1)."""

    kc: KnowledgeComponentId
    status: CourseNodeStatus
    prerequisites: tuple[KnowledgeComponentId, ...]
    probability: float | None


def build_course_map(
    skills: list[ReviewableSkill],
    now: datetime,
    *,
    threshold: float = REVIEW_THRESHOLD,
    half_life: timedelta = DEFAULT_HALF_LIFE,
) -> tuple[CourseNode, ...]:
    """Derive the status of every KC for one learner, in teaching (``SPINE_ORDER``) order.

    ``skills`` is the learner's per-skill retention inputs — one entry per KC that has a
    persisted ``MasteryState`` row (i.e. has been touched). KCs absent from ``skills`` are
    untouched. The map always has exactly one node per catalog KC (a path needs all its stops),
    so a brand-new learner (``skills == []``) still gets the full path with the root AVAILABLE.
    """
    touched = {s.kc: s for s in skills}
    confirmed = frozenset(s.kc for s in skills if s.confirmed)
    unlocked_set = unlocked(confirmed)

    nodes: list[CourseNode] = []
    for kc in SPINE_ORDER:
        skill = touched.get(kc)
        if skill is not None and skill.confirmed:
            # Confirmed: mastered unless retention has decayed below the review bar.
            status = (
                CourseNodeStatus.DUE_REVIEW
                if is_due_for_review(skill, now, threshold=threshold, half_life=half_life)
                else CourseNodeStatus.MASTERED
            )
        elif skill is not None:
            # Touched but not confirmed — beats locked, even if prereqs aren't met (the graph is
            # advisory; real progress on a route the learner chose takes precedence).
            status = CourseNodeStatus.IN_PROGRESS
        elif kc in unlocked_set:
            status = CourseNodeStatus.AVAILABLE
        else:
            status = CourseNodeStatus.LOCKED

        nodes.append(
            CourseNode(
                kc=kc,
                status=status,
                prerequisites=tuple(sorted(prerequisites_of(kc), key=lambda k: k.value)),
                probability=skill.bkt_probability if skill is not None else None,
            )
        )
    return tuple(nodes)


__all__ = ["CourseNode", "CourseNodeStatus", "build_course_map"]
