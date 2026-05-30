"""Tests for homework grading + the ★★ pass gate (PROJECT.md §3.4 two-star model)."""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.homework.assignment import build_assignment
from app.homework.grading import PASS_THRESHOLD, grade
from app.homework.scanner import MockScanner

_TARGET = KnowledgeComponentId.ADDITION_UNLIKE


def test_all_target_correct_earns_the_second_star() -> None:
    """A clean target-skill sheet (read correctly) passes the ★★ gate at score 1.0."""
    a = build_assignment(_TARGET, target_count=5, review_count=2)
    reading = MockScanner().scan([b"page"], a)

    result = grade(a, reading)
    assert result.target_total == 5
    assert result.target_correct == 5
    assert result.target_score == 1.0
    assert result.passed is True
    assert len(result.results) == len(a.problems)  # every question carried for the review


def test_one_target_miss_still_passes_at_threshold() -> None:
    """4/5 target correct = 0.8 = exactly the bar → ★★ (PASS_THRESHOLD is inclusive)."""
    a = build_assignment(_TARGET, target_count=5, review_count=0)
    reading = MockScanner(miss_indices=frozenset({0})).scan([b"page"], a)

    result = grade(a, reading)
    assert result.target_correct == 4
    assert result.target_score == 0.8 == PASS_THRESHOLD
    assert result.passed is True


def test_two_target_misses_fails_the_gate() -> None:
    """3/5 = 0.6 < 0.8 → no ★★; the caller routes this to redo-the-lesson + a fresh set."""
    a = build_assignment(_TARGET, target_count=5, review_count=0)
    reading = MockScanner(miss_indices=frozenset({0, 1})).scan([b"page"], a)

    result = grade(a, reading)
    assert result.target_correct == 3
    assert result.passed is False


def test_unreadable_answer_is_flagged_not_silently_wrong() -> None:
    """An unreadable scan is graded incorrect BUT flagged so the read-back can confirm it,
    rather than silently counting a misread as a real mistake (the OCR safety valve)."""
    a = build_assignment(_TARGET, target_count=5, review_count=0)
    reading = MockScanner(unreadable_indices=frozenset({0})).scan([b"page"], a)

    result = grade(a, reading)
    q0 = result.results[0]
    assert q0.unreadable is True
    assert q0.submitted is None
    assert q0.correct is False


def test_equivalence_numerator_only_answer_grades_correct() -> None:
    """Equivalence asks for only the top number ('4'); grading reconstructs it against the given
    denominator ('4/8') so a correct paper answer isn't marked wrong."""
    a = build_assignment(KnowledgeComponentId.EQUIVALENCE, target_count=5, review_count=0)
    # Each equivalence item's correct numerator over its given denominator.
    numerator_answers = {
        i: str((item.problem.correct_value * item.problem.given_denominator).p)
        for i, item in enumerate(a.problems)
    }
    result = grade(a, numerator_answers)
    assert result.passed is True
    assert result.target_score == 1.0


def test_review_items_do_not_count_toward_the_gate() -> None:
    """The ★★ gate is scored over the ANCHORED target skill only; review items are evidence,
    not part of the threshold (so a flubbed review can't deny mastery of the new skill)."""
    a = build_assignment(_TARGET, target_count=5, review_count=2)
    # Miss only review items (indices 5,6) — target stays perfect.
    reading = MockScanner(miss_indices=frozenset({5, 6})).scan([b"page"], a)

    result = grade(a, reading)
    assert result.target_total == 5
    assert result.target_correct == 5
    assert result.passed is True
