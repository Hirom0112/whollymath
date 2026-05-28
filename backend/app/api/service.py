"""The turn-loop service boundary — the real deterministic pipeline (Slices 1.9, 2.6 → API).

ARCHITECTURE.md §10 describes the turn loop as a deterministic pipeline: ``verify
(SymPy) -> update mastery (BKT) -> choose next state (policy)`` -> serve the next
problem (the HelpNeed/XGBoost and LLM-surface steps are off this path — §8.1, and
later slices). CLAUDE.md §7 / ARCHITECTURE.md §14 require the route handler to stay
thin and each stage to live in its own layer. This module is the **seam** the route
calls; it ORCHESTRATES the already-built, already-tested ``TutorSession`` (which in
turn composes the domain verifier, the mastery model, and the §3.6 policy) — it does
not re-implement any of their jobs.

Invariants honored here (the boundary must not bake in a contract bug):
  - **No SymPy here** — correctness is the domain verifier's job, reached via
    ``TutorSession.submit_answer`` (§9, §14 invariant 2).
  - **No LLM here** — the deterministic path runs with the LLM off (§8.1, §14 inv 1).
    Nudge hints are pre-written (Slice 3.8), not model-generated.
  - **No DB here** — sessions live in an in-memory ``SessionStore`` keyed by
    session id (TECH_STACK §9: v1 uses session-id identification, no auth/DB). A
    persistence repository over the DB models is a deliberately later slice.

Determinism: the tutor logic is deterministic (PROJECT.md §4.1). The only
non-deterministic element is the opaque ``session_id`` minted per ``start`` — that
is runtime identity, not part of the reproducible harness, so a ``uuid`` is correct.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.api.schemas import (
    ActionType,
    ErrorType,
    MasterySnapshot,
    ProblemView,
    RouteOptionView,
    StartSessionResponse,
    TurnRequest,
    TurnResponse,
)
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import Problem
from app.tutor.hints import select_nudge
from app.tutor.session import RouteOption, TutorSession, routing_choices


class SessionNotFoundError(LookupError):
    """A ``TurnRequest`` named a ``session_id`` the store does not know.

    Named (not a bare ``KeyError``) so the route can map exactly this condition to a
    404 without catching unrelated lookup failures. A session is unknown when it was
    never started or the in-memory store was reset (e.g. a server restart — there is
    no persistence yet, TECH_STACK §9).
    """


class UnknownRouteError(LookupError):
    """A ``StartSessionRequest`` named a ``route_key`` not in the Turn-0 menu (0.D.2).

    The routing table is the single source of truth (tutor ``routing_choices``); a
    key outside it is a client error the route maps to a 422-style rejection rather
    than guessing a route (CLAUDE.md §8.5 — fail loudly, don't invent).
    """


def _problem_view(problem: Problem) -> ProblemView:
    """Project a domain ``Problem`` to the answer-free ``ProblemView`` the wire ships.

    Deliberately drops ``correct_value`` / ``operands``: the answer never crosses to
    the client (correctness is the verifier's job server-side, §8.2). Only the
    renderable subset travels — plus, for a number-line problem, the snap-grid hint.

    ``tick_segments`` is the displayed target's denominator (``correct_value.q``). The
    generator displays the REDUCED target (``target.p/target.q``) and sets
    ``correct_value`` to that same value, so the denominator is exactly the grid the
    learner reads, and the target sits on one of the k/q ticks. Exposing the
    denominator (e.g. "fifths") is the standard number-line scaffold; it does not
    reveal WHERE the fraction sits. ``None`` for any non-number-line surface — those
    do not snap a drag, so they need no grid.
    """
    is_number_line = problem.surface_format is Representation.NUMBER_LINE
    return ProblemView(
        problem_id=problem.problem_id,
        kc=problem.kc,
        surface_format=problem.surface_format,
        statement=problem.statement,
        tick_segments=int(problem.correct_value.q) if is_number_line else None,
    )


def routing_menu() -> list[RouteOptionView]:
    """The Turn-0 routing menu as wire views (decision 0.D.2).

    Projects the tutor's ``RouteOption``s (the single source of truth for the menu)
    to the client view: ``key`` (echoed back to start a session), the kid-friendly
    ``prompt``, and the ``is_unsure_default`` flag the surface uses to de-emphasize
    the one default option. The KC each option routes to stays server-side (0.D.2:
    the client never sets the KC directly).
    """
    return [
        RouteOptionView(key=o.key, prompt=o.prompt, is_unsure_default=o.is_unsure_default)
        for o in routing_choices()
    ]


def _route_for_key(route_key: str) -> RouteOption:
    """The tutor ``RouteOption`` for a menu key, or raise ``UnknownRouteError``."""
    for option in routing_choices():
        if option.key == route_key:
            return option
    raise UnknownRouteError(route_key)


def _serve_next(session: TutorSession, kc: KnowledgeComponentId) -> Problem:
    """Choose and present the next problem after a turn (the MVP scheduling default).

    **Scope flag (CLAUDE.md §1):** the real adaptive scheduler — interleaving across
    KCs (0.D.5: 3 items / ≥2 KCs) and HelpNeed-driven selection — is Slice 4.x and is
    NOT wired here. Until then this uses a conservative, sourced default: **stay on
    the KC just practiced**, in a representation the live frontend can actually answer.

    The format is chosen by the KC, not the surface state, so the served statement
    always matches a rendered input widget: number-line placement → ``NUMBER_LINE``
    (the draggable marker, with ``tick_segments``), everything else → ``SYMBOLIC`` (the
    fraction editor, which expresses any ``a/b``). The S2/S3 manipulatives-as-workspace
    morph (a number line / fraction bars that VISUALIZE an arithmetic problem while the
    answer is entered separately) is the fuller Slice 2.5 follow-up; until it lands a
    surface state must not pick a format with no answer widget, or the learner sees a
    statement with no usable input. The seed is the session's turn count, so the walk
    is deterministic and each turn yields a fresh problem (PROJECT.md §4.1).
    """
    surface_format = (
        Representation.NUMBER_LINE
        if kc is KnowledgeComponentId.NUMBER_LINE_PLACEMENT
        else Representation.SYMBOLIC
    )
    return session.present_problem(kc=kc, seed=len(session.history), surface_format=surface_format)


def _answer_response(session: TutorSession, request: TurnRequest) -> TurnResponse:
    """Run one SUBMIT_ANSWER turn end-to-end and shape the wire reply.

    The raw answer string is handed straight to ``submit_answer``: the domain
    verifier owns parsing ``"7/12"`` to a SymPy ``Rational`` (verifier
    ``_parse_to_rational``) and never raises on what a kid types, so the API does not
    pre-parse or pre-validate the math (§8.2). A missing answer on a submit becomes
    the empty string, which the verifier treats as wrong (honest, never a crash).
    """
    answered = session.current_problem
    result = session.submit_answer(
        request.submitted_answer or "",
        latency_ms=request.latency_ms,
        hint_used=request.hint_used,
    )
    next_problem = _serve_next(session, answered.kc)
    return TurnResponse(
        correct=result.correct,
        error_type=result.error_category,
        next_surface_state=result.surface_state,
        feedback=result.feedback,
        hint=None,
        mastery=[
            MasterySnapshot(kc_id=m.kc, probability=m.probability, mastered=m.mastered)
            for m in result.mastery_snapshot
        ],
        next_problem=_problem_view(next_problem),
    )


def _hint_response(session: TutorSession) -> TurnResponse:
    """Answer a REQUEST_HINT turn with a pre-written nudge — no state change, no advance.

    A hint request is not an answer: it does not verify, update mastery, or advance
    the problem. Per the refuse-rules it never changes the surface state (§3.8 rule 3:
    a pause/help is not a transition), so the state is echoed unchanged and the learner
    stays on the SAME problem. The nudge is the deterministic, pre-written conceptual
    prompt for the current KC (Slice 3.8, ``select_nudge`` — no LLM, no SymPy, §8.1).
    The LLM-filled ``partial_step``/``worked_step`` levels are Slice 5.6.
    """
    problem = session.current_problem
    nudge = select_nudge(problem.kc)
    return TurnResponse(
        correct=False,
        error_type=ErrorType.NONE,
        next_surface_state=session.surface_state,
        feedback="Here's something to think about.",
        hint=nudge.text,
        mastery=[],
        next_problem=_problem_view(problem),
    )


@dataclass
class SessionStore:
    """In-memory ``session_id -> TutorSession`` map — the live-session boundary.

    Runtime state, not deterministic-harness state: a live learner session is
    identified by an opaque id the client echoes onto each turn (TECH_STACK §9 — no
    auth in v1). One store is created per app (``create_app``) and injected into the
    routes, so tests get an isolated store and sessions never leak between apps.
    Persistence (a repository over the Slice-1.8 DB models) is a deliberately later
    slice; ``create_all`` / in-memory is the path for now (CLAUDE.md §8.6).
    """

    _sessions: dict[str, TutorSession] = field(default_factory=dict)

    def start(self, route_key: str) -> StartSessionResponse:
        """Start a session from a Turn-0 route key and return its Turn-1 problem (0.D.2).

        Derives everything server-side from the locked routing table: the chosen
        ``RouteOption`` builds a ``TutorSession`` via ``from_route`` (which seeds the
        BKT prior-not-commitment and presents the locked calibration item). The new
        session is stored under a freshly minted opaque id the client threads onto
        every subsequent turn.
        """
        option = _route_for_key(route_key)
        session = TutorSession.from_route(option)
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = session
        return StartSessionResponse(
            session_id=session_id,
            surface_state=session.surface_state,
            problem=_problem_view(session.current_problem),
        )

    def process_turn(self, request: TurnRequest) -> TurnResponse:
        """Process one learner action against its session (the route's entrypoint).

        Looks up the session (``SessionNotFoundError`` if unknown — the route maps it
        to a 404), then dispatches on the action: a hint request returns a nudge
        without advancing; a submitted answer runs the full deterministic turn and
        serves the next problem. All turn-loop composition happens behind this seam so
        the route stays thin (CLAUDE.md §7).
        """
        session = self._sessions.get(request.session_id)
        if session is None:
            raise SessionNotFoundError(request.session_id)
        if request.action is ActionType.REQUEST_HINT:
            return _hint_response(session)
        return _answer_response(session, request)


__all__ = [
    "SessionNotFoundError",
    "SessionStore",
    "UnknownRouteError",
    "routing_menu",
]
