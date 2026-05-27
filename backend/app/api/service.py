"""The turn-loop service boundary (Slice 1.9 — stub).

ARCHITECTURE.md §10 describes the turn loop as a deterministic pipeline:
``verify (SymPy) -> update mastery (BKT) -> predict HelpNeed (XGBoost) -> choose
next state (policy)`` -> optional LLM surface. CLAUDE.md §7 / ARCHITECTURE.md §14
require that the *route handler stays thin* — no business logic in it — and that
each of those stages lives in its own layer (``domain/``, ``mastery/``,
``helpneed/``, ``policy/``). None of those layers' turn-loop entrypoints exist
yet (they are later slices).

This module is the **seam** the route calls. Today it returns a clearly-marked
stub so the API contract is exercisable end-to-end (a learner action in, a
well-typed ``TurnResponse`` out). When the real services land, they get wired in
*here* — behind this same function signature — so the contract (and the
frontend, and the generated TS types) does not change. That is the whole point
of putting the boundary in a separate module instead of in the route: the route
depends on a stable interface, not on the (not-yet-built) implementation.

Invariants this stub deliberately honors so it does not bake in a contract bug:
  - No SymPy here (verification is the domain layer's job — §9, §14).
  - No LLM here (the deterministic path must run with the LLM off — §14 inv. 1/4).
  - No DB here (queries live in repositories — §14 inv. 5).
The stub computes nothing about correctness; it just produces a shape.
"""

from __future__ import annotations

from app.api.schemas import (
    ErrorType,
    TurnRequest,
    TurnResponse,
)


class TurnLoopNotImplementedError(NotImplementedError):
    """Raised by the real-pipeline marker until the deterministic services exist.

    Kept as a named type (not a bare ``NotImplementedError``) so a later slice —
    and any test — can target *exactly* the "real turn loop isn't wired yet"
    condition, and so a grep for the class name finds every place the real
    pipeline still needs to be dropped in.
    """


def run_real_turn_loop(request: TurnRequest) -> TurnResponse:
    """Placeholder for the real verify -> mastery -> helpneed -> policy pipeline.

    This is where Slice 1.4 (SymPy verifier), the mastery model, the HelpNeed
    predictor, and the policy will be composed (ARCHITECTURE.md §10). Until then
    it raises, so nothing silently ships a fake "correct/incorrect" verdict as if
    it were real evidence. ``process_turn`` calls the stub below, *not* this, for
    now; the swap is a one-line change when the real services arrive.
    """
    raise TurnLoopNotImplementedError(
        "The deterministic turn loop (verify -> mastery -> helpneed -> policy) is not "
        "implemented yet; wire the real services into run_real_turn_loop in a later slice."
    )


def process_turn(request: TurnRequest) -> TurnResponse:
    """Service entrypoint the route calls — STUB response for the contract slice.

    Returns a well-typed ``TurnResponse`` that is shape-faithful to
    ARCHITECTURE.md §10 but computes no real correctness/mastery. It deliberately
    echoes the learner's current ``surface_state`` as ``next_surface_state`` (a
    no-op transition) and reports ``correct=False`` with ``ErrorType.NONE`` and an
    empty mastery list — an honest "nothing decided yet" placeholder rather than a
    fabricated verdict. Later slices replace this body with a call to
    ``run_real_turn_loop`` once the deterministic services exist.

    Kept here (not in the route) so the route stays thin (CLAUDE.md §7): the route
    validates and delegates; all turn-loop composition happens behind this seam.
    """
    return TurnResponse(
        correct=False,
        error_type=ErrorType.NONE,
        # No-op transition: the policy isn't built, so we do NOT invent a state
        # change (refuse-rule spirit, §7 — never transition without a reason).
        next_surface_state=request.surface_state,
        feedback="Turn received (stub): deterministic verify/mastery/policy not yet implemented.",
        hint=None,
        mastery=[],
    )


__all__ = [
    "TurnLoopNotImplementedError",
    "process_turn",
    "run_real_turn_loop",
]
