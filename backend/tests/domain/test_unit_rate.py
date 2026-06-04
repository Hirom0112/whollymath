"""Behavioral tests for KC_unit_rate — the first Grade-6 (Unit 1) lesson (2026-05-30).

Exercises the new KC through the SAME oracle the tutor uses (the SymPy verifier), so
"correct"/"wrong" means exactly what it means in production (ARCHITECTURE.md §9). Pins:
the generator builds a clean, in-scope unit rate in BOTH modes (per-ONE and SCALE-the-rate),
the verifier confirms the correct rate and classifies the rate-inversion misconception (on
the per-ONE direction only); the worked example lands on the answer; and generation is
deterministic (PROJECT.md §4.1). Mandatory-TDD domain Layer 1 (CLAUDE.md §2).

SCALE mode (mode 1) implements 6.RP.3b multi-step rate reasoning ("$24 for 4 tickets; how
much for 7?") so the catalog lesson U1.L4 ("Rate problems") is genuinely distinct from the
per-ONE generator it reuses (panel audit, 2026-06-04).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.misconceptions import MisconceptionId, invert_rate
from app.domain.problem_generators import (
    _UNIT_RATE_PER_ONE,
    _UNIT_RATE_SCALE,
    AnswerKind,
    Problem,
    generate_problem,
)
from app.domain.verifier import ErrorCategory, verify
from app.tutor.hints import select_nudge
from app.tutor.worked_example import worked_example_for
from sympy import Rational

_KC = KnowledgeComponentId.UNIT_RATE


def _problem(seed: int) -> Problem:
    return generate_problem(_KC, seed)


def _mode(problem: Problem) -> int:
    """The mode flag is the LAST operand in both shapes (3-tuple per-ONE, 4-tuple scale)."""
    assert problem.operands is not None
    return int(problem.operands[-1])


def test_unit_rate_is_live() -> None:
    """The KC is content-complete (registered), so the tutor can schedule it."""
    assert _KC in LIVE_KCS


def test_per_one_problem_is_clean_and_unchanged() -> None:
    """A per-ONE item (mode 0) is still (total, count, mode) with answer total/count."""
    # Seed 7 historically generated a per-ONE item; assert that shape explicitly.
    per_one_seed = next(s for s in range(1, 200) if _mode(_problem(s)) == _UNIT_RATE_PER_ONE)
    problem = _problem(per_one_seed)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 3
    total, count, mode = problem.operands
    assert int(mode) == _UNIT_RATE_PER_ONE
    assert problem.correct_value == total / count
    assert problem.correct_value > 0


def test_scale_problem_is_a_clean_multi_step_rate() -> None:
    """A SCALE item (mode 1) is (total, count, new_count, mode); answer = r*new_count, a whole."""
    scale_seed = next(s for s in range(1, 200) if _mode(_problem(s)) == _UNIT_RATE_SCALE)
    problem = _problem(scale_seed)
    assert problem.kc is _KC
    assert problem.answer_kind is AnswerKind.NUMERIC
    assert problem.operands is not None and len(problem.operands) == 4
    total, count, new_count, mode = problem.operands
    assert int(mode) == _UNIT_RATE_SCALE
    assert int(new_count) != int(count)  # the scaling is to a DIFFERENT number of units
    rate = Rational(total, count)
    assert problem.correct_value == rate * new_count
    # answer is a positive WHOLE number (clean by construction: total = r*count, r whole)
    assert problem.correct_value > 0
    assert problem.correct_value.q == 1


def test_both_modes_appear_across_seeds() -> None:
    """The seeded RNG produces BOTH the per-ONE and the SCALE direction across seeds."""
    modes = {_mode(_problem(s)) for s in range(1, 60)}
    assert _UNIT_RATE_PER_ONE in modes
    assert _UNIT_RATE_SCALE in modes


def test_correct_answer_verifies_correct_both_modes() -> None:
    """The correct value (rate or scaled total) is graded correct by the tutor's own oracle."""
    for seed in range(1, 40):
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct, f"seed {seed} mode {_mode(problem)}"
        assert result.error_category is ErrorCategory.NONE


def test_rate_inversion_is_classified_on_per_one() -> None:
    """The inverted rate (count/total) is flagged OPERATION + rate-inversion — per-ONE only."""
    seeds = [s for s in range(1, 200) if _mode(_problem(s)) == _UNIT_RATE_PER_ONE][:12]
    assert seeds  # sanity: per-ONE items exist
    for seed in seeds:
        problem = _problem(seed)
        assert problem.operands is not None
        total, count = problem.operands[0], problem.operands[1]
        inverted = invert_rate(int(total), int(count))
        # total > count > 0 ⇒ total/count != count/total, so this is a genuine wrong value.
        result = verify(problem, str(inverted))
        assert not result.is_correct
        assert result.error_category is ErrorCategory.OPERATION
        assert result.matched_misconception is MisconceptionId.RATE_INVERSION


def test_rate_inversion_is_inert_on_scale() -> None:
    """The per-ONE rate-inversion misconception does NOT fire on a SCALE item (mode 1)."""
    seeds = [s for s in range(1, 200) if _mode(_problem(s)) == _UNIT_RATE_SCALE][:12]
    assert seeds  # sanity: scale items exist
    for seed in seeds:
        problem = _problem(seed)
        assert problem.operands is not None
        total, count = problem.operands[0], problem.operands[1]
        inverted = invert_rate(int(total), int(count))
        result = verify(problem, str(inverted))
        # The inverted-rate value, if submitted, must never be labelled rate-inversion here:
        # the misconception is gated to the per-ONE direction.
        assert result.matched_misconception is not MisconceptionId.RATE_INVERSION


def test_correct_scale_answer_is_never_flagged() -> None:
    """A correct SCALE answer is graded correct, never mislabeled as any misconception."""
    seeds = [s for s in range(1, 200) if _mode(_problem(s)) == _UNIT_RATE_SCALE][:12]
    assert seeds
    for seed in seeds:
        problem = _problem(seed)
        result = verify(problem, str(problem.correct_value))
        assert result.is_correct
        assert result.error_category is ErrorCategory.NONE
        assert result.matched_misconception is None


def test_generation_is_deterministic() -> None:
    """Same seed ⇒ identical problem (the reproducibility contract, §4.1)."""
    for seed in (5, 17, 42, 100):
        a, b = generate_problem(_KC, seed), generate_problem(_KC, seed)
        assert a.statement == b.statement
        assert a.correct_value == b.correct_value
        assert a.operands == b.operands


def test_worked_example_lands_on_the_answer_both_modes() -> None:
    """The worked example's final step equals the correct value, for per-ONE AND scale."""
    per_one_seed = next(s for s in range(1, 200) if _mode(_problem(s)) == _UNIT_RATE_PER_ONE)
    scale_seed = next(s for s in range(1, 200) if _mode(_problem(s)) == _UNIT_RATE_SCALE)
    for seed in (per_one_seed, scale_seed):
        problem = _problem(seed)
        example = worked_example_for(problem)
        assert example.final_value == problem.correct_value


def test_nudge_bank_covers_unit_rate() -> None:
    """A conceptual nudge exists for the KC (no numbers, just orientation)."""
    nudge = select_nudge(_KC)
    assert nudge.kc is _KC
    assert nudge.text
