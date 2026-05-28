"""Tests for the retention / forgetting model (Slice 6.x — spaced repetition).

Decision 0.D.6 sketched a BKT ``p_forget`` style decay for retention. A confirmed skill's
retained mastery decays with time since it was last practiced; when it falls below a review
bar the skill is "due". These tests pin the decay shape, that only CONFIRMED skills are
reviewable, and that the review plan surfaces the most-decayed skills first.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.knowledge_components import KnowledgeComponentId
from app.mastery.retention import (
    DEFAULT_HALF_LIFE,
    REVIEW_THRESHOLD,
    ReviewableSkill,
    is_due_for_review,
    next_review,
    retained_probability,
)

KC = KnowledgeComponentId  # local shorthand (a constant alias; ruff-clean, unlike `import as`)
_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def test_no_decay_at_zero_elapsed() -> None:
    """Just-practiced: retained equals the stored mastery probability."""
    assert retained_probability(0.9, timedelta(0)) == 0.9


def test_halves_after_one_half_life() -> None:
    """After one half-life the retained probability is half the stored value."""
    assert retained_probability(0.9, DEFAULT_HALF_LIFE) == 0.45


def test_decay_is_monotonic() -> None:
    """More elapsed time ⇒ less retained (never increases)."""
    a = retained_probability(0.9, timedelta(days=1))
    b = retained_probability(0.9, timedelta(days=3))
    c = retained_probability(0.9, timedelta(days=7))
    assert a > b > c


def test_unconfirmed_skill_is_never_due() -> None:
    """Review is for CONFIRMED skills only — an unconfirmed one is never 'due for review'."""
    skill = ReviewableSkill(
        kc=KC.EQUIVALENCE,
        confirmed=False,
        bkt_probability=0.9,
        last_practiced=_NOW - timedelta(days=30),  # very stale, but never confirmed
    )
    assert not is_due_for_review(skill, _NOW)


def test_freshly_confirmed_skill_is_not_due() -> None:
    """A skill confirmed moments ago is still well-retained → not due."""
    skill = ReviewableSkill(
        kc=KC.EQUIVALENCE, confirmed=True, bkt_probability=0.9, last_practiced=_NOW
    )
    assert not is_due_for_review(skill, _NOW)


def test_confirmed_skill_becomes_due_after_enough_time() -> None:
    """A confirmed skill whose retention has decayed below the bar is due for review."""
    stale = ReviewableSkill(
        kc=KC.EQUIVALENCE,
        confirmed=True,
        bkt_probability=0.9,
        last_practiced=_NOW - 3 * DEFAULT_HALF_LIFE,  # decayed to ~0.9/8 ≈ 0.11
    )
    assert retained_probability(0.9, 3 * DEFAULT_HALF_LIFE) < REVIEW_THRESHOLD
    assert is_due_for_review(stale, _NOW)


def test_next_review_returns_due_skills_most_decayed_first() -> None:
    """The plan lists due CONFIRMED skills, most-decayed first; excludes fresh + unconfirmed."""
    skills = [
        ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.9, _NOW - 5 * DEFAULT_HALF_LIFE),
        ReviewableSkill(KC.EQUIVALENCE, True, 0.9, _NOW - 2 * DEFAULT_HALF_LIFE),
        ReviewableSkill(KC.COMMON_DENOMINATOR, True, 0.9, _NOW),  # fresh → not due
        ReviewableSkill(
            KC.ADDITION_UNLIKE, False, 0.9, _NOW - 9 * DEFAULT_HALF_LIFE
        ),  # unconfirmed
    ]
    # most-decayed first; the fresh and the unconfirmed skills are excluded.
    due = next_review(skills, _NOW)
    assert due == [KC.NUMBER_LINE_PLACEMENT, KC.EQUIVALENCE]


def test_next_review_is_deterministic() -> None:
    skills = [
        ReviewableSkill(KC.EQUIVALENCE, True, 0.9, _NOW - 4 * DEFAULT_HALF_LIFE),
        ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.9, _NOW - 4 * DEFAULT_HALF_LIFE),
    ]
    assert next_review(skills, _NOW) == next_review(skills, _NOW)
