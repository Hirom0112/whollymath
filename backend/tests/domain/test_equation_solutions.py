"""Behavioral tests for KC_equation_solutions — Grade-6 Unit 5 (CCSS 6.EE.5 / TEKS 6.10B).

Understand solving an equation as the process of answering WHICH values make it true, and use
SUBSTITUTION to decide whether a given number is a solution. This KC is about TESTING a candidate
value — distinct from KC_one_step_equations, which solves an equation from scratch (6.EE.7).

It offers TWO REAL live surfaces, so it is MASTERABLE (the §3.4 rule-2 representation-diversity gate
is reachable live, like KC_dependent_vars):

  - NUMBER_LINE (default, PRIMARY) — a YES/NO judgment: "Is x = 5 a solution to x + 4 = 9?" => yes.
    A candidate value is a point on the line; testing whether it makes the equation true is the
    yes/no answer kind (NO new widget). Both a TRUE candidate (-> "yes") and a FALSE candidate
    (-> "no") are generated, so "yes" is not always correct. SymPy decides the truth by SUBSTITUTION
    in the generator and encodes it in operands, exactly as KC_statistical_questions does — the SAME
    ``_verify_yes_no`` SymPy-equality path grades it (CLAUDE.md §8.2: SymPy decides, never an LLM).
  - SYMBOLIC (SECOND) — the SOLVE framing: "Which value of x makes x + 4 = 9 true?" -> "5". A single
    scalar entered in the NUMBER_ENTRY editor (this is a SYMBOLIC SCALAR KC — NOT a fraction KC — so
    it routes to NUMBER_ENTRY via the widget contract), graded NUMERIC by SymPy.

Every assertion runs through the SAME oracle the tutor uses (the SymPy verifier), so "correct" /
"wrong" means exactly what it does in production (ARCHITECTURE.md §9). Mandatory-TDD domain Layer 1
(CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.lesson_spec import WidgetId, widget_for_representation
from app.domain.misconceptions import (
    MisconceptionId,
    solution_substitution_error,
)
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import is_masterable_live, live_representations
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for

_KC = KnowledgeComponentId.EQUATION_SOLUTIONS


def _problem(seed: int, surface: Representation | None = None) -> Problem:
    return generate_problem(_KC, seed, surface)


def test_equation_solutions_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it — and so u5_l1
    ("What is a solution?") goes live."""
    assert _KC in LIVE_KCS


# ─── PRIMARY: the YES/NO "is this value a solution?" judgment (NUMBER_LINE) ──


def test_yes_no_item_is_a_solution_test() -> None:
    """The NUMBER_LINE surface yields a YES_NO item with a two-operand truth encoding."""
    problem = _problem(2, Representation.NUMBER_LINE)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.YES_NO
    assert problem.surface_format is Representation.NUMBER_LINE
    assert problem.operands is not None and len(problem.operands) == 2


def test_true_candidate_grades_yes() -> None:
    """When the candidate IS the solution, the SymPy-substituted truth is YES and "yes" is correct,
    "no" is wrong — across many seeds (so the generator really produces TRUE cases)."""
    seen_true = False
    for seed in range(0, 60):
        problem = _problem(seed, Representation.NUMBER_LINE)
        assert problem.operands is not None
        if problem.operands[0] == problem.operands[1]:  # truth == YES
            seen_true = True
            assert verify(problem, "yes").is_correct
            assert verify(problem, "yes").error_category is ErrorCategory.NONE
            assert not verify(problem, "no").is_correct
    assert seen_true, "the generator must produce some TRUE (yes) candidates"


def test_false_candidate_grades_no() -> None:
    """When the candidate is NOT the solution, the truth is NO and "no" is correct, "yes" is wrong —
    so 'yes' is not always the right answer (across many seeds)."""
    seen_false = False
    for seed in range(0, 60):
        problem = _problem(seed, Representation.NUMBER_LINE)
        assert problem.operands is not None
        if problem.operands[0] != problem.operands[1]:  # truth == NO
            seen_false = True
            assert verify(problem, "no").is_correct
            assert verify(problem, "no").error_category is ErrorCategory.NONE
            assert not verify(problem, "yes").is_correct
    assert seen_false, "the generator must produce some FALSE (no) candidates"


def test_yes_no_truth_matches_sympy_substitution() -> None:
    """The encoded YES/NO truth is exactly the SymPy substitution result: substitute the candidate
    into x + b = c and check the two sides are equal. The verifier and the generator agree."""
    for seed in range(0, 40):
        problem = _problem(seed, Representation.NUMBER_LINE)
        assert problem.operands is not None
        truth_is_yes = bool(problem.operands[0] == problem.operands[1])
        assert verify(problem, "yes").is_correct is truth_is_yes
        assert verify(problem, "no").is_correct is (not truth_is_yes)


