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
    """Arithmetic routes have 2 live representations → masterable now. Equivalence and
    number-line placement have only one live representation → not yet (rule 2 can't be met
    until their 2nd representation is built)."""
    assert is_masterable_live(_ADD) is True
    assert is_masterable_live(_SUB) is True
    assert is_masterable_live(_EQ) is False
    assert is_masterable_live(_NL) is False


def test_negative_index_is_a_programming_error() -> None:
    import pytest

    with pytest.raises(ValueError):
        next_spec(_ADD, -1)
