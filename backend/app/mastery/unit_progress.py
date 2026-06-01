"""Unit-progress + unit-gating overlay (pure, deterministic).

This module bridges the static curriculum catalog
(:mod:`app.domain.curriculum`) to the per-KC course map
(:mod:`app.mastery.course_map`). It overlays a learner's progress onto the
unit/lesson structure the frontend renders: for each unit it derives every
lesson's status from the matching course-map node, aggregates those into a
unit-level status and a percent-complete, and applies unit gating.

It deliberately introduces **no new mastery logic** (PROJECT.md §3.13). All
lesson-status truth comes from :func:`app.mastery.course_map.build_course_map`;
the overlay only aggregates those statuses and applies *unit-level* gating.

**Unit gating is PROGRESSIVE (DEC.1 = progressive, owner-resolved 2026-05-31).**
A unit unlocks when the learner has finished the unit before it — it does **not**
consult the per-KC foundation prerequisite DAG for cross-unit gating. Concretely
(see :func:`_unit_status`): a unit whose playable lessons are all completed is
``mastered``; a unit with some progress is ``in_progress``; a unit with no
progress is ``available`` iff it is the first unit in catalog order *or* the
previous unit is ``mastered``, else ``locked``. This makes the entry-point unit
always reachable by a fresh learner (the old DAG-per-first-KC gate wrongly locked
Unit 1 and inverted Unit 8 to "available"), and makes each later unit unlock only
when its predecessor is mastered. The foundation fraction skills remain a
remediation drop-down (CURRICULUM_STANDARD.md §11), **not** a start gate, so the
KC prerequisite DAG is no longer consulted here.

Pure: no DB, no SymPy, no LLM, no clock. The course map is computed upstream
with an injected ``now``; this overlay only reshapes already-derived state,
so it is deterministic for a given input.

One lesson-level fallback is intentionally conservative (see DAT.6 and the open
decision DEC.3 in the team tracker):

* **Forward-declared / missing KCs (lesson level).** Many catalog lessons
  carry a ``kc_id`` that is a forward-declared *string* not yet in
  :class:`KnowledgeComponentId` (e.g. the Decimals unit), or ``None`` (a
  lesson with no KC yet). Such lessons cannot be resolved to a course-map
  node, so their status defaults to :attr:`CourseNodeStatus.AVAILABLE` with
  ``probability=None``. ``AVAILABLE`` is a *neutral placeholder*, not a new
  "coming soon" status. Whether these should instead surface a distinct
  ``coming_soon`` state is open (DEC.3) and is escalated to the owner.

**Concept-only lessons** (``concept_only=True``, the four non-arithmetic Unit-8
financial-literacy items — DEC.FINLIT) are excluded from the unit-level
mastered/percent aggregation: they have no tutor mechanism to complete, so a unit
must not be held back from ``mastered`` by lessons that can never be mastered.
This keeps progression honest (e.g. Unit 8 completes on its two SymPy-graded
lessons, so Unit 7 reaching mastered correctly unlocks Unit 8).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.curriculum import CatalogUnit
from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
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
        playable: ``True`` when the lesson's ``kc_id`` resolves to a
            CONTENT-COMPLETE KC (a member of ``LIVE_KCS`` — generator + spec +
            hints), so ``POST /session`` can actually serve it. ``False`` for a
            forward-declared/unbuilt ``kc_id`` or ``None``. This is the single
            authoritative "can the tutor start this lesson" flag the frontend
            gates its "coming soon" notice on (replacing the stale hardcoded
            frontend ``LIVE_KCS``); it reuses the same ``LIVE_KCS`` membership
            ``_resolve_kc`` already computes, so it cannot drift from the
            backend's own gating.
        concept_only: ``True`` for a lesson we deliberately chose NOT to build as
            an interactive tutor lesson — a pure-concept TEKS item with no
            SymPy/tutor mechanism (DEC.FINLIT: the four non-arithmetic Unit-8
            financial-literacy lessons). Mirrored straight from the catalog
            ``CatalogLesson.concept_only``; the overlay adds no logic of its own.
            It lets the surface render an honest "concept lesson" state instead of
            the misleading "coming soon" a ``playable=False`` lesson would show.
    """

    lesson_slug: str
    kc_id: str | None
    status: CourseNodeStatus
    probability: float | None
    playable: bool
    concept_only: bool


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
    """Resolve a catalog ``kc_id`` to a real, CONTENT-COMPLETE :class:`KnowledgeComponentId`.

    Returns ``None`` when ``kc_id`` is ``None``, not a member of the enum, **or** a member
    that is not yet content-complete (a Grade-6 ontology KC in ``KnowledgeComponentId`` but
    not in ``LIVE_KCS`` — no generator/spec/hints). Those are treated as forward-declared,
    exactly as they were before they entered the enum, so the course/gating behavior is
    unchanged until their content is built (T1_T2_COORDINATION.md §4; this keeps the KC
    label-space expansion behavior-preserving for the tutor).

    Args:
        kc_id: The raw catalog ``kc_id``.

    Returns:
        The matching live enum member, or ``None`` if unresolvable / not yet built.
    """
    if kc_id is None:
        return None
    try:
        kc = KnowledgeComponentId(kc_id)
    except ValueError:
        return None
    return kc if kc in LIVE_KCS else None


