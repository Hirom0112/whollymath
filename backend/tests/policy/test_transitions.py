"""Tests for the reactive UI adaptation policy (Slice 2.4).

Written test-first per CLAUDE.md §2 — TDD is *recommended* for "state transition
logic" with the canonical assertion shape "given event X in state Y, transition to
state Z". The adaptation policy is pure decision logic (CLAUDE.md §7: no SymPy, no
LLM, no DB) that routes between the five surface states (PROJECT.md §3.5).

These tests pin the PROJECT.md §3.6 transition table ROW-BY-ROW. Each test names
the row it covers, asserts the resulting state, and asserts the transition carries
a non-empty one-line label (PROJECT.md §3.8 refuse-rule 4 / ARCHITECTURE.md §7).

The §3.6 rows covered here:

  - magnitude error, from S1/S3/S4              -> S2
  - operation/format error, from S1/S2/S4       -> S3
  - 2 correct in current state without hints, from S2/S3/S4 -> S1 (fade scaffold)
  - 2+ consecutive errors, from any            -> S4
  - mastery model says "interleaved set passed" -> S5 (transfer probe)
  - transfer probe failed, from S5             -> S2 or S3 by the failed KC's kind
  - idle > 90s                                  -> a NUDGE, NOT a state change

The policy consumes SIGNALS (e.g. "interleaved set passed") — it does NOT import
or re-derive the mastery model (the build-director scope note). Error kind is
mapped from the domain ``ErrorCategory`` the SymPy verifier produces.
"""

from __future__ import annotations

import pytest
from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.verifier import ErrorCategory
from app.policy.surface_states import SurfaceState
from app.policy.transitions import (
    AnswerOutcome,
    IdleNudge,
    InterleavedSetPassed,
    StateChange,
    TransferProbeFailed,
    next_transition,
)

# ─── §3.6 row 1: magnitude error, from S1/S3/S4 -> S2 ───
# "Surface error type to representation that exposes it" — magnitude lives on the
# number line (PROJECT.md §3.5 S2; verifier.py maps MAGNITUDE -> S2).


@pytest.mark.parametrize(
    "current",
    [SurfaceState.SYMBOLIC_FOCUS, SurfaceState.FRACTION_BARS_PRIMARY, SurfaceState.WORKED_EXAMPLE],
)
def test_magnitude_error_routes_to_number_line(current: SurfaceState) -> None:
    event = AnswerOutcome(is_correct=False, error_category=ErrorCategory.MAGNITUDE, hint_used=False)
    transition = next_transition(current, event)
    assert isinstance(transition, StateChange)
    assert transition.to_state is SurfaceState.NUMBER_LINE_PRIMARY
    assert transition.label.strip()


# ─── §3.6 row 2: operation/format error, from S1/S2/S4 -> S3 ───
# "Operation errors visible in part-manipulation" — fraction bars (S3).


@pytest.mark.parametrize(
    "current",
    [SurfaceState.SYMBOLIC_FOCUS, SurfaceState.NUMBER_LINE_PRIMARY, SurfaceState.WORKED_EXAMPLE],
)
@pytest.mark.parametrize("category", [ErrorCategory.OPERATION, ErrorCategory.FORMAT])
def test_operation_or_format_error_routes_to_fraction_bars(
    current: SurfaceState, category: ErrorCategory
) -> None:
    event = AnswerOutcome(is_correct=False, error_category=category, hint_used=False)
    transition = next_transition(current, event)
    assert isinstance(transition, StateChange)
    assert transition.to_state is SurfaceState.FRACTION_BARS_PRIMARY
    assert transition.label.strip()


# ─── §3.6 row 3: 2 correct in current state without hints, from S2/S3/S4 -> S1 ───
# "Fade scaffold (Aleven & Koedinger fading-scaffolds finding)".


