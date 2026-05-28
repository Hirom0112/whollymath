"""Tests for the Layer-1 problem generators + the shared ``Problem`` type (Slice 1.3).

Written test-first per CLAUDE.md §2 (TDD is mandatory for the domain model — the
single most load-bearing system; if the problem generators are wrong, the mastery
model, the persona harness, and the transfer test all train and evaluate on bad
problems). These tests pin the contract that the LOCKED hybrid problem-generation
strategy (PROJECT.md §8, decision 0.D.1) requires of Layer 1:

  - one shared, typed, immutable ``Problem`` type that BOTH procedurally-generated
    problems AND the handpicked ``diagnostic_gems.json`` bank items conform to, so
    downstream code is source-agnostic;
  - a procedural generator PER KC producing in-scope, well-formed problems
    (positive fractions only; equivalence / common-denominator / add / subtract /
    number-line; NO multiplication or division — PROJECT.md §3.1);
  - surface format is a generator PARAMETER (symbolic / area_model / number_line /
    word_problem) so interleaving across formats is possible and Surface Sam can be
    defeated (decision 0.D.1);
  - generators are DETERMINISTIC given a seed (same seed ⇒ identical problems),
    which is what makes the persona harness reproducible (PROJECT.md §4.1,
    ARCHITECTURE.md §5 Layer 3);
  - a bank item adapts cleanly onto the ``Problem`` type.

SymPy IS allowed here (this is ``domain/`` — CLAUDE.md §7, ARCHITECTURE.md §14): the
correct answer of every generated problem is computed with ``sympy.Rational``, never
asserted by hand. No LLM, no DB (CLAUDE.md §8.1/§8.2): the generators are pure,
deterministic functions. The answer VERIFIER (Slice 1.4) and any mastery/policy
logic are intentionally NOT tested here.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import (
    GENERATORS,
    AnswerKind,
    Problem,
    generate_problem,
    problem_from_bank_item,
)
from sympy import Rational

# The five KCs each get a procedural generator (PROJECT.md §3.1, ARCHITECTURE.md §4).
ALL_KCS = (
    KnowledgeComponentId.EQUIVALENCE,
    KnowledgeComponentId.COMMON_DENOMINATOR,
    KnowledgeComponentId.ADDITION_UNLIKE,
    KnowledgeComponentId.SUBTRACTION_UNLIKE,
    KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
)

_GEMS_PATH = Path(__file__).resolve().parents[2] / "app" / "domain" / "diagnostic_gems.json"


def _load_items() -> list[dict[str, Any]]:
    """Load the gem-bank items; skip the bank-adapter checks if the bank is absent.

    The domain layer's tests must not hard-depend on a downstream data asset
    (mirrors test_knowledge_components.py / test_misconceptions.py), so the
    bank-adapter tests skip when the bank is not on disk rather than failing.
    """
    if not _GEMS_PATH.exists():
        pytest.skip("diagnostic_gems.json not present — bank-adapter checks skipped")
    data = json.loads(_GEMS_PATH.read_text())
    items: list[dict[str, Any]] = list(data["items"])
    return items


# ─── The shared Problem type ─────────────────────────────────────────────────


def test_problem_is_immutable() -> None:
    """Problem objects are frozen — Layer 1 is a source of truth, not mutable state."""
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=1)
    with pytest.raises(AttributeError):
        problem.problem_id = "tampered"  # type: ignore[misc]


def test_problem_carries_the_minimum_required_fields() -> None:
    """A Problem exposes a stable id, KC, format, statement, answer, and formats.

    These are the 0.D.1 "one shared type" fields downstream code (mastery model,
    persona simulator, transfer test) reads regardless of where the problem came
    from. The correct answer is a SymPy-computed value.
    """
    problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=1)
    assert isinstance(problem, Problem)
    assert problem.problem_id.strip()
    assert problem.kc in ALL_KCS
    assert isinstance(problem.surface_format, Representation)
    assert problem.statement.strip()
    assert isinstance(problem.correct_value, Rational)
    assert len(problem.representations_available) >= 1
    assert all(isinstance(r, Representation) for r in problem.representations_available)
    # The surface format the problem is presented in must be one it can be shown in.
    assert problem.surface_format in problem.representations_available


def test_problem_operands_are_present_for_arithmetic_kcs() -> None:
    """Arithmetic problems expose their operand fractions for the simulator/verifier.

    The persona simulator needs the operands to apply a misconception generator
    (e.g. add-across on the operands), so a generated arithmetic problem carries
    them rather than only the rendered string.
    """
    problem = generate_problem(KnowledgeComponentId.SUBTRACTION_UNLIKE, seed=3)
    assert problem.operands is not None
    assert all(isinstance(op, Rational) for op in problem.operands)
    assert len(problem.operands) == 2


# ─── One generator per KC, registered ────────────────────────────────────────


def test_a_generator_exists_for_every_kc() -> None:
    """Exactly the five KCs have a registered procedural generator (PROJECT.md §3.1)."""
    assert set(GENERATORS.keys()) == set(ALL_KCS)
    assert len(GENERATORS) == 5


@pytest.mark.parametrize("kc", ALL_KCS)
def test_generator_produces_a_problem_for_its_kc(kc: KnowledgeComponentId) -> None:
    """Each KC's generator returns a Problem tagged with that same KC."""
    problem = generate_problem(kc, seed=7)
    assert problem.kc == kc


