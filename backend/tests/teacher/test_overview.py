"""Unit tests for the teacher per-student overview projection (Slice TCH.B3).

Pure functions over course-map nodes + unit progress + the catalog — no DB. We pin the
strength/weakness partition (status + BKT thresholds) and the current-unit/lesson selection,
because the dashboard's headline numbers come straight from these.
"""

from __future__ import annotations

from app.api.schemas import KcMasteryView, KcStatus
from app.domain.curriculum import CatalogLesson, CatalogUnit
from app.domain.knowledge_components import KnowledgeComponentId, get_kc
from app.mastery.course_map import CourseNode, CourseNodeStatus
from app.mastery.unit_progress import LessonProgress, UnitProgress, UnitStatus
from app.teacher.overview import (
    assignable_units,
    current_unit_and_lesson,
    kc_masteries,
    split_strengths_weaknesses,
)

_EQ = KnowledgeComponentId.EQUIVALENCE
_CD = KnowledgeComponentId.COMMON_DENOMINATOR
_ADD = KnowledgeComponentId.ADDITION_UNLIKE


def _node(kc: KnowledgeComponentId, status: CourseNodeStatus, prob: float | None) -> CourseNode:
    return CourseNode(kc=kc, status=status, prerequisites=(), probability=prob)


def _mastery(kc: KnowledgeComponentId, status: KcStatus, prob: float) -> KcMasteryView:
    return KcMasteryView(
        kc_id=kc.value, skill_name=get_kc(kc).skill_name, probability=prob, status=status
    )


def test_kc_masteries_projects_status_and_probability() -> None:
    rows = kc_masteries(
        [
            _node(_EQ, CourseNodeStatus.MASTERED, 0.95),
            _node(_CD, CourseNodeStatus.IN_PROGRESS, 0.31),
        ]
    )
    assert [r.kc_id for r in rows] == [_EQ.value, _CD.value]
    assert rows[0].status is KcStatus.MASTERED
    assert rows[0].skill_name == get_kc(_EQ).skill_name
    assert rows[1].probability == 0.31


def test_kc_masteries_untouched_probability_is_zero_not_none() -> None:
    """An untouched KC carries ``probability=None`` on the node; the view must show 0.0."""
    rows = kc_masteries([_node(_ADD, CourseNodeStatus.AVAILABLE, None)])
    assert rows[0].probability == 0.0


def test_split_strengths_weaknesses_partitions_and_sorts() -> None:
    masteries = [
        _mastery(_EQ, KcStatus.MASTERED, 0.95),  # strength (mastered)
        _mastery(_CD, KcStatus.IN_PROGRESS, 0.82),  # strength (high in-progress)
        _mastery(_ADD, KcStatus.IN_PROGRESS, 0.18),  # weakness (low in-progress)
        _mastery(KnowledgeComponentId.SUBTRACTION_UNLIKE, KcStatus.IN_PROGRESS, 0.40),  # weakness
        _mastery(KnowledgeComponentId.NUMBER_LINE_PLACEMENT, KcStatus.AVAILABLE, 0.0),  # neither
    ]
    strengths, weaknesses = split_strengths_weaknesses(masteries)

    assert [s.kc_id for s in strengths] == [_EQ.value, _CD.value]  # strongest first
    assert [w.kc_id for w in weaknesses] == [
        _ADD.value,
        KnowledgeComponentId.SUBTRACTION_UNLIKE.value,
    ]  # weakest first
    # The untouched/available KC is on neither list.
    touched = {m.kc_id for m in strengths + weaknesses}
    assert KnowledgeComponentId.NUMBER_LINE_PLACEMENT.value not in touched


def _lesson(slug: str, title: str, kc: str | None) -> CatalogLesson:
    return CatalogLesson(
        slug=slug,
        unit_slug="u-frac",
        order=0,
        title=title,
        kc_id=kc,
        ccss_code=None,
        teks_code=None,
        description="",
    )


def _catalog() -> tuple[CatalogUnit, ...]:
    return (
        CatalogUnit(
            slug="u-frac",
            title="Fractions & Decimals",
            order=1,
            ccss_cluster=None,
            teks_cluster=None,
            description="",
            lessons=(
                _lesson("u-frac-l1", "Equivalent fractions", _EQ.value),
                _lesson("u-frac-l2", "Common denominators", _CD.value),
            ),
        ),
        CatalogUnit(
            slug="u-ratio",
            title="Ratios & Rates",
            order=2,
            ccss_cluster=None,
            teks_cluster=None,
            description="",
            lessons=(_lesson("u-ratio-l1", "Ratio language", "KC_ratio_meaning"),),
        ),
    )


def _unit_progress(slug: str, status: UnitStatus, pct: float, lessons: tuple) -> UnitProgress:  # type: ignore[type-arg]
    return UnitProgress(unit_slug=slug, status=status, percent_complete=pct, lessons=lessons)


def test_current_unit_and_lesson_picks_in_progress_and_first_undone_lesson() -> None:
    progress = [
        _unit_progress(
            "u-frac",
            UnitStatus.IN_PROGRESS,
            0.5,
            (
                LessonProgress("u-frac-l1", _EQ.value, CourseNodeStatus.MASTERED, 0.95, True),
                LessonProgress("u-frac-l2", _CD.value, CourseNodeStatus.IN_PROGRESS, 0.3, True),
            ),
        ),
        _unit_progress("u-ratio", UnitStatus.LOCKED, 0.0, ()),
    ]
    unit_title, lesson_title, pct = current_unit_and_lesson(progress, _catalog())
    assert unit_title == "Fractions & Decimals"
    assert lesson_title == "Common denominators"  # first lesson not yet done
    assert pct == 0.5


def test_current_unit_falls_back_to_first_available_when_none_in_progress() -> None:
    progress = [
        _unit_progress("u-frac", UnitStatus.AVAILABLE, 0.0, ()),
        _unit_progress("u-ratio", UnitStatus.LOCKED, 0.0, ()),
    ]
    unit_title, _lesson_title, pct = current_unit_and_lesson(progress, _catalog())
    assert unit_title == "Fractions & Decimals"
    assert pct == 0.0


def test_current_unit_none_when_all_locked() -> None:
    progress = [_unit_progress("u-frac", UnitStatus.LOCKED, 0.0, ())]
    assert current_unit_and_lesson(progress, _catalog()) == (None, None, 0.0)


def test_assignable_units_flags_availability_but_lists_all() -> None:
    progress = [
        _unit_progress("u-frac", UnitStatus.IN_PROGRESS, 0.5, ()),
        _unit_progress("u-ratio", UnitStatus.LOCKED, 0.0, ()),
    ]
    units = assignable_units(progress, _catalog())
    by_id = {u.unit_id: u for u in units}
    # Every catalog unit is offered (a teacher may assign a locked one too — TCH.Q5)...
    assert set(by_id) == {"u-frac", "u-ratio"}
    # ...but the advisory flag reflects the lock.
    assert by_id["u-frac"].available is True
    assert by_id["u-ratio"].available is False