def _lesson_progress(
    lesson_slug: str,
    kc_id: str | None,
    nodes_by_kc: dict[KnowledgeComponentId, CourseNode],
    *,
    concept_only: bool,
) -> LessonProgress:
    """Derive one lesson's progress from the course map.

    A lesson maps to a node only when its ``kc_id`` resolves to a real KC
    *and* that KC has a node in the course map. Otherwise it falls back to
    the neutral :attr:`CourseNodeStatus.AVAILABLE` placeholder (DEC.3).

    Args:
        lesson_slug: The lesson slug.
        kc_id: The lesson's raw catalog ``kc_id``.
        nodes_by_kc: Course-map nodes indexed by KC.
        concept_only: The catalog lesson's ``concept_only`` flag, mirrored
            straight through (no logic of its own — DEC.FINLIT).

    Returns:
        The :class:`LessonProgress` for this lesson.
    """
    resolved = _resolve_kc(kc_id)
    # ``_resolve_kc`` returns a member only when ``kc_id`` is a CONTENT-COMPLETE KC
    # (in ``LIVE_KCS``), so a non-None resolution is exactly "the tutor can serve this
    # lesson" — the authoritative ``playable`` signal (reused, never re-derived).
    playable = resolved is not None
    node = nodes_by_kc.get(resolved) if resolved is not None else None
    if node is None:
        return LessonProgress(
            lesson_slug=lesson_slug,
            kc_id=kc_id,
            status=CourseNodeStatus.AVAILABLE,
            probability=None,
            playable=playable,
            concept_only=concept_only,
        )
    return LessonProgress(
        lesson_slug=lesson_slug,
        kc_id=kc_id,
        status=node.status,
        probability=node.probability,
        playable=playable,
        concept_only=concept_only,
    )