# ─── In-scope: positive fractions, no mult/div (PROJECT.md §3.1) ──────────────


@pytest.mark.parametrize("kc", ALL_KCS)
@pytest.mark.parametrize("seed", range(25))
def test_generated_problems_are_in_scope(kc: KnowledgeComponentId, seed: int) -> None:
    """Every generated problem uses positive fractions strictly between 0 and 1.

    PROJECT.md §3.1 locks the scope to POSITIVE fractions only. We sample many
    seeds per KC so a generator that occasionally emits an out-of-scope operand
    (zero, negative, or a denominator of 1) is caught.
    """
    problem = generate_problem(kc, seed=seed)
    if problem.operands is not None:
        for operand in problem.operands:
            assert operand > 0, f"{kc} seed={seed}: non-positive operand {operand}"
            assert operand.q != 1, f"{kc} seed={seed}: operand {operand} is a whole number"
    # The correct value of an in-scope fraction problem is itself a positive rational.
    assert problem.correct_value > 0


@pytest.mark.parametrize("seed", range(25))
def test_arithmetic_answers_are_only_add_or_subtract(seed: int) -> None:
    """Addition/subtraction answers equal the SymPy sum/difference — never a product.

    Guards the "no multiplication or division" scope boundary (PROJECT.md §3.1):
    the only operations a generated answer reflects are + and -, computed by SymPy.
    """
    add_problem = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=seed)
    assert add_problem.operands is not None
    a, b = add_problem.operands
    assert add_problem.correct_value == a + b
    # A sum of two positive fractions is strictly greater than either addend.
    assert add_problem.correct_value > a
    assert add_problem.correct_value > b

    sub_problem = generate_problem(KnowledgeComponentId.SUBTRACTION_UNLIKE, seed=seed)
    assert sub_problem.operands is not None
    c, d = sub_problem.operands
    assert sub_problem.correct_value == c - d
    # Subtraction is well-formed: minuend exceeds subtrahend so the result is positive.
    assert c > d
    assert sub_problem.correct_value > 0


@pytest.mark.parametrize("seed", range(25))
def test_addition_and_subtraction_use_unlike_denominators(seed: int) -> None:
    """The add/subtract KCs are 'with unlike denominators' (PROJECT.md §3.1).

    A like-denominator pair would not exercise the common-denominator step the KC
    is named for, so the generator must pick differing denominators.
    """
    for kc in (KnowledgeComponentId.ADDITION_UNLIKE, KnowledgeComponentId.SUBTRACTION_UNLIKE):
        problem = generate_problem(kc, seed=seed)
        assert problem.operands is not None
        first, second = problem.operands
        assert first.q != second.q, f"{kc} seed={seed}: like denominators {first.q}"


