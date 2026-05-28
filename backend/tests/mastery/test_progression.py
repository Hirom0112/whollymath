"""Tests for the study planner — prerequisites + retention combined (Slice 6.x).

The planner answers one question for a learner: "what next?" It prefers a DUE REVIEW (keep
mastered skills from rotting — spaced repetition) over introducing a NEW skill, and the new
skill it suggests respects the algebra-readiness prerequisite graph. Pure + deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.knowledge_components import KnowledgeComponentId
from app.mastery.progression import plan_study
from app.mastery.retention import DEFAULT_HALF_LIFE, ReviewableSkill

KC = KnowledgeComponentId  # local shorthand (a constant alias; ruff-clean, unlike `import as`)
_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def test_brand_new_learner_is_pointed_at_the_root_skill() -> None:
    """Nothing confirmed → no reviews due; the recommended next skill is the foundational root."""
    plan = plan_study([], _NOW)
    assert plan.due_reviews == ()
    assert KC.NUMBER_LINE_PLACEMENT in plan.unlocked_next
    assert plan.recommended == KC.NUMBER_LINE_PLACEMENT


def test_unlocked_next_follows_the_prerequisite_graph() -> None:
    """With number-line confirmed (and fresh), the next new skill is equivalence."""
    skills = [ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.9, _NOW)]
    plan = plan_study(skills, _NOW)
    assert plan.due_reviews == ()  # fresh, not due
    assert KC.EQUIVALENCE in plan.unlocked_next
    assert plan.recommended == KC.EQUIVALENCE


def test_a_due_review_takes_priority_over_new_material() -> None:
    """A decayed confirmed skill is recommended for REVIEW ahead of introducing a new one."""
    skills = [
        ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.9, _NOW - 4 * DEFAULT_HALF_LIFE),  # due
    ]
    plan = plan_study(skills, _NOW)
    assert plan.due_reviews == (KC.NUMBER_LINE_PLACEMENT,)
    # equivalence is unlocked, but review comes first
    assert KC.EQUIVALENCE in plan.unlocked_next
    assert plan.recommended == KC.NUMBER_LINE_PLACEMENT


def test_recommended_is_none_when_all_done_and_nothing_due() -> None:
    """Everything confirmed and freshly practiced → nothing to review, nothing new to unlock."""
    skills = [ReviewableSkill(kc, True, 0.9, _NOW) for kc in KC]
    plan = plan_study(skills, _NOW)
    assert plan.due_reviews == ()
    assert plan.unlocked_next == ()
    assert plan.recommended is None


def test_plan_is_deterministic() -> None:
    skills = [ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.9, _NOW - 5 * DEFAULT_HALF_LIFE)]
    assert plan_study(skills, _NOW) == plan_study(skills, _NOW)