def _unit_status(
    lessons: tuple[LessonProgress, ...],
    *,
    is_first_unit: bool,
    prev_unit_mastered: bool,
) -> UnitStatus:
    """Aggregate lesson statuses + PROGRESSIVE gating into a unit status.

    Resolution order (DEC.1 = progressive, owner-resolved 2026-05-31):

    1. **All playable lessons completed** (mastered or due-for-review) ->
       ``mastered``. Aggregation is over *playable* (non-``concept_only``)
       lessons only: concept-only lessons (DEC.FINLIT) have no tutor mechanism
       and can never be mastered, so they must not hold a unit back from
       ``mastered``.
    2. **Any real progress** (some lesson in_progress/mastered/due_review, but
       not all completed) -> ``in_progress``. Real progress beats gating: a
       unit with progress is never reported ``locked``, mirroring
       :func:`app.mastery.course_map.build_course_map`.
    3. **Otherwise (no progress), progression decides.** The unit is
       ``available`` when it is the **first unit in catalog order** OR the
       **previous unit is mastered**, else ``locked``. This is *unit-level*
       progression — it does **not** consult the per-KC prerequisite DAG (the
       foundation fraction skills are a remediation drop-down, not a start
       gate; CURRICULUM_STANDARD.md §11).

    Args:
        lessons: This unit's per-lesson progress, in order.
        is_first_unit: ``True`` for the first unit in catalog order (always
            available to a fresh learner).
        prev_unit_mastered: ``True`` when the immediately preceding unit (in
            catalog order) is ``mastered``.

    Returns:
        The aggregated :class:`UnitStatus`.
    """
    # Aggregate over playable lessons only — concept-only lessons can never be
    # mastered, so including them would permanently block ``mastered``.
    statuses = [lp.status for lp in lessons if not lp.concept_only]
    if statuses and all(s in _COMPLETED_STATUSES for s in statuses):
        return UnitStatus.MASTERED
    if any(s in _PROGRESS_STATUSES for s in statuses):
        return UnitStatus.IN_PROGRESS

    if is_first_unit or prev_unit_mastered:
        return UnitStatus.AVAILABLE
    return UnitStatus.LOCKED


def _percent_complete(lessons: tuple[LessonProgress, ...]) -> float:
    """Fraction of PLAYABLE lessons completed (mastered or due-for-review).

    ``DUE_REVIEW`` counts as completed-but-decayed: the learner has covered
    the material, so it is included in the numerator. Concept-only lessons
    (``concept_only=True``, DEC.FINLIT) are excluded from both numerator and
    denominator — they have no tutor mechanism to complete, so counting them
    would cap a unit's percent below 100% even when every playable lesson is
    done (this matches the ``mastered`` aggregation in :func:`_unit_status`).

    Args:
        lessons: This unit's per-lesson progress.

    Returns:
        A value in ``[0.0, 1.0]``. A unit with no playable lessons yields
        ``0.0``.
    """
    playable = [lp for lp in lessons if not lp.concept_only]
    if not playable:
        return 0.0
    done = sum(1 for lp in playable if lp.status in _COMPLETED_STATUSES)
    return done / len(playable)


def build_unit_progress(
    units: tuple[CatalogUnit, ...],
    course_nodes: tuple[CourseNode, ...],
    confirmed: frozenset[KnowledgeComponentId],
) -> tuple[UnitProgress, ...]:
    """Overlay learner progress onto the catalog, per unit.

    For each unit (in catalog order) this derives every lesson's status from
    the matching course-map node, aggregates lesson statuses into a unit
    status + percent-complete, and applies **progressive** unit gating
    (DEC.1 = progressive): a unit unlocks when it is first in order or the
    previous unit is mastered. It adds no mastery logic of its own — all
    lesson-status truth comes from ``course_nodes``.

    Args:
        units: The catalog units, already in display order.
        course_nodes: The per-KC course map from
            :func:`app.mastery.course_map.build_course_map`.
        confirmed: The learner's confirmed-mastered KC set. Retained for
            signature stability and lesson-status callers; the progressive
            unit gate (DEC.1) does not consult it (cross-unit ordering is
            unit-level, not per-KC DAG).

    Returns:
        One :class:`UnitProgress` per unit, in the same order as ``units``.
    """
    del confirmed  # progressive gating is unit-level; the per-KC DAG is not consulted here
    nodes_by_kc = {node.kc: node for node in course_nodes}
    result: list[UnitProgress] = []
    prev_unit_mastered = False
    for index, unit in enumerate(units):
        lessons = tuple(
            _lesson_progress(
                lesson.slug, lesson.kc_id, nodes_by_kc, concept_only=lesson.concept_only
            )
            for lesson in unit.lessons
        )
        status = _unit_status(
            lessons,
            is_first_unit=index == 0,
            prev_unit_mastered=prev_unit_mastered,
        )
        result.append(
            UnitProgress(
                unit_slug=unit.slug,
                status=status,
                percent_complete=_percent_complete(lessons),
                lessons=lessons,
            )
        )
        prev_unit_mastered = status is UnitStatus.MASTERED
    return tuple(result)
