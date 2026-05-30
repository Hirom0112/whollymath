"""Spec-driven signal routing: error category → representation → surface state (Slice HR.A3).

The hyperreactive engine routes a wrong answer to the representation that exposes its error — and
it should read that routing from the lesson's ``LessonSpec`` (HR.A1), not from hard-coded KC
branches in ``transitions``. This module is that table: it reads ``spec.error_routes`` and maps
the chosen representation to the concrete ``SurfaceState`` the workspace renders.

Layering (CLAUDE.md §7): ``policy`` may read ``domain`` (the spec), so this is cycle-free — the
spec never imports back up into ``policy``. The representation→state map is the single source of
truth for "which surface shows which representation".

Wiring status: ``transitions._from_transfer_fail`` reads this now (it carries the failed KC). The
main answer path (``_from_answer``) routes the same way but its ``AnswerOutcome`` event does not
yet carry the KC; threading the KC into that event is the follow-up that completes HR.A3 — until
then this module's ``representation_for_error`` is exercised by tests and the transfer-fail path.
"""

from __future__ import annotations

from app.domain.knowledge_components import Representation
from app.domain.lesson_spec import LessonSpec
from app.domain.verifier import ErrorCategory
from app.policy.surface_states import SurfaceState

# The single source of truth for which surface state renders which representation. WORD_PROBLEM has
# no dedicated remediation state (it is a framing, not a manipulative), so it maps to ``None`` — a
# caller treats that as "no representation swap".
_STATE_FOR_REPRESENTATION: dict[Representation, SurfaceState] = {
    Representation.SYMBOLIC: SurfaceState.SYMBOLIC_FOCUS,
    Representation.NUMBER_LINE: SurfaceState.NUMBER_LINE_PRIMARY,
    Representation.AREA_MODEL: SurfaceState.FRACTION_BARS_PRIMARY,
    # The typed EXPRESSION answer surface (the ExpressionInput) lives in the symbolic-focus state:
    # like the fraction editor it is a typed symbolic input with no manipulative, so it reuses
    # SYMBOLIC_FOCUS rather than adding a sixth state — the "exactly five surface states" set stays
    # closed (PROJECT.md §3.5 / ARCHITECTURE.md §2 "adapt with restraint").
    Representation.EXPRESSION: SurfaceState.SYMBOLIC_FOCUS,
}


def representation_for_error(
    spec: LessonSpec, error_category: ErrorCategory
) -> Representation | None:
    """The representation a lesson routes ``error_category`` to, or ``None`` if it has no route.

    Reads ``spec.error_routes`` — the per-lesson table from HR.A1, where each route is guaranteed
    to target a representation the lesson actually offers. ``None`` for an error category the
    lesson does not route (e.g. NONE/OTHER, or a category with no declared route)."""
    for route in spec.error_routes:
        if route.error_category is error_category:
            return route.representation
    return None


def primary_remediation_representation(spec: LessonSpec) -> Representation:
    """The lesson's main fall-back representation — the first declared error route's target.

    Used when a learner needs scaffolding but there is no specific error category to route on (a
    transfer-probe failure: "this KC failed, go back to its primary manipulative"). ``error_routes``
    is non-empty by the HR.A1 contract, so this never raises."""
    return spec.error_routes[0].representation


def surface_state_for_representation(representation: Representation) -> SurfaceState | None:
    """The surface state that renders ``representation``, or ``None`` if it has no own state."""
    return _STATE_FOR_REPRESENTATION.get(representation)


def next_representation_on_correct() -> Representation:
    """Where a confident, unscaffolded learner fades TO — the fluent symbolic view (§3.6 row 3).

    The fade target is uniform across lessons (the symbolic surface is the fluent end state), so
    this takes no spec; it exists so the answer path can read its fade target from the routing
    table rather than hard-coding the state, once the KC is threaded into the answer event."""
    return Representation.SYMBOLIC


__all__ = [
    "next_representation_on_correct",
    "primary_remediation_representation",
    "representation_for_error",
    "surface_state_for_representation",
]
