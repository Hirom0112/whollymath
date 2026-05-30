"""Behavioral tests for KC_ratio_language — a Grade-6 (Unit 1) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope part-whole item; the verifier confirms the correct
part-whole ratio and classifies the part-part-vs-part-whole confusion; the worked example
lands on the answer; and generation is deterministic (PROJECT.md §4.1). Mandatory-TDD
domain Layer 1 (CLAUDE.md §2). Skill: 6.RP.1 — a ratio vs a single count, part-part vs
part-whole.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, part_part_ratio
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.RATIO_LANGUAGE


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def test_ratio_language_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_ratio_language_is_a_clean_in_scope_problem() -> None:
    """The generator yields a numeric item with a (part, other) pair and a part-whole fraction.

    The asked-for ratio is part-to-whole, ``part / (part + other)`` — strictly between 0 and 1
    (a part is smaller than the whole), the property that defeats the part-part confusion.
    """
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 2
    part, other = problem.operands
    assert problem.correct_value == part / (part + other)
    assert 0 < problem.correct_value < 1


def test_correct_part_whole_ratio_verifies_correct() -> None:
    """The SymPy part-whole fraction is graded correct by the tutor's own oracle."""
    for seed in range(1, 12):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_part_part_confusion_is_classified() -> None:
    """The part-part ratio (part/other) is flagged OPERATION + the part-part-whole misconception.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG SETUP — compared the part to
    the other part rather than to the whole — which is a procedure/relationship error, the same
    family as rate-inversion (verifier.py module docstring; PROJECT.md §3.6). The part-part value
    ``part/other`` is always DISTINCT from the correct part-whole ``part/(part+other)`` because
    ``other != part + other`` whenever ``part > 0`` — always, since ``part >= 1``.
    """
    for seed in range(1, 12):
        problem = _problem(seed)
        assert problem.operands is not None
        part, other = problem.operands
        confused = part_part_ratio(int(part), int(other))
        result = verify(problem, str(confused))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.PART_PART_WHOLE_CONFUSION


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    problem = _problem(3)
    example = worked_example_for(problem)
    assert example.final_value == problem.correct_value


def test_nudge_bank_covers_ratio_language() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
