"""Tests for the Grade-6 curriculum catalog (``app.domain.curriculum``).

These are the TDD-mandatory Layer-1 tests for DAT.3 (CLAUDE.md §2: the domain
model gets a test before the implementation). The catalog is pure frozen data
transcribed from the AUTHORITATIVE content spec — ``CURRICULUM_STANDARD.md`` §3–§7b
and the tracker's §FULL CONTENT list — so the assertions here pin the structural
invariants that spec demands:

* every lesson/unit slug is unique (the catalog is a registry, not a bag);
* lesson ``order`` is contiguous 1..N within each unit and unit ``order`` is
  contiguous 1..M, so nothing is silently dropped or duplicated;
* every lesson carries at least one framework code (CCSS or TEKS) and every
  *dual-tagged* lesson carries BOTH (the dual-coverage superset requirement,
  CURRICULUM_STANDARD.md §2 / TEKS_CCSS_COMPARISON.md §5);
* every ``kc_id`` is well-formed, and the five KCs that exist in the enum today
  resolve through ``get_kc`` (forward-declared KCs land in Wave 3 — see the
  module docstring of ``curriculum.py``);
* the catalog is the expected size (≈52 lessons) so an accidental truncation
  fails the suite;
* the registry-style accessors fail loudly on unknown slugs and at construction
  on duplicate slugs (mirrors ``KnowledgeComponentRegistry``).
"""

from __future__ import annotations

import pytest
from app.domain.curriculum import (
    CURRICULUM,
    CatalogLesson,
    CatalogUnit,
    all_units,
    get_lesson,
    get_unit,
    lessons_for_unit,
)
from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, get_kc


def _all_lessons() -> list[CatalogLesson]:
    return [lesson for unit in CURRICULUM for lesson in unit.lessons]


# ---------------------------------------------------------------------------
# Shape / immutability
# ---------------------------------------------------------------------------


def test_curriculum_is_a_tuple_of_units() -> None:
    assert isinstance(CURRICULUM, tuple)
    assert all(isinstance(unit, CatalogUnit) for unit in CURRICULUM)
    assert len(CURRICULUM) >= 8  # U1..U8 plus U-INT


def test_units_and_lessons_are_frozen_and_hashable() -> None:
    # Frozen dataclasses are hashable; this also guards against a list slipping
    # into the `lessons` field (a list would make the unit unhashable).
    for unit in CURRICULUM:
        hash(unit)
        for lesson in unit.lessons:
            hash(lesson)
            with pytest.raises(AttributeError):
                lesson.title = "mutated"  # type: ignore[misc]


def test_all_units_returns_the_curriculum_in_order() -> None:
    assert all_units() == CURRICULUM


# ---------------------------------------------------------------------------
# Uniqueness
# ---------------------------------------------------------------------------


def test_every_lesson_slug_is_unique_across_the_catalog() -> None:
    slugs = [lesson.slug for lesson in _all_lessons()]
    assert len(slugs) == len(set(slugs)), "duplicate lesson slug(s) in CURRICULUM"


def test_every_unit_slug_is_unique() -> None:
    slugs = [unit.slug for unit in CURRICULUM]
    assert len(slugs) == len(set(slugs)), "duplicate unit slug(s) in CURRICULUM"


def test_each_lesson_points_back_at_its_unit() -> None:
    for unit in CURRICULUM:
        for lesson in unit.lessons:
            assert lesson.unit_slug == unit.slug


# ---------------------------------------------------------------------------
# Contiguous ordering
# ---------------------------------------------------------------------------


def test_unit_orders_are_contiguous_one_to_m() -> None:
    orders = [unit.order for unit in CURRICULUM]
    assert orders == list(range(1, len(CURRICULUM) + 1))


def test_lesson_orders_are_contiguous_one_to_n_within_each_unit() -> None:
    for unit in CURRICULUM:
        orders = [lesson.order for lesson in unit.lessons]
        assert orders == list(range(1, len(unit.lessons) + 1)), (
            f"non-contiguous lesson order in unit {unit.slug}: {orders}"
        )


# ---------------------------------------------------------------------------
# Framework coverage (dual-coverage superset)
# ---------------------------------------------------------------------------


def test_every_lesson_has_a_ccss_or_teks_code() -> None:
    for lesson in _all_lessons():
        assert lesson.ccss_code or lesson.teks_code, (
            f"lesson {lesson.slug} has neither a CCSS nor a TEKS code"
        )


def test_every_dual_tagged_lesson_has_both_codes() -> None:
    # A lesson is dual-tagged unless it is honestly encoded as single-framework
    # (one of the two code fields is None). TEKS-only / CCSS-only lessons are the
    # documented single-framework exceptions (CURRICULUM_STANDARD.md §2.5).
    for lesson in _all_lessons():
        is_single_framework = (lesson.ccss_code is None) ^ (lesson.teks_code is None)
        if not is_single_framework:
            assert lesson.ccss_code and lesson.teks_code, (
                f"dual-tagged lesson {lesson.slug} is missing a code"
            )


def test_single_framework_lessons_are_genuinely_single() -> None:
    # Exactly one of the two code fields is set on a single-framework lesson;
    # never both-None (that would be the neither-code bug) — the OR test above
    # already guards neither, this pins that single-framework means exactly one.
    for lesson in _all_lessons():
        if lesson.ccss_code is None or lesson.teks_code is None:
            assert lesson.ccss_code or lesson.teks_code


