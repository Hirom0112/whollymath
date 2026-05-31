"""Tests for the Layer-1 misconception catalog + wrong-answer generators (Slice 1.2).

Written test-first per CLAUDE.md §2 (TDD is mandatory for the domain model — the
single most load-bearing system; if the misconceptions are wrong, the personas
and the mastery model are wrong). These tests pin the contract that PROJECT.md
§4.2 (the five personas and their misconceptions), RESEARCH.md §1.2 (the fraction-
misconception catalog) and ARCHITECTURE.md §5/§14 require of Layer 1:

  - exactly the five named misconceptions exist, ids matching the gem bank's
    `_meta.misconception_catalog` verbatim
  - each misconception is typed, immutable, and references real KC ids
  - each deterministic wrong-answer generator produces the documented wrong
    answer on canonical cases AND reproduces the SymPy-verified
    `wrong_answer_produced` oracle values in `diagnostic_gems.json`

SymPy IS allowed here (this is `domain/`, the one place math lives — CLAUDE.md §7,
ARCHITECTURE.md §14). No LLM, no DB (CLAUDE.md §8.1/§8.2): the generators are pure,
deterministic functions. Problem generators (1.3) and the SymPy verifier (1.4) are
intentionally NOT tested here.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.misconceptions import (
    MISCONCEPTION_REGISTRY,
    EqualSignVerdict,
    Misconception,
    MisconceptionId,
    NumberLineMisplacement,
    ProcedureWithoutConceptResult,
    add_across,
    equal_sign_as_procedural_relational,
    get_misconception,
    natural_number_bias_compare,
    natural_number_bias_number_line,
    procedure_without_concept,
    reduce_means_smaller_judges_same,
    subtract_across,
)
from sympy import Rational

# The five misconception ids are the Layer-1 contract. The catalog string VALUES
# must match `diagnostic_gems.json` `_meta.misconception_catalog` verbatim — they
# are the join key between this module, the bank, and the persona configs.
# The five misconceptions that match the fraction-only gem bank verbatim (RESEARCH.md §1.2).
EXPECTED_MISCONCEPTION_IDS = {
    "natural-number-bias",
    "add-across-error",
    "reduce-means-smaller",
    "equal-sign-as-procedural",
    "procedure-without-concept",
}

# Grade-6 content-build misconceptions: NOT in the fraction-only bank — each enters with its
# lesson (Grade-6 build, 2026-05-30). The enum/registry == bank ∪ these; the bank-verbatim
# check stays scoped to the five bank ids above.
EXPECTED_GRADE6_MISCONCEPTION_IDS = {
    "part-part-whole-confusion",  # KC_ratio_language
    "rate-inversion",  # KC_unit_rate
    "additive-ratio",  # KC_equivalent_ratios
    "percent-as-amount",  # KC_percent
    "multiply-as-add",  # KC_multiply_fractions (Unit 2, T2)
    "multiply-without-inverting",  # KC_divide_fractions (Unit 2, T2)
    "conversion-inversion",  # KC_unit_conversion
    "gcf-lcm-confusion",  # KC_gcf_lcm (Unit 2)
    "place-value-slip",  # KC_multi_digit_division (Unit 2)
    "decimal-point-misplacement",  # KC_decimal_operations (Unit 2)
    "signed-not-magnitude",  # KC_absolute_value (Unit 3)
    "sign-handling-error",  # KC_integer_add_subtract (Unit-INT)
    "sign-error",  # KC_signed_numbers (Unit 3)
    "reversed-operands",  # KC_write_expressions (Unit 4)
    "order-of-operations-slip",  # KC_evaluate_expressions (Unit 4)
    "inverse-operation-error",  # KC_one_step_equations (Unit 5)
    "distributive-error",  # KC_equivalent_expressions (Unit 4)
    "flipped-inequality",  # KC_inequalities (Unit 5)
    "coordinate-swap",  # KC_coordinate_plane (Unit 3)
    "integer-not-rational",  # KC_classify_number_sets (Unit 3, TEKS 6.2A)
    "part-confusion",  # KC_expression_parts (Unit 4, 6.EE.2b)
    "multiply-base-by-exponent",  # KC_exponents (Unit 4)
}
EXPECTED_ALL_MISCONCEPTION_IDS = EXPECTED_MISCONCEPTION_IDS | EXPECTED_GRADE6_MISCONCEPTION_IDS

_GEMS_PATH = Path(__file__).resolve().parents[2] / "app" / "domain" / "diagnostic_gems.json"


def _load_items() -> list[dict[str, Any]]:
    """Load the gem-bank items; skip the whole oracle suite if the bank is absent.

    The domain layer's tests must not hard-depend on a downstream data asset
    (mirrors test_knowledge_components.py), so oracle tests skip when the bank is
    not on disk rather than failing.
    """
    if not _GEMS_PATH.exists():
        pytest.skip("diagnostic_gems.json not present — oracle checks skipped")
    data = json.loads(_GEMS_PATH.read_text())
    items: list[dict[str, Any]] = list(data["items"])
    return items


# ─── Catalog / registry contract ───────────────────────────────────────────


def test_registry_contains_exactly_the_five_misconceptions() -> None:
    """The registry has the 5 fraction misconceptions (RESEARCH.md §1.2) + Grade-6 additions."""
    registry_ids = {m.id.value for m in MISCONCEPTION_REGISTRY.all()}
    assert registry_ids == EXPECTED_ALL_MISCONCEPTION_IDS
    assert len(MISCONCEPTION_REGISTRY.all()) == len(EXPECTED_ALL_MISCONCEPTION_IDS)


def test_enum_values_match_the_bank_catalog_verbatim() -> None:
    """The MisconceptionId enum = the gem-bank catalog (5) PLUS the Grade-6 build additions."""
    enum_values = {member.value for member in MisconceptionId}
    assert enum_values == EXPECTED_ALL_MISCONCEPTION_IDS


def test_enum_values_match_gem_bank_when_present() -> None:
    """If the bank is on disk, its misconception_catalog must match the enum."""
    if not _GEMS_PATH.exists():
        pytest.skip("diagnostic_gems.json not present — catalog drift check skipped")
    catalog = set(json.loads(_GEMS_PATH.read_text())["_meta"]["misconception_catalog"])
    assert catalog == EXPECTED_MISCONCEPTION_IDS


def test_lookup_by_id_resolves_enum_and_string() -> None:
    """get_misconception resolves a known id (enum and raw string) to one object."""
    from_enum = get_misconception(MisconceptionId.ADD_ACROSS_ERROR)
    assert from_enum.id is MisconceptionId.ADD_ACROSS_ERROR

    from_string = get_misconception("add-across-error")
    assert from_string is from_enum  # canonical singleton


def test_unknown_misconception_id_raises_keyerror() -> None:
    """An unknown id raises KeyError naming the bad id — not a silent None."""
    with pytest.raises(KeyError) as exc:
        get_misconception("not-a-misconception")
    assert "not-a-misconception" in str(exc.value)


def test_each_misconception_has_name_description_and_kcs() -> None:
    """Every misconception carries human text and references real KC ids."""
    for m in MISCONCEPTION_REGISTRY.all():
        assert isinstance(m, Misconception)
        assert m.name.strip()
        assert m.description.strip()
        assert len(m.applicable_kcs) >= 1
        assert all(isinstance(kc, KnowledgeComponentId) for kc in m.applicable_kcs)


def test_misconception_is_immutable() -> None:
    """Misconception objects are frozen — Layer 1 is a source of truth."""
    m = get_misconception(MisconceptionId.NATURAL_NUMBER_BIAS)
    with pytest.raises(AttributeError):
        m.name = "tampered"  # type: ignore[misc]


def test_misconception_kc_coverage_matches_personas() -> None:
    """The KCs each misconception applies to trace to PROJECT.md §4.2 / §3.1.

    add-across is an addition error; natural-number-bias spans comparison/
    common-denominator/subtraction/number-line; procedure-without-concept spans
    every KC (the procedure can be run rotely anywhere). We assert the
    load-bearing memberships, not an exhaustive map.
    """
    add_across_m = get_misconception(MisconceptionId.ADD_ACROSS_ERROR)
    assert KnowledgeComponentId.ADDITION_UNLIKE in add_across_m.applicable_kcs

    nnb = get_misconception(MisconceptionId.NATURAL_NUMBER_BIAS)
    assert KnowledgeComponentId.NUMBER_LINE_PLACEMENT in nnb.applicable_kcs

    pwc = get_misconception(MisconceptionId.PROCEDURE_WITHOUT_CONCEPT)
    # Procedure-without-concept is probed across multiple KCs in the bank.
    assert KnowledgeComponentId.EQUIVALENCE in pwc.applicable_kcs


# ─── add-across-error generator ─────────────────────────────────────────────


def test_add_across_canonical_quarter_plus_quarter() -> None:
    """The textbook Surface-Sam error: 1/4 + 1/4 -> 2/8 (PROJECT.md §4.2)."""
    wrong = add_across(1, 4, 1, 4)
    assert (wrong.numerator, wrong.denominator) == (2, 8)
    assert wrong.as_rational() == Rational(2, 8)  # == 1/4, smaller than a part


def test_add_across_formula_is_sum_of_parts() -> None:
    """a/b + c/d -> (a+c)/(b+d), the documented independent-parts error."""
    wrong = add_across(1, 2, 1, 3)
    assert (wrong.numerator, wrong.denominator) == (2, 5)


def test_add_across_reproduces_bank_oracle() -> None:
    """Reproduce every add-across `wrong_answer_produced` in the bank by VALUE.

    The bank's raw strings include forms like 'yes (2/8)' (error-finding items)
    and reduced/unreduced fractions; we parse the fraction out of each and compare
    the generator's rational value to the oracle's rational value.
    """
    items = _load_items()
    checked = 0
    for item in items:
        if item.get("kc_primary") != "KC_addition_unlike":
            continue
        a, b, c, d = _parse_two_fractions(str(item["problem_statement"]["symbolic"]))
        produced = add_across(a, b, c, d).as_rational()
        for probe in item["misconceptions_probed"]:
            if probe["name"] != "add-across-error":
                continue
            oracle = _parse_fraction_value(str(probe["wrong_answer_produced"]))
            assert produced == oracle, f"{item['id']}: add-across {produced} != {oracle}"
            checked += 1
    assert checked == 10  # all of KC_addition_unlike probes add-across


# ─── subtract-across generator (natural-number-bias on subtraction) ──────────


def test_subtract_across_formula() -> None:
    """a/b - c/d -> (a-c)/(b-d), the subtraction analog of the across error."""
    wrong = subtract_across(3, 4, 1, 3)
    assert (wrong.numerator, wrong.denominator) == (2, 1)  # bank SUB-002 raw 2/1


def test_subtract_across_can_produce_negative_or_zero_denominator() -> None:
    """The error yields meaningless forms (negative/zero bottom) — kept raw.

    The generator must NOT silently normalize these; the impossibility (e.g. a
    negative denominator) is the diagnostic signal the bank records (SUB-003).
    """
    wrong = subtract_across(2, 3, 1, 6)
    assert (wrong.numerator, wrong.denominator) == (1, -3)  # bank SUB-003 raw '1/-3'


def test_subtract_across_reproduces_bank_oracle_by_value() -> None:
    """Reproduce every subtraction `wrong_answer_produced` in the bank by VALUE.

    All KC_subtraction_unlike items label the across error 'natural-number-bias'
    (RESEARCH.md §6.4: the relabeling is a deliberate citation-honesty choice).
    SUB-001 stores the raw string '0/2' while (a-c)/(b-d) yields 0/-2; both equal
    0, so a value comparison is the honest oracle (see module docstring).
    """
    items = _load_items()
    checked = 0
    for item in items:
        if item.get("kc_primary") != "KC_subtraction_unlike":
            continue
        a, b, c, d = _parse_two_fractions(str(item["problem_statement"]["symbolic"]))
        produced = subtract_across(a, b, c, d).as_rational()
        for probe in item["misconceptions_probed"]:
            if probe["name"] != "natural-number-bias":
                continue
            oracle = _parse_fraction_value(str(probe["wrong_answer_produced"]))
            assert produced == oracle, f"{item['id']}: subtract-across {produced} != {oracle}"
            checked += 1
    assert checked == 10  # all of KC_subtraction_unlike probes the across error


# ─── natural-number-bias: magnitude / comparison ────────────────────────────


def test_nnb_compare_judges_bigger_denominator_as_larger() -> None:
    """1/6 vs 1/2: the bias judges 1/6 larger because 6 > 2 (PROJECT.md §3.1)."""
    judged_larger = natural_number_bias_compare((1, 6), (1, 2))
    assert judged_larger == (1, 6)
    # And it is WRONG: 1/6 is actually the smaller magnitude.
    assert Rational(1, 6) < Rational(1, 2)


def test_nnb_compare_same_numerator_picks_bigger_denominator() -> None:
    """1/3 vs 1/4: bias picks 1/4 (4 > 3) though 1/3 is actually larger (NL-004)."""
    judged_larger = natural_number_bias_compare((1, 3), (1, 4))
    assert judged_larger == (1, 4)


def test_nnb_compare_uses_denominator_then_numerator() -> None:
    """The bias reads the pair as whole numbers; denominator dominates the digits.

    For 2/5 vs 3/5 (same bottom) it falls back to comparing the tops, picking 3/5.
    """
    assert natural_number_bias_compare((2, 5), (3, 5)) == (3, 5)


def test_nnb_number_line_places_by_the_digits() -> None:
    """Number-line placement by the bias reads the digits, not the magnitude.

    1/2 lands near 2 (the denominator digit) — off the 0–1 line — per NL-001.
    """
    misplacement = natural_number_bias_number_line(1, 2)
    assert isinstance(misplacement, NumberLineMisplacement)
    assert misplacement.true_value == Rational(1, 2)
    # The bias positions by the denominator digit, landing past 1.
    assert misplacement.biased_position >= 1
    assert misplacement.biased_position != misplacement.true_value


def test_nnb_number_line_large_denominator_lands_far_right() -> None:
    """1/8: a large bottom is read as 'big', placing 1/8 far right though it is tiny (NL-009)."""
    misplacement = natural_number_bias_number_line(1, 8)
    assert misplacement.true_value == Rational(1, 8)
    assert misplacement.biased_position > misplacement.true_value


# ─── reduce-means-smaller generator ─────────────────────────────────────────


def test_reduce_means_smaller_judges_equal_pair_as_not_same() -> None:
    """6/8 vs 3/4 are equal, but the misconception answers 'no' (EQ-006)."""
    verdict = reduce_means_smaller_judges_same((6, 8), (3, 4))
    assert verdict == "no"
    assert Rational(6, 8) == Rational(3, 4)  # they ARE equal


def test_reduce_means_smaller_reproduces_bank_oracle() -> None:
    """Every reduce-means-smaller probe in the bank yields 'no'."""
    items = _load_items()
    checked = 0
    for item in items:
        for probe in item["misconceptions_probed"]:
            if probe["name"] != "reduce-means-smaller":
                continue
            f1, f2 = _parse_equivalence_pair(str(item["problem_statement"]["symbolic"]))
            assert reduce_means_smaller_judges_same(f1, f2) == "no"
            assert str(probe["wrong_answer_produced"]).strip().lower() == "no"
            checked += 1
    assert checked == 3  # EQ-005, EQ-006, EQ-010


# ─── equal-sign-as-procedural generator ─────────────────────────────────────


def test_equal_sign_as_procedural_defaults_to_no_on_relational() -> None:
    """On an 'are these the same amount?' item there is nothing to compute.

    The operational reader has no procedure to run and defaults to 'no' (EQ-001).
    """
    verdict = equal_sign_as_procedural_relational()
    assert isinstance(verdict, EqualSignVerdict)
    assert verdict.answer == "no"
    assert verdict.tried_to_compute is False  # nothing to compute; falls back to 'no'


def test_equal_sign_as_procedural_reproduces_bank_oracle() -> None:
    """Every equal-sign-as-procedural probe in the bank yields 'no'."""
    items = _load_items()
    checked = 0
    for item in items:
        for probe in item["misconceptions_probed"]:
            if probe["name"] != "equal-sign-as-procedural":
                continue
            assert equal_sign_as_procedural_relational().answer == "no"
            assert str(probe["wrong_answer_produced"]).strip().lower() == "no"
            checked += 1
    assert checked == 3  # EQ-001, EQ-002, EQ-010


# ─── procedure-without-concept marker ───────────────────────────────────────


def test_procedure_without_concept_returns_correct_value_but_unjustified() -> None:
    """Priya runs the procedure correctly but cannot justify it (PROJECT.md §4.2).

    Modeled as a marker: the CORRECT numeric answer plus a 'cannot explain' flag,
    NOT a fabricated wrong number. This is the nuance the brief calls out.
    """
    result = procedure_without_concept(Rational(7, 12))
    assert isinstance(result, ProcedureWithoutConceptResult)
    assert result.answer == Rational(7, 12)  # the answer is RIGHT
    assert result.can_justify is False  # but unjustified / fails error-finding


def test_procedure_without_concept_preserves_any_answer_type() -> None:
    """The marker wraps whatever the correct answer is (int, fraction, str)."""
    int_result = procedure_without_concept(4)
    assert int_result.answer == 4
    assert int_result.can_justify is False

    str_result = procedure_without_concept("yes")
    assert str_result.answer == "yes"
    assert str_result.can_justify is False


def test_procedure_without_concept_fails_error_finding() -> None:
    """On an error-finding item, Priya accepts a wrong worked answer (SUB-005).

    She cannot apply a reasonableness check (4/3 > 5/6 after subtracting), so she
    agrees with the bad work. The marker exposes this as can_justify == False; the
    answer it carries is whatever the procedure-less learner endorses (here the
    presented-but-wrong 'yes').
    """
    result = procedure_without_concept("yes (4/3)")
    assert result.can_justify is False


# ─── helpers (parse the kid-friendly symbolic strings into integer parts) ────


def _parse_fraction_value(raw: str) -> Rational:
    """Pull the first a/b out of a bank wrong-answer string and return its value.

    Bank strings may be 'yes (2/8)', '2/6', '0/2', '1/-3', etc. We extract the
    first signed fraction and return it as a SymPy Rational for VALUE comparison.
    """
    match = re.search(r"(-?\d+)\s*/\s*(-?\d+)", raw)
    assert match is not None, f"no fraction found in {raw!r}"
    return Rational(int(match.group(1)), int(match.group(2)))


def _parse_two_fractions(symbolic: str) -> tuple[int, int, int, int]:
    """Extract the two operand fractions a/b and c/d from an item's symbolic text."""
    fractions = re.findall(r"(\d+)\s*/\s*(\d+)", symbolic)
    assert len(fractions) >= 2, f"expected two fractions in {symbolic!r}"
    (a, b), (c, d) = fractions[0], fractions[1]
    return int(a), int(b), int(c), int(d)


def _parse_equivalence_pair(symbolic: str) -> tuple[tuple[int, int], tuple[int, int]]:
    """Extract a same-amount pair from a reduce-means-smaller item.

    These items compare a fraction against a half; the half (and sometimes the
    whole pair, e.g. EQ-005's word problem '4 of 8 pieces ... half') may be phrased
    in words rather than slash-fractions. The generator's verdict does not depend
    on the specific numbers (it always answers 'no' on a same-amount judgment), so
    when fewer than two slash-fractions appear we supply a representative equal
    pair (a fraction against 1/2). This is a test-only parsing convenience.
    """
    fractions = re.findall(r"(\d+)\s*/\s*(\d+)", symbolic)
    if len(fractions) >= 2:
        (a, b), (c, d) = fractions[0], fractions[1]
        return (int(a), int(b)), (int(c), int(d))
    if len(fractions) == 1:
        (a, b) = fractions[0]
        return (int(a), int(b)), (1, 2)
    # No slash-fraction in the text (a fully word-phrased equal pair): supply a
    # representative equal pair so the always-'no' verdict is exercised.
    return (1, 2), (1, 2)
