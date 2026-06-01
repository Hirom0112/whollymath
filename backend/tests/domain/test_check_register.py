"""Behavioral tests for KC_check_register — Grade-6 Unit 8 (TEKS 6.14C).

Balance a check register: keep a RUNNING BALANCE across a short sequence of deposits (+) and
withdrawals (−). This is one of the two SymPy-gradeable financial-literacy KCs (owner decision
DEC.FINLIT); the other four U8 lessons stay concept stubs.

It offers TWO REAL live surfaces, so it is MASTERABLE (the §3.4 rule-2 representation-diversity gate
is reachable live, like KC_equation_solutions):

  - SYMBOLIC (default, PRIMARY) — the ENDING BALANCE: given a starting balance and a sequence of
    deposits/withdrawals, compute the final balance (a currency/decimal answer like "182.50"). The
    answer is the exact SymPy sum of the signed transactions (deposits +, withdrawals −); the data
    is VARIABLE-LENGTH (``operands = (start, *signed_transactions)``, matched ``operand_count=None``
    like the stats KCs). Entered in the single-box NUMBER_ENTRY editor (NOT a fraction KC).
  - NUMBER_LINE (SECOND) — an OVERDRAFT check: "After these transactions, is the balance enough to
    cover a $X withdrawal?" A YES/NO judgment whose SymPy truth (balance >= X) is encoded in
    ``operands`` exactly as KC_equation_solutions encodes its yes/no truth — the SAME
    ``_verify_yes_no`` SymPy path grades it (CLAUDE.md §8.2: SymPy decides, never an LLM). Both
    "enough" (-> yes) and "not enough" (-> no) cases are produced, so "yes" is not always correct.

Every assertion runs through the SAME oracle the tutor uses (the SymPy verifier). Mandatory-TDD
domain Layer 1 (CLAUDE.md §2).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId, Representation
from app.domain.lesson_spec import WidgetId, widget_for_representation
from app.domain.misconceptions import (
    MisconceptionId,
    add_withdrawal_instead_of_subtracting,
)
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.domain.verifier import ErrorCategory, verify
from app.policy.scheduler import is_masterable_live, live_representations
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.CHECK_REGISTER


def _problem(seed: int, surface: Representation | None = None) -> Problem:
    return generate_problem(_KC, seed, surface)


def test_check_register_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it — and so u8_l3
    ("Balance a check register") goes live."""
    assert _KC in LIVE_KCS


# ─── PRIMARY: the ending-balance scalar (SYMBOLIC, NUMBER_ENTRY) ─────────────


def test_ending_balance_is_a_numeric_scalar_item() -> None:
    """The SYMBOLIC surface yields a NUMERIC ending-balance item over a variable-length
    (start, *transactions) operand tuple."""
    problem = _problem(3, Representation.SYMBOLIC)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.surface_format is Representation.SYMBOLIC
    assert problem.operands is not None and len(problem.operands) >= 3  # start + >=2 transactions


def test_ending_balance_equals_the_signed_sum() -> None:
    """The correct value is exactly the SymPy sum of the starting balance and the signed
    transactions (deposits +, withdrawals −) — the running balance, graded by the tutor's oracle."""
    for seed in range(0, 40):
        problem = _problem(seed, Representation.SYMBOLIC)
        assert problem.operands is not None
        expected = sum(problem.operands, Rational(0))
        assert problem.correct_value == expected
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE


def test_ending_balance_routes_to_number_entry_not_fraction_editor() -> None:
    """A currency/decimal answer goes in the single-box NUMBER_ENTRY, not the two-box fraction
    editor (it must NOT be in _FRACTION_ANSWER_KCS — the editor cannot express a decimal)."""
    assert widget_for_representation(Representation.SYMBOLIC, _KC) is WidgetId.NUMBER_ENTRY


def test_a_decimal_currency_answer_is_accepted() -> None:
    """A balance with cents grades correct when typed as a decimal string ("182.50"), since the
    verifier parses a decimal literal EXACTLY (no float fuzz)."""
    seen_cents = False
    for seed in range(0, 60):
        problem = _problem(seed, Representation.SYMBOLIC)
        if problem.correct_value.q != 1:  # a fractional dollar amount (has cents)
            seen_cents = True
            cents = problem.correct_value * 100
            assert cents.q == 1  # a whole number of cents (currency is exact to the penny)
            decimal_text = f"{int(cents) // 100}.{int(cents) % 100:02d}"
            assert verify(problem, decimal_text).is_correct
    assert seen_cents, "the generator must produce some balances with cents"


