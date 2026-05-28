"""Retention / forgetting model for spaced repetition (Slice 6.x; decision 0.D.6).

Mastery that is never revisited rots. This module models that decay so the scheduler can
bring a confirmed skill back for review *before* it is forgotten — the "space" in spaced
repetition. It is the BKT ``p_forget`` style decay 0.D.6 sketched, kept deliberately simple:

  retained(t) = bkt_probability · (1/2) ^ (elapsed / HALF_LIFE)

i.e. a confirmed skill's *retained* mastery halves every ``HALF_LIFE`` of no practice. When
retained falls below ``REVIEW_THRESHOLD`` the skill is "due". Practicing it resets the clock
(``last_practiced`` moves to now), so retention recovers — review pushes the next due date out.

Scope + honesty: this is continuous decay from the last-practice time, NOT yet Leitner's
*expanding* intervals (a confirmed-twice skill should decay slower than a confirmed-once one);
that enhancement wants a per-skill review count we don't store yet — flagged, not faked. And
spacing only has visible effect ACROSS sessions separated by real time (a single demo session
has no gap to space over) — which is exactly what the persisted ``MasteryState.updated_at`` +
the persistence layer (PL.1) enable. Pure: no DB/LLM/SymPy, deterministic in its inputs
(``now`` is passed in, never read from the clock here — CLAUDE.md §8.1, §4.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.knowledge_components import KnowledgeComponentId

# A confirmed skill's retained mastery halves after this long without practice. Tunable
# (weeks 4-5 family, like the other 0.D.5 tunings); 3 days is a reasonable review cadence
# for a within-unit skill.
DEFAULT_HALF_LIFE: timedelta = timedelta(days=3)

# Retained mastery below this bar ⇒ due for review. Sits below τ=0.85 (a skill needn't have
# decayed all the way to "forgotten" to be worth a refresh) but well above chance.
REVIEW_THRESHOLD: float = 0.7


@dataclass(frozen=True)
class ReviewableSkill:
    """One learner-skill's retention inputs (a tutor-agnostic projection of MasteryState).

    Decoupled from the DB model so the retention math has no DB dependency: the service maps
    a persisted ``MasteryState`` → this. ``confirmed`` gates reviewability (only mastered
    skills are reviewed); ``bkt_probability`` is the mastery level review decays from;
    ``last_practiced`` is when it was last exercised (``MasteryState.updated_at``).
    """

    kc: KnowledgeComponentId
    confirmed: bool
    bkt_probability: float
    last_practiced: datetime


def retained_probability(
    bkt_probability: float,
    elapsed: timedelta,
    *,
    half_life: timedelta = DEFAULT_HALF_LIFE,
) -> float:
    """The decayed mastery probability after ``elapsed`` without practice (half-life decay).

    Equals ``bkt_probability`` at ``elapsed == 0`` and halves every ``half_life``. Elapsed is
    clamped at 0 (a clock skew where "now" precedes the last practice is treated as no decay).
    """
    seconds = max(0.0, elapsed.total_seconds())
    return float(bkt_probability * 0.5 ** (seconds / half_life.total_seconds()))


def is_due_for_review(
    skill: ReviewableSkill,
    now: datetime,
    *,
    threshold: float = REVIEW_THRESHOLD,
    half_life: timedelta = DEFAULT_HALF_LIFE,
) -> bool:
    """Whether ``skill`` is a CONFIRMED skill whose retention has decayed below ``threshold``."""
    if not skill.confirmed:
        return False
    retained = retained_probability(
        skill.bkt_probability, now - skill.last_practiced, half_life=half_life
    )
    return retained < threshold


def next_review(
    skills: list[ReviewableSkill],
    now: datetime,
    *,
    threshold: float = REVIEW_THRESHOLD,
    half_life: timedelta = DEFAULT_HALF_LIFE,
) -> list[KnowledgeComponentId]:
    """The confirmed skills due for review, MOST-DECAYED first (deterministic ordering).

    Excludes unconfirmed skills (not reviewable) and freshly-practiced ones (still retained).
    Sorted by retained probability ascending, tie-broken by KC id, so the same inputs always
    yield the same review order (PROJECT.md §4.1).
    """
    due = [s for s in skills if is_due_for_review(s, now, threshold=threshold, half_life=half_life)]
    due.sort(
        key=lambda s: (
            retained_probability(s.bkt_probability, now - s.last_practiced, half_life=half_life),
            s.kc.value,
        )
    )
    return [s.kc for s in due]


__all__ = [
    "DEFAULT_HALF_LIFE",
    "REVIEW_THRESHOLD",
    "ReviewableSkill",
    "is_due_for_review",
    "next_review",
    "retained_probability",
]