@pytest.mark.parametrize(
    "current",
    [
        SurfaceState.NUMBER_LINE_PRIMARY,
        SurfaceState.FRACTION_BARS_PRIMARY,
        SurfaceState.WORKED_EXAMPLE,
    ],
)
def test_two_correct_no_hints_fades_scaffold_to_symbolic(current: SurfaceState) -> None:
    event = AnswerOutcome(
        is_correct=True,
        error_category=ErrorCategory.NONE,
        hint_used=False,
        consecutive_correct_no_hint_in_state=2,
    )
    transition = next_transition(current, event)
    assert isinstance(transition, StateChange)
    assert transition.to_state is SurfaceState.SYMBOLIC_FOCUS
    assert transition.label.strip()


def test_one_correct_no_hints_does_not_fade_scaffold() -> None:
    # The rule is TWO correct; one is not enough — no state change yet.
    event = AnswerOutcome(
        is_correct=True,
        error_category=ErrorCategory.NONE,
        hint_used=False,
        consecutive_correct_no_hint_in_state=1,
    )
    transition = next_transition(SurfaceState.FRACTION_BARS_PRIMARY, event)
    assert transition.to_state is SurfaceState.FRACTION_BARS_PRIMARY  # NO-CHANGE
    assert not transition.is_state_change


def test_two_correct_with_a_hint_does_not_fade_scaffold() -> None:
    # "without hints" is load-bearing — a hinted correct run does not fade scaffold.
    # The streak counter only counts UNHINTED corrects, so a hinted turn resets it.
    event = AnswerOutcome(
        is_correct=True,
        error_category=ErrorCategory.NONE,
        hint_used=True,
        consecutive_correct_no_hint_in_state=0,
    )
    transition = next_transition(SurfaceState.NUMBER_LINE_PRIMARY, event)
    assert transition.to_state is SurfaceState.NUMBER_LINE_PRIMARY
    assert not transition.is_state_change


# ─── §3.6 row 4: 2+ consecutive errors, from ANY -> S4 ───
# "Don't wait too long — help-avoidance research". Worked example (S4).


@pytest.mark.parametrize(
    "current",
    [
        SurfaceState.SYMBOLIC_FOCUS,
        SurfaceState.NUMBER_LINE_PRIMARY,
        SurfaceState.FRACTION_BARS_PRIMARY,
        SurfaceState.WORKED_EXAMPLE,
    ],
)
def test_two_consecutive_errors_routes_to_worked_example(current: SurfaceState) -> None:
    event = AnswerOutcome(
        is_correct=False,
        error_category=ErrorCategory.OPERATION,
        hint_used=False,
        consecutive_errors=2,
    )
    transition = next_transition(current, event)
    assert isinstance(transition, StateChange)
    assert transition.to_state is SurfaceState.WORKED_EXAMPLE
    assert transition.label.strip()


def test_stuck_overrides_error_kind_routing() -> None:
    # §3.6 row 4 ("any -> S4") is the stuck rule; being stuck (2+ errors) takes
    # precedence over the single-error kind routing (rows 1/2), per the state
    # diagram (ARCHITECTURE.md §7: 2+ consecutive errors -> S4 from any state).
    event = AnswerOutcome(
        is_correct=False,
        error_category=ErrorCategory.MAGNITUDE,
        hint_used=False,
        consecutive_errors=3,
    )
    transition = next_transition(SurfaceState.SYMBOLIC_FOCUS, event)
    assert isinstance(transition, StateChange)
    assert transition.to_state is SurfaceState.WORKED_EXAMPLE


# ─── §3.6 row 6: interleaved set passed -> S5 (the transfer probe) ───
# The policy takes the mastery signal as INPUT; it does not compute it.


@pytest.mark.parametrize(
    "current",
    [
        SurfaceState.SYMBOLIC_FOCUS,
        SurfaceState.NUMBER_LINE_PRIMARY,
        SurfaceState.FRACTION_BARS_PRIMARY,
        SurfaceState.WORKED_EXAMPLE,
    ],
)
def test_interleaved_set_passed_routes_to_transfer_probe(current: SurfaceState) -> None:
    event = InterleavedSetPassed(kc=KnowledgeComponentId.ADDITION_UNLIKE)
    transition = next_transition(current, event)
    assert isinstance(transition, StateChange)
    assert transition.to_state is SurfaceState.TRANSFER_PROBE
    assert transition.label.strip()


