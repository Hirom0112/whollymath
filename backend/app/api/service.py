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
    InterventionKind,
    InterventionView,
    MasterySnapshot,
    ProblemView,
    RouteOptionView,
    StartSessionResponse,
    SurfaceState,
    TurnRequest,
    TurnResponse,
)
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.problem_generators import Problem
from app.domain.verifier import verify
from app.helpneed.live_features import LiveTurn, live_features
from app.helpneed.predictor import HelpNeedPredictor
from app.llm.provider import LLMProvider
from app.persona_surface.tutor_voice import voice_help
from app.policy.intervention_gate import SustainedHelpNeedGate
from app.policy.scheduler import is_masterable_live, next_spec
from app.tutor.hints import select_nudge
from app.tutor.live_transfer_probe import build_live_probe_steps
from app.tutor.session import (
    MasterySnapshot as TutorMasterySnapshot,
)
from app.tutor.session import (
    RouteOption,
    TutorSession,
    routing_choices,
)


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
        answer_kind=problem.answer_kind,
        yes_no_relation=problem.yes_no_relation,
        tick_segments=int(problem.correct_value.q) if is_number_line else None,
        given_denominator=problem.given_denominator,
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


def _serve_next(session: TutorSession) -> Problem:
    """Choose and present the next problem after a turn, via the interleaving scheduler.

    The goal KC is the cold-start route's KC (the first turn). The scheduler
    (``policy.scheduler.next_spec``) interleaves a companion KC on a fixed cadence (so the
    mastery model's ≥2-KC interleaving rule can fire) and rotates the goal KC through the
    representations the live surface can render and answer (so the ≥2-representations rule can
    fire). Both were impossible under the old "stay on one KC, one format" stub — which made
    the experience monotonous AND mastery unreachable live (PROJECT.md §3.4/§3.6, 0.D.5).

    Every served ``(kc, format)`` pair has a real answer widget (scheduler only emits live
    representations), so the learner never sees a statement with no usable input. The seed is
    the session's turn count, so the walk is deterministic and fresh (PROJECT.md §4.1).
    """
    goal_kc = session.history[0].observation.kc
    served_index = len(session.history) - 1  # 0 = the first problem after the cold-start item
    kc, surface_format = next_spec(goal_kc, served_index)
    return session.present_problem(kc=kc, seed=len(session.history), surface_format=surface_format)


def _help_need(
    session: TutorSession,
    next_problem: Problem,
    predictor: HelpNeedPredictor | None,
) -> float | None:
    """Observe-only P(unproductive) for the NEXT problem (Slice 4.4.1).

    **Observe-only by construction (the locked 4.3 decision, RESEARCH.md §7.5):** this
    reads ``predict_proba`` and hands the number back in the response. It NEVER feeds a
    transition, a refuse-rule, or the next-problem choice — interventions are Slice 4.5,
    gated on a *sustained* high-P signal (``turns_since_last_correct`` dominates the
    model, so a single high-P turn right after a resolved error streak is not enough).

    Stays on the deterministic, sub-100ms path (§8.1): the §3.3 features are built from
    the live history by ``live_features`` and scored by XGBoost — no LLM, no SymPy, no
    DB. Leakage-safe: the in-progress next problem is not yet in ``session.history``, so
    every feature comes from strictly-earlier completed turns (live_features docstring).

    ``None`` when no predictor is injected (a test/degraded store — ``create_app``
    always loads the committed artifact, so production always scores).
    """
    if predictor is None:
        return None
    history = [
        LiveTurn(
            correct=turn.observation.correct,
            hinted=turn.observation.hinted,
            latency_ms=turn.observation.latency_ms,
        )
        for turn in session.history
    ]
    features = live_features(history, current_kc=next_problem.kc)
    return predictor.predict_proba(features)


