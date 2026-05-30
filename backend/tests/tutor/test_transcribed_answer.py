"""Tests for the handwritten/OCR answer adapter (Slice HR.C2).

Pins the normalization (LaTeX → plain fraction) and — the point of the beat — that a transcribed
answer flows through the SAME SymPy verifier as a typed one (handwriting is a second input, not a
second grader).
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import AnswerKind, Problem
from app.domain.verifier import verify
from app.tutor.transcribed_answer import read_back_answer
from sympy import Rational


def test_normalizes_latex_fraction() -> None:
    assert read_back_answer("\\frac{3}{4}") == "3/4"


def test_normalizes_with_delimiters_and_equals() -> None:
    assert read_back_answer("$= 7 / 12$") == "7/12"


def test_plain_integer_is_read_whole() -> None:
    assert read_back_answer("5") == "5"


def test_unreadable_returns_none() -> None:
    assert read_back_answer("hmm, not sure") is None


def _addition_problem() -> Problem:
    # 1/3 + 1/4 = 7/12 — the addition calibration shape.
    return Problem(
        problem_id="ADD-OCR",
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        surface_format=Representation.SYMBOLIC,
        statement="1/3 + 1/4 = ?",
        correct_value=Rational(7, 12),
        representations_available=(Representation.SYMBOLIC,),
        operands=(Rational(1, 3), Rational(1, 4)),
        answer_kind=AnswerKind.NUMERIC,
    )


def test_transcribed_answer_verifies_like_a_typed_one() -> None:
    """A correct handwritten answer, once read back, grades correct through the real verifier."""
    problem = _addition_problem()
    submitted = read_back_answer("\\frac{7}{12}")
    assert submitted == "7/12"
    assert verify(problem, submitted).is_correct is True


def test_transcribed_wrong_answer_is_graded_wrong() -> None:
    """SymPy still owns correctness — a misread/wrong handwritten answer is not waved through."""
    problem = _addition_problem()
    submitted = read_back_answer("\\frac{2}{7}")
    assert submitted == "2/7"
    assert verify(problem, submitted).is_correct is False
