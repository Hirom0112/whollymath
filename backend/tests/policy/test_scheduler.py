"""Tests for the live single-skill scheduler.

Single-skill lessons (2026-05-29 product-owner decision): a lesson stays on ONE skill (a
number-line lesson is number-line questions only), so the scheduler (a) serves only the goal
KC, and (b) rotates that KC's live representations so the learner answers it more than one way
— which satisfies the mastery model's representation-diversity rule (≥2 representations) and
the within-skill path of its varied-practice rule. Pure/deterministic, so these are plain unit
tests (CLAUDE.md §2/§9).
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.policy.scheduler import (
    is_masterable_live,
    next_spec,
    next_spec_after_outcome,
)

_ADD = KnowledgeComponentId.ADDITION_UNLIKE
_SUB = KnowledgeComponentId.SUBTRACTION_UNLIKE
_EQ = KnowledgeComponentId.EQUIVALENCE
_NL = KnowledgeComponentId.NUMBER_LINE_PLACEMENT
_CD = KnowledgeComponentId.COMMON_DENOMINATOR
_MUL = KnowledgeComponentId.MULTIPLY_FRACTIONS
_DIV = KnowledgeComponentId.DIVIDE_FRACTIONS
_DEC = KnowledgeComponentId.DECIMAL_OPERATIONS
_IAS = KnowledgeComponentId.INTEGER_ADD_SUBTRACT
_SGN = KnowledgeComponentId.SIGNED_NUMBERS
_IMD = KnowledgeComponentId.INTEGER_MULTIPLY_DIVIDE
_ABS = KnowledgeComponentId.ABSOLUTE_VALUE
_SUMMARY = KnowledgeComponentId.SUMMARY_STATISTICS
_DISPLAYS = KnowledgeComponentId.DATA_DISPLAYS
_CSS = KnowledgeComponentId.CENTER_SPREAD_SHAPE
_MAD = KnowledgeComponentId.MEAN_ABSOLUTE_DEVIATION


def test_schedule_stays_on_goal_kc_but_varies_representations() -> None:
    """Single-skill lessons: the schedule stays on the GOAL KC the whole way (no other skill
    mixed in), but it is not monotonous — it rotates the goal KC's live representations so the
    learner answers it more than one way (mastery rule 2 + within-skill varied practice)."""
    specs = [next_spec(_ADD, i) for i in range(9)]
    assert all(kc == _ADD for kc, _ in specs), "a single-skill lesson serves only the goal KC"
    assert len({rep for _, rep in specs}) >= 2, "but it varies representations, not one forever"


def test_goal_kc_rotates_through_its_live_representations() -> None:
    """An arithmetic goal is served in BOTH live representations across the run, so the
    learner can be correct in ≥2 representations (mastery rule 2)."""
    goal_reps = {rep for i in range(12) for kc, rep in [next_spec(_ADD, i)] if kc == _ADD}
    assert goal_reps == {Representation.SYMBOLIC, Representation.NUMBER_LINE}


def test_no_cross_skill_companion_is_served() -> None:
    """A lesson never mixes in a different skill (2026-05-29 single-skill decision): every
    served item is the goal KC, at every index."""
    assert all(next_spec(_ADD, i)[0] == _ADD for i in range(12))
    assert all(next_spec(_NL, i)[0] == _NL for i in range(12))


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


def test_common_denominator_is_single_skill_and_practice_only_for_now() -> None:
    """A common-denominator lesson serves only the CD skill (single-skill), but is
    PRACTICE-ONLY: it has one live representation, so it cannot satisfy the ≥2-representation
    mastery gate yet. The AREA_MODEL (fraction-bars) representation that would make it
    masterable lands with its widget."""
    assert all(next_spec(_CD, i)[0] == _CD for i in range(6))
    # Honest: one live representation today → not masterable until the second rep exists.
    assert is_masterable_live(_CD) is False


def test_fraction_decimal_kcs_are_masterable_via_symbolic_plus_area_model() -> None:
    """Multiply/divide fractions and decimal operations are masterable: each is served in
    SYMBOLIC + AREA_MODEL (the area picture is a display stimulus over the same numeric
    answer — fraction_area / decimal_place_value scenes — so no new input widget is needed).
    Promoting them closes the panel's #1 finding: these were practice-only naked symbolic
    drills that could never reach the ≥2-representation mastery gate. (Panel audit 2026-06-04.)"""
    for kc in (_MUL, _DIV, _DEC):
        assert all(next_spec(kc, i)[0] == kc for i in range(8)), "single-skill serves only the goal"
        reps = {rep for i in range(12) for k, rep in [next_spec(kc, i)] if k == kc}
        assert reps == {Representation.SYMBOLIC, Representation.AREA_MODEL}, (
            f"{kc.value} should rotate symbolic + area-model, got {reps}"
        )
        assert is_masterable_live(kc) is True, f"{kc.value} must be masterable after promotion"


def test_integer_and_absolute_value_kcs_are_masterable_via_symbolic_plus_number_line() -> None:
    """Signed-number, integer add/sub & mult/div, and absolute-value KCs are masterable: each is
    served in SYMBOLIC + NUMBER_LINE. The number-line picture is a display stimulus over the same
    scalar answer (IntegerJump / SignedPoint / AbsoluteValue scenes); INTEGER_MULTIPLY_DIVIDE is
    masterable but pictureless for now (the EVALUATE_EXPRESSIONS precedent — number-line jumps for
    products are a later polish). Closes the panel's naked-computation finding (2026-06-04)."""
    for kc in (_IAS, _SGN, _IMD, _ABS):
        assert all(next_spec(kc, i)[0] == kc for i in range(8)), "single-skill serves only the goal"
        reps = {rep for i in range(12) for k, rep in [next_spec(kc, i)] if k == kc}
        assert reps == {Representation.SYMBOLIC, Representation.NUMBER_LINE}, (
            f"{kc.value} should rotate symbolic + number-line, got {reps}"
        )
        assert is_masterable_live(kc) is True, f"{kc.value} must be masterable after promotion"