@pytest.mark.parametrize("seed", range(25))
def test_common_denominator_answer_is_the_lcm(seed: int) -> None:
    """The common-denominator answer is the LCM of the two denominators (in-scope).

    It is an integer piece-size, computed from the operands, never a product of the
    fractions (no mult/div). LCM is the smallest shared piece-size the KC asks for.
    """
    from sympy import ilcm

    problem = generate_problem(KnowledgeComponentId.COMMON_DENOMINATOR, seed=seed)
    assert problem.operands is not None
    first, second = problem.operands
    assert problem.correct_value == Rational(ilcm(first.q, second.q))


@pytest.mark.parametrize("seed", range(25))
def test_number_line_answer_is_on_the_unit_interval(seed: int) -> None:
    """A number-line placement target sits strictly inside the 0–1 line (NL items)."""
    problem = generate_problem(KnowledgeComponentId.NUMBER_LINE_PLACEMENT, seed=seed)
    assert 0 < problem.correct_value < 1


# ─── Determinism: same seed ⇒ identical problem (PROJECT.md §4.1) ─────────────


@pytest.mark.parametrize("kc", ALL_KCS)
def test_same_seed_yields_identical_problem(kc: KnowledgeComponentId) -> None:
    """Same KC + same seed ⇒ identical Problem, every time (reproducible harness)."""
    first = generate_problem(kc, seed=42)
    second = generate_problem(kc, seed=42)
    assert first == second
    # Frozen + hashable, so the equality is structural across all fields.
    assert hash(first) == hash(second)


@pytest.mark.parametrize("kc", ALL_KCS)
def test_different_seeds_can_yield_different_problems(kc: KnowledgeComponentId) -> None:
    """Different seeds explore the problem space (the generator is not a constant).

    We don't require every pair to differ (small spaces collide), only that the
    generator varies across a span of seeds — otherwise it isn't really generating.
    """
    problems = {generate_problem(kc, seed=s) for s in range(20)}
    assert len(problems) > 1, f"{kc}: generator produced one problem for 20 seeds"


def test_problem_ids_are_unique_per_seed_within_a_kc() -> None:
    """Distinct generated problems carry distinct ids (no id collisions in a run)."""
    problems = [generate_problem(KnowledgeComponentId.EQUIVALENCE, seed=s) for s in range(20)]
    distinct_problems = set(problems)
    distinct_ids = {p.problem_id for p in distinct_problems}
    assert len(distinct_ids) == len(distinct_problems)


def test_equivalence_fill_exposes_the_given_denominator() -> None:
    """The 'fill in the missing top number' item names a denominator in the statement
    ('… is the same as ?/8'); the surface must pre-fill and lock it so the widget asks
    only for the numerator. The denominator is exposed as structured data (not parsed
    from the string), and the correct numerator over it equals the target value."""
    from app.domain.verifier import verify

    for seed in range(10):
        problem = generate_problem(KnowledgeComponentId.EQUIVALENCE, seed=seed)
        given = problem.given_denominator
        assert given is not None and given > 0
        # The statement's "?/{given}" matches the exposed denominator (no drift).
        assert f"?/{given}" in problem.statement
        # The correct numerator over the given denominator names the target value.
        numerator = problem.correct_value * given
        assert numerator == int(numerator)  # it is a whole number of those pieces
        assert verify(problem, f"{int(numerator)}/{given}").is_correct is True