def _maybe_intervene(
    live: _LiveSession,
    gate: SustainedHelpNeedGate,
    next_problem: Problem,
    voice_provider: LLMProvider | None,
) -> InterventionView | None:
    """Decide whether to PROACTIVELY offer help before the next problem (Slice 4.5.1).

    Returns an intervention only when BOTH (a) this session's proactive arm is enabled
    and (b) the §3.7 sustained-signal ``gate`` fires on the accumulated HelpNeed stream
    (K consecutive turns at P ≥ threshold). Default-OFF means the live experience is
    unchanged until the Slice 5.4 A/B turns the arm on per session — so we make no
    "proactive helps" claim before it is measured (RESEARCH.md §7.5 decision).

    The offered text is the pre-written conceptual nudge for the upcoming problem's KC
    (Slice 3.8 ``select_nudge`` — no LLM, no SymPy, §8.1). It is rendered as an inline
    assertion (§3.8 refuse-rule 6); the LLM-mediated partial worked step is Slice 5.6.
    This is consistent with refuse-rule 5 (no auto-help in the first 60s *except in
    response to wrong answers*): the gate fires precisely on accumulated unproductive
    struggle, and the offer is made between problems, not mid-problem (refuse-rule 1).
    """
    if not live.proactive_enabled:
        return None
    if not gate.should_intervene(live.help_need_history):
        return None
    # A help moment: voice the pre-written nudge in the mascot's voice (Slice 5.5.2), or
    # return it verbatim if voicing is disabled/fails (invariant 4). The LLM only rephrases
    # an already-decided nudge — it never decides whether to intervene (§8.1).
    nudge_text = select_nudge(next_problem.kc).text
    return InterventionView(
        kind=InterventionKind.INLINE_ASSERTION,
        text=voice_help(nudge_text, provider=voice_provider),
    )


# Practice turns to wait after a FAILED probe before re-offering it: a still-provisional KC
# would otherwise re-trigger the probe every turn. The learner practices a little more first.
_PROBE_COOLDOWN = 3


def _mastery_view(
    snapshot: tuple[TutorMasterySnapshot, ...], live: _LiveSession
) -> list[MasterySnapshot]:
    """Per-KC snapshot for the wire, with ``mastered`` meaning CONFIRMED (passed the S5
    transfer probe), never bare provisional — so the surface only celebrates earned mastery
    (PROJECT.md §3.4). ``probability`` is the model's BKT value either way."""
    return [
        MasterySnapshot(kc_id=m.kc, probability=m.probability, mastered=m.kc in live.confirmed)
        for m in snapshot
    ]


def _probe_mastery_view(
    session: TutorSession, live: _LiveSession, kc: KnowledgeComponentId
) -> list[MasterySnapshot]:
    """The goal KC's snapshot during/after a probe turn (the probe doesn't run the mastery
    model, so we read its BKT probability and report mastered = confirmed)."""
    return [
        MasterySnapshot(
            kc_id=kc,
            probability=session.mastery_probability(kc),
            mastered=kc in live.confirmed,
        )
    ]


def _probe_turn(live: _LiveSession, request: TurnRequest) -> TurnResponse:
    """Handle one turn while the S5 transfer probe is in progress (PROJECT.md §3.9).

    The submitted answer is judged DIRECTLY by the SymPy verifier against the current probe
    step — the probe is the confirm gate, separate from the mastery model (so a probe turn
    never updates BKT). Any wrong step fails the probe → DEMOTE (back to practice, with a
    cooldown). Passing every step → CONFIRM the KC (mastered becomes true). Steps are served
    as ordinary problems, so the existing widgets render them.
    """
    session = live.tutor
    goal_kc = session.history[0].observation.kc
    step = live.probe_steps[live.probe_index]
    verdict = verify(step, request.submitted_answer or "")

    if not verdict.is_correct:
        live.probe_steps = []
        live.probe_index = 0
        live.probe_cooldown = _PROBE_COOLDOWN
        next_problem = _serve_next(session)
        return TurnResponse(
            correct=False,
            error_type=verdict.error_category,
            next_surface_state=session.surface_state,
            feedback="Not quite — let's practice a little more before the final check.",
            hint=None,
            mastery=_probe_mastery_view(session, live, goal_kc),
            help_need=None,
            intervention=None,
            next_problem=_problem_view(next_problem),
        )

    live.probe_index += 1
    if live.probe_index >= len(live.probe_steps):
        live.confirmed.add(goal_kc)
        live.probe_steps = []
        live.probe_index = 0
        next_problem = _serve_next(session)
        return TurnResponse(
            correct=True,
            error_type=ErrorType.NONE,
            next_surface_state=session.surface_state,
            feedback="You showed it more than one way — that's real mastery, not a lucky answer.",
            hint=None,
            mastery=_probe_mastery_view(session, live, goal_kc),
            help_need=None,
            intervention=None,
            next_problem=_problem_view(next_problem),
        )

    return TurnResponse(
        correct=True,
        error_type=ErrorType.NONE,
        next_surface_state=SurfaceState.TRANSFER_PROBE,
        feedback="Nice — one more, a different way.",
        hint=None,
        mastery=_probe_mastery_view(session, live, goal_kc),
        help_need=None,
        intervention=None,
        next_problem=_problem_view(live.probe_steps[live.probe_index]),
    )