def test_statistics_kcs_are_masterable_via_symbolic_plus_number_line() -> None:
    """Summary statistics, data displays, center/spread/shape, and MAD are masterable: each is
    served in SYMBOLIC + NUMBER_LINE over a data set that already renders as a real dot plot /
    histogram (stats_stimulus, wired in service.py) — so the second representation carries a genuine
    visual, not a bare list. Promoting them lets a stats lesson reach mastery (panel audit
    2026-06-04)."""
    for kc in (_SUMMARY, _DISPLAYS, _CSS, _MAD):
        assert all(next_spec(kc, i)[0] == kc for i in range(8)), "single-skill serves only the goal"
        reps = {rep for i in range(12) for k, rep in [next_spec(kc, i)] if k == kc}
        assert reps == {Representation.SYMBOLIC, Representation.NUMBER_LINE}, (
            f"{kc.value} should rotate symbolic + number-line, got {reps}"
        )
        assert is_masterable_live(kc) is True, f"{kc.value} must be masterable after promotion"


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


# ── Adaptive re-practice on a wrong answer (Fix B) ──


def test_wrong_answer_stays_on_the_same_kc_for_more_practice() -> None:
    """A wrong answer on the goal KC gives MORE practice on that SAME KC (same difficulty
    family) and the SAME representation just missed, rather than rotating to the other
    representation — the adaptive re-practice fix keeps the struggling skill in front of the
    learner."""
    kc, _rep = next_spec_after_outcome(
        _ADD, 2, last_correct=False, last_kc=_ADD, last_format=Representation.SYMBOLIC
    )
    assert kc == _ADD  # NOT the companion (_SUB) the plain cadence would have served


def test_wrong_answer_keeps_the_same_representation() -> None:
    """Re-practice stays in the SAME representation the learner just struggled on, so the
    surface label and the served problem agree and the difficulty is similar."""
    kc, rep = next_spec_after_outcome(
        _NL, 1, last_correct=False, last_kc=_NL, last_format=Representation.NUMBER_LINE
    )
    assert kc == _NL
    assert rep == Representation.NUMBER_LINE


def test_wrong_answer_repractices_the_kc_actually_answered() -> None:
    """If the learner missed a COMPANION-KC item, re-practice is on that companion KC (the
    one they actually struggled on), not the goal — they get more practice on the skill that
    is shaky."""
    kc, rep = next_spec_after_outcome(
        _ADD, 5, last_correct=False, last_kc=_SUB, last_format=Representation.SYMBOLIC
    )
    assert kc == _SUB
    assert rep == Representation.SYMBOLIC


def test_correct_answer_interleaves_exactly_like_next_spec() -> None:
    """A correct answer leaves interleaving UNCHANGED — the schedule still rotates KCs and
    representations exactly as ``next_spec`` always did (no regression to §3.4 rule 4)."""
    for i in range(12):
        assert next_spec_after_outcome(
            _ADD, i, last_correct=True, last_kc=_ADD, last_format=Representation.SYMBOLIC
        ) == next_spec(_ADD, i)


def test_repractice_format_falls_back_to_a_live_one() -> None:
    """If the just-answered format is somehow not a live representation for the KC (defensive),
    re-practice still serves a renderable live representation, never a dead surface."""
    kc, rep = next_spec_after_outcome(
        _NL, 3, last_correct=False, last_kc=_NL, last_format=Representation.AREA_MODEL
    )
    assert kc == _NL
    assert rep in (Representation.NUMBER_LINE, Representation.SYMBOLIC)
