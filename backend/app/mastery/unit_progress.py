"""Unit-progress + unit-gating overlay (pure, deterministic).

This module bridges the static curriculum catalog
(:mod:`app.domain.curriculum`) to the per-KC course map
(:mod:`app.mastery.course_map`). It overlays a learner's progress onto the
unit/lesson structure the frontend renders: for each unit it derives every
lesson's status from the matching course-map node, aggregates those into a
unit-level status and a percent-complete, and applies unit gating.

It deliberately introduces **no new mastery logic** (PROJECT.md §3.13). All
status truth comes from :func:`app.mastery.course_map.build_course_map`, and
all gating reuses the one KC prerequisite DAG via
:func:`app.domain.prerequisites.unlocked` — there is no second lock system.

Pure: no DB, no SymPy, no LLM, no clock. The course map is computed upstream
with an injected ``now``; this overlay only reshapes already-derived state,
so it is deterministic for a given input.

Two fallback decisions are intentionally conservative (see DAT.6 / DAT.7 and
the open decision DEC.3 in the team tracker):

* **Forward-declared / missing KCs (lesson level).** Many catalog lessons
  carry a ``kc_id`` that is a forward-declared *string* not yet in
  :class:`KnowledgeComponentId` (e.g. the Decimals unit), or ``None`` (a
  lesson with no KC yet). Such lessons cannot be resolved to a course-map
  node, so their status defaults to :attr:`CourseNodeStatus.AVAILABLE` with
  ``probability=None``. ``AVAILABLE`` is a *neutral placeholder*, not a new
  "coming soon" status. Whether these should instead surface a distinct
  ``coming_soon`` state is open (DEC.3) and is escalated to the owner.

* **Forward-declared / missing first-lesson KC (unit gating).** A unit whose
  *first* lesson has a forward-declared/``None`` KC is not in the DAG, so it
  cannot be gated against prerequisites. Such a unit defaults to
  :attr:`UnitStatus.AVAILABLE`. This means cross-unit ordering is **not**
  enforced until those KCs join the DAG.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.curriculum import CatalogUnit
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.prerequisites import unlocked
from app.mastery.course_map import CourseNode, CourseNodeStatus

# Statuses that count a lesson as "done" for percent-complete. ``DUE_REVIEW``
# is included deliberately: a due-for-review lesson was mastered once, so it
# counts as completed-but-decayed rather than incomplete — the learner has
# covered the material, the retention overlay merely flags it for revisiting.
_COMPLETED_STATUSES: frozenset[CourseNodeStatus] = frozenset(
    {CourseNodeStatus.MASTERED, CourseNodeStatus.DUE_REVIEW}
)

# Statuses that prove a learner has touched a lesson (real progress). Used to
# decide unit-level in_progress and to let progress beat the gating graph.
_PROGRESS_STATUSES: frozenset[CourseNodeStatus] = frozenset(
    {
        CourseNodeStatus.IN_PROGRESS,
        CourseNodeStatus.MASTERED,
        CourseNodeStatus.DUE_REVIEW,
    }
)


class UnitStatus(StrEnum):
    """Status of a whole unit in the unit/lesson shell.

    Serializes lowercase (``StrEnum``), matching
    :class:`app.mastery.course_map.CourseNodeStatus`.
    """

    LOCKED = "locked"
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    MASTERED = "mastered"


@dataclass(frozen=True, slots=True)
class LessonProgress:
    """A lesson's progress, derived from its KC's course-map node.

    Attributes:
        lesson_slug: The catalog lesson slug.
        kc_id: The lesson's raw catalog ``kc_id`` (a real KC id string, a
            forward-declared string, or ``None``).
        status: The lesson status — the matching node's status when the KC
            resolves to a real, mapped node, otherwise
            :attr:`CourseNodeStatus.AVAILABLE` (the neutral placeholder).
        probability: The node's mastery probability when resolved, else
            ``None``.
    """

    lesson_slug: str
    kc_id: str | None
    status: CourseNodeStatus
    probability: float | None


@dataclass(frozen=True, slots=True)
class UnitProgress:
    """A unit's aggregated progress over its lessons.

    Attributes:
        unit_slug: The catalog unit slug.
        status: The aggregated unit status (see :func:`build_unit_progress`).
        percent_complete: Fraction of lessons completed, in ``[0.0, 1.0]``,
            where "completed" means mastered or due-for-review.
        lessons: Per-lesson progress, in catalog lesson order.
    """

    unit_slug: str
    status: UnitStatus
    percent_complete: float
    lessons: tuple[LessonProgress, ...]


def _resolve_kc(kc_id: str | None) -> KnowledgeComponentId | None:
    """Resolve a catalog ``kc_id`` to a real :class:`KnowledgeComponentId`.

    Returns ``None`` when ``kc_id`` is ``None`` or a forward-declared string
    that is not (yet) a member of the enum.

    Args:
        kc_id: The raw catalog ``kc_id``.

    Returns:
        The matching enum member, or ``None`` if unresolvable.
    """
    if kc_id is None:
        return None
    try:
        return KnowledgeComponentId(kc_id)
    except ValueError:
        return None


def _lesson_progress(
    lesson_slug: str,
    kc_id: str | None,
    nodes_by_kc: dict[KnowledgeComponentId, CourseNode],
) -> LessonProgress:
    """Derive one lesson's progress from the course map.

    A lesson maps to a node only when its ``kc_id`` resolves to a real KC
    *and* that KC has a node in the course map. Otherwise it falls back to
    the neutral :attr:`CourseNodeStatus.AVAILABLE` placeholder (DEC.3).

    Args:
        lesson_slug: The lesson slug.
        kc_id: The lesson's raw catalog ``kc_id``.
        nodes_by_kc: Course-map nodes indexed by KC.

    Returns:
        The :class:`LessonProgress` for this lesson.
    """
    resolved = _resolve_kc(kc_id)
    node = nodes_by_kc.get(resolved) if resolved is not None else None
    if node is None:
        return LessonProgress(
            lesson_slug=lesson_slug,
            kc_id=kc_id,
            status=CourseNodeStatus.AVAILABLE,
            probability=None,
        )
    return LessonProgress(
        lesson_slug=lesson_slug,
        kc_id=kc_id,
        status=node.status,
        probability=node.probability,
    )


def _unit_status(
    lessons: tuple[LessonProgress, ...],
    first_kc_id: str | None,
    confirmed: frozenset[KnowledgeComponentId],
) -> UnitStatus:
    """Aggregate lesson statuses + gating into a unit status.

    Resolution order (PROJECT.md §3.13; DEC.1):

    1. **All lessons completed** (mastered or due-for-review) -> ``mastered``.
    2. **Any real progress** (some lesson in_progress/mastered/due_review, but
       not all completed) -> ``in_progress``. Real progress beats the gating
       graph: a unit with progress is never reported ``locked``, mirroring
       :func:`app.mastery.course_map.build_course_map`.
    3. **Otherwise, gating decides.** The unit is ``available`` when its first
       lesson's KC is unlocked per the prerequisite DAG (a root with no
       prereqs is always unlocked), else ``locked``. A first lesson whose KC
       is forward-declared/``None`` (not in the DAG) defaults to
       ``available`` (DEC.3 / DAT.7 fallback).

    Args:
        lessons: This unit's per-lesson progress, in order.
        first_kc_id: The raw ``kc_id`` of the first lesson (gating key).
        confirmed: The learner's confirmed-mastered KC set.

    Returns:
        The aggregated :class:`UnitStatus`.
    """
    statuses = [lp.status for lp in lessons]
    if statuses and all(s in _COMPLETED_STATUSES for s in statuses):
        return UnitStatus.MASTERED
    if any(s in _PROGRESS_STATUSES for s in statuses):
        return UnitStatus.IN_PROGRESS

    first_kc = _resolve_kc(first_kc_id)
    if first_kc is None:
        # First lesson's KC is not in the DAG -> cannot gate; neutral default.
        return UnitStatus.AVAILABLE
    # A KC is "available to start" when it is unlocked per the prerequisite DAG
    # (all its prereqs confirmed and it is not itself confirmed) OR it is
    # already confirmed. ``unlocked`` deliberately excludes confirmed KCs (they
    # are review candidates, not "next to learn"), so a unit whose first lesson
    # is already mastered must not fall back to ``locked`` — we treat a
    # confirmed first KC as available too.
    if first_kc in confirmed or first_kc in unlocked(confirmed):
        return UnitStatus.AVAILABLE
    return UnitStatus.LOCKED


def _percent_complete(lessons: tuple[LessonProgress, ...]) -> float:
    """Fraction of lessons completed (mastered or due-for-review).

    ``DUE_REVIEW`` counts as completed-but-decayed: the learner has covered
    the material, so it is included in the numerator.

    Args:
        lessons: This unit's per-lesson progress.

    Returns:
        A value in ``[0.0, 1.0]``. An empty unit yields ``0.0``.
    """
    if not lessons:
        return 0.0
    done = sum(1 for lp in lessons if lp.status in _COMPLETED_STATUSES)
    return done / len(lessons)


def build_unit_progress(
    units: tuple[CatalogUnit, ...],
    course_nodes: tuple[CourseNode, ...],
    confirmed: frozenset[KnowledgeComponentId],
) -> tuple[UnitProgress, ...]:
    """Overlay learner progress onto the catalog, per unit.

    For each unit (in catalog order) this derives every lesson's status from
    the matching course-map node, aggregates lesson statuses into a unit
    status + percent-complete, and applies unit gating. It adds no mastery
    logic of its own — all status truth comes from ``course_nodes``, and all
    gating reuses the prerequisite DAG (PROJECT.md §3.13).

    Args:
        units: The catalog units, already in display order.
        course_nodes: The per-KC course map from
            :func:`app.mastery.course_map.build_course_map`.
        confirmed: The learner's confirmed-mastered KC set, used for gating.

    Returns:
        One :class:`UnitProgress` per unit, in the same order as ``units``.
    """
    nodes_by_kc = {node.kc: node for node in course_nodes}
    result: list[UnitProgress] = []
    for unit in units:
        lessons = tuple(
            _lesson_progress(lesson.slug, lesson.kc_id, nodes_by_kc) for lesson in unit.lessons
        )
        first_kc_id = unit.lessons[0].kc_id if unit.lessons else None
        result.append(
            UnitProgress(
                unit_slug=unit.slug,
                status=_unit_status(lessons, first_kc_id, confirmed),
                percent_complete=_percent_complete(lessons),
                lessons=lessons,
            )
        )
    return tuple(result)
