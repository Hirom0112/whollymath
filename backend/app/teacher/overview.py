"""Per-student overview: mastery-per-KC, current unit/lesson, strengths/weaknesses (TCH.B3).

Pure projection over already-computed engine state — the course map (status + BKT probability per
KC) and the unit progress (per-lesson status + percent-complete) — plus the catalog for display
names. No DB, no clock, no new mastery logic: it reuses exactly what ``/me`` and the course
product already derive, re-shaped for a teacher reading ONE student (CLAUDE.md §7, §8.1).

Strength/weakness thresholds are taste-level cutoffs on BKT p(known), recorded here so the
decision log can see them (CLAUDE.md §8.4): a *strength* is a confirmed/mastered KC or one whose
probability has climbed past ``_STRENGTH_THRESHOLD``; a *weakness* is a TOUCHED-but-unconfirmed KC
(status ``in_progress``) still below ``_WEAKNESS_THRESHOLD``. Untouched/locked KCs are neither —
they are "not yet reached", not "struggling", so they stay off both lists.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.api.schemas import AssignableUnitView, KcMasteryView, KcStatus
from app.domain.curriculum import CatalogUnit
from app.domain.knowledge_components import get_kc
from app.mastery.course_map import CourseNode, CourseNodeStatus
from app.mastery.unit_progress import UnitProgress

# A KC at or above this BKT p(known) reads as a strength (confirmed/mastered always qualifies).
_STRENGTH_THRESHOLD = 0.7
# A touched-but-unconfirmed KC below this p(known) reads as a weakness.
_WEAKNESS_THRESHOLD = 0.5

# Lesson/unit statuses that mean "already done" — used to find the FIRST not-yet-done lesson as
# the student's current lesson. ``due_review`` counts as done: it was mastered once.
_DONE_STATUSES: frozenset[CourseNodeStatus] = frozenset(
    {CourseNodeStatus.MASTERED, CourseNodeStatus.DUE_REVIEW}
)


def kc_masteries(course_nodes: Sequence[CourseNode]) -> list[KcMasteryView]:
    """Project each course-map node into a ``KcMasteryView`` (status + BKT probability + name).

    One row per KC in course-map (spine) order. ``CourseNodeStatus`` and ``KcStatus`` share their
    string values verbatim, so the status maps across by value.
    """
    return [
        KcMasteryView(
            kc_id=node.kc.value,
            skill_name=get_kc(node.kc).skill_name,
            # An untouched KC has no stored probability (``None``); show 0.0 p(known).
            probability=node.probability if node.probability is not None else 0.0,
            status=KcStatus(node.status.value),
        )
        for node in course_nodes
    ]


def split_strengths_weaknesses(
    masteries: Sequence[KcMasteryView],
) -> tuple[list[KcMasteryView], list[KcMasteryView]]:
    """Partition KC rows into (strengths, weaknesses) by status + BKT probability.

    Strengths: mastered/due-review KCs, or in-progress KCs at/above ``_STRENGTH_THRESHOLD`` —
    sorted strongest-first. Weaknesses: in-progress KCs below ``_WEAKNESS_THRESHOLD`` — sorted
    weakest-first (the most urgent gap on top). Untouched (``available``/``locked``) KCs are on
    neither list: they are not-yet-reached, not strengths and not struggles.
    """
    strengths: list[KcMasteryView] = []
    weaknesses: list[KcMasteryView] = []
    for m in masteries:
        if m.status in (KcStatus.MASTERED, KcStatus.DUE_REVIEW):
            strengths.append(m)
        elif m.status is KcStatus.IN_PROGRESS:
            if m.probability >= _STRENGTH_THRESHOLD:
                strengths.append(m)
            elif m.probability < _WEAKNESS_THRESHOLD:
                weaknesses.append(m)
    strengths.sort(key=lambda m: m.probability, reverse=True)
    weaknesses.sort(key=lambda m: m.probability)
    return strengths, weaknesses


def current_unit_and_lesson(
    unit_progress: Sequence[UnitProgress],
    catalog: Sequence[CatalogUnit],
) -> tuple[str | None, str | None, float]:
    """The student's current unit title, current lesson title, and that unit's percent-complete.

    The current unit is the first one in progress, else the first available (not-locked) one —
    matching what the student shell would put them in next. The current lesson is the first lesson
    in that unit not yet done. Titles come from the catalog (progress carries only slugs).
    ``(None, None, 0.0)`` when there is no in-progress or available unit (everything locked/empty).
    """
    units_by_slug = {u.slug: u for u in catalog}
    in_progress = [up for up in unit_progress if up.status.value == "in_progress"]
    available = [up for up in unit_progress if up.status.value == "available"]
    current = in_progress[0] if in_progress else (available[0] if available else None)
    if current is None:
        return None, None, 0.0

    cat_unit = units_by_slug.get(current.unit_slug)
    unit_title = cat_unit.title if cat_unit is not None else None

    lesson_title: str | None = None
    if cat_unit is not None:
        lesson_titles = {lesson.slug: lesson.title for lesson in cat_unit.lessons}
        next_lesson = next(
            (lp for lp in current.lessons if lp.status not in _DONE_STATUSES),
            None,
        )
        if next_lesson is not None:
            lesson_title = lesson_titles.get(next_lesson.lesson_slug)
    return unit_title, lesson_title, current.percent_complete


def assignable_units(
    unit_progress: Sequence[UnitProgress],
    catalog: Sequence[CatalogUnit],
) -> list[AssignableUnitView]:
    """Every catalog unit a teacher can assign next, with an advisory ``available`` flag.

    ``available`` is ``True`` when the unit is not locked (its prereqs are met). It is advisory
    only: a teacher may assign a locked unit too (TCH.Q5 — the teacher's judgment overrides the
    gate). Order follows the catalog's display order.
    """
    status_by_slug = {up.unit_slug: up.status for up in unit_progress}
    out: list[AssignableUnitView] = []
    for unit in catalog:
        status = status_by_slug.get(unit.slug)
        available = status is not None and status.value != "locked"
        out.append(AssignableUnitView(unit_id=unit.slug, title=unit.title, available=available))
    return out


__all__ = [
    "assignable_units",
    "current_unit_and_lesson",
    "kc_masteries",
    "split_strengths_weaknesses",
]