def test_adding_a_withdrawal_is_classified() -> None:
    """ADDING a withdrawal instead of subtracting it (a sign slip) is flagged OPERATION + the
    add-withdrawal misconception — the wrong PROCEDURE the lesson surfaces. The slip is always
    DISTINCT from the correct running balance (a withdrawal is always present and nonzero)."""
    for seed in range(0, 40):
        problem = _problem(seed, Representation.SYMBOLIC)
        assert problem.operands is not None
        wrong = add_withdrawal_instead_of_subtracting(problem.operands)
        assert wrong is not None
        assert wrong != problem.correct_value
        result = verify(problem, str(wrong))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.ADD_WITHDRAWAL_INSTEAD_OF_SUBTRACTING


# ─── SECOND: the overdraft YES/NO check (NUMBER_LINE) ────────────────────────


def test_overdraft_item_is_a_yes_no_check() -> None:
    """The NUMBER_LINE surface yields a YES_NO overdraft item with a two-operand truth encoding."""
    problem = _problem(2, Representation.NUMBER_LINE)
    assert problem.answer_kind is AnswerKind.YES_NO
    assert problem.surface_format is Representation.NUMBER_LINE
    assert problem.operands is not None and len(problem.operands) == 2


def test_overdraft_truth_is_sympy_and_both_verdicts_appear() -> None:
    """Across seeds the overdraft check produces BOTH 'enough' (-> yes) and 'not enough' (-> no)
    cases, and the encoded truth grades the right verdict correct via the SAME yes/no SymPy path."""
    seen_yes = seen_no = False
    for seed in range(0, 60):
        problem = _problem(seed, Representation.NUMBER_LINE)
        assert problem.operands is not None
        truth_is_yes = bool(problem.operands[0] == problem.operands[1])
        if truth_is_yes:
            seen_yes = True
            assert verify(problem, "yes").is_correct
            assert not verify(problem, "no").is_correct
        else:
            seen_no = True
            assert verify(problem, "no").is_correct
            assert not verify(problem, "yes").is_correct
    assert seen_yes, "the generator must produce some 'enough' (yes) overdraft cases"
    assert seen_no, "the generator must produce some 'not enough' (no) overdraft cases"


# ─── Masterable: two live surfaces ───────────────────────────────────────────


def test_two_live_surfaces_offered() -> None:
    """SYMBOLIC (ending balance) and NUMBER_LINE (overdraft YES/NO) are BOTH live, so the KC is
    masterable (§3.4 rule 2 reachable live)."""
    assert set(live_representations(_KC)) == {
        Representation.SYMBOLIC,
        Representation.NUMBER_LINE,
    }
    assert is_masterable_live(_KC)


# ─── Robustness + reproducibility ────────────────────────────────────────────


def test_unparseable_submissions_are_wrong_not_a_crash() -> None:
    """Garbled input grades wrong on both surfaces, never raises (CLAUDE.md §8.2)."""
    balance = _problem(1, Representation.SYMBOLIC)
    for junk in ("", "abc", "$", "/"):
        result = verify(balance, junk)
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OTHER
    overdraft = _problem(1, Representation.NUMBER_LINE)
    assert not verify(overdraft, "maybe").is_correct
    assert verify(overdraft, "maybe").error_category is ErrorCategory.OTHER


def test_generation_is_deterministic() -> None:
    """Same seed (and surface) => identical problem (the reproducibility contract, §4.1)."""
    assert generate_problem(_KC, 42).statement == generate_problem(_KC, 42).statement
    first = generate_problem(_KC, 42, Representation.SYMBOLIC)
    second = generate_problem(_KC, 42, Representation.SYMBOLIC)
    assert first.correct_value == second.correct_value
    assert first.statement == second.statement


def test_worked_example_lands_on_the_balance() -> None:
    """The worked example for the ending-balance surface lands on the correct running balance; the
    overdraft surface's example explains the YES/NO verdict in its last step without crashing."""
    balance = _problem(3, Representation.SYMBOLIC)
    assert worked_example_for(balance).final_value == balance.correct_value
    overdraft = _problem(3, Representation.NUMBER_LINE)
    assert worked_example_for(overdraft).steps


def test_nudge_bank_covers_check_register() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
