"""The study planner — what a learner should do next (Slice 6.x; spaced repetition).

Combines the two pieces that make spaced repetition coherent without a curriculum:

  - the prerequisite graph (``domain/prerequisites.py``) — which NEW skill is unlocked next,
    along the fractions→algebra spine; and
  - the retention model (``mastery/retention.py``) — which CONFIRMED skill has decayed and is
    DUE FOR REVIEW.

The policy: a due review takes PRIORITY over new material (don't let mastered skills rot
while racing ahead — the whole point of spacing), and the new skill suggested respects
prerequisites. Pure + deterministic; ``now`` is passed in (CLAUDE.md §8.1, §4.1). The natural
call site is across sessions (the persistence layer, PL.1) — within one session nothing has
had time to decay, which is honest: spacing needs a real time gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.prerequisites import unlocked
from app.mastery.retention import ReviewableSkill, next_review

# The teaching order along the algebra-readiness spine (prerequisites.py rationale). Used to
# pick a single deterministic "recommended" new skill among those unlocked (earliest spine
# skill first), so the suggestion is stable and pedagogically ordered.
_SPINE_ORDER: tuple[KnowledgeComponentId, ...] = (
    KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
    KnowledgeComponentId.EQUIVALENCE,
    KnowledgeComponentId.COMMON_DENOMINATOR,
    KnowledgeComponentId.ADDITION_UNLIKE,
    KnowledgeComponentId.SUBTRACTION_UNLIKE,
)


@dataclass(frozen=True)
class StudyPlan:
    """What to do next for one learner.

    ``due_reviews`` — confirmed skills whose retention has decayed, most-decayed first
    (spaced repetition). ``unlocked_next`` — new skills whose prerequisites are confirmed,
    in spine order. ``recommended`` — the single best next action: the most-decayed due
    review if any, else the earliest unlocked new skill, else ``None`` (all confirmed + fresh).
    """

    due_reviews: tuple[KnowledgeComponentId, ...]
    unlocked_next: tuple[KnowledgeComponentId, ...]
    recommended: KnowledgeComponentId | None


def plan_study(skills: list[ReviewableSkill], now: datetime) -> StudyPlan:
    """Build the StudyPlan for a learner from their per-skill retention inputs + ``now``."""
    confirmed = frozenset(s.kc for s in skills if s.confirmed)
    due = tuple(next_review(skills, now))
    unlocked_set = unlocked(confirmed)
    unlocked_ordered = tuple(kc for kc in _SPINE_ORDER if kc in unlocked_set)

    if due:
        recommended: KnowledgeComponentId | None = due[0]
    elif unlocked_ordered:
        recommended = unlocked_ordered[0]
    else:
        recommended = None

    return StudyPlan(due_reviews=due, unlocked_next=unlocked_ordered, recommended=recommended)


__all__ = ["StudyPlan", "plan_study"]