def _answer_response(
    live: _LiveSession,
    request: TurnRequest,
    predictor: HelpNeedPredictor | None,
    gate: SustainedHelpNeedGate,
    voice_provider: LLMProvider | None,
) -> TurnResponse:
    """Run one SUBMIT_ANSWER turn end-to-end and shape the wire reply.

    The raw answer string is handed straight to ``submit_answer``: the domain
    verifier owns parsing ``"7/12"`` to a SymPy ``Rational`` (verifier
    ``_parse_to_rational``) and never raises on what a kid types, so the API does not
    pre-parse or pre-validate the math (§8.2). A missing answer on a submit becomes
    the empty string, which the verifier treats as wrong (honest, never a crash).

    Order matters (CLAUDE.md §8.1): the deterministic verify/mastery/policy path runs and
    fixes the turn outcome FIRST. Only then does the HelpNeed predictor score the next
    problem (``_help_need``); that P is appended to the session stream and the §3.7 gate
    decides whether to proactively intervene. Neither the score nor the gate can perturb
    correctness, the surface state, or the next-problem choice — they are read off the
    settled turn, so a proactive arm changes only the ``intervention`` field.
    """
    # A probe in progress takes the turn: the learner is answering a transfer-probe item, not
    # a practice problem (so it does not feed the mastery model — the probe is the confirm
    # gate, judged directly by the verifier). §3.4/§3.9.
    if live.probe_steps:
        return _probe_turn(live, request)

    session = live.tutor
    result = session.submit_answer(
        request.submitted_answer or "",
        latency_ms=request.latency_ms,
        hint_used=request.hint_used,
    )
    if live.probe_cooldown > 0:
        live.probe_cooldown -= 1

    goal_kc = session.history[0].observation.kc
    provisional = any(m.kc == goal_kc and m.mastered for m in result.mastery_snapshot)
    if (
        provisional
        and goal_kc not in live.confirmed
        and live.probe_cooldown == 0
        and is_masterable_live(goal_kc)
    ):
        # Provisional reached → present the S5 transfer probe before declaring mastery (§3.9).
        live.probe_steps = build_live_probe_steps(
            goal_kc, recent_format=session.current_problem.surface_format
        )
        live.probe_index = 0
        return TurnResponse(
            correct=result.correct,
            error_type=result.error_category,
            next_surface_state=SurfaceState.TRANSFER_PROBE,
            feedback="Great — one last check to be sure you've really got it.",
            hint=None,
            mastery=_mastery_view(result.mastery_snapshot, live),
            help_need=None,
            intervention=None,
            next_problem=_problem_view(live.probe_steps[0]),
        )

    next_problem = _serve_next(session)
    help_need = _help_need(session, next_problem, predictor)
    if help_need is not None:
        live.help_need_history.append(help_need)
    return TurnResponse(
        correct=result.correct,
        error_type=result.error_category,
        next_surface_state=result.surface_state,
        feedback=result.feedback,
        hint=None,
        mastery=_mastery_view(result.mastery_snapshot, live),
        help_need=help_need,
        intervention=_maybe_intervene(live, gate, next_problem, voice_provider),
        next_problem=_problem_view(next_problem),
    )


def _hint_response(session: TutorSession, voice_provider: LLMProvider | None) -> TurnResponse:
    """Answer a REQUEST_HINT turn with a pre-written nudge — no state change, no advance.

    A hint request is not an answer: it does not verify, update mastery, or advance
    the problem. Per the refuse-rules it never changes the surface state (§3.8 rule 3:
    a pause/help is not a transition), so the state is echoed unchanged and the learner
    stays on the SAME problem. The nudge is the deterministic, pre-written conceptual
    prompt for the current KC (Slice 3.8, ``select_nudge`` — which DECIDES the help; no
    SymPy, §8.1). A hint is a help moment, so the nudge is rephrased in the mascot's voice
    (Slice 5.5.2) when voicing is enabled, or returned verbatim otherwise (invariant 4).
    The LLM-filled ``partial_step``/``worked_step`` levels are Slice 5.6.
    """
    problem = session.current_problem
    nudge = select_nudge(problem.kc)
    return TurnResponse(
        correct=False,
        error_type=ErrorType.NONE,
        next_surface_state=session.surface_state,
        feedback="Here's something to think about.",
        hint=voice_help(nudge.text, provider=voice_provider),
        mastery=[],
        next_problem=_problem_view(problem),
    )


