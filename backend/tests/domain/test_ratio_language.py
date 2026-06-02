"""Behavioral tests for KC_ratio_language — a Grade-6 (Unit 1) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds clean, in-scope items in BOTH question modes (part-to-whole AND
part-to-part — the distinction 6.RP.A.1 is actually about); the verifier confirms the
correct answer for each mode and classifies the part-part-vs-part-whole confusion in the
right direction; counts are kept distinct so no item degenerates to 1/2 or 1:1; the worked
example lands on the answer; and generation is deterministic (PROJECT.md §4.1).
Mandatory-TDD domain Layer 1 (CLAUDE.md §2). Skill: 6.RP.1 — part-part vs part-whole.
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, part_part_ratio, part_whole_ratio
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.RATIO_LANGUAGE


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _parts(problem: Problem) -> tuple[int, int, int]:
    """(mode, part, other) decoded from operands = (mode, colour_idx, part, other)."""
    assert problem.operands is not None and len(problem.operands) == 4
    mode, _colour_idx, part, other = problem.operands
    return int(mode), int(part), int(other)


def test_ratio_language_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_item_is_clean_and_in_scope_in_both_modes() -> None:
    """The generator yields a numeric item whose answer matches its question mode.

    Operands are ``(mode, colour_idx, part, other)`` with ``part != other`` (so the part-whole
    fraction is never the trivial 1/2 and the part-part ratio is never 1:1). A part-WHOLE item
    (mode 0) answers ``part/(part+other)`` ∈ (0, 1); a part-PART item (mode 1) answers part/other.
    """
    seen_modes = set()
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.kc is _KC
        assert problem.answer_kind is AnswerKind.NUMERIC
        mode, part, other = _parts(problem)
        assert part != other  # no degenerate 1/2 / 1:1
        seen_modes.add(mode)
        if mode == 0:
            assert problem.correct_value == Rational(part, part + other)
            assert 0 < problem.correct_value < 1
        else:
            assert problem.correct_value == Rational(part, other)
    assert seen_modes == {0, 1}, "the lesson must interleave BOTH question modes (6.RP.A.1)"


def test_correct_answer_verifies_correct_in_both_modes() -> None:
    """The SymPy answer for each mode is graded correct by the tutor's own oracle."""
    for seed in range(1, 40):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_confusion_is_classified_in_the_right_direction() -> None:
    """The OTHER ratio is flagged OPERATION + the part-part-whole misconception, per mode.

    Routed to OPERATION (not MAGNITUDE): the learner ran the WRONG SETUP — compared against the
    wrong reference — a procedure/relationship error (verifier.py module docstring; PROJECT.md
    §3.6). A part-WHOLE question (mode 0) is missed by answering the part-to-part ratio
    ``part/other``; a part-PART question (mode 1) is missed by answering the part-of-the-whole
    ``part/(part+other)``. Either confusion is always DISTINCT from the correct value because
    ``other != part + other`` whenever ``part >= 1``.
    """
    for seed in range(1, 40):
        problem = _problem(seed)
        mode, part, other = _parts(problem)
        confused = part_part_ratio(part, other) if mode == 0 else part_whole_ratio(part, other)
        assert confused != problem.correct_value  # the confusion is a genuinely wrong value
        result = verify(problem, str(confused))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.PART_PART_WHOLE_CONFUSION


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value


def test_worked_example_lands_on_the_answer_in_both_modes() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency).

    Checked across enough seeds to cover both question modes (each has its own step script)."""
    for seed in range(1, 40):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_structured_prompt_parts_compose_the_statement() -> None:
    """Every item carries setup/ask/rule parts, and the flat statement is exactly those parts.

    The card renders the three parts; ``statement`` is the accessible fallback. Composing it FROM
    the parts (situation + question + '(' + rule + ')') guarantees the two can never drift (§8.4).
    """
    for seed in range(1, 40):
        problem = _problem(seed)
        parts = problem.prompt_parts
        assert parts is not None
        assert parts.situation and parts.question and parts.guiding_rule
        assert problem.statement == f"{parts.situation} {parts.question} ({parts.guiding_rule})"
        # The collection still appears in the setup, so the picture-vs-words pin still holds.
        assert "jar has" in parts.situation


def test_nudge_bank_covers_ratio_language() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