def test_equivalence_word_problem_is_a_yes_no_judgment() -> None:
    """The WORD_PROBLEM equivalence item is a yes/no story judgment over two amounts: its
    truth (SymPy over the operands) matches the learner's yes/no — verified both ways — and
    both yes and no cases occur across seeds (so the answer isn't trivially constant)."""
    from app.domain.verifier import verify

    saw_equal = saw_unequal = False
    for seed in range(20):
        p = generate_problem(
            KnowledgeComponentId.EQUIVALENCE, seed=seed, surface_format=Representation.WORD_PROBLEM
        )
        assert p.answer_kind is AnswerKind.YES_NO
        assert p.operands is not None and len(p.operands) == 2
        assert "?" in p.statement and "same amount" in p.statement  # a real judgment prompt
        truly_equal = p.operands[0] == p.operands[1]
        assert verify(p, "yes").is_correct is truly_equal
        assert verify(p, "no").is_correct is (not truly_equal)
        saw_equal = saw_equal or truly_equal
        saw_unequal = saw_unequal or not truly_equal
    assert saw_equal and saw_unequal


def test_number_line_symbolic_is_a_magnitude_comparison() -> None:
    """The SYMBOLIC placement item is a 'greater than?' yes/no comparison (the magnitude
    skill without the line): truth (SymPy a > b) matches the learner's yes/no both ways, and
    both yes and no occur across seeds. The default (number_line) stays the drag placement."""
    from app.domain.verifier import verify

    saw_yes = saw_no = False
    for seed in range(20):
        p = generate_problem(
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
            seed=seed,
            surface_format=Representation.SYMBOLIC,
        )
        assert p.answer_kind is AnswerKind.YES_NO
        assert p.yes_no_relation == "greater"
        assert p.operands is not None and len(p.operands) == 2
        assert "greater than" in p.statement
        truly_greater = bool(p.operands[0] > p.operands[1])
        assert verify(p, "yes").is_correct is truly_greater
        assert verify(p, "no").is_correct is (not truly_greater)
        saw_yes = saw_yes or truly_greater
        saw_no = saw_no or not truly_greater
    assert saw_yes and saw_no
    # The default placement item is still the number-line drag (numeric), unchanged.
    drag = generate_problem(KnowledgeComponentId.NUMBER_LINE_PLACEMENT, seed=1)
    assert drag.surface_format is Representation.NUMBER_LINE
    assert drag.answer_kind is AnswerKind.NUMERIC


def test_non_equivalence_items_have_no_given_denominator() -> None:
    """``given_denominator`` is an equivalence-fill rendering hint; it is None elsewhere
    so no other surface tries to lock a denominator."""
    for kc in (
        KnowledgeComponentId.ADDITION_UNLIKE,
        KnowledgeComponentId.SUBTRACTION_UNLIKE,
        KnowledgeComponentId.COMMON_DENOMINATOR,
        KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
    ):
        assert generate_problem(kc, seed=1).given_denominator is None


# ─── Surface format is a generator parameter (decision 0.D.1) ────────────────


@pytest.mark.parametrize("kc", ALL_KCS)
def test_format_parameter_is_honored(kc: KnowledgeComponentId) -> None:
    """Asking for a specific surface format yields a problem in that format.

    Surface format being a parameter is exactly what supports interleaving across
    formats and defeats Surface Sam (decision 0.D.1). We request each format the KC
    advertises and assert the generated problem is rendered in it.
    """
    from app.domain.knowledge_components import get_kc

    for representation in get_kc(kc).representations:
        problem = generate_problem(kc, seed=5, surface_format=representation)
        assert problem.surface_format == representation
        assert representation in problem.representations_available


def test_requesting_an_unsupported_format_raises() -> None:
    """A KC cannot be rendered in a format it does not support — fail loudly.

    KC_equivalence is not exercised on a number line in the registry, so asking for
    it must raise rather than silently substitute a different format.
    """
    with pytest.raises((ValueError, KeyError)):
        generate_problem(
            KnowledgeComponentId.EQUIVALENCE,
            seed=1,
            surface_format=Representation.NUMBER_LINE,
        )


