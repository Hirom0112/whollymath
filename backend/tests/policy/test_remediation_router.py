"""Tests for the reactive-remediation router (Slice P0.4).

Mandatory-TDD (CLAUDE.md §2, §9): this is load-bearing policy — the live wiring that drops a
struggling grade-level learner to the prerequisite the lesson rests on. Each rule from
CURRICULUM_STANDARD.md §11 gets a test that pins it. This module tests the PURE pieces — the §11.3
selector (which prerequisite to drop to) and the §11.4 hard-gate predicate — in isolation; the
end-to-end live-loop wiring (pause → serve → gate → resume) and the P0.6 red-team persona are pinned
in tests/api/test_remediation_router_live.py and tests/api/test_remediation_redteam.py.

Pure / deterministic (no SymPy, LLM, DB): same inputs → same chosen target.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.verifier import ErrorCategory
from app.policy.remediation_router import select_remediation_target

_KC = KnowledgeComponentId


def _flat_mastery(value: float = 0.5) -> dict[KnowledgeComponentId, float]:
    """A mastery lookup that returns the same probability for every KC (no lowest-mastery edge)."""
    return {kc: value for kc in KnowledgeComponentId}


# ─── §11.3 signal 2: lowest-mastery prerequisite ───────────────────────────────


def test_selects_the_lowest_mastery_prerequisite() -> None:
    """Among a lesson's listed prerequisites, drop to the WEAKEST one (§11.3 signal 2).

    DIVIDE_FRACTIONS lists three prereqs (add/sub unlike + equivalence). With no error-category
    bias in play, the one with the lowest mastery probability is chosen.
    """
    mastery = _flat_mastery(0.8)
    mastery[_KC.SUBTRACTION_UNLIKE] = 0.2  # the weakest of DIVIDE_FRACTIONS' prereqs
    mastery[_KC.ADDITION_UNLIKE] = 0.6
    mastery[_KC.EQUIVALENCE] = 0.7

    chosen = select_remediation_target(
        _KC.DIVIDE_FRACTIONS, error_category=ErrorCategory.NONE, mastery=mastery
    )
    assert chosen is _KC.SUBTRACTION_UNLIKE


def test_single_prerequisite_is_chosen_regardless_of_mastery() -> None:
    """A lesson with one listed prerequisite drops to it (no choice to make)."""
    chosen = select_remediation_target(
        _KC.MULTIPLY_FRACTIONS, error_category=ErrorCategory.MAGNITUDE, mastery=_flat_mastery()
    )
    assert chosen is _KC.EQUIVALENCE


# ─── §11.3 signal 1: error-category bias ───────────────────────────────────────


def test_magnitude_error_biases_toward_the_number_line_prerequisite() -> None:
    """A MAGNITUDE error biases the drop toward the magnitude-flavored prereq (number line) — §11.3.

    ORDERING_INEQUALITIES lists [NUMBER_LINE_PLACEMENT, SIGNED_NUMBERS]. On a magnitude error the
    number-line prereq is preferred EVEN when it is not the lowest-mastery candidate — the error
    flavor is the primary §11.3 signal that says WHICH of the row's prereqs the slip points at.
    """
    mastery = _flat_mastery(0.8)
    mastery[_KC.NUMBER_LINE_PLACEMENT] = 0.7  # higher mastery, but matches the error flavor
    mastery[_KC.SIGNED_NUMBERS] = 0.3  # lower mastery, but not the magnitude-flavored prereq

    chosen = select_remediation_target(
        _KC.ORDERING_INEQUALITIES, error_category=ErrorCategory.MAGNITUDE, mastery=mastery
    )
    assert chosen is _KC.NUMBER_LINE_PLACEMENT


def test_operation_error_biases_toward_the_operation_prerequisite() -> None:
    """An OPERATION error biases toward the operation-flavored prereq (add/subtract) — §11.3.

    DIVIDE_FRACTIONS lists add/sub unlike + equivalence. An operation slip points at the
    add/subtract procedure, so it is preferred even when equivalence has lower mastery.
    """
    mastery = _flat_mastery(0.8)
    mastery[_KC.ADDITION_UNLIKE] = 0.7  # operation-flavored, higher mastery
    mastery[_KC.EQUIVALENCE] = 0.2  # lower mastery, but not operation-flavored

    chosen = select_remediation_target(
        _KC.DIVIDE_FRACTIONS, error_category=ErrorCategory.OPERATION, mastery=mastery
    )
    # The add/subtract prereqs are the operation-flavored ones; the lowest-mastery of THOSE wins.
    assert chosen in (_KC.ADDITION_UNLIKE, _KC.SUBTRACTION_UNLIKE)


def test_error_bias_breaks_ties_within_the_flavored_group_by_lowest_mastery() -> None:
    """When the error flavor matches MULTIPLE prereqs, the lowest-mastery of those is taken (§11.3).

    DIVIDE_FRACTIONS' operation-flavored prereqs are BOTH add-unlike and sub-unlike; on an operation
    error the weaker of the two is chosen (signal 1 narrows the group, signal 2 picks within it).
    """
    mastery = _flat_mastery(0.8)
    mastery[_KC.ADDITION_UNLIKE] = 0.6
    mastery[_KC.SUBTRACTION_UNLIKE] = 0.3  # the weaker operation-flavored prereq

    chosen = select_remediation_target(
        _KC.DIVIDE_FRACTIONS, error_category=ErrorCategory.OPERATION, mastery=mastery
    )
    assert chosen is _KC.SUBTRACTION_UNLIKE


def test_no_flavored_match_falls_back_to_lowest_mastery() -> None:
    """When NO listed prereq matches the error flavor, signal 2 (lowest mastery) decides alone.

    MULTIPLY_FRACTIONS' only prereq is equivalence (neither magnitude- nor operation-flavored). A
    magnitude error has no flavored match, so the selector falls back to the lowest-mastery rule —
    which still picks equivalence (the only option), never raising.
    """
    chosen = select_remediation_target(
        _KC.MULTIPLY_FRACTIONS, error_category=ErrorCategory.MAGNITUDE, mastery=_flat_mastery()
    )
    assert chosen is _KC.EQUIVALENCE


# ─── §11.1: foundations are terminal (no routed target) ─────────────────────────


def test_terminal_foundation_kc_has_no_target() -> None:
    """A foundation fraction KC is terminal — the selector returns None (§11.1, no auto-drop below).

    The five foundation KCs are deliberately absent from the routing table; a learner struggling
    inside one STAYS and works it. The selector signals "no drop" with None rather than guessing.
    """
    for foundation in (
        _KC.EQUIVALENCE,
        _KC.COMMON_DENOMINATOR,
        _KC.ADDITION_UNLIKE,
        _KC.SUBTRACTION_UNLIKE,
        _KC.NUMBER_LINE_PLACEMENT,
    ):
        chosen = select_remediation_target(
            foundation, error_category=ErrorCategory.OPERATION, mastery=_flat_mastery()
        )
        assert chosen is None, f"{foundation.value} is terminal and must not route a drop"


def test_selection_is_deterministic() -> None:
    """Same (parent, error, mastery) → same target every call (reproducibility, PROJECT.md §4.1)."""
    mastery = _flat_mastery(0.8)
    mastery[_KC.EQUIVALENCE] = 0.25
    first = select_remediation_target(
        _KC.PERCENT, error_category=ErrorCategory.NONE, mastery=mastery
    )
    second = select_remediation_target(
        _KC.PERCENT, error_category=ErrorCategory.NONE, mastery=mastery
    )
    assert first is second


def test_missing_mastery_entry_is_treated_as_unknown_not_a_crash() -> None:
    """A mastery lookup missing a candidate KC must not crash — it defaults high (no false weakest).

    A KC the learner has never touched has no in-session probability; rather than KeyError on the
    turn loop (§8.5 would have us fail loudly for a PROGRAMMING error, but a missing learner
    observation is normal runtime data), we treat an absent entry as its seeded/neutral value so the
    selector stays total. Here equivalence is absent and the present candidate is lower, so the
    present one wins.
    """
    mastery = {_KC.SIGNED_NUMBERS: 0.1}  # NUMBER_LINE_PLACEMENT absent
    chosen = select_remediation_target(
        _KC.ORDERING_INEQUALITIES, error_category=ErrorCategory.NONE, mastery=mastery
    )
    assert chosen is _KC.SIGNED_NUMBERS
