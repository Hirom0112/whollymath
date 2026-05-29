"""Tests for the live interleaving scheduler (Slice 4.x MVP).

The scheduler must produce a sequence that (a) varies — not one KC forever — and (b) can
satisfy the mastery model's interleaving rule (≥2 KCs) and representation-diversity rule
(≥2 representations of the goal KC) for an arithmetic route, so mastery is reachable live.
Pure/deterministic, so these are plain unit tests (CLAUDE.md §2/§9).
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.policy.scheduler import is_masterable_live, next_spec

_ADD = KnowledgeComponentId.ADDITION_UNLIKE
_SUB = KnowledgeComponentId.SUBTRACTION_UNLIKE
_EQ = KnowledgeComponentId.EQUIVALENCE
_NL = KnowledgeComponentId.NUMBER_LINE_PLACEMENT
_CD = KnowledgeComponentId.COMMON_DENOMINATOR


def test_schedule_is_not_one_kc_forever() -> None:
    """The headline fix: across a run the schedule spans ≥2 KCs (it used to be one KC)."""
    kcs = {next_spec(_ADD, i)[0] for i in range(9)}
    assert len(kcs) >= 2
    assert _ADD in kcs  # the goal still dominates
    assert _SUB in kcs  # the companion is interleaved in


def test_goal_kc_rotates_through_its_live_representations() -> None:
    """An arithmetic goal is served in BOTH live representations across the run, so the
    learner can be correct in ≥2 representations (mastery rule 2)."""
    goal_reps = {rep for i in range(12) for kc, rep in [next_spec(_ADD, i)] if kc == _ADD}
    assert goal_reps == {Representation.SYMBOLIC, Representation.NUMBER_LINE}


def test_companion_appears_on_the_fixed_cadence() -> None:
    """Every third served item is the companion KC (0.D.5 interleaving cadence)."""
    assert next_spec(_ADD, 2)[0] == _SUB  # 3rd item (index 2)
    assert next_spec(_ADD, 5)[0] == _SUB  # 6th item
    assert next_spec(_ADD, 0)[0] == _ADD
    assert next_spec(_ADD, 1)[0] == _ADD


def test_schedule_is_deterministic() -> None:
    """Same inputs → same spec, every call (PROJECT.md §4.1 reproducibility)."""
    assert next_spec(_ADD, 4) == next_spec(_ADD, 4)
    assert next_spec(_EQ, 7) == next_spec(_EQ, 7)


def test_masterable_live_is_honest_about_each_route() -> None:
    """Every route now has ≥2 live representations → all masterable: arithmetic (symbolic +
    number line), equivalence (symbolic + word-problem judgment), and number-line placement
    (drag + symbolic magnitude comparison)."""
    assert is_masterable_live(_ADD) is True
    assert is_masterable_live(_SUB) is True
    assert is_masterable_live(_EQ) is True
    assert is_masterable_live(_NL) is True


def test_common_denominator_is_schedulable_but_practice_only_for_now() -> None:
    """A common-denominator lesson runs end-to-end (it has a companion, so the cadence turn never
    KeyErrors), but is PRACTICE-ONLY: one live representation, so not yet masterable. The
    AREA_MODEL alignment representation (which would make it masterable) lands with its widget."""
    # The cadence turn (every 3rd item) must resolve a companion, not crash.
    assert next_spec(_CD, 2)[0] == _EQ
    # The goal turns are the common-denominator skill itself.
    assert next_spec(_CD, 0)[0] == _CD
    assert next_spec(_CD, 1)[0] == _CD
    # Honest: one live representation today → not masterable until the second rep exists.
    assert is_masterable_live(_CD) is False


def test_placement_rotates_number_line_and_symbolic() -> None:
    """The placement goal is served as BOTH the drag and the symbolic comparison, so a
    learner can be correct in 2 representations (mastery rule 2)."""
    reps = {rep for i in range(12) for kc, rep in [next_spec(_NL, i)] if kc == _NL}
    assert reps == {Representation.NUMBER_LINE, Representation.SYMBOLIC}


def test_equivalence_rotates_symbolic_and_word_problem() -> None:
    """The equivalence goal is served in BOTH its live representations across a run, so a
    learner can be correct in 2 representations (mastery rule 2)."""
    reps = {rep for i in range(12) for kc, rep in [next_spec(_EQ, i)] if kc == _EQ}
    assert reps == {Representation.SYMBOLIC, Representation.WORD_PROBLEM}


def test_negative_index_is_a_programming_error() -> None:
    import pytest

    with pytest.raises(ValueError):
        next_spec(_ADD, -1)