@dataclass
class _LiveSession:
    """The per-session runtime record behind a ``session_id`` (Slices 4.4/4.5).

    Bundles the ``TutorSession`` with the live-loop state that is an API-layer concern,
    not the tutor's: the accumulated observe-only HelpNeed ``help_need_history`` the §3.7
    gate reads, and ``proactive_enabled`` — this session's A/B arm. The arm defaults OFF
    (observe-only), so a session never sees a proactive intervention unless it was started
    into the proactive arm; the Slice 5.4 A/B is what turns it on per session.
    """

    tutor: TutorSession
    proactive_enabled: bool = False
    help_need_history: list[float] = field(default_factory=list)
    # S5 transfer-probe state (the live confirm-gate). When ``probe_steps`` is non-empty a
    # probe is in progress: the learner is answering ``probe_steps[probe_index]``. ``confirmed``
    # holds the KCs whose provisional mastery the learner has CONFIRMED by passing the probe —
    # the snapshot reports mastered = confirmed, never bare provisional. ``probe_cooldown`` is
    # the number of practice turns to wait before re-offering the probe after a failed attempt,
    # so a still-provisional KC doesn't re-trigger the probe every turn.
    probe_steps: list[Problem] = field(default_factory=list)
    probe_index: int = 0
    confirmed: set[KnowledgeComponentId] = field(default_factory=set)
    probe_cooldown: int = 0


@dataclass
class SessionStore:
    """In-memory ``session_id -> _LiveSession`` map — the live-session boundary.

    Runtime state, not deterministic-harness state: a live learner session is
    identified by an opaque id the client echoes onto each turn (TECH_STACK §9 — no
    auth in v1). One store is created per app (``create_app``) and injected into the
    routes, so tests get an isolated store and sessions never leak between apps.
    Persistence (a repository over the Slice-1.8 DB models) is a deliberately later
    slice; ``create_all`` / in-memory is the path for now (CLAUDE.md §8.6).

    ``predictor`` is the boot-loaded HelpNeed model used to score each answer turn
    observe-only (Slice 4.4.1). It is optional so contract/boundary tests can build a
    bare store; ``create_app`` always injects the committed artifact, so production
    always scores. When absent, ``help_need`` is simply omitted (left ``None``).

    ``gate`` is the §3.7 sustained-signal intervention gate (Slice 4.5.1), shared across
    sessions because it is pure/stateless (the per-session P stream lives on each
    ``_LiveSession``). It only matters for sessions whose proactive arm is enabled.

    ``voice_provider`` is the optional LLM backend that rephrases help text in the mascot's
    voice on help moments (Slice 5.5.2). ``None`` (the default, and what tests use) returns
    the pre-written help verbatim — no LLM call; ``create_app`` injects the Anthropic
    provider to enable voicing live (invariant 4: voicing is a polish, never load-bearing).
    """

    predictor: HelpNeedPredictor | None = None
    gate: SustainedHelpNeedGate = field(default_factory=SustainedHelpNeedGate)
    voice_provider: LLMProvider | None = None
    _sessions: dict[str, _LiveSession] = field(default_factory=dict)

    def start(self, route_key: str, *, proactive_enabled: bool = False) -> StartSessionResponse:
        """Start a session from a Turn-0 route key and return its Turn-1 problem (0.D.2).

        Derives everything server-side from the locked routing table: the chosen
        ``RouteOption`` builds a ``TutorSession`` via ``from_route`` (which seeds the
        BKT prior-not-commitment and presents the locked calibration item). The new
        session is stored under a freshly minted opaque id the client threads onto
        every subsequent turn. ``proactive_enabled`` is the session's A/B arm (default
        OFF = observe-only); the Slice 5.4 harness sets it, not the client.
        """
        option = _route_for_key(route_key)
        live = _LiveSession(
            tutor=TutorSession.from_route(option),
            proactive_enabled=proactive_enabled,
        )
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = live
        return StartSessionResponse(
            session_id=session_id,
            surface_state=live.tutor.surface_state,
            problem=_problem_view(live.tutor.current_problem),
        )

    def process_turn(self, request: TurnRequest) -> TurnResponse:
        """Process one learner action against its session (the route's entrypoint).

        Looks up the session (``SessionNotFoundError`` if unknown — the route maps it
        to a 404), then dispatches on the action: a hint request returns a nudge
        without advancing; a submitted answer runs the full deterministic turn and
        serves the next problem. All turn-loop composition happens behind this seam so
        the route stays thin (CLAUDE.md §7).
        """
        live = self._sessions.get(request.session_id)
        if live is None:
            raise SessionNotFoundError(request.session_id)
        if request.action is ActionType.REQUEST_HINT:
            return _hint_response(live.tutor, self.voice_provider)
        return _answer_response(live, request, self.predictor, self.gate, self.voice_provider)


__all__ = [
    "SessionNotFoundError",
    "SessionStore",
    "UnknownRouteError",
    "routing_menu",
]
