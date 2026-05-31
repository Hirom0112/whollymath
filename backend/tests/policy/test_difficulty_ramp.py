"""The easy→hard difficulty ramp (CP.B; CURRICULUM_DRAFT.md §1.1).

A lesson must walk from friendly numbers to bias-baiting large denominators, not serve a flat
uniform-random difficulty. These tests pin the ramp schedule (``scheduler.difficulty_for``) and
the generator's difficulty pools (``problem_generators._DENOM_BY_DIFFICULTY``).
"""

from __future__ import annotations

from app.domain.knowledge_components import LIVE_KCS, KnowledgeComponentId
from app.domain.problem_generators import generate_problem
from app.policy.scheduler import difficulty_for


def test_ramp_is_monotonic_non_decreasing_and_capped() -> None:
    tiers = [difficulty_for(i) for i in range(30)]
    assert tiers[0] == 1, "the lesson must open on the easiest tier"
    assert all(b >= a for a, b in zip(tiers, tiers[1:], strict=False)), (
        "the ramp must never get easier"
    )
    assert max(tiers) == 4, "the ramp must reach the hardest tier"
    assert all(1 <= t <= 4 for t in tiers), "tiers stay in 1..4"
    # Past the ramp it stays hard, never wraps back to easy.
    assert difficulty_for(100) == 4


def test_negative_index_opens_easy() -> None:
    assert difficulty_for(-1) == 1


def test_generator_difficulty_narrows_denominators() -> None:
    """Tier 1 draws only small denominators; tier 4 reaches the large ones — for every KC whose
    hard tier is a denominator-size ramp. Number-line is excluded: its hard tiers ramp by
    sign/magnitude (improper, then negative), not denominator size — covered separately below."""
    for kc in LIVE_KCS:
        # Number-line ramps by sign/magnitude; the ratio KCs ramp by their own pools and use
        # whole-number operands (denominator 1) — none is a fraction-denominator ramp.
        if kc in (
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
            KnowledgeComponentId.RATIO_LANGUAGE,
            KnowledgeComponentId.UNIT_RATE,
            KnowledgeComponentId.EQUIVALENT_RATIOS,
            KnowledgeComponentId.PERCENT,
            KnowledgeComponentId.UNIT_CONVERSION,
            KnowledgeComponentId.GCF_LCM,  # whole-number operands; ramps by pair pool, not denom
            KnowledgeComponentId.MULTI_DIGIT_DIVISION,  # whole-number operands; ramps by dividend
            # decimal operands are powers of ten (tenths/hundredths); ramps by place value + digit
            # size, not by a fraction-denominator pool.
            KnowledgeComponentId.DECIMAL_OPERATIONS,
            KnowledgeComponentId.ABSOLUTE_VALUE,  # whole-number operand; ramps by magnitude
            KnowledgeComponentId.INTEGER_ADD_SUBTRACT,  # signed-integer operands; magnitude ramp
            KnowledgeComponentId.SIGNED_NUMBERS,  # signed-integer operand; ramps by magnitude pool
            # write-expressions has NO operands (an expression answer; the constant ramps the
            # phrase, not a denominator) — nothing to read on the denominator path.
            KnowledgeComponentId.WRITE_EXPRESSIONS,
            # evaluate-expressions has whole-number operands (a, x, b; denominator 1); it ramps by
            # coefficient/value/constant pool, not by a fraction denominator.
            KnowledgeComponentId.EVALUATE_EXPRESSIONS,
            # one-step equations use whole-number operands (mode/coefficient/result, all
            # denominator 1); the ramp widens the coefficient pool, not a fraction denominator.
            KnowledgeComponentId.ONE_STEP_EQUATIONS,
            # equivalent-expressions likewise: an expression answer, no operand fractions; the
            # integer coefficients ramp the source expression, not a denominator pool.
            KnowledgeComponentId.EQUIVALENT_EXPRESSIONS,
            # inequalities has NO operands (an inequality answer; the integer bound ramps the
            # constraint phrase, not a denominator) — nothing to read on the denominator path.
            KnowledgeComponentId.INEQUALITIES,
            # coordinate-plane has NO operands (a point-set answer; the coordinate magnitude ramps
            # the plane range, not a denominator) — nothing to read on the denominator path.
            KnowledgeComponentId.COORDINATE_PLANE,
            # classify-number-sets: the operand is the VALUE being classified (an integer or a small
            # fraction), so its denominator spans membership cases (1 for integers, 2–5 for
            # fractions), not a fraction-size ramp — the difficulty widens the value RANGE, not a
            # denominator pool.
            KnowledgeComponentId.CLASSIFY_NUMBER_SETS,
        ):
            continue
        easy_ops = _operand_denoms(kc, difficulty=1)
        hard_ops = _operand_denoms(kc, difficulty=4)
        assert max(easy_ops) <= 4, f"{kc.value} tier-1 operands should be small, got {easy_ops}"
        assert max(hard_ops) >= 8, f"{kc.value} tier-4 operands should reach large, got {hard_ops}"


def test_number_line_ramps_proper_then_improper_then_negative() -> None:
    """The number-line skill ramps by MAGNITUDE/SIGN (CCSS 6.NS.6, PROJECT.md §3.1 scope):
    tiers 1–2 stay a proper fraction on 0–1, tier 3 is improper (>1, placed past the whole),
    tier 4 is negative (<0, left of zero)."""
    from app.domain.knowledge_components import Representation
    from sympy import Rational

    nl = KnowledgeComponentId.NUMBER_LINE_PLACEMENT
    nlr = Representation.NUMBER_LINE
    for seed in range(40):
        easy = generate_problem(nl, seed, nlr, difficulty=1).correct_value
        improper = generate_problem(nl, seed, nlr, difficulty=3).correct_value
        negative = generate_problem(nl, seed, nlr, difficulty=4).correct_value
        assert Rational(0) < easy < Rational(1), f"tier-1 should be proper, got {easy}"
        assert improper > Rational(1), f"tier-3 should be improper (>1), got {improper}"
        assert negative < Rational(0), f"tier-4 should be negative, got {negative}"


def _operand_denoms(kc: KnowledgeComponentId, *, difficulty: int) -> set[int]:
    """Distinct operand denominators a KC's generator emits at a difficulty tier, over many
    seeds. Reads ``operands`` (the sampled fractions), not ``correct_value`` (which for
    addition/common-denominator is a derived sum/LCD, not an operand size)."""
    denoms: set[int] = set()
    for seed in range(60):
        problem = generate_problem(kc, seed, difficulty=difficulty)
        for operand in problem.operands or ():
            denoms.add(int(operand.q))
    return denoms


def test_difficulty_is_deterministic() -> None:
    a = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, 7, difficulty=2)
    b = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, 7, difficulty=2)
    assert a == b, "same (kc, seed, difficulty) must yield an identical problem"
