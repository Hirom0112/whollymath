"""Tests for the HelpNeed training label (Slice 3.4).

The label is the predictor's target: was the learner in an UNPRODUCTIVE state on
this turn? Decision (2026-05-27): unproductive = gave up (asked for the answer) OR
never solved it OR floundered (3+ wrong tries) OR leaned on hints (2+). A single
wrong try then self-correcting is PRODUCTIVE struggle, not a help-need — that
distinction is the whole point (PROJECT.md §3.7; protects productive struggle).

These tests pin the boundary on crafted ``EdmCupTurn``s before the implementation
exists (TDD — CLAUDE.md §2: the HelpNeed pipeline is mandatory-TDD).
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.labels import (
    HINT_DEPENDENCE_THRESHOLD,
    WRONG_ATTEMPT_THRESHOLD,
    is_unproductive,
)
from app.helpneed.parse_edmcup import EdmCupTurn


def _turn(
    *,
    correct: bool = True,
    first_attempt_correct: bool = True,
    attempt_count: int = 1,
    hint_count: int = 0,
    requested_answer: bool = False,
) -> EdmCupTurn:
    """A crafted turn; defaults describe a clean first-try-unaided-correct solve."""
    return EdmCupTurn(
        assignment_log_id="a1",
        problem_id="p1",
        ccss_code="5.NF.A.1",
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        correct=correct,
        first_attempt_correct=first_attempt_correct,
        attempt_count=attempt_count,
        hint_count=hint_count,
        requested_answer=requested_answer,
        latency_ms_to_first_response=4000,
        total_latency_ms=4000,
    )


def test_clean_first_try_is_productive() -> None:
    """First-attempt unaided correct is the canonical PRODUCTIVE turn."""
    assert is_unproductive(_turn()) is False


def test_one_wrong_then_correct_is_productive() -> None:
    """One wrong try then self-correcting is productive struggle, not a help-need."""
    turn = _turn(correct=True, first_attempt_correct=False, attempt_count=2)
    assert is_unproductive(turn) is False


def test_two_wrong_then_correct_is_still_productive() -> None:
    """Two wrong tries (under the 3-wrong floundering threshold) still counts as fine."""
    turn = _turn(correct=True, first_attempt_correct=False, attempt_count=3)
    assert is_unproductive(turn) is False


def test_three_wrong_then_correct_is_unproductive() -> None:
    """3+ wrong tries is floundering even if eventually correct."""
    turn = _turn(correct=True, first_attempt_correct=False, attempt_count=4)
    assert is_unproductive(turn) is True


def test_never_solved_is_unproductive() -> None:
    """A turn that never reached a correct response is unproductive."""
    assert is_unproductive(_turn(correct=False, first_attempt_correct=False)) is True


def test_requested_answer_is_unproductive() -> None:
    """Asking for the answer is the clearest give-up signal."""
    turn = _turn(correct=True, first_attempt_correct=False, attempt_count=2, requested_answer=True)
    assert is_unproductive(turn) is True


def test_hint_dependence_is_unproductive() -> None:
    """Leaning on 2+ hints is unproductive even if the turn ends correct."""
    turn = _turn(correct=True, first_attempt_correct=False, attempt_count=1, hint_count=2)
    assert is_unproductive(turn) is True


def test_one_hint_is_still_productive() -> None:
    """A single hint, otherwise clean, is allowed (productive use of help)."""
    turn = _turn(correct=True, first_attempt_correct=False, attempt_count=1, hint_count=1)
    assert is_unproductive(turn) is False


def test_thresholds_are_the_documented_values() -> None:
    """Lock the tunable thresholds so a change is a deliberate, reviewed edit."""
    assert WRONG_ATTEMPT_THRESHOLD == 3
    assert HINT_DEPENDENCE_THRESHOLD == 2