def test_catalog_contains_the_known_teks_only_units() -> None:
    # U-INT (integer arithmetic) and U8 (financial literacy) are the two whole
    # TEKS-only strands (TEKS_CCSS_COMPARISON.md §4); their lessons must all be
    # TEKS-coded and CCSS-None.
    teks_only_units = {"uint", "u8"}
    for unit in CURRICULUM:
        if unit.slug in teks_only_units:
            for lesson in unit.lessons:
                assert lesson.teks_code is not None, (
                    f"{lesson.slug} in TEKS-only unit {unit.slug} lacks a TEKS code"
                )
                assert lesson.ccss_code is None, (
                    f"{lesson.slug} in TEKS-only unit {unit.slug} unexpectedly has a CCSS code"
                )


# ---------------------------------------------------------------------------
# KC ids
# ---------------------------------------------------------------------------


def test_present_kc_ids_are_well_formed() -> None:
    for lesson in _all_lessons():
        if lesson.kc_id is not None:
            assert lesson.kc_id, f"empty kc_id on {lesson.slug}"
            assert lesson.kc_id.startswith("KC_"), (
                f"malformed kc_id {lesson.kc_id!r} on {lesson.slug}"
            )


def test_the_five_existing_kc_ids_resolve_via_get_kc() -> None:
    known = {kc.value for kc in LIVE_KCS}
    resolved_at_least_one = False
    for lesson in _all_lessons():
        if lesson.kc_id in known:
            resolved = get_kc(lesson.kc_id)
            assert resolved.id.value == lesson.kc_id
            resolved_at_least_one = True
    assert resolved_at_least_one, (
        "expected at least one lesson to reference one of the 5 existing KCs"
    )


def test_forward_declared_kc_ids_do_not_resolve_yet() -> None:
    # The catalog is forward-declared: most kc_ids are NOT yet members of the
    # KnowledgeComponentId enum (they land per-lesson in Wave 3). They must still
    # be well-formed strings, but must not silently resolve.
    known = {kc.value for kc in KnowledgeComponentId}
    forward = {
        lesson.kc_id
        for lesson in _all_lessons()
        if lesson.kc_id is not None and lesson.kc_id not in known
    }
    assert forward, "expected forward-declared KCs (the Wave-3 content) in the catalog"
    for kc_id in forward:
        with pytest.raises(KeyError):
            get_kc(kc_id)


# ---------------------------------------------------------------------------
# Size (catches accidental truncation)
# ---------------------------------------------------------------------------


def test_lesson_count_is_in_the_expected_ballpark() -> None:
    # The spec is "~52 lessons across 9 units" (CURRICULUM_STANDARD.md §2). A
    # lower bound of 45 catches an accidental dropped unit while leaving room
    # for the documented granularity question (CURRICULUM_STANDARD.md §10.3).
    count = len(_all_lessons())
    assert 45 <= count <= 60, f"unexpected lesson count {count}"


def test_there_are_nine_units() -> None:
    # U1..U8 plus U-INT = 9 (CURRICULUM_STANDARD.md §2).
    assert len(CURRICULUM) == 9


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------


def test_get_unit_returns_the_unit() -> None:
    first = CURRICULUM[0]
    assert get_unit(first.slug) is first


def test_get_unit_raises_on_unknown_slug() -> None:
    with pytest.raises(KeyError):
        get_unit("no_such_unit")


def test_get_lesson_returns_the_lesson() -> None:
    first_lesson = CURRICULUM[0].lessons[0]
    assert get_lesson(first_lesson.slug) is first_lesson


def test_get_lesson_raises_on_unknown_slug() -> None:
    with pytest.raises(KeyError):
        get_lesson("no_such_lesson")


def test_lessons_for_unit_matches_the_unit_lessons() -> None:
    for unit in CURRICULUM:
        assert lessons_for_unit(unit.slug) == unit.lessons


def test_lessons_for_unit_raises_on_unknown_slug() -> None:
    with pytest.raises(KeyError):
        lessons_for_unit("no_such_unit")


# ---------------------------------------------------------------------------
# Duplicate detection at construction
# ---------------------------------------------------------------------------


def test_duplicate_lesson_slug_raises_at_construction() -> None:
    from app.domain.curriculum import build_index

    dup = CatalogUnit(
        slug="dupunit",
        title="Dup",
        order=1,
        ccss_cluster=None,
        teks_cluster=None,
        description="",
        lessons=(
            CatalogLesson(
                slug="dup_l1",
                unit_slug="dupunit",
                order=1,
                title="A",
                kc_id=None,
                ccss_code="6.X.1",
                teks_code=None,
                description="",
            ),
            CatalogLesson(
                slug="dup_l1",  # duplicate slug
                unit_slug="dupunit",
                order=2,
                title="B",
                kc_id=None,
                ccss_code="6.X.2",
                teks_code=None,
                description="",
            ),
        ),
    )
    with pytest.raises(ValueError, match="Duplicate lesson slug"):
        build_index((dup,))


def test_duplicate_unit_slug_raises_at_construction() -> None:
    from app.domain.curriculum import build_index

    unit = CatalogUnit(
        slug="dupunit",
        title="Dup",
        order=1,
        ccss_cluster=None,
        teks_cluster=None,
        description="",
        lessons=(),
    )
    with pytest.raises(ValueError, match="Duplicate unit slug"):
        build_index((unit, unit))
