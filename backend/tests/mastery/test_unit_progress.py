"""Tests for the unit-progress + unit-gating overlay (DAT.6 / DAT.7).

These tests assert the *pure* logic that bridges the curriculum catalog
(:mod:`app.domain.curriculum`) to the per-KC course map
(:mod:`app.mastery.course_map`). They are written first (TDD, CLAUDE.md §2):
unit progress aggregation and gating are load-bearing for the student
unit/lesson shell, so every rule below has an assertion.

Catalog facts the fixtures rely on (transcribed from ``curriculum.py``):

* Only the five fraction KCs are real ``KnowledgeComponentId`` members. The
  catalog lessons that resolve to them are ``u2_l0`` (``KC_equivalence``),
  ``u2_l1`` (``KC_addition_unlike``), and ``u3_l2`` / ``u3_l3`` (both
  ``KC_number_line_placement``). Every other lesson's ``kc_id`` is a
  forward-declared string or ``None``.
* Unit ``u2``'s FIRST lesson (``u2_l0``) is ``KC_equivalence`` — a DAG node
  whose prereq is ``NUMBER_LINE_PLACEMENT``. So ``u2`` is gated.
* Unit ``u3``'s first lesson (``u3_l1``) is ``KC_signed_numbers`` — now a BUILT
  DAG node (Grade-6 build, 2026-05-30) whose prereq is ``NUMBER_LINE_PLACEMENT``,
  so ``u3`` is gated (LOCKED until that prereq is confirmed). A unit that still
  defaults available is one whose first lesson is forward-declared/``None`` (e.g.
  ``u4`` → ``KC_exponents``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.curriculum import CatalogLesson, CatalogUnit, all_units
from app.domain.knowledge_components import KnowledgeComponentId
from app.mastery.course_map import (
    CourseNode,
    CourseNodeStatus,
    build_course_map,
)
from app.mastery.retention import DEFAULT_HALF_LIFE, ReviewableSkill
from app.mastery.unit_progress import (
    LessonProgress,
    UnitProgress,
    UnitStatus,
    build_unit_progress,
)

KC = KnowledgeComponentId
_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def _course(skills: list[ReviewableSkill]) -> tuple[CourseNode, ...]:
    return build_course_map(skills, _NOW)


def _by_slug(units: tuple[UnitProgress, ...]) -> dict[str, UnitProgress]:
    return {u.unit_slug: u for u in units}


def _lessons_by_slug(unit: UnitProgress) -> dict[str, LessonProgress]:
    return {lp.lesson_slug: lp for lp in unit.lessons}


# --- Fresh learner ---------------------------------------------------------


def test_fresh_learner_fraction_lessons_show_course_map_statuses() -> None:
    """U2's real-KC lessons reflect the course-map node status (DAT.6)."""
    progress = build_unit_progress(all_units(), _course([]), frozenset())
    u2 = _by_slug(progress)["u2"]
    lessons = _lessons_by_slug(u2)

    # u2_l0 -> KC_equivalence; prereq NUMBER_LINE_PLACEMENT unmet -> LOCKED.
    assert lessons["u2_l0"].kc_id == "KC_equivalence"
    assert lessons["u2_l0"].status is CourseNodeStatus.LOCKED
    assert lessons["u2_l0"].probability is None
    # u2_l1 -> KC_addition_unlike; also locked on a fresh learner.
    assert lessons["u2_l1"].status is CourseNodeStatus.LOCKED


def test_fresh_learner_number_line_lesson_available_as_root() -> None:
    """U3's number-line lessons map to the AVAILABLE root node."""
    progress = build_unit_progress(all_units(), _course([]), frozenset())
    u3 = _by_slug(progress)["u3"]
    lessons = _lessons_by_slug(u3)
    # u3_l2 / u3_l3 reuse KC_number_line_placement (the root) -> AVAILABLE.
    assert lessons["u3_l2"].kc_id == "KC_number_line_placement"
    assert lessons["u3_l2"].status is CourseNodeStatus.AVAILABLE
    assert lessons["u3_l3"].status is CourseNodeStatus.AVAILABLE


def test_fresh_learner_unbuilt_lessons_default_available_zero_percent() -> None:
    """Forward-declared / None KC lessons default to AVAILABLE; unit 0% (DAT.6)."""
    progress = build_unit_progress(all_units(), _course([]), frozenset())

    # u1 now MIXES built lessons with placeholders: KC_unit_rate (u1_l3/l4) is content-complete
    # (Grade-6 build) and gates on its prerequisite, so it is not an AVAILABLE placeholder. Every
    # still-unbuilt (forward-declared) u1 lesson defaults to the AVAILABLE placeholder.
    from app.domain.knowledge_components import LIVE_KCS

    u1 = _by_slug(progress)["u1"]
    for lp in u1.lessons:
        if lp.kc_id and KnowledgeComponentId(lp.kc_id) in LIVE_KCS:
            continue  # a built lesson — gated by its prereq, not a placeholder
        assert lp.status is CourseNodeStatus.AVAILABLE
        assert lp.probability is None
    assert u1.percent_complete == 0.0

    # u2_l7 has kc_id None (interleave gate) -> AVAILABLE placeholder.
    u2 = _by_slug(progress)["u2"]
    gate = _lessons_by_slug(u2)["u2_l7"]
    assert gate.kc_id is None
    assert gate.status is CourseNodeStatus.AVAILABLE
    assert gate.probability is None

    # No progress anywhere -> 0% across every unit.
    assert all(u.percent_complete == 0.0 for u in progress)


