"""Tests for the course-map status derivation (Slice CP.A.1 — course product).

The course map turns the learner's persisted mastery into one STATUS per KC, so the home
screen can show a learning path: ``locked`` (prereqs unmet) / ``available`` (unlocked, not
started) / ``in_progress`` (touched, not confirmed) / ``mastered`` (confirmed, retained) /
``due_review`` (confirmed but decayed). It is a thin, pure composition of the existing engine —
``prerequisites.unlocked`` (the algebra spine) + ``retention.is_due_for_review`` (spaced
repetition) — and adds NO new mastery logic (PROJECT.md §3.13: reuse the engine, never rebuild).
Pure + deterministic; ``now`` is passed in (CLAUDE.md §8.1, §4.1).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.prerequisites import prerequisites_of
from app.mastery.course_map import CourseNodeStatus, build_course_map
from app.mastery.retention import DEFAULT_HALF_LIFE, ReviewableSkill

KC = KnowledgeComponentId  # local shorthand (a constant alias; ruff-clean, unlike `import as`)
_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def _by_kc(skills: list[ReviewableSkill]) -> dict[KnowledgeComponentId, CourseNodeStatus]:
    return {node.kc: node.status for node in build_course_map(skills, _NOW)}


def test_map_always_has_one_node_per_kc_in_spine_order() -> None:
    """Every KC is always a node (a path needs all its stops), in teaching order."""
    nodes = build_course_map([], _NOW)
    assert [n.kc for n in nodes] == [
        KC.NUMBER_LINE_PLACEMENT,
        KC.EQUIVALENCE,
        KC.COMMON_DENOMINATOR,
        KC.ADDITION_UNLIKE,
        KC.SUBTRACTION_UNLIKE,
        KC.RATIO_LANGUAGE,  # Grade-6 Unit 1 (built 2026-05-30)
        KC.UNIT_RATE,  # Grade-6 Unit 1 (built 2026-05-30)
        KC.EQUIVALENT_RATIOS,  # Grade-6 Unit 1
        KC.PERCENT,  # Grade-6 Unit 1
        KC.MULTIPLY_FRACTIONS,  # Grade-6 Unit 2 (built 2026-05-30, T2)
        KC.UNIT_CONVERSION,  # Grade-6 Unit 1 (built 2026-05-30), last on the spine
    ]


def test_brand_new_learner_root_available_rest_locked() -> None:
    """Nothing touched → the root is AVAILABLE to start; everything downstream is LOCKED."""
    status = _by_kc([])
    assert status[KC.NUMBER_LINE_PLACEMENT] == CourseNodeStatus.AVAILABLE
    assert status[KC.EQUIVALENCE] == CourseNodeStatus.LOCKED
    assert status[KC.COMMON_DENOMINATOR] == CourseNodeStatus.LOCKED
    assert status[KC.ADDITION_UNLIKE] == CourseNodeStatus.LOCKED
    assert status[KC.SUBTRACTION_UNLIKE] == CourseNodeStatus.LOCKED


def test_confirmed_root_is_mastered_and_unlocks_the_next_skill() -> None:
    """A fresh-confirmed root is MASTERED; equivalence becomes AVAILABLE; the rest stay LOCKED."""
    status = _by_kc([ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.9, _NOW)])
    assert status[KC.NUMBER_LINE_PLACEMENT] == CourseNodeStatus.MASTERED
    assert status[KC.EQUIVALENCE] == CourseNodeStatus.AVAILABLE
    assert status[KC.COMMON_DENOMINATOR] == CourseNodeStatus.LOCKED


def test_touched_but_unconfirmed_skill_is_in_progress() -> None:
    """A KC with a mastery row that is not yet confirmed is IN_PROGRESS, not available/locked."""
    status = _by_kc([ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, False, 0.6, _NOW)])
    assert status[KC.NUMBER_LINE_PLACEMENT] == CourseNodeStatus.IN_PROGRESS


def test_in_progress_beats_locked_even_when_prereqs_unmet() -> None:
    """The prereq graph is advisory: a learner who started a downstream skill shows IN_PROGRESS.

    (The cold-start route lets a learner begin any route; the graph never blocks that — it only
    orders what is *suggested* next. So actual progress must win over the locked-by-prereq view.)
    """
    status = _by_kc([ReviewableSkill(KC.ADDITION_UNLIKE, False, 0.4, _NOW)])
    assert status[KC.ADDITION_UNLIKE] == CourseNodeStatus.IN_PROGRESS


def test_confirmed_but_decayed_skill_is_due_review() -> None:
    """A confirmed skill last practiced long ago decays below the bar → DUE_REVIEW, not mastered."""
    status = _by_kc(
        [ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.9, _NOW - 4 * DEFAULT_HALF_LIFE)]
    )
    assert status[KC.NUMBER_LINE_PLACEMENT] == CourseNodeStatus.DUE_REVIEW


def test_node_carries_prerequisites_and_probability() -> None:
    """Each node exposes its prereq edges (for rendering) and the mastery level if touched."""
    nodes = {
        n.kc: n for n in build_course_map([ReviewableSkill(KC.EQUIVALENCE, True, 0.88, _NOW)], _NOW)
    }
    eq = nodes[KC.EQUIVALENCE]
    assert set(eq.prerequisites) == set(prerequisites_of(KC.EQUIVALENCE))
    assert eq.probability == 0.88
    # An untouched node has no mastery level to show.
    assert nodes[KC.SUBTRACTION_UNLIKE].probability is None


def test_full_path_when_everything_confirmed_and_fresh() -> None:
    """All confirmed + freshly practiced → every node MASTERED, nothing locked or due."""
    skills = [ReviewableSkill(kc, True, 0.95, _NOW) for kc in KC]
    status = _by_kc(skills)
    assert all(s == CourseNodeStatus.MASTERED for s in status.values())


def test_build_is_deterministic() -> None:
    """Same inputs → identical map (PROJECT.md §4.1 reproducibility)."""
    skills = [ReviewableSkill(KC.NUMBER_LINE_PLACEMENT, True, 0.9, _NOW - 5 * DEFAULT_HALF_LIFE)]
    assert build_course_map(skills, _NOW) == build_course_map(skills, _NOW)