# ─── §3.6 row 7: transfer probe failed, from S5 -> S2 or S3 by failed KC ───
# "Treat transfer fail as diagnostic data." Routing by the failed KC's error kind:
#   number-line placement KC -> a magnitude KC -> S2;
#   the operation KCs (add/subtract/common-denominator/equivalence) -> S3.


def test_transfer_fail_on_magnitude_kc_routes_to_number_line() -> None:
    event = TransferProbeFailed(failed_kc=KnowledgeComponentId.NUMBER_LINE_PLACEMENT)
    transition = next_transition(SurfaceState.TRANSFER_PROBE, event)
    assert isinstance(transition, StateChange)
    assert transition.to_state is SurfaceState.NUMBER_LINE_PRIMARY
    assert transition.label.strip()


@pytest.mark.parametrize(
    "failed_kc",
    [
        KnowledgeComponentId.ADDITION_UNLIKE,
        KnowledgeComponentId.SUBTRACTION_UNLIKE,
        KnowledgeComponentId.COMMON_DENOMINATOR,
        KnowledgeComponentId.EQUIVALENCE,
    ],
)
def test_transfer_fail_on_operation_kc_routes_to_fraction_bars(
    failed_kc: KnowledgeComponentId,
) -> None:
    event = TransferProbeFailed(failed_kc=failed_kc)
    transition = next_transition(SurfaceState.TRANSFER_PROBE, event)
    assert isinstance(transition, StateChange)
    assert transition.to_state is SurfaceState.FRACTION_BARS_PRIMARY
    assert transition.label.strip()


# ─── §3.6 row 8: idle > 90s -> a NUDGE, explicitly NOT a state change ───
# "Avoid interrupting productive struggle." (PROJECT.md §0.D.5 idle-timer = 90s.)


def test_idle_over_threshold_produces_nudge_not_state_change() -> None:
    event = IdleNudge(idle_seconds=91)
    transition = next_transition(SurfaceState.SYMBOLIC_FOCUS, event)
    # A nudge is NOT a StateChange — the contract is that idle never changes state.
    assert not isinstance(transition, StateChange)
    assert transition.label.strip()
    # And, defensively, whatever state we report stays put.
    assert transition.to_state is SurfaceState.SYMBOLIC_FOCUS


def test_idle_under_threshold_is_no_op() -> None:
    # Below 90s there is no nudge and no state change (refuse-rule 3: pausing is
    # not a signal). The policy returns a no-change with no nudge surfaced.
    event = IdleNudge(idle_seconds=10)
    transition = next_transition(SurfaceState.SYMBOLIC_FOCUS, event)
    assert not transition.is_state_change
    assert transition.to_state is SurfaceState.SYMBOLIC_FOCUS


# ─── Every transition carries a non-empty label (refuse-rule 4, all paths) ───


def test_every_state_change_path_has_a_label() -> None:
    events: list[object] = [
        AnswerOutcome(is_correct=False, error_category=ErrorCategory.MAGNITUDE, hint_used=False),
        AnswerOutcome(is_correct=False, error_category=ErrorCategory.OPERATION, hint_used=False),
        AnswerOutcome(
            is_correct=True,
            error_category=ErrorCategory.NONE,
            hint_used=False,
            consecutive_correct_no_hint_in_state=2,
        ),
        AnswerOutcome(
            is_correct=False,
            error_category=ErrorCategory.OPERATION,
            hint_used=False,
            consecutive_errors=2,
        ),
        InterleavedSetPassed(kc=KnowledgeComponentId.ADDITION_UNLIKE),
        TransferProbeFailed(failed_kc=KnowledgeComponentId.NUMBER_LINE_PLACEMENT),
    ]
    for event in events:
        transition = next_transition(SurfaceState.SYMBOLIC_FOCUS, event)  # type: ignore[arg-type]
        assert transition.label.strip(), f"transition for {event!r} has no label"
