"""Tests for homework set generation (PROJECT.md §3.4 two-star model / RD.0.4)."""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.prerequisites import SPINE_ORDER
from app.homework.assignment import build_assignment


def test_set_is_anchored_target_plus_spaced_review() -> None:
    """The set is mostly the target skill, plus a few spaced-review items — not a blocked run."""
    a = build_assignment(KnowledgeComponentId.ADDITION_UNLIKE, target_count=5, review_count=2)

    assert len(a.problems) == 7
    targets = a.target_problems
    assert len(targets) == 5
    assert all(p.problem.kc is KnowledgeComponentId.ADDITION_UNLIKE for p in targets)
    # Target items come first, review items after.
    assert [p.is_target for p in a.problems] == [True] * 5 + [False] * 2


def test_review_pulls_only_from_earlier_spine_skills() -> None:
    """Spaced review never tests a skill taught after the target (reviews ⊂ earlier spine)."""
    target = KnowledgeComponentId.ADDITION_UNLIKE
    a = build_assignment(target, review_count=2)
    earlier = set(SPINE_ORDER[: SPINE_ORDER.index(target)])

    review_kcs = [p.problem.kc for p in a.problems if not p.is_target]
    assert review_kcs, "addition has earlier spine skills to review"
    assert all(kc in earlier for kc in review_kcs)
    # Closest-earlier-first: the skill just below addition (common denominator) is reviewed first.
    assert review_kcs[0] is KnowledgeComponentId.COMMON_DENOMINATOR


def test_number_line_placement_is_never_a_scanned_review() -> None:
    """Number-line placement can't be scan-graded (a mark on a line is not a written answer), so it
    never appears as a scanned-homework review — even when it's an earlier spine skill."""
    a = build_assignment(KnowledgeComponentId.SUBTRACTION_UNLIKE, review_count=5)
    review_kcs = [p.problem.kc for p in a.problems if not p.is_target]
    assert KnowledgeComponentId.NUMBER_LINE_PLACEMENT not in review_kcs
    assert review_kcs, "subtraction still has written earlier skills to review"


def test_root_skill_has_no_review_items() -> None:
    """The first spine skill (number line) has nothing earlier to review → target-only set."""
    a = build_assignment(KnowledgeComponentId.NUMBER_LINE_PLACEMENT, target_count=4, review_count=2)
    assert len(a.problems) == 4
    assert all(p.is_target for p in a.problems)


def test_deterministic() -> None:
    """Same (target, seed_base) ⇒ identical set (seeded generator) — so a session can rebuild it."""
    a = build_assignment(KnowledgeComponentId.SUBTRACTION_UNLIKE, seed_base=7)
    b = build_assignment(KnowledgeComponentId.SUBTRACTION_UNLIKE, seed_base=7)
    assert [p.problem.problem_id for p in a.problems] == [p.problem.problem_id for p in b.problems]