def test_format_does_not_change_the_math() -> None:
    """The same seed yields the same operands/answer regardless of surface format.

    Format is a presentation choice; the underlying problem (operands, correct
    value) is determined by the seed alone. This is what lets the harness interleave
    the SAME item across representations to test multi-representation mastery.
    """
    symbolic = generate_problem(
        KnowledgeComponentId.ADDITION_UNLIKE,
        seed=11,
        surface_format=Representation.SYMBOLIC,
    )
    area = generate_problem(
        KnowledgeComponentId.ADDITION_UNLIKE,
        seed=11,
        surface_format=Representation.AREA_MODEL,
    )
    assert symbolic.operands == area.operands
    assert symbolic.correct_value == area.correct_value
    assert symbolic.surface_format != area.surface_format


# ─── The bank adapter: a gem item maps onto Problem (decision 0.D.1) ─────────


def test_bank_item_adapts_onto_problem_type() -> None:
    """A single diagnostic-gem item loads as a Problem with the right fields.

    The "one shared Problem type" requirement of 0.D.1: a handpicked bank item and
    a procedurally-generated problem are indistinguishable to downstream code.
    """
    items = _load_items()
    # ADD-001 (1/2 + 1/4 = 3/4) is a stable, simple arithmetic anchor.
    item = next(it for it in items if it["id"] == "ADD-001")
    problem = problem_from_bank_item(item)

    assert isinstance(problem, Problem)
    assert problem.problem_id == "ADD-001"
    assert problem.kc == KnowledgeComponentId.ADDITION_UNLIKE
    assert problem.surface_format == Representation.SYMBOLIC
    assert Representation.SYMBOLIC in problem.representations_available
    assert Representation.AREA_MODEL in problem.representations_available
    # The bank's correct_answer for ADD-001 is the fraction 3/4.
    assert problem.correct_value == Rational(3, 4)
    # Operands parsed from the symbolic statement.
    assert problem.operands == (Rational(1, 2), Rational(1, 4))


def test_every_bank_item_adapts_without_error() -> None:
    """Every one of the ~50 handpicked items maps onto Problem.

    Covers all answer shapes the bank uses (yes_no, integer, choice, fraction,
    structured, point_on_unit_interval, ordered_points) so the adapter is total over
    the bank, not just the easy arithmetic cases.
    """
    items = _load_items()
    assert len(items) >= 50
    for item in items:
        problem = problem_from_bank_item(item)
        assert problem.problem_id == item["id"]
        assert problem.kc == KnowledgeComponentId(item["kc_primary"])
        assert problem.surface_format == Representation(item["format"])
        assert problem.statement == item["problem_statement"]["symbolic"]
        expected_formats = {
            Representation(r) for r in item["problem_statement"]["representations_available"]
        }
        assert set(problem.representations_available) == expected_formats
        # Every adapted problem carries a SymPy-typed correct value.
        assert problem.correct_value is not None


def test_bank_item_correct_value_matches_sympy_for_arithmetic() -> None:
    """For arithmetic bank items, the adapted correct_value equals the SymPy result.

    The bank stores a SymPy-verified value (e.g. '3/4'); the adapter must surface it
    as the same Rational, so a downstream verifier compares against the same oracle
    whether the problem is generated or handpicked.
    """
    items = _load_items()
    for item in items:
        if item["correct_answer"]["type"] != "fraction":
            continue
        problem = problem_from_bank_item(item)
        a, b = item["correct_answer"]["value"].split("/")
        assert problem.correct_value == Rational(int(a), int(b)), item["id"]


def test_generated_and_bank_problems_share_one_type() -> None:
    """A generated problem and a bank problem are the SAME type (source-agnostic).

    This is the heart of 0.D.1: downstream code receives ``Problem`` and cannot tell
    (or need not care) whether it was procedurally generated or handpicked.
    """
    items = _load_items()
    bank_problem = problem_from_bank_item(items[0])
    generated = generate_problem(KnowledgeComponentId.ADDITION_UNLIKE, seed=1)
    assert type(bank_problem) is type(generated) is Problem
