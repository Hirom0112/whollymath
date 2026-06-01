"""Tests for the unit-progress + unit-gating overlay (DAT.6 / DAT.7).

These tests assert the *pure* logic that bridges the curriculum catalog
(:mod:`app.domain.curriculum`) to the per-KC course map
(:mod:`app.mastery.course_map`). They are written first (TDD, CLAUDE.md §2):
unit progress aggregation and gating are load-bearing for the student
unit/lesson shell, so every rule below has an assertion.

Unit gating is PROGRESSIVE (DEC.1 = progressive, owner-resolved 2026-05-31):
a unit unlocks when it is FIRST in catalog order or the PREVIOUS unit is
mastered — it does NOT consult the per-KC prerequisite DAG. So on a fresh
learner the first catalog unit (``u1``) is ``available`` and every later unit
is ``locked`` until its predecessor is mastered. Lesson-level statuses still
come from the course map; only the per-KC *unit gate* is gone.

Catalog facts the fixtures rely on (transcribed from ``curriculum.py``):

* ``u1`` is the FIRST unit in catalog order, so it is always ``available`` to a
  fresh learner. Its six lessons all resolve to content-complete Grade-6 KCs
  (``KC_ratio_language`` … ``KC_unit_conversion``), so mastering all six makes
  ``u1`` ``mastered`` and unlocks ``u2``.
* The catalog units in order are ``u1, u2, u3, uint, u4, u5, u6, u7, u8``
  (``uint`` — Integer Operations — sits 4th). Progression follows that order.
* ``u8``'s four financial-literacy lessons (``u8_l1, u8_l2, u8_l4, u8_l5``) are
  ``concept_only`` (DEC.FINLIT): they are excluded from the unit's
  mastered/percent aggregation, so ``u8`` completes on its two SymPy-graded
  lessons (``u8_l3, u8_l6``).
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


def test_playable_is_true_exactly_for_content_complete_kcs() -> None:
    """``playable`` is the authoritative "tutor can serve this lesson" flag.

    It must be ``True`` for exactly the lessons whose ``kc_id`` is a CONTENT-COMPLETE KC
    (in ``LIVE_KCS``) and ``False`` for forward-declared/unbuilt strings and ``None`` —
    the contract the frontend gates its "coming soon" notice on. Asserting it tracks
    ``LIVE_KCS`` membership exactly is what keeps the frontend gate from drifting (the
    stale hardcoded frontend ``LIVE_KCS`` this replaces).
    """
    from app.domain.knowledge_components import LIVE_KCS

    progress = build_unit_progress(all_units(), _course([]), frozenset())
    for unit in progress:
        for lp in unit.lessons:
            expected = lp.kc_id is not None and lp.kc_id in {kc.value for kc in LIVE_KCS}
            assert lp.playable is expected, f"{lp.lesson_slug} ({lp.kc_id})"

    # Spot-check the two namespaces explicitly: a built KC is playable, the interleave
    # gate (None kc_id) and a genuinely-unbuilt KC are not.
    lessons = {lp.lesson_slug: lp for u in progress for lp in u.lessons}
    assert lessons["u2_l0"].playable is True  # KC_equivalence — built
    assert lessons["u2_l4"].playable is True  # KC_multiply_fractions — built (namespace fix)
    assert lessons["u2_l7"].playable is False  # interleave gate, kc_id None
    assert lessons["u8_l1"].playable is False  # KC_banking — concept lesson, no tutor mechanism


def test_concept_only_is_true_exactly_for_the_four_u8_concept_lessons() -> None:
    """``concept_only`` flags the lessons we deliberately chose NOT to build as tutor lessons.

    DEC.FINLIT: the four non-arithmetic Unit-8 financial-literacy lessons (u8_l1, u8_l2,
    u8_l4, u8_l5) are pure-concept TEKS items with no SymPy/tutor mechanism — stubbed by
    owner decision, NOT genuinely-unbuilt-but-planned. ``concept_only`` must be ``True`` for
    exactly those four and ``False`` for everything else: the two SymPy-graded U8 lessons
    (u8_l3, u8_l6), the interleave gates, and every forward-declared/unbuilt lesson (which
    keep the honest "coming soon"). This is what lets the surface render an honest "concept
    lesson" state instead of a misleading "coming soon".
    """
    progress = build_unit_progress(all_units(), _course([]), frozenset())
    lessons = {lp.lesson_slug: lp for u in progress for lp in u.lessons}

    concept_slugs = {"u8_l1", "u8_l2", "u8_l4", "u8_l5"}
    for slug, lp in lessons.items():
        assert lp.concept_only is (slug in concept_slugs), f"{slug}"

    # Spot-check the boundary cases explicitly: the two SymPy-graded U8 lessons are NOT
    # concept-only, nor are interleave gates or a forward-declared/unbuilt lesson.
    assert lessons["u8_l3"].concept_only is False  # check register — SymPy-graded
    assert lessons["u8_l6"].concept_only is False  # lifetime income — SymPy-graded
    assert lessons["u2_l7"].concept_only is False  # interleave gate
    assert lessons["u4_l6"].concept_only is False  # dependent_vars — unbuilt-but-planned


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


# --- Gating (DEC.1 = progressive) ------------------------------------------


def _master_unit_skills(unit_slug: str) -> tuple[list[ReviewableSkill], frozenset[KC]]:
    """Build the mastered ReviewableSkills + confirmed set for every live KC in a unit.

    Used to drive a unit to MASTERED so the NEXT unit unlocks under progressive
    gating. Only lessons whose ``kc_id`` resolves to a content-complete KC need
    a skill — placeholder/concept lessons don't gate the unit's mastered status.
    """
    unit = next(u for u in all_units() if u.slug == unit_slug)
    kcs: set[KC] = set()
    for lesson in unit.lessons:
        if lesson.kc_id is None:
            continue
        try:
            kc = KC(lesson.kc_id)
        except ValueError:
            continue
        kcs.add(kc)
    skills = [ReviewableSkill(kc, True, 0.95, _NOW) for kc in kcs]
    return skills, frozenset(kcs)


def test_fresh_learner_first_unit_available_rest_locked() -> None:
    """Progressive gating (DEC.1): fresh learner -> u1 available, u2..u8 locked.

    The first catalog unit is always reachable; every later unit is locked until
    its predecessor is mastered. This is the core fix: the old per-KC DAG gate
    wrongly locked u1 (its first KC needs an unmet prereq) and inverted u8 to
    "available" (its first KC was unbuilt).
    """
    progress = build_unit_progress(all_units(), _course([]), frozenset())
    by_slug = _by_slug(progress)
    assert by_slug["u1"].status is UnitStatus.AVAILABLE
    later = [u.slug for u in all_units() if u.slug != "u1"]
    for slug in later:
        assert by_slug[slug].status is UnitStatus.LOCKED, slug
    # The inverted-u8 anomaly is fixed: u8 is locked, not falsely available.
    assert by_slug["u8"].status is UnitStatus.LOCKED


def test_mastering_first_unit_unlocks_second_only() -> None:
    """After u1 is mastered, u2 unlocks (AVAILABLE) but u3 stays LOCKED.

    Progressive gating advances exactly one unit: the predecessor of u3 (u2) is
    not yet mastered, so u3 remains locked.
    """
    skills, confirmed = _master_unit_skills("u1")
    course = _course(skills)
    progress = build_unit_progress(all_units(), course, confirmed)
    by_slug = _by_slug(progress)
    assert by_slug["u1"].status is UnitStatus.MASTERED
    assert by_slug["u2"].status is UnitStatus.AVAILABLE
    assert by_slug["u3"].status is UnitStatus.LOCKED


def test_first_unit_synthetic_is_available_fresh() -> None:
    """The first unit in order is available even with nothing confirmed."""
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


def test_second_unit_locked_until_first_mastered() -> None:
    """A two-unit catalog: the second unit unlocks only when the first is mastered."""
    nl_lesson = CatalogLesson(
        slug="a_l1",
        unit_slug="unit-a",
        order=1,
        title="Number line",
        kc_id="KC_number_line_placement",
        ccss_code="6.NS.6",
        teks_code="6.2C",
        description="x",
    )
    unit_a = CatalogUnit(
        slug="unit-a",
        title="A",
        order=1,
        ccss_cluster="x",
        teks_cluster="x",
        description="x",
        lessons=(nl_lesson,),
    )
    unit_b = CatalogUnit(
        slug="unit-b",
        title="B",
        order=2,
        ccss_cluster="x",
        teks_cluster="x",
        description="x",
        lessons=(
            CatalogLesson(
                slug="b_l1",
                unit_slug="unit-b",
                order=1,
                title="Equivalence",
                kc_id="KC_equivalence",
                ccss_code="6.NS.1",
                teks_code="6.3",
                description="x",
            ),
        ),
    )
    catalog = (unit_a, unit_b)

    # Fresh: A available, B locked.
    fresh = _by_slug(build_unit_progress(catalog, _course([]), frozenset()))
    assert fresh["unit-a"].status is UnitStatus.AVAILABLE
    assert fresh["unit-b"].status is UnitStatus.LOCKED

    # Master A's only KC -> A mastered, B unlocks.
    course = _course([ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.95, _NOW)])
    done = _by_slug(build_unit_progress(catalog, course, frozenset({KC.NUMBER_LINE_PLACEMENT})))
    assert done["unit-a"].status is UnitStatus.MASTERED
    assert done["unit-b"].status is UnitStatus.AVAILABLE


def test_concept_only_lessons_excluded_from_mastered_and_percent() -> None:
    """U8's two SymPy-graded lessons completing makes U8 mastered at 100% (DEC.FINLIT).

    The four concept_only lessons (u8_l1/l2/l4/l5) are excluded from both the
    mastered aggregation and percent-complete, so mastering only u8_l3 (check
    register) and u8_l6 (lifetime income) is enough to complete the unit.
    """
    from app.domain.knowledge_components import LIVE_KCS

    u8 = next(u for u in all_units() if u.slug == "u8")
    # The playable (non-concept) U8 lessons and their KCs.
    playable_kcs: set[KC] = set()
    for lesson in u8.lessons:
        lp_kc = lesson.kc_id
        if lp_kc is None:
            continue
        try:
            kc = KC(lp_kc)
        except ValueError:
            continue
        if kc in LIVE_KCS:
            playable_kcs.add(kc)
    assert playable_kcs, "expected at least one content-complete U8 lesson"

    course = _course([ReviewableSkill(kc, True, 0.95, _NOW) for kc in playable_kcs])
    progress = build_unit_progress(all_units(), course, frozenset(playable_kcs))
    u8_prog = _by_slug(progress)["u8"]
    # Concept-only lessons are NOT in the denominator, so percent hits 100%.
    assert u8_prog.percent_complete == 1.0
    assert u8_prog.status is UnitStatus.MASTERED


def test_progress_beats_the_graph() -> None:
    """A unit with real progress is at least in_progress even if progression locks it.

    U2 is locked under progressive gating (u1 not mastered), but a learner who
    has *touched* KC_equivalence (u2_l0) -> in_progress wins, mirroring
    course_map's "real progress beats the graph".
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
    # It is the first (and only) unit in order -> available under progressive gating.
    assert progress[0].status is UnitStatus.AVAILABLE


def test_unit_status_serializes_lowercase() -> None:
    assert UnitStatus.LOCKED.value == "locked"
    assert UnitStatus.AVAILABLE.value == "available"
    assert UnitStatus.IN_PROGRESS.value == "in_progress"
    assert UnitStatus.MASTERED.value == "mastered"
