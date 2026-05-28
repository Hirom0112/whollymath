"""Tests for the SymPy numeric-claim gate on LLM-rephrased hints (Slice 5.6).

The domain produces the verified-correct canonical hint text; the LLM only REPHRASES
it warmly (``persona_surface/hint_renderer.py``). Before a rephrase may be shown, SymPy
must confirm it preserved every numeric claim of the canonical text — neither dropping,
altering, nor adding a number (decision 0.D.3: "LLM slot-fill → SymPy-validated").

This module is the SymPy boundary for that gate (it lives in ``domain/``; SymPy is
allowed only there — CLAUDE.md §7, ARCHITECTURE.md §14 invariant 5). We follow
``verifier.py``'s safety posture: parse numbers with a regex + plain ``int``, NEVER
``eval``/``sympify`` on free text. We assert:

  - integers and ``a/b`` fractions are parsed to the right ``Rational`` SET ("1/3" is
    ONE value, not 1 and 3; "12" is Rational(12));
  - a reworded/reordered text with the SAME distinct numbers is preserved (True);
  - a changed / dropped / added number is NOT preserved (False);
  - spelled-out words ("one third") carry no digit token and so do not satisfy the
    digit-preservation gate (False against a digit-bearing canonical text).
"""

from __future__ import annotations

from app.domain.hint_validation import extract_rationals, numeric_claims_preserved
from sympy import Rational

# ─── extract_rationals: integers and fractions → the distinct Rational SET ────


def test_extracts_standalone_integers() -> None:
    assert extract_rationals("the smallest is 12") == {Rational(12)}


def test_extracts_a_fraction_as_one_value_not_two() -> None:
    # "1/3" is the single value 1/3 — NOT the integers 1 and 3.
    assert extract_rationals("rewrite 1/3 over the new bottom") == {Rational(1, 3)}


def test_extracts_a_mix_of_integers_and_fractions() -> None:
    text = "Find a common denominator for 1/3 and 1/4: the smallest is 12."
    assert extract_rationals(text) == {Rational(1, 3), Rational(1, 4), Rational(12)}


def test_distinct_set_collapses_repeats() -> None:
    # The SET is of distinct values: 2/4 and 1/2 are the same magnitude, one entry.
    assert extract_rationals("2/4 is the same amount as 1/2") == {Rational(1, 2)}


def test_no_numbers_yields_empty_set() -> None:
    assert extract_rationals("are the pieces the same size?") == set()


def test_words_are_not_parsed_as_numbers() -> None:
    # Spelled-out numbers carry no digit token — the gate is over DIGITS.
    assert extract_rationals("one third of the way along") == set()


# ─── numeric_claims_preserved: value-equality of the distinct-number sets ─────


_CANONICAL = "Find a common denominator for 1/3 and 1/4: the smallest is 12."


def test_preserved_when_reordered_and_reworded_same_numbers() -> None:
    candidate = "The smallest common bottom for 1/4 and 1/3 is 12 — nice!"
    assert numeric_claims_preserved(_CANONICAL, candidate) is True


def test_not_preserved_when_a_number_is_changed() -> None:
    # 12 → 24 alters a numeric fact.
    candidate = "The smallest common bottom for 1/3 and 1/4 is 24."
    assert numeric_claims_preserved(_CANONICAL, candidate) is False


def test_not_preserved_when_a_number_is_dropped() -> None:
    candidate = "Find a common denominator for 1/3 and 1/4."
    assert numeric_claims_preserved(_CANONICAL, candidate) is False


def test_not_preserved_when_a_number_is_added() -> None:
    candidate = "Find a common denominator for 1/3 and 1/4: the smallest is 12, way more than 5."
    assert numeric_claims_preserved(_CANONICAL, candidate) is False


def test_not_preserved_when_digits_replaced_by_words() -> None:
    # A warm rephrase that spells the numbers out drops every digit claim → fails the gate.
    candidate = "Find a common bottom for one third and one fourth: the smallest is twelve."
    assert numeric_claims_preserved(_CANONICAL, candidate) is False


def test_preserved_is_reflexive_on_canonical_text() -> None:
    assert numeric_claims_preserved(_CANONICAL, _CANONICAL) is True