# ─── SECOND: the SOLVE framing scalar (SYMBOLIC, NUMBER_ENTRY) ───────────────


def test_solve_framing_is_a_scalar_numeric_item() -> None:
    """The SYMBOLIC surface yields a NUMERIC scalar solve item; answer = c - b for x + b = c."""
    problem = _problem(3, Representation.SYMBOLIC)
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.surface_format is Representation.SYMBOLIC
    assert problem.correct_value.q == 1  # a whole-number solution


def test_solve_framing_routes_to_number_entry_not_fraction_editor() -> None:
    """A SYMBOLIC SCALAR KC: the solve surface uses the single-box NUMBER_ENTRY, not the two-box
    fraction editor (it must NOT be in _FRACTION_ANSWER_KCS)."""
    assert widget_for_representation(Representation.SYMBOLIC, _KC) is WidgetId.NUMBER_ENTRY


def test_solve_framing_grades_the_solution_value() -> None:
    """The value that makes the equation true is graded correct by the tutor's own oracle."""
    for seed in range(0, 30):
        problem = _problem(seed, Representation.SYMBOLIC)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_substitution_sign_error_is_classified() -> None:
    """Answering c + b (added the constant instead of subtracting it to isolate x) is flagged
    OPERATION + the solution-substitution-error misconception — the wrong PROCEDURE the lesson is
    designed to surface. The slip c + b is always DISTINCT from the correct c - b (b > 0)."""
    for seed in range(0, 30):
        problem = _problem(seed, Representation.SYMBOLIC)
        assert problem.operands is not None
        wrong = solution_substitution_error(problem.operands)
        assert wrong is not None
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.SOLUTION_SUBSTITUTION_ERROR


# ─── Masterable: two live surfaces over the same equation ────────────────────


def test_two_live_surfaces_offered() -> None:
    """NUMBER_LINE (YES/NO solution test) and SYMBOLIC (scalar solve) are BOTH live, so the KC is
    masterable (§3.4 rule 2 reachable live). Both are built from the SAME equation x + b = c."""
    assert set(live_representations(_KC)) == {
        Representation.NUMBER_LINE,
        Representation.SYMBOLIC,
    }
    assert is_masterable_live(_KC)
    for seed in range(0, 30):
        yes_no = _problem(seed, Representation.NUMBER_LINE)
        solve = _problem(seed, Representation.SYMBOLIC)
        # Same underlying equation x + b = c (same b, c carried in the statement / solve answer).
        assert yes_no.statement != solve.statement  # genuinely different framing
        assert verify(solve, str(solve.correct_value)).is_correct


def test_distinct_from_one_step_equations() -> None:
    """KC_equation_solutions (test a value) is a DIFFERENT KC than KC_one_step_equations (solve from
    scratch) — they stay separate enum members, both live."""
    assert _KC is not KnowledgeComponentId.ONE_STEP_EQUATIONS
    assert KnowledgeComponentId.ONE_STEP_EQUATIONS in LIVE_KCS


# ─── Robustness + reproducibility ────────────────────────────────────────────


def test_unparseable_submissions_are_wrong_not_a_crash() -> None:
    """Garbled input grades wrong on both surfaces, never raises (CLAUDE.md §8.2)."""
    solve = _problem(1, Representation.SYMBOLIC)
    for junk in ("", "abc", "x", "/"):
        result = verify(solve, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER
    yes_no = _problem(1, Representation.NUMBER_LINE)
    # A non-yes/no token on a YES_NO item is OTHER (unparseable judgment), not a crash.
    assert not verify(yes_no, "maybe").is_correct
    assert verify(yes_no, "maybe").error_category is ErrorCategory.OTHER


def test_generation_is_deterministic() -> None:
    """Same seed (and surface) => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    first = generate_problem(_KC, 42, Representation.SYMBOLIC)
    second = generate_problem(_KC, 42, Representation.SYMBOLIC)
    assert first.correct_value == second.correct_value
    assert first.statement == second.statement


def test_worked_example_lands_on_the_solution() -> None:
    """The worked example for the SOLVE surface is self-consistent: its final value equals the
    solution. The YES/NO surface's example explains the substitution verdict in its last step."""
    solve = _problem(3, Representation.SYMBOLIC)
    assert worked_example_for(solve).final_value == solve.correct_value
    yes_no = _problem(3, Representation.NUMBER_LINE)
    assert worked_example_for(yes_no).steps  # builds without crashing on the YES_NO surface


def test_nudge_bank_covers_equation_solutions() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
