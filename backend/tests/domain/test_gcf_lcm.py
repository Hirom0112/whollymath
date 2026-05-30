"""Behavioral tests for KC_gcf_lcm — Grade-6 Unit 2 (2026-05-30).

Exercises the KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator asks for either the GCF or the LCM of two whole numbers (a clean integer
answer computed by SymPy ``gcd``/``lcm``); the verifier confirms the correct answer and
classifies the GCF↔LCM-confusion misconception (returning the OTHER aggregate — the LCM
when the GCF was asked, or the GCF when the LCM was asked); the worked example lands on
the answer; and generation is deterministic (PROJECT.md §4.1). Mandatory-TDD domain
Layer 1 (CLAUDE.md §2).

A note on the OPERATION error category: the GCF↔LCM confusion is the learner applying the
WRONG aggregating operation (taking common multiples when common factors were asked, or
vice versa) — a procedure/operation mix-up, not a magnitude misjudgment — so it routes to
OPERATION, matching the rate-inversion / multiply-as-add precedent (both "wrong operation
on the right operands" → OPERATION; verifier.py).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, gcf_lcm_confusion
from app.domain.problem_generators import AnswerKind, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational, gcd, lcm

_KC = KnowledgeComponentId.GCF_LCM

# operands = (a, b, mode); mode 0 = GCF asked, mode 1 = LCM asked (a Rational flag, so the
# verifier's value-producing model can replay the confusion without seeing the statement).
_GCF_MODE = 0
_LCM_MODE = 1


def _problem(seed: int):  # type: ignore[no-untyped-def]
    return generate_problem(_KC, seed)


def test_gcf_lcm_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_problem_is_a_clean_integer_aggregate() -> None:
    """A numeric item: (a, b, mode) operands whose answer is gcd(a,b) or lcm(a,b)."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 3
    a, b, mode = (int(o) for o in problem.operands)
    assert mode in (_GCF_MODE, _LCM_MODE)
    expected = gcd(a, b) if mode == _GCF_MODE else lcm(a, b)
    assert problem.correct_value == Rational(int(expected))
    assert problem.correct_value.q == 1  # a whole-number answer


def test_both_modes_appear_across_seeds() -> None:
    """The generator asks for the GCF on some seeds and the LCM on others (both are exercised)."""
    modes = {int(_problem(seed).operands[2]) for seed in range(1, 40)}
    assert modes == {_GCF_MODE, _LCM_MODE}


def test_gcf_and_lcm_differ_so_the_confusion_is_always_wrong() -> None:
    """a != b with the larger not a multiple of the smaller, so gcd != lcm — the confusion is a
    genuinely wrong answer on every generated item (never accidentally correct)."""
    for seed in range(1, 30):
        problem = _problem(seed)
        a, b, _ = (int(o) for o in problem.operands)
        assert gcd(a, b) != lcm(a, b)


def test_correct_aggregate_verifies_correct() -> None:
    """The SymPy gcd/lcm answer is graded correct by the tutor's own oracle."""
    for seed in range(1, 30):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_gcf_lcm_confusion_is_classified() -> None:
    """Returning the OTHER aggregate (LCM for GCF, or GCF for LCM) is flagged OPERATION +
    gcf-lcm-confusion — the misconception the lesson is designed to surface."""
    for seed in range(1, 30):
        problem = _problem(seed)
        a, b, mode = (int(o) for o in problem.operands)
        confused = gcf_lcm_confusion(a, b, lcm_asked=(mode == _LCM_MODE))
        assert confused != problem.correct_value  # it is the OTHER aggregate, so wrong
        result = verify(problem, str(confused))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.GCF_LCM_CONFUSION


def test_confusion_helper_returns_the_other_aggregate() -> None:
    """The helper is exactly the swap: GCF asked → returns LCM; LCM asked → returns GCF."""
    assert gcf_lcm_confusion(12, 18, lcm_asked=False) == Rational(int(lcm(12, 18)))
    assert gcf_lcm_confusion(12, 18, lcm_asked=True) == Rational(int(gcd(12, 18)))


def test_generation_is_deterministic() -> None:
    """Same seed => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).correct_value == generate_problem(_KC, 42).correct_value
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_worked_example_lands_on_the_answer() -> None:
    """The worked example's final step equals the problem's correct value (self-consistency)."""
    for seed in (3, 8):  # cover at least one GCF item and one LCM item
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_gcf_lcm() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