# --- Progress / percent math ----------------------------------------------


def test_confirmed_kc_marks_lesson_mastered_and_raises_percent() -> None:
    """Mastering KC_equivalence marks u2_l0 MASTERED and lifts u2's percent."""
    confirmed = frozenset({KC.EQUIVALENCE})
    course = _course(
        [
            # Confirm the prereq so KC_equivalence is reachable + confirmed.
            ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.95, _NOW),
            ReviewableSkill(KC.EQUIVALENCE, True, 0.93, _NOW),
        ]
    )
    progress = build_unit_progress(all_units(), course, confirmed)
    u2 = _by_slug(progress)["u2"]
    lessons = _lessons_by_slug(u2)

    assert lessons["u2_l0"].status is CourseNodeStatus.MASTERED
    assert lessons["u2_l0"].probability == 0.93
    # 1 of u2's 8 lessons complete.
    assert u2.percent_complete == 1 / 8
    # Some progress but not all -> in_progress.
    assert u2.status is UnitStatus.IN_PROGRESS


def test_due_review_counts_as_complete_for_percent() -> None:
    """A mastered-but-decayed (due_review) lesson counts toward percent (DAT.6)."""
    long_ago = _NOW - 4 * DEFAULT_HALF_LIFE
    course = _course([ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.95, long_ago)])
    node = next(n for n in course if n.kc is KC.NUMBER_LINE_PLACEMENT)
    assert node.status is CourseNodeStatus.DUE_REVIEW

    progress = build_unit_progress(all_units(), course, frozenset({KC.NUMBER_LINE_PLACEMENT}))
    u3 = _by_slug(progress)["u3"]
    lessons = _lessons_by_slug(u3)
    # u3_l2 + u3_l3 both reuse the number-line KC -> both due_review.
    assert lessons["u3_l2"].status is CourseNodeStatus.DUE_REVIEW
    assert lessons["u3_l3"].status is CourseNodeStatus.DUE_REVIEW
    # due_review counts as completed-but-decayed: 2 of u3's 7 lessons.
    assert u3.percent_complete == 2 / 7


def test_all_lessons_complete_makes_unit_mastered() -> None:
    """A synthetic unit whose only lesson is mastered -> unit mastered, 100%."""
    synthetic = (
        CatalogUnit(
            slug="solo",
            title="Solo",
            order=1,
            ccss_cluster="x",
            teks_cluster="x",
            description="x",
            lessons=(
                CatalogLesson(
                    slug="solo_l1",
                    unit_slug="solo",
                    order=1,
                    title="Number line",
                    kc_id="KC_number_line_placement",
                    ccss_code="6.NS.6",
                    teks_code="6.2C",
                    description="x",
                ),
            ),
        ),
    )
    course = _course([ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.95, _NOW)])
    progress = build_unit_progress(synthetic, course, frozenset({KC.NUMBER_LINE_PLACEMENT}))
    assert progress[0].status is UnitStatus.MASTERED
    assert progress[0].percent_complete == 1.0


# --- Gating (DAT.7 / DEC.1) ------------------------------------------------


def test_gating_locks_unit_when_first_lesson_kc_prereqs_unmet() -> None:
    """U2 is LOCKED on a fresh learner: u2_l0's KC prereq is unmet."""
    progress = build_unit_progress(all_units(), _course([]), frozenset())
    assert _by_slug(progress)["u2"].status is UnitStatus.LOCKED


def test_gating_unlocks_unit_when_first_lesson_kc_prereqs_met() -> None:
    """Confirming NUMBER_LINE_PLACEMENT unlocks U2 (KC_equivalence available)."""
    confirmed = frozenset({KC.NUMBER_LINE_PLACEMENT})
    course = _course([ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.95, _NOW)])
    progress = build_unit_progress(all_units(), course, confirmed)
    assert _by_slug(progress)["u2"].status is UnitStatus.AVAILABLE


def test_gating_root_first_lesson_unit_available() -> None:
    """A unit whose first lesson KC is a DAG root -> available even fresh."""
    synthetic = (
        CatalogUnit(
            slug="root-first",
            title="Root First",
            order=1,
            ccss_cluster="x",
            teks_cluster="x",
            description="x",
            lessons=(
                CatalogLesson(
                    slug="rf_l1",
                    unit_slug="root-first",
                    order=1,
                    title="Number line",
                    kc_id="KC_number_line_placement",
                    ccss_code="6.NS.6",
                    teks_code="6.2C",
                    description="x",
                ),
            ),
        ),
    )
    progress = build_unit_progress(synthetic, _course([]), frozenset())
    assert progress[0].status is UnitStatus.AVAILABLE


