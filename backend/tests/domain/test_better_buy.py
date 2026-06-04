"""Behavioral tests for KC_better_buy — a Grade-6 Unit-1 lesson (2026-06-04).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope YES/NO "is Store A the better buy?" item over two
stores selling the SAME item, each with a (quantity, price) pair; the better buy is the
LOWER price-per-unit (price/quantity). The truth rides in ``operands`` as the 4-tuple
(qA, pA, qB, pB) so the verifier recomputes the unit-price comparison with EXACT SymPy
Rationals (no floats, no stored boolean); a wrong yes/no is scored MAGNITUDE with no
operand-classified misconception (the existing YES_NO contract — see _verify_yes_no);
the worked example computes each unit price, compares, and names the better buy; and
generation is deterministic (PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2).
Skill: CCSS 6.RP.3b / 6.RP.2 — solve a rate problem by comparing two unit rates.

DIAGNOSTIC OF THE COMPARE-TOTALS TRAP: a meaningful fraction of items are built so the
store with the LOWER TOTAL PRICE (or MORE items) is NOT the better unit-rate buy — a
student who compares totals or item counts instead of unit prices gives the wrong yes/no.

NOTE on the YES/NO wrong-answer path: the YES_NO answer kind does NOT use the operand-based
``_WRONG_ANSWER_MODELS`` mechanism. ``_verify_yes_no`` computes truth by SymPy over the
operands and, on a wrong judgment, returns ``ErrorCategory.MAGNITUDE`` with
``matched_misconception=None`` — it never over-claims a specific misconception (exactly how
the existing STATISTICAL_QUESTIONS / EQUIVALENCE / NUMBER_LINE YES_NO KCs behave). The
"compare totals not unit rates" misconception is therefore modeled in the registry/enum for
catalog completeness and hint framing, but is NOT classified by the verifier; this test pins
the actual MAGNITUDE/None behavior.
"""

from __future__ import annotations

from app.domain.knowledge_components import (
    LIVE_KCS,
    KnowledgeComponentId,
    Representation,
    get_kc,
)
from app.domain.lesson_spec import LESSON_SPEC_REGISTRY
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.BETTER_BUY


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _store_a_is_better(problem: Problem) -> bool:
    """The item's truth, read from operands exactly as ``_verify_yes_no`` does for better-buy.

    Operands are (qA, pA, qB, pB); Store A is the better buy iff its unit price is strictly
    lower: pA/qA < pB/qB. Compared by cross-multiplication over EXACT Rationals (qA, qB > 0)."""
    assert problem.operands is not None and len(problem.operands) == 4
    qa, pa, qb, pb = problem.operands
    return bool(pa * qb < pb * qa)  # pA/qA < pB/qB ⟺ pA·qB < pB·qA


def test_better_buy_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_generated_item_is_a_clean_in_scope_yes_no_problem() -> None:
    """The generator yields a YES/NO judgment with a four-operand (qA,pA,qB,pB) truth carrier."""
    problem = _problem(7)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.YES_NO
    assert problem.operands is not None and len(problem.operands) == 4
    qa, pa, qb, pb = problem.operands
    # Quantities and prices are positive (a store sells a positive count for a positive price).
    assert qa > 0 and pa > 0 and qb > 0 and pb > 0
    # The two unit prices are DISTINCT (no ties), so the better buy is unambiguous.
    assert pa * qb != pb * qa
    # The statement poses the better-buy comparison the learner judges yes/no.
    assert "?" in problem.statement
    assert "better buy" in problem.statement.lower()


def test_correct_verdict_verifies_correct() -> None:
    """The canonical yes/no (yes iff Store A's unit price is lower) is graded correct."""
    for seed in range(1, 60):
        problem = _problem(seed)
        truth = "yes" if _store_a_is_better(problem) else "no"
        result = verify(problem, truth)
        assert result.is_correct, f"seed {seed}: {truth} should be correct"
        assert result.error_category is ErrorCategory.NONE
        assert result.matched_misconception is None


def test_wrong_verdict_is_magnitude_with_no_misconception() -> None:
    """A flipped judgment is wrong → MAGNITUDE, NO operand-classified misconception (YES_NO path).

    ``_verify_yes_no`` returns MAGNITUDE with ``matched_misconception=None`` on any wrong
    judgment (it never over-claims a misconception), exactly like the existing YES_NO KCs.
    """
    for seed in range(1, 60):
        problem = _problem(seed)
        flipped = "no" if _store_a_is_better(problem) else "yes"
        result = verify(problem, flipped)
        assert not result.is_correct, f"seed {seed}: {flipped} should be wrong"
        assert result.error_category is ErrorCategory.MAGNITUDE
        assert result.matched_misconception is None


