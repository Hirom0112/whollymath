"""Nudge-level hint bank + selection tests (Slice 3.8, phase 1 of 0.D.3).

These assert the FIRST, working hint path — pre-written conceptual nudges, no LLM
and no SymPy (locked decision 0.D.3: "nudge (pre-written, no LLM, no SymPy)";
phased "nudges weeks 2-3"). The §3.7 example conceptual prompt ("what does the
denominator tell us about each piece?") is the spirit of a nudge: it ORIENTS the
learner toward the concept without revealing an answer. That is exactly why a nudge
needs no SymPy validation (PROJECT.md §3.10: SymPy validates the *symbolic content*
of LLM hints — a later slice — but a nudge carries no symbolic content to validate).

The load-bearing properties asserted here:

  - ``HintLevel`` pins the locked 0.D.3 vocabulary EXACTLY (the three levels), even
    though only NUDGE is implemented in this slice;
  - every one of the five KCs has 2-4 nudges (``3.8.1``);
  - every nudge string carries NO digit and NO obvious math claim — the property
    that makes "no SymPy needed" true, scanned over the whole bank;
  - selection is DETERMINISTIC: the same inputs yield the identical ``NudgeHint``
    (PROJECT.md §4.1 reproducibility);
  - the unbuilt levels (partial_step / worked_step, Slice 5.6) raise
    ``NotImplementedError`` rather than silently returning a hollow hint.

No LLM, no SymPy, no DB, no network (CLAUDE.md §8.1/§8.2) — pure strings + a
deterministic selector.
"""

from __future__ import annotations

import re

import pytest
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.verifier import ErrorCategory
from app.tutor.hints import (
    NUDGE_BANK,
    HintLevel,
    NudgeHint,
    select_nudge,
)

_ALL_KCS = tuple(KnowledgeComponentId)


# ─── HintLevel pins the locked 0.D.3 vocabulary ──────────────────────────────


def test_hint_level_has_exactly_the_three_locked_members() -> None:
    """HintLevel is EXACTLY the three 0.D.3 levels — no more, no fewer."""
    assert {level.value for level in HintLevel} == {
        "nudge",
        "partial_step",
        "worked_step",
    }


def test_hint_level_members_named_as_locked() -> None:
    """The member handles match the locked decision's names."""
    assert HintLevel.NUDGE.value == "nudge"
    assert HintLevel.PARTIAL_STEP.value == "partial_step"
    assert HintLevel.WORKED_STEP.value == "worked_step"


# ─── The bank: 2-4 nudges per KC, all five KCs covered (3.8.1) ────────────────


def test_bank_covers_every_kc() -> None:
    """Every one of the five KCs is present in the nudge bank."""
    assert set(NUDGE_BANK.keys()) == set(_ALL_KCS)


@pytest.mark.parametrize("kc", _ALL_KCS)
def test_each_kc_has_two_to_four_nudges(kc: KnowledgeComponentId) -> None:
    """Each KC carries 2-4 pre-written nudges (3.8.1 '2-4 pre-written nudges per KC')."""
    nudges = NUDGE_BANK[kc]
    assert 2 <= len(nudges) <= 4


@pytest.mark.parametrize("kc", _ALL_KCS)
def test_nudges_are_nudge_level_for_their_kc(kc: KnowledgeComponentId) -> None:
    """Every banked nudge is NUDGE-level and tagged with its own KC."""
    for nudge in NUDGE_BANK[kc]:
        assert isinstance(nudge, NudgeHint)
        assert nudge.level is HintLevel.NUDGE
        assert nudge.kc is kc


@pytest.mark.parametrize("kc", _ALL_KCS)
def test_nudge_text_is_nonempty(kc: KnowledgeComponentId) -> None:
    """No nudge is blank — a hollow nudge helps no one (CLAUDE.md §5)."""
    for nudge in NUDGE_BANK[kc]:
        assert nudge.text.strip()


# ─── The no-math property (why no SymPy is needed) ────────────────────────────