def test_gating_forward_declared_first_lesson_defaults_available() -> None:
    """A unit whose first lesson is a forward-declared (unbuilt) KC defaults to available (DEC.3).

    U4's first lesson (KC_exponents) is not yet content-complete, so it is not in the prerequisite
    DAG and cannot gate — the unit falls back to the neutral AVAILABLE placeholder. U1 and U3 are
    NO LONGER such cases: their first lessons (KC_ratio_language, KC_signed_numbers) are now BUILT
    (Grade-6 build, 2026-05-30), so they are real DAG nodes that gate on their prerequisites —
    covered below.
    """
    progress = build_unit_progress(all_units(), _course([]), frozenset())
    assert _by_slug(progress)["u4"].status is UnitStatus.AVAILABLE


def test_gating_built_first_lesson_locks_until_prereq_confirmed() -> None:
    """U1/U3 first lessons are now BUILT KCs, so each gates on its prerequisite (not AVAILABLE).

    With nothing confirmed, KC_ratio_language (U1) and KC_signed_numbers (U3) are locked — their
    prerequisites (and those prerequisites' own prereqs) are unconfirmed — so each unit is LOCKED,
    not the old forward-declared AVAILABLE default. This is the intended consequence of making
    u1_l1 / u3_l1 content-complete (Grade-6 build, 2026-05-30): real gating replaces the neutral
    placeholder once the first lesson exists.
    """
    progress = build_unit_progress(all_units(), _course([]), frozenset())
    assert _by_slug(progress)["u1"].status is UnitStatus.LOCKED
    assert _by_slug(progress)["u3"].status is UnitStatus.LOCKED


def test_gating_none_first_lesson_defaults_available() -> None:
    """A unit whose first lesson has kc_id None defaults to available (DEC.3)."""
    synthetic = (
        CatalogUnit(
            slug="none-first",
            title="None First",
            order=1,
            ccss_cluster="x",
            teks_cluster="x",
            description="x",
            lessons=(
                CatalogLesson(
                    slug="nf_l1",
                    unit_slug="none-first",
                    order=1,
                    title="Gate",
                    kc_id=None,
                    ccss_code="6.NS.1",
                    teks_code="6.3",
                    description="x",
                ),
            ),
        ),
    )
    progress = build_unit_progress(synthetic, _course([]), frozenset())
    assert progress[0].status is UnitStatus.AVAILABLE


def test_progress_beats_the_graph() -> None:
    """A unit with real progress is at least in_progress even if graph locks it.

    U2 is gated on NUMBER_LINE_PLACEMENT (locked with nothing confirmed), but a
    learner who has *touched* KC_equivalence (u2_l0) -> in_progress wins,
    mirroring course_map's "real progress beats the graph".
    """
    # Touched but unconfirmed -> course node IN_PROGRESS for KC_equivalence.
    course = _course([ReviewableSkill(KC.EQUIVALENCE, False, 0.4, _NOW)])
    progress = build_unit_progress(all_units(), course, frozenset())
    u2 = _by_slug(progress)["u2"]
    assert _lessons_by_slug(u2)["u2_l0"].status is CourseNodeStatus.IN_PROGRESS
    assert u2.status is UnitStatus.IN_PROGRESS


# --- Ordering / determinism ------------------------------------------------


def test_units_returned_in_catalog_order() -> None:
    progress = build_unit_progress(all_units(), _course([]), frozenset())
    assert [u.unit_slug for u in progress] == [u.slug for u in all_units()]


def test_lessons_returned_in_catalog_order() -> None:
    progress = build_unit_progress(all_units(), _course([]), frozenset())
    u2_catalog = next(u for u in all_units() if u.slug == "u2")
    u2 = _by_slug(progress)["u2"]
    assert [lp.lesson_slug for lp in u2.lessons] == [lesson.slug for lesson in u2_catalog.lessons]


def test_deterministic() -> None:
    course = _course([ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.95, _NOW)])
    a = build_unit_progress(all_units(), course, frozenset({KC.NUMBER_LINE_PLACEMENT}))
    b = build_unit_progress(all_units(), course, frozenset({KC.NUMBER_LINE_PLACEMENT}))
    assert a == b


def test_empty_unit_is_zero_percent_and_not_crash() -> None:
    """A unit with no lessons yields 0% and is gated (no first lesson)."""
    synthetic = (
        CatalogUnit(
            slug="empty",
            title="Empty",
            order=1,
            ccss_cluster="x",
            teks_cluster="x",
            description="x",
            lessons=(),
        ),
    )
    progress = build_unit_progress(synthetic, _course([]), frozenset())
    assert progress[0].percent_complete == 0.0
    # No first lesson -> first_kc_id is None -> neutral available default.
    assert progress[0].status is UnitStatus.AVAILABLE


def test_unit_status_serializes_lowercase() -> None:
    assert UnitStatus.LOCKED.value == "locked"
    assert UnitStatus.AVAILABLE.value == "available"
    assert UnitStatus.IN_PROGRESS.value == "in_progress"
    assert UnitStatus.MASTERED.value == "mastered"
