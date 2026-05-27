"""The reactive UI adaptation policy — the §3.6 transition rules (Slice 2.4).

This is the *pedagogical model's* routing layer (ARCHITECTURE.md §3, §7): given the
learner's current surface state and a SIGNAL from a turn, it decides the next
surface state — or a no-change, or a nudge. It is **pure decision logic** over
enums and small dataclasses: no SymPy, no LLM, no DB (CLAUDE.md §7, §8.1/§8.2;
ARCHITECTURE.md §14 invariants 1 & 5). SymPy already decided correctness in
``domain/`` and the mastery model already decided readiness in ``mastery/``; this
module only *routes* on the signals they produce. It deliberately does NOT import
the mastery model — the "interleaved set passed" verdict arrives as INPUT, so the
policy never re-derives mastery (the build-director scope note; ARCHITECTURE.md §6
keeps the mastery decision in one place).

It implements the PROJECT.md §3.6 transition table verbatim:

  | Event                                    | From        | To  |
  |------------------------------------------|-------------|-----|
  | Magnitude error                          | S1, S3, S4  | S2  |
  | Operation/format error                   | S1, S2, S4  | S3  |
  | 2 correct in state, no hints             | S2, S3, S4  | S1  |
  | 2+ consecutive errors                    | any         | S4  |
  | Interleaved set passed (mastery signal)  | (post-set)  | S5  |
  | Transfer probe failed                    | S5          | S2/S3 by KC |
  | Idle > 90s                               | any         | NUDGE (no change) |

Error kind -> state follows the verifier's own mapping (verifier.py docstring,
PROJECT.md §3.6 rationale column): a MAGNITUDE error routes to S2 (the number line
exposes magnitude); an OPERATION or FORMAT error routes to S3 (fraction bars make
the operation visible).

Every state change carries a one-line ``label`` because PROJECT.md §3.8 refuse-rule
4 forbids presenting a new state without one ("Let's try this another way.").
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.knowledge_components import KnowledgeComponentId
from app.domain.verifier import ErrorCategory
from app.policy.surface_states import SurfaceState

# The PROJECT.md §0.D.5 idle timer: idle beyond this many seconds earns a nudge,
# never a state change (PROJECT.md §3.6 last row, §3.8 refuse-rule 3). Tunable in
# weeks 4-5 (PROJECT.md §8); named here so the threshold is not a magic number.
IDLE_NUDGE_THRESHOLD_SECONDS = 90

# PROJECT.md §3.6 row 3: the scaffold fades after this many correct, unhinted
# answers in the current state. The "without hints" qualifier is enforced by the
# caller only counting unhinted corrects into the streak (see ``AnswerOutcome``).
FADE_SCAFFOLD_CORRECT_STREAK = 2

# PROJECT.md §3.6 row 4 / §3.5 S4: "2+ consecutive errors" means the learner is
# stuck; route to the worked example. "Don't wait too long — help-avoidance
# research" (PROJECT.md §3.6 rationale).
STUCK_CONSECUTIVE_ERRORS = 2


# ─── Events (the signals the policy routes on) ───
#
# Each event is a small frozen dataclass — a value describing what happened on a
# turn, never mutable state. The policy reads them; it does not own them. Frozen
# so a routed signal cannot be rewritten downstream (CLAUDE.md §8.4).


@dataclass(frozen=True)
class AnswerOutcome:
    """The verifier's verdict on a submitted answer, as the policy needs it.

    Carries only what §3.6 routes on: correctness, the §3.6 error category (the
    ``ErrorCategory`` the SymPy verifier produces — verifier.py), whether a hint
    was used on this turn, and the two running counters the table's rate rules
    depend on. The counters are computed by the caller (the tutor session loop),
    NOT here — the policy is stateless and routes on the numbers it is handed:

    - ``consecutive_correct_no_hint_in_state``: how many correct, *unhinted*
      answers in a row in the CURRENT state. Resets on a wrong answer, on a hint,
      or on a state change. This is how "2 correct without hints" (§3.6 row 3) is
      enforced — a hinted turn never increments it, so a hinted run never fades.
    - ``consecutive_errors``: how many wrong answers in a row, across the session.
      "2+ consecutive errors -> S4" (§3.6 row 4).
    """

    is_correct: bool
    error_category: ErrorCategory
    hint_used: bool
    consecutive_correct_no_hint_in_state: int = 0
    consecutive_errors: int = 0


@dataclass(frozen=True)
class InterleavedSetPassed:
    """Mastery signal: the mandatory interleaved-practice set was passed (§3.6 row 6).

    The mastery model decides this (ARCHITECTURE.md §6: a BKT threshold crossing
    does NOT jump straight to S5 — it first requires a passed interleaved set).
    The policy takes the verdict as input and routes to the transfer probe; it does
    NOT compute mastery (build-director scope; CLAUDE.md §8.1 keeps the mastery
    update off the policy). ``kc`` is the KC whose mastery is now provisional and
    about to be probed — recorded for the transition label and downstream logging.
    """

    kc: KnowledgeComponentId


@dataclass(frozen=True)
class TransferProbeFailed:
    """The transfer probe (S5) was failed (§3.6 row 7) — diagnostic data, not a verdict.

    "Treat transfer fail as diagnostic data" (PROJECT.md §3.6 rationale). The policy
    routes back to the scaffolded state that exposes the failed KC's error kind:
    a magnitude KC -> S2, an operation KC -> S3 (see ``_state_for_error_kind`` and
    ``_error_kind_for_kc``).
    """

    failed_kc: KnowledgeComponentId


@dataclass(frozen=True)
class IdleNudge:
    """The learner has been idle (§3.6 row 8 / §0.D.5 idle timer).

    Idle is the one signal that must NEVER change state (§3.8 refuse-rule 3:
    "pausing is not a signal of needing a different representation"). Past the 90s
    threshold the policy surfaces a NUDGE; below it, nothing. ``idle_seconds`` is
    the elapsed idle time the caller measured.
    """

    idle_seconds: int


# A turn can carry any one of these signals into the policy.
PolicyEvent = AnswerOutcome | InterleavedSetPassed | TransferProbeFailed | IdleNudge


# ─── Transition (the policy's decision) ───


@dataclass(frozen=True)
class Transition:
    """The base policy decision: a labeled move (or no move) for one signal.

    Every transition carries a non-empty one-line ``label`` — PROJECT.md §3.8
    refuse-rule 4 forbids presenting a new state without one, and the §3.6 table is
    only legible to a reviewer if every row says *why* it fired. ``to_state`` is the
    state the learner ends up in (equal to the current state for a no-change).
    ``is_state_change`` distinguishes a real transition from a no-op / nudge so the
    caller can apply refuse-rule 1 (no state change mid-problem) without inspecting
    the concrete type.

    Frozen: a routed decision is a fact about a turn, not mutable state
    (CLAUDE.md §8.4, ARCHITECTURE.md §14).
    """

    to_state: SurfaceState
    label: str
    is_state_change: bool


@dataclass(frozen=True)
class StateChange(Transition):
    """A transition that actually moves the learner to a new surface state.

    A distinct type (not just ``is_state_change=True``) so callers and tests can
    pattern-match the §3.6 rows that change state, vs. ``NoChange`` / ``Nudge``.
    """

    def __init__(self, to_state: SurfaceState, label: str) -> None:
        # is_state_change is always True for a StateChange; set it on the frozen
        # base via object.__setattr__ so the invariant can't be passed wrong.
        object.__setattr__(self, "to_state", to_state)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "is_state_change", True)


@dataclass(frozen=True)
class NoChange(Transition):
    """The signal did not warrant a transition — the learner stays put.

    Carries a label anyway (so refuse-rule 4 holds on every path) and
    ``is_state_change=False`` so the caller treats it as a no-op.
    """

    def __init__(self, state: SurfaceState, label: str) -> None:
        object.__setattr__(self, "to_state", state)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "is_state_change", False)


@dataclass(frozen=True)
class Nudge(Transition):
    """A small idle nudge (§3.6 row 8) — explicitly NOT a state change.

    The learner stays in the current state (``is_state_change=False``); the label
    is the nudge copy. This is the type that encodes "Avoid interrupting productive
    struggle" — idle never re-skins the workspace.
    """

    def __init__(self, state: SurfaceState, label: str) -> None:
        object.__setattr__(self, "to_state", state)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "is_state_change", False)


# ─── Error-kind <-> state and KC <-> error-kind mappings (§3.6) ───


def _state_for_error_kind(error_category: ErrorCategory) -> SurfaceState | None:
    """Map a §3.6 error category to the state that exposes it, or ``None``.

    PROJECT.md §3.6 rationale column (and verifier.py's own mapping):
      - MAGNITUDE        -> S2 (number line exposes magnitude);
      - OPERATION/FORMAT -> S3 (fraction bars make the operation visible).

    NONE and OTHER have no §3.6 routing — we do not invent one (CLAUDE.md §12). A
    correct answer (NONE) is handled by the fade-scaffold rule, not by error kind;
    an unrecognized error (OTHER) leaves the learner in place rather than guessing
    a representation.
    """
    if error_category is ErrorCategory.MAGNITUDE:
        return SurfaceState.NUMBER_LINE_PRIMARY
    if error_category in (ErrorCategory.OPERATION, ErrorCategory.FORMAT):
        return SurfaceState.FRACTION_BARS_PRIMARY
    return None


def _error_kind_for_kc(kc: KnowledgeComponentId) -> ErrorCategory:
    """Map a failed KC to the error kind its failure represents (§3.6 row 7 routing).

    The §3.6 table says transfer fail routes "Back to S3 or S2 based on which KC
    failed" but does not enumerate the KC->state mapping; we ground it in the same
    representation logic the rest of §3.6 uses (the verifier.py mapping):

      - the number-line PLACEMENT KC is the MAGNITUDE skill — failing it is a
        magnitude problem -> route to S2 (the number line);
      - the four operative KCs (equivalence, common-denominator, addition,
        subtraction) are PROCEDURE skills — failing one is an operation problem ->
        route to S3 (the fraction bars, where part-manipulation makes the operation
        visible).

    This is the one routing decision not spelled out cell-by-cell in §3.6; it is
    recorded here (and in the commit message per CLAUDE.md §8.4) as a documented
    extension consistent with the table's own magnitude/operation -> S2/S3 logic.
    """
    if kc is KnowledgeComponentId.NUMBER_LINE_PLACEMENT:
        return ErrorCategory.MAGNITUDE
    return ErrorCategory.OPERATION


# ─── The policy ───


def next_transition(current: SurfaceState, event: PolicyEvent) -> Transition:
    """Decide the next surface state (or no-change / nudge) for one signal.

    The single entry point for the reactive §3.6 policy. It dispatches on the
    signal type and returns a labeled ``Transition``. It is stateless and pure: the
    same ``(current, event)`` always yields the same decision (this is what makes
    the policy testable row-by-row and the persona harness reproducible,
    ARCHITECTURE.md §5).

    Ordering note: an ``AnswerOutcome`` is evaluated stuck-first. "2+ consecutive
    errors -> S4 from any state" (§3.6 row 4) is the catch-all the state diagram
    draws from every state, so it takes precedence over the single-error kind
    routing of rows 1/2 — a learner who is clearly stuck gets the worked example,
    not another representation swap.
    """
    if isinstance(event, AnswerOutcome):
        return _from_answer(current, event)
    if isinstance(event, InterleavedSetPassed):
        # §3.6 row 6: the interleaved set passed -> the transfer probe (S5).
        return StateChange(
            SurfaceState.TRANSFER_PROBE,
            "Great — let's try a fresh challenge to confirm you've got it.",
        )
    if isinstance(event, TransferProbeFailed):
        return _from_transfer_fail(event)
    # IdleNudge — the only remaining variant.
    return _from_idle(current, event)


def _from_answer(current: SurfaceState, event: AnswerOutcome) -> Transition:
    """Route an answer outcome through §3.6 rows 3 (fade), 4 (stuck), 1/2 (error kind)."""
    # Row 4 first (catch-all from any state): the learner is stuck.
    if not event.is_correct and event.consecutive_errors >= STUCK_CONSECUTIVE_ERRORS:
        return StateChange(
            SurfaceState.WORKED_EXAMPLE,
            "Let's walk through one together, step by step.",
        )

    # Row 3: two correct, unhinted answers in the current state -> fade scaffold to
    # S1. Only applies away from S1 (you cannot fade from the fluent state); the
    # counter already excludes hinted turns, so "without hints" is enforced upstream.
    if (
        event.is_correct
        and not event.hint_used
        and current is not SurfaceState.SYMBOLIC_FOCUS
        and event.consecutive_correct_no_hint_in_state >= FADE_SCAFFOLD_CORRECT_STREAK
    ):
        return StateChange(
            SurfaceState.SYMBOLIC_FOCUS,
            "Nice work — let's move to the quicker symbolic view.",
        )

    # Rows 1 & 2: a single error routes to the representation that exposes its kind.
    if not event.is_correct:
        target = _state_for_error_kind(event.error_category)
        if target is not None and target is not current:
            return StateChange(target, _label_for_error_kind(event.error_category))

    # Anything else (a lone correct answer below the streak, an OTHER/NONE error, or
    # an error whose target is the current state) is a no-change — the policy adapts
    # with restraint (ARCHITECTURE.md §2) rather than re-skinning on every turn.
    return NoChange(current, "Keep going.")


def _label_for_error_kind(error_category: ErrorCategory) -> str:
    """The one-line §3.8-rule-4 label for an error-kind transition (rows 1/2)."""
    if error_category is ErrorCategory.MAGNITUDE:
        return "Let's look at where this fraction sits on the number line."
    # OPERATION / FORMAT
    return "Let's try this another way, with bars you can move."


def _from_transfer_fail(event: TransferProbeFailed) -> Transition:
    """Route a transfer-probe failure back to scaffolded practice (§3.6 row 7)."""
    error_kind = _error_kind_for_kc(event.failed_kc)
    target = _state_for_error_kind(error_kind)
    # error_kind is always MAGNITUDE or OPERATION here, so target is never None;
    # assert it for the type-checker and as a guard against a future mapping change.
    assert target is not None  # noqa: S101 — invariant of _error_kind_for_kc
    if error_kind is ErrorCategory.MAGNITUDE:
        label = "Let's revisit the number line to nail down the size."
    else:
        label = "Let's go back to the bars and rebuild the steps."
    return StateChange(target, label)


def _from_idle(current: SurfaceState, event: IdleNudge) -> Transition:
    """Idle handling (§3.6 row 8 / §3.8 refuse-rule 3): nudge past 90s, else no-op.

    Idle NEVER changes state. Past the 90s threshold we surface a gentle nudge in
    place; below it we return a no-change with no nudge, because "pausing is not a
    signal of needing a different representation" (§3.8 refuse-rule 3).
    """
    if event.idle_seconds > IDLE_NUDGE_THRESHOLD_SECONDS:
        return Nudge(current, "Still there? Take your time — give it a try when you're ready.")
    return NoChange(current, "")


__all__ = [
    "AnswerOutcome",
    "IdleNudge",
    "InterleavedSetPassed",
    "NoChange",
    "Nudge",
    "PolicyEvent",
    "StateChange",
    "Transition",
    "TransferProbeFailed",
    "next_transition",
]