def test_both_verdicts_are_generated() -> None:
    """Across seeds the generator yields BOTH a better-Store-A (YES) and a worse-Store-A (NO)."""
    verdicts = {_store_a_is_better(_problem(s)) for s in range(1, 80)}
    assert verdicts == {True, False}


def test_unit_prices_are_exact_rationals_never_floats() -> None:
    """Every operand is an exact SymPy Rational — no float ever enters the comparison (§8.2)."""
    for seed in range(1, 40):
        problem = _problem(seed)
        assert problem.operands is not None
        for operand in problem.operands:
            assert isinstance(operand, Rational)


def test_some_items_are_compare_totals_diagnostic() -> None:
    """A meaningful fraction of items trap the compare-totals / more-items student.

    The better unit buy is NOT the store with the lower TOTAL price (nor the one with MORE
    items): a learner who compares totals or item counts instead of unit rates answers wrong.
    We require this property to hold for a non-trivial share of seeds, so the lesson is
    genuinely diagnostic of the trap rather than incidentally so on a lucky seed.
    """
    lower_total_is_not_better = 0
    more_items_is_not_better = 0
    total = 0
    for seed in range(1, 120):
        problem = _problem(seed)
        assert problem.operands is not None
        qa, pa, qb, pb = problem.operands
        a_is_better = _store_a_is_better(problem)
        total += 1
        # Which store has the lower TOTAL price? (Skip ties — neither traps cleanly.)
        if pa != pb:
            lower_total_store_a = bool(pa < pb)
            if lower_total_store_a != a_is_better:
                lower_total_is_not_better += 1
        # Which store sells MORE items? (Skip ties.)
        if qa != qb:
            more_items_store_a = bool(qa > qb)
            if more_items_store_a != a_is_better:
                more_items_is_not_better += 1
    # At least a fifth of items must trap EACH naive comparison — a real diagnostic share.
    assert lower_total_is_not_better >= total // 5, lower_total_is_not_better
    assert more_items_is_not_better >= total // 5, more_items_is_not_better


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    assert generate_problem(_KC, 42).operands == generate_problem(_KC, 42).operands


def test_word_problem_surface_is_the_same_judgment() -> None:
    """The KC advertises SYMBOLIC + WORD_PROBLEM; the WORD_PROBLEM surface is the same yes/no item.

    The comparison text IS a word problem, so the two advertised reps render the SAME judgment
    (the answer kind and truth do not change with the surface) — the ≥2-rep advertisement that
    satisfies the LessonSpec contract.
    """
    advertised = get_kc(_KC).representations
    assert Representation.SYMBOLIC in advertised
    assert Representation.WORD_PROBLEM in advertised
    word = generate_problem(_KC, 11, Representation.WORD_PROBLEM)
    assert word.answer_kind is AnswerKind.YES_NO
    assert "?" in word.statement


def test_worked_example_names_the_better_buy() -> None:
    """The worked example's last step states the canonical verdict (a non-magnitude answer).

    Like KC_statistical_questions (a yes/no verdict), the better-buy verdict is not a Rational
    magnitude, so the final step carries ``revealed_value=None`` and names the verdict in its
    ``shown`` text. The verdict the example lands on agrees with the verifier's truth.
    """
    for seed in (3, 4, 5, 6):
        problem = _problem(seed)
        example = worked_example_for(problem)
        a_is_better = _store_a_is_better(problem)
        verdict_phrase = "store a is the better buy" if a_is_better else "store b is the better buy"
        assert verdict_phrase in example.steps[-1].shown.lower()
        assert example.steps[-1].revealed_value is None


def test_nudge_bank_covers_better_buy() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text


def test_lesson_spec_advertises_two_reps_and_routes_errors_off_word_problem() -> None:
    """The lesson advertises ≥2 reps and routes every error to a rep WITH a surface state.

    WORD_PROBLEM has no surface state, so error routes must never target it — they stay on the
    live SYMBOLIC surface (practice-only: SYMBOLIC is the only live answer surface).
    """
    spec = LESSON_SPEC_REGISTRY.get(_KC)
    assert len(spec.representations) >= 2
    assert spec.misconceptions  # the lesson-spec contract requires ≥1 applicable misconception
    for route in spec.error_routes:
        assert route.representation is not Representation.WORD_PROBLEM
        assert route.representation is Representation.SYMBOLIC