# A nudge is a CONCEPTUAL prompt: no digit (so no fraction, no numeric answer) and
# none of the bare arithmetic-operator glyphs that would make it a math claim. This
# is the property scanned below; it is what makes "no SymPy validation" sound.
_DIGIT = re.compile(r"\d")
_MATH_GLYPH = re.compile(r"[+\-*/=<>÷×½⅓¼¾]")


@pytest.mark.parametrize("kc", _ALL_KCS)
def test_no_nudge_contains_a_digit(kc: KnowledgeComponentId) -> None:
    """No nudge contains a digit — no numeric answer, no specific fraction."""
    for nudge in NUDGE_BANK[kc]:
        assert not _DIGIT.search(nudge.text), f"digit in nudge: {nudge.text!r}"


@pytest.mark.parametrize("kc", _ALL_KCS)
def test_no_nudge_contains_a_math_claim_glyph(kc: KnowledgeComponentId) -> None:
    """No nudge contains a bare math-operator/fraction glyph (no math claim)."""
    for nudge in NUDGE_BANK[kc]:
        assert not _MATH_GLYPH.search(nudge.text), f"math glyph in nudge: {nudge.text!r}"


# ─── Determinism of selection (PROJECT.md §4.1) ───────────────────────────────


@pytest.mark.parametrize("kc", _ALL_KCS)
def test_select_nudge_is_deterministic(kc: KnowledgeComponentId) -> None:
    """Same inputs ⇒ identical NudgeHint, every call (reproducibility)."""
    first = select_nudge(kc)
    second = select_nudge(kc)
    assert first == second


@pytest.mark.parametrize("kc", _ALL_KCS)
def test_select_nudge_returns_a_banked_nudge_for_the_kc(kc: KnowledgeComponentId) -> None:
    """A selected nudge is one of that KC's own banked nudges."""
    selected = select_nudge(kc)
    assert selected in NUDGE_BANK[kc]
    assert selected.kc is kc


@pytest.mark.parametrize("kc", _ALL_KCS)
def test_index_selects_distinct_nudges_within_the_bank(kc: KnowledgeComponentId) -> None:
    """Consecutive indices walk the KC's bank; index wraps (no out-of-range)."""
    bank = NUDGE_BANK[kc]
    for i in range(len(bank)):
        assert select_nudge(kc, index=i) == bank[i]
    # Wrap: an index past the end maps deterministically back into the bank.
    assert select_nudge(kc, index=len(bank)) == bank[0]


def test_error_category_changes_selection_deterministically() -> None:
    """A given error_category maps to a fixed nudge for the KC (same every call)."""
    kc = KnowledgeComponentId.ADDITION_UNLIKE
    magnitude_pick = select_nudge(kc, error_category=ErrorCategory.MAGNITUDE)
    operation_pick = select_nudge(kc, error_category=ErrorCategory.OPERATION)
    assert magnitude_pick == select_nudge(kc, error_category=ErrorCategory.MAGNITUDE)
    assert operation_pick == select_nudge(kc, error_category=ErrorCategory.OPERATION)
    assert magnitude_pick in NUDGE_BANK[kc]
    assert operation_pick in NUDGE_BANK[kc]


@pytest.mark.parametrize("kc", _ALL_KCS)
def test_error_category_none_matches_default(kc: KnowledgeComponentId) -> None:
    """error_category=None behaves like the plain default index-0 selection."""
    assert select_nudge(kc, error_category=None) == select_nudge(kc)


# ─── The unbuilt levels (Slice 5.6) fail loudly ──────────────────────────────


@pytest.mark.parametrize("level", [HintLevel.PARTIAL_STEP, HintLevel.WORKED_STEP])
def test_non_nudge_levels_are_not_implemented(level: HintLevel) -> None:
    """partial_step / worked_step are Slice 5.6 — selecting them raises, never stubs."""
    with pytest.raises(NotImplementedError):
        select_nudge(KnowledgeComponentId.ADDITION_UNLIKE, level=level)


def test_nudge_level_is_the_default() -> None:
    """The default level is NUDGE — the only level this slice implements."""
    assert select_nudge(KnowledgeComponentId.EQUIVALENCE).level is HintLevel.NUDGE
