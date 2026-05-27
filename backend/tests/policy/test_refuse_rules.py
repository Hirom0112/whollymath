"""Tests for the policy-enforceable refuse-rules (Slice 2.7 / PROJECT.md §3.8).

The PRD requires us to define what the interface refuses to change automatically
(PROJECT.md §3.8, ARCHITECTURE.md §7, §14 invariant 6). Four of the six §3.8
refuse-rules are POLICY-enforceable (pure decision logic); two are frontend/UI
concerns and are deferred to the frontend (documented in ``refuse_rules.py``).

These tests pin the four policy-enforceable guards:

  - rule 1: never change state MID-PROBLEM (transitions only between problems);
  - rule 3: never change state because the learner PAUSED;
  - rule 4: never present a new state without a one-line LABEL;
  - rule 5: never AUTO-HELP in the first 60s of a problem except on a wrong answer
            or explicit hint request (productive-struggle window, PROJECT.md §0.D.5).
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.verifier import ErrorCategory
from app.policy.refuse_rules import (
    AutoHelpRequest,
    is_state_change_allowed,
    may_auto_help,
)
from app.policy.surface_states import SurfaceState
from app.policy.transitions import (
    AnswerOutcome,
    IdleNudge,
    InterleavedSetPassed,
    next_transition,
)

# ─── §3.8 rule 1: never change state mid-problem ───


def test_state_change_refused_mid_problem() -> None:
    assert is_state_change_allowed(problem_in_progress=True) is False


def test_state_change_allowed_between_problems() -> None:
    assert is_state_change_allowed(problem_in_progress=False) is True


# ─── §3.8 rule 3: pausing never changes state ───


def test_pause_does_not_change_state() -> None:
    # An idle event (a pause) yields a nudge at most, never a StateChange.
    event = IdleNudge(idle_seconds=120)
    transition = next_transition(SurfaceState.FRACTION_BARS_PRIMARY, event)
    assert not transition.is_state_change
    assert transition.to_state is SurfaceState.FRACTION_BARS_PRIMARY


# ─── §3.8 rule 4: every presented state carries a one-line label ───


def test_state_changing_transitions_always_carry_a_label() -> None:
    # A representative state-changing event must produce a non-empty label.
    event = AnswerOutcome(is_correct=False, error_category=ErrorCategory.MAGNITUDE, hint_used=False)
    transition = next_transition(SurfaceState.SYMBOLIC_FOCUS, event)
    assert transition.is_state_change
    assert transition.label.strip()


def test_interleaved_pass_to_transfer_probe_carries_a_label() -> None:
    event = InterleavedSetPassed(kc=KnowledgeComponentId.ADDITION_UNLIKE)
    transition = next_transition(SurfaceState.SYMBOLIC_FOCUS, event)
    assert transition.is_state_change
    assert transition.label.strip()


# ─── §3.8 rule 5: no auto-help in the first 60s except wrong-answer / hint request ───


def test_no_auto_help_in_first_60s_with_no_wrong_answer() -> None:
    request = AutoHelpRequest(
        seconds_into_problem=10,
        had_wrong_answer=False,
        explicit_hint_request=False,
    )
    assert may_auto_help(request) is False


def test_auto_help_allowed_in_first_60s_on_a_wrong_answer() -> None:
    request = AutoHelpRequest(
        seconds_into_problem=10,
        had_wrong_answer=True,
        explicit_hint_request=False,
    )
    assert may_auto_help(request) is True


def test_auto_help_allowed_in_first_60s_on_explicit_hint_request() -> None:
    request = AutoHelpRequest(
        seconds_into_problem=5,
        had_wrong_answer=False,
        explicit_hint_request=True,
    )
    assert may_auto_help(request) is True


def test_auto_help_allowed_after_struggle_window_elapses() -> None:
    # After the 60s productive-struggle window, proactive help may fire on its own.
    request = AutoHelpRequest(
        seconds_into_problem=61,
        had_wrong_answer=False,
        explicit_hint_request=False,
    )
    assert may_auto_help(request) is True


def test_struggle_window_boundary_is_closed_at_60s() -> None:
    # Exactly at 60s we are still inside the protected window (window is the FIRST
    # 60 seconds, PROJECT.md §3.8 rule 5 / §0.D.5 productive-struggle window = 60s).
    request = AutoHelpRequest(
        seconds_into_problem=60,
        had_wrong_answer=False,
        explicit_hint_request=False,
    )
    assert may_auto_help(request) is False
