"""Behavioral tests for Natural-number Nate (PROJECT.md §4.2 Persona 1).

These are MANDATORY-TDD persona behavioral tests (CLAUDE.md §2: "the persona
simulator's specific expected behaviors get tests-first development"). They pin
Nate's §4.2 signature — "correct on symbolic equivalence where surface pattern
matches; reliably wrong on magnitude comparisons; places fractions with bigger
denominators further from zero on a number line" — and they assert correctness
through the SAME oracle the tutor uses, the Layer-1 SymPy verifier
(``domain/verifier.py``), so "correct"/"wrong" mean exactly what they mean in
production (ARCHITECTURE.md §9). No LLM, no DB, deterministic (§8.1, §8.3, §4.1).

Nate forces the §3.4 rule that mastery cannot be declared from a single
representation: if the threshold were "5 correct in a row on symbolic
equivalence" he would hit it, then fail number-line placement (§4.2 P1, §3.4
rule 2). These tests pin the evidence that makes that rule load-bearing.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.misconceptions import (
    MisconceptionId,
    natural_number_bias_number_line,
)
from app.domain.problem_generators import generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.personas.nate import NATE
from app.personas.simulator import simulate_action

# Fixed seeds keep the underlying operands and correct answers reproducible, so a
# test that says "Nate is correct/wrong" is checking a stable, known problem.
_EQ_SEED = 7
_NL_SEED = 4


def test_nate_correct_on_symbolic_equivalence_surface_match() -> None:
    """§4.2 P1: 'correct on symbolic equivalence where the surface pattern matches.'

    A symbolic equivalence item is inside the surface pattern Nate recognizes, so
    he submits the CORRECT equivalent value — confirmed by the tutor's own SymPy
    verifier. This is exactly the single-representation success that would falsely
    pass a one-representation mastery threshold (§3.4 rule 2 is the fix it forces).
    """
    problem = generate_problem(KnowledgeComponentId.EQUIVALENCE, _EQ_SEED, Representation.SYMBOLIC)
    action = simulate_action(NATE, problem)

    result = verify(problem, action.submitted_answer)
    assert result.is_correct, "Nate must get a surface-matching symbolic equivalence item right"
    assert result.error_category is ErrorCategory.NONE


def test_nate_wrong_on_number_line_placement_natural_number_bias() -> None:
    """§4.2 P1: 'places fractions with bigger denominators further from zero.'

    On a number-line placement item Nate's natural-number bias places the marker
    at the denominator read as a whole-number position (``biased_position``). The
    verifier marks it WRONG and classifies it MAGNITUDE / natural-number-bias — the
    representation that exposes the bias the symbolic surface hid (§3.6, §4.2 P1).
    """
    problem = generate_problem(
        KnowledgeComponentId.NUMBER_LINE_PLACEMENT, _NL_SEED, Representation.NUMBER_LINE
    )
    assert problem.operands is not None
    (target,) = problem.operands
    expected_biased = natural_number_bias_number_line(target.p, target.q).biased_position

    action = simulate_action(NATE, problem)

    # He submits the biased position (the denominator read as a position), NOT the
    # true magnitude — the natural-number-bias number-line misplacement.
    assert action.submitted_answer == expected_biased

    result = verify(problem, action.submitted_answer)
    assert result.is_correct is False, "Nate must misplace on the number line"
    assert result.error_category is ErrorCategory.MAGNITUDE
    assert result.matched_misconception is MisconceptionId.NATURAL_NUMBER_BIAS


def test_nate_symbolic_pass_number_line_fail_is_the_two_representation_gap() -> None:
    """The §3.4-rule-2 gap, in one test: same learner, right symbolic, wrong on the line.

    Nate succeeds in ONE representation (symbolic equivalence) and fails in another
    (number-line magnitude). That single-representation success is exactly why
    mastery must require correctness across >= 2 representations (§3.4 rule 2);
    here we hold the learner constant and show both outcomes.
    """
    equivalence = generate_problem(
        KnowledgeComponentId.EQUIVALENCE, _EQ_SEED, Representation.SYMBOLIC
    )
    number_line = generate_problem(
        KnowledgeComponentId.NUMBER_LINE_PLACEMENT, _NL_SEED, Representation.NUMBER_LINE
    )

    eq_correct = verify(equivalence, simulate_action(NATE, equivalence).submitted_answer).is_correct
    nl_correct = verify(number_line, simulate_action(NATE, number_line).submitted_answer).is_correct

    assert eq_correct is True
    assert nl_correct is False


def test_nate_answers_fast_with_high_engagement() -> None:
    """§4.2 P1: 'answers in <3 seconds with high confidence.'

    His think time comes from his characteristic latency (< 3s), and his engagement
    is high — a confident snap-guesser, not a disengaged clicker (contrast Cleo).
    """
    problem = generate_problem(KnowledgeComponentId.EQUIVALENCE, _EQ_SEED, Representation.SYMBOLIC)
    action = simulate_action(NATE, problem)

    assert action.think_time_seconds < 3.0
    assert NATE.behavior.engagement_floor >= 0.7


def test_nate_is_deterministic() -> None:
    """Same persona + problem ⇒ identical action (§4.1; CLAUDE.md §2)."""
    problem = generate_problem(
        KnowledgeComponentId.NUMBER_LINE_PLACEMENT, _NL_SEED, Representation.NUMBER_LINE
    )
    assert simulate_action(NATE, problem) == simulate_action(NATE, problem)
