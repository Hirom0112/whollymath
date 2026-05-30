"""Tests for the homework scanners (transcription only — SymPy still grades)."""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.verifier import verify
from app.homework.assignment import build_assignment
from app.homework.scanner import MathpixScanner, MockScanner, _extract_answers

_TARGET = KnowledgeComponentId.ADDITION_UNLIKE


def test_mock_reads_correct_answers_that_verify() -> None:
    """The mock's default reading is the answer key, and each target reading verifies as correct
    through the SAME domain verifier the live tutor uses (transcription → SymPy grades it)."""
    a = build_assignment(_TARGET, target_count=5, review_count=0)
    reading = MockScanner().scan([b"page1", b"page2"], a)

    assert set(reading) == set(range(5))  # one answer per question, across the pages
    for index, item in enumerate(a.target_problems):
        answer = reading[index]
        assert answer is not None
        assert verify(item.problem, answer).is_correct


def test_mock_injects_misses_and_unreadable_for_demo() -> None:
    """The mock can script a wrong answer and an unreadable answer so a demo shows a fail + the
    misread-confirm path without a real photo."""
    a = build_assignment(_TARGET, target_count=5, review_count=0)
    reading = MockScanner(miss_indices=frozenset({1}), unreadable_indices=frozenset({2})).scan(
        [b"page"], a
    )

    assert reading[2] is None  # unreadable
    assert reading[1] is not None
    assert not verify(a.problems[1].problem, reading[1]).is_correct  # the injected miss is wrong


def test_mock_overrides_win() -> None:
    """An explicit override sets exactly what the scanner 'reads' for that question."""
    a = build_assignment(_TARGET, target_count=3, review_count=0)
    reading = MockScanner(overrides={0: "1/2", 1: None}).scan([b"page"], a)
    assert reading[0] == "1/2"
    assert reading[1] is None


def test_mathpix_without_a_key_degrades_to_none_not_crash() -> None:
    """No key (or any API failure) is fail-safe: every question comes back None, so the desktop
    read-back becomes manual entry — OCR is never blocking."""
    a = build_assignment(_TARGET, target_count=3, review_count=0)
    reading = MathpixScanner(app_key=None).scan([b"fake-image-bytes"], a)
    assert set(reading) == {0, 1, 2}
    assert all(v is None for v in reading.values())


def test_extract_answers_maps_after_equals_positionally() -> None:
    """The answer-extraction heuristic: take what follows the last '=' on each line, in order,
    flattening \\frac{a}{b} → a/b, and map positionally (unread questions stay None)."""
    text = "3/5 + 1/12 = 41/60\n3/4 + 1/2 = \\frac{5}{4}\n(scribble with no equals)\n2/5 + 5/8 ="
    extracted = _extract_answers(text, count=4)
    assert extracted[0] == "41/60"
    assert extracted[1] == "5/4"  # \frac flattened
    assert extracted[2] is None  # third answer-bearing line was the 4th question's blank '='
    assert extracted[3] is None  # only two answers were found → questions 2,3 unfilled
