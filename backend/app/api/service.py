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

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.api.schemas import (
    ActionType,
    CourseNodeView,
    CourseView,
    ErrorType,
    EventBatchRequest,
    InteractionEventIn,
    InterventionKind,
    InterventionView,
    LessonView,
    MasterySnapshot,
    ProblemView,
    RouteOptionView,
    StartSessionResponse,
    StudyPlanView,
    SurfaceState,
    TurnRequest,
    TurnResponse,
    UnitDetailView,
    UnitListView,
    UnitView,
    WorkedStepView,
)
from app.db import repositories as repo
from app.db.models import Unit
from app.db.repositories import EventRow
from app.domain.curriculum import CatalogUnit, all_units, get_unit
from app.domain.knowledge_components import KnowledgeComponentId, Representation, get_kc
from app.domain.problem_generators import Problem
from app.domain.verifier import verify
from app.events.ingest import ingest_events
from app.helpneed.live_features import LiveTurn, live_features
from app.helpneed.predictor import HelpNeedPredictor
from app.llm.provider import LLMProvider
from app.mastery.course_map import build_course_map
from app.mastery.mastery_model import Observation
from app.mastery.progression import plan_study
from app.mastery.retention import ReviewableSkill
from app.mastery.unit_progress import UnitProgress, build_unit_progress
from app.persona_surface.tutor_voice import voice_help
from app.policy.intervention_gate import SustainedHelpNeedGate
from app.policy.scheduler import (
    difficulty_for,
    is_masterable_live,
    live_representations,
    next_spec_after_outcome,
)
from app.tutor.hints import HintLevel, build_validated_hint, select_nudge
from app.tutor.live_transfer_probe import build_live_probe_steps
from app.tutor.session import (
    MasterySnapshot as TutorMasterySnapshot,
)
from app.tutor.session import (
    RouteOption,
    TutorSession,
    routing_choices,
)
from app.tutor.worked_example import worked_example_for

# Persistence is best-effort and OFF the decision path (ARCHITECTURE.md §14 invariant 7):
# a DB failure is logged and swallowed, never allowed to break a turn. This module-level
# logger is the channel for those swallowed failures.
_log = logging.getLogger(__name__)


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
    # Axis bounds for a number-line item, derived from the target's magnitude: a proper
    # fraction sits on 0–1, an improper target stretches the right end to its ceiling (5/4 →
    # 0–2), a negative target stretches the left end to its floor (−5/4 → −2…1). Always anchored
    # on 0 and ≥1 so the learner keeps the whole as a reference (CP.B; PROJECT.md §3.1).
    value = problem.correct_value
    floor_value = value.p // value.q
    ceil_value = -((-value.p) // value.q)
    axis_min = min(0, floor_value) if is_number_line else 0
    axis_max = max(1, ceil_value) if is_number_line else 1
    return ProblemView(
        problem_id=problem.problem_id,
        kc=problem.kc,
        surface_format=problem.surface_format,
        statement=problem.statement,
        answer_kind=problem.answer_kind,
        yes_no_relation=problem.yes_no_relation,
        tick_segments=int(problem.correct_value.q) if is_number_line else None,
        axis_min=axis_min,
        axis_max=axis_max,
        given_denominator=problem.given_denominator,
    )


def _worked_example_view(problem: Problem) -> list[WorkedStepView]:
    """Project the S4 worked example of ``problem`` to the wire — empty if not buildable.

    Builds the worked solution via ``worked_example_for`` (the domain S4 builder; no SymPy
    or LLM reached here — the verifier boundary stays in ``domain/``, §8.2) and maps each
    ``WorkedStep`` to its renderable ``shown`` / ``why_prompt`` (the ``revealed_value`` is
    internal and never crosses the wire). ``worked_example_for`` raises ``ValueError`` for a
    problem whose KC procedure needs operands it does not carry (e.g. some yes/no or
    word-problem items); on that we return ``[]`` so an S4 turn degrades to "show S4 without
    a walkthrough" rather than 500-ing (CLAUDE.md §8.5 caller side — fail soft on the surface,
    never crash the turn loop). This is OFF the sub-100ms path: it runs only on an S4
    transition (a help moment), like the voice/hint code.
    """
    try:
        example = worked_example_for(problem)
    except ValueError:
        return []
    return [WorkedStepView(shown=step.shown, why_prompt=step.why_prompt) for step in example.steps]


def _event_row(event: InteractionEventIn) -> EventRow:
    """Map one validated wire ``InteractionEventIn`` to the repository's ``EventRow`` (Slice PL.2).

    The schema → storage carrier translation, kept in the API layer so ``app.events.ingest`` and
    the repository never import the wire schemas (the import direction stays API → events → repo,
    nothing back into the turn loop). Pure projection: no SymPy, no LLM, no decision (§8.1/§8.2).
    """
    return EventRow(
        event_type=event.event_type,
        payload=event.payload,
        client_ts=event.client_ts,
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


def _seed_base_from_session_id(session_id: str) -> int:
    """A stable, non-negative integer seed BASE derived from an opaque session id.

    The problem generators are intentionally seed-deterministic (same seed ⇒ same problem —
    that is what makes the persona harness reproducible, PROJECT.md §4.1). The reported "same
    problems every session" symptom came from the scheduler seeding every session's turns from
    the turn index alone (0, 1, 2, …): every session on a route therefore drew the identical
    problems. The fix is to vary the SEED SOURCE per session — NOT to make the generators
    random. We fold the session id (a uuid hex, runtime identity) into a stable integer base;
    the per-turn seed is then ``base + turn_index``, so a session's walk is unique to that
    session yet fully reproducible WITHIN the session (PROJECT.md §4.1). SHA-256 (not Python's
    salted ``hash``) keeps it stable across processes, so a fixed session id replays identically.

    Masked to 32 bits to stay a small, friendly seed for ``random.Random`` and the generated
    problem id. No crypto purpose — this is a deterministic spreader, not a security boundary.
    """
    digest = hashlib.sha256(session_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _serve_next(live: _LiveSession) -> Problem:
    """Choose and present the next problem after a turn, via the interleaving scheduler.

    The goal KC is the cold-start route's KC (the first turn). On a CORRECT last answer the
    scheduler (``policy.scheduler.next_spec``) interleaves a companion KC on a fixed cadence (so
    the mastery model's ≥2-KC interleaving rule can fire) and rotates the goal KC through the
    representations the live surface can render and answer (so the ≥2-representations rule can
    fire). On a WRONG last answer the scheduler keeps the learner on the SAME KC they just
    struggled on, in the same representation, for more practice on the shaky skill
    (``next_spec_after_outcome`` — the adaptive re-practice fix) rather than rotating them onto a
    different KC the moment they slip. The surface-transition policy (S1↔S5) is decided
    separately by the tutor and is unaffected here; this only chooses which KC/representation to
    draw the next problem from (PROJECT.md §3.4/§3.6, 0.D.5).

    Every served ``(kc, format)`` pair has a real answer widget (scheduler only emits live
    representations), so the learner never sees a statement with no usable input.

    The seed is ``seed_base + turn_index``: the per-session ``seed_base`` (derived from the
    session id) makes each session draw a DIFFERENT problem sequence, while the turn index keeps
    the walk deterministic and reproducible WITHIN the session (PROJECT.md §4.1). The generators
    stay seed-deterministic — only the seed SOURCE varies per session.
    """
    session = live.tutor
    goal_kc = session.history[0].observation.kc
    served_index = len(session.history) - 1  # 0 = the first problem after the cold-start item
    last = session.history[-1]
    kc, surface_format = next_spec_after_outcome(
        goal_kc,
        served_index,
        last_correct=last.observation.correct,
        last_kc=last.observation.kc,
        last_format=last.problem.surface_format,
    )
    seed = live.seed_base + len(session.history)
    # The easy→hard ramp tier for this rung (CP.B): the next problem's difficulty climbs with
    # how far into the lesson we are, so a lesson opens friendly and works up to bias-baiting
    # large denominators instead of feeling flat (CURRICULUM_DRAFT.md §1.1).
    difficulty = difficulty_for(served_index)
    return session.present_problem(
        kc=kc, seed=seed, surface_format=surface_format, difficulty=difficulty
    )


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

# Minimum practice problems a lesson serves before the S5 probe can fire — the "~10 then
# probe" bounded-lesson shape (CP.B; CURRICULUM_DRAFT.md §1.1). Without this floor the probe
# fired as soon as BKT crossed τ (~turn 7), ending the lesson BEFORE the easy→hard ramp reached
# its 6th-grade top rungs (improper, then negative placements), so the hard content never
# appeared. Holding the probe until the ramp is walked guarantees the learner meets the full
# difficulty progression first. 10 problems: with single-skill lessons every problem is the
# goal KC (no companion turns), and the steeper ramp reaches improper/negative by ~problem 6–8,
# so 10 walks the full easy→hard progression and clears the §3.4 evidence floors before the gate.
_LESSON_RAMP_MIN = 10


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
        next_problem = _serve_next(live)
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
        next_problem = _serve_next(live)
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
            # The goal KC is now CONFIRMED — the lesson is finished. Signal the surface to
            # show the completion screen and route home instead of looping on practice
            # (CP.B bounded-lesson terminal state; fixes the never-ending-lesson bug).
            lesson_complete=True,
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
        # Walk the full easy→hard ramp (incl. the improper/negative top rungs) before the gate —
        # the "~10 then probe" bounded-lesson shape (CP.B; see ``_LESSON_RAMP_MIN``).
        and len(session.history) >= _LESSON_RAMP_MIN
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

    next_problem = _serve_next(live)
    # A fresh practice problem was just served → reset the per-problem hint-escalation
    # counter so the next REQUEST_HINT on it starts again at a NUDGE (Feature B). The probe
    # paths above return before here, so entering/leaving the probe never touches the counter.
    live.hints_this_problem = 0
    help_need = _help_need(session, next_problem, predictor)
    if help_need is not None:
        live.help_need_history.append(help_need)
    # When the policy routed to S4 (≥2 consecutive errors, §3.6 row 4), serve the worked
    # solution of the problem the learner JUST got stuck on — history[-1] is that answered
    # problem (submit_answer appended it). NOT next_problem: that is the fresh practice item,
    # and revealing its worked solution would hand over its answer (§3.5 S4). Other states
    # leave worked_example empty (the default). Non-buildable stuck problems yield [].
    worked_example: list[WorkedStepView] = []
    if result.surface_state is SurfaceState.WORKED_EXAMPLE:
        worked_example = _worked_example_view(session.history[-1].problem)
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
        worked_example=worked_example,
    )


def _hint_response(
    live: _LiveSession,
    voice_provider: LLMProvider | None,
    hint_provider: LLMProvider | None,
) -> TurnResponse:
    """Answer a REQUEST_HINT turn with an ESCALATING hint — no state change, no advance.

    A hint request is not an answer: it does not verify, update mastery, or advance the
    problem. Per the refuse-rules it never changes the surface state (§3.8 rule 3: a
    pause/help is not a transition), so the state is echoed unchanged and the learner stays
    on the SAME problem.

    Escalation by ``live.hints_this_problem`` — how many hints have been requested on the
    CURRENT problem (the counter resets when an answer serves a fresh problem, §3.5/0.D.3):

      - 0 → NUDGE: the deterministic, pre-written conceptual prompt for the KC (Slice 3.8
        ``select_nudge`` — no SymPy/LLM decision, §8.1), rephrased in the mascot's voice
        (Slice 5.5.2) when voicing is enabled, or verbatim otherwise (invariant 4).
      - 1 → PARTIAL_STEP, 2+ → WORKED_STEP: the validated worked-example hint
        (``build_validated_hint`` — the locked 5.6 pipeline: canonical worked text → LLM
        rephrase → SymPy numeric gate → ≤2 retries → canonical fallback). We use its
        ``natural_language`` directly and do NOT also run it through ``voice_help``: the
        hint pipeline already does its own LLM rephrase behind the SymPy gate, so a second
        voicing would bypass that numeric gate. With ``hint_provider=None`` (tests, degraded
        store) the pipeline returns the deterministic canonical text — escalation is still
        real, just not LLM-warmed.

    The counter is incremented AFTER selecting, so the first request on a problem is the
    nudge. A hint never advances the problem (refuse-rule 3), so the count only grows here.
    """
    problem = live.tutor.current_problem
    requests_so_far = live.hints_this_problem
    if requests_so_far == 0:
        hint_text = voice_help(select_nudge(problem.kc).text, provider=voice_provider)
    else:
        level = HintLevel.PARTIAL_STEP if requests_so_far == 1 else HintLevel.WORKED_STEP
        hint_text = build_validated_hint(problem, level, provider=hint_provider).natural_language
    live.hints_this_problem += 1
    return TurnResponse(
        correct=False,
        error_type=ErrorType.NONE,
        next_surface_state=live.tutor.surface_state,
        feedback="Here's something to think about.",
        hint=hint_text,
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
    # Persistence linkage (Slice PL.1), all OFF the decision path. ``learner_session_id`` is
    # the opaque external key the client echoes (== the API session id), used to find/create
    # the Learner row. ``db_session_id`` is the persisted tutoring Session row's id (``None``
    # when no factory is wired, so the in-memory store keeps working unchanged).
    # ``persisted_turn_count`` is the monotonic turn_index for persisted Turn rows; it counts
    # BOTH submit and hint turns so the stored sequence matches the order they happened.
    learner_session_id: str = ""
    db_session_id: int | None = None
    persisted_turn_count: int = 0
    # The per-session base for the problem-generator seed (Fix A: problem variety). Derived
    # from the session id at construction (``_seed_base_from_session_id``); the per-turn seed
    # is ``seed_base + turn_index`` so each session draws a DIFFERENT problem sequence while
    # staying reproducible WITHIN the session (PROJECT.md §4.1). Default 0 reproduces the old
    # turn-index-only seeding for a bare ``_LiveSession`` built without a session id (tests).
    seed_base: int = 0
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
    # How many hints have been REQUESTED on the current problem (Feature B, §8 0.D.3). Drives
    # the reactive hint escalation nudge → partial_step → worked_step in ``_hint_response``;
    # reset to 0 in ``_answer_response`` when a submitted answer serves a fresh practice item.
    hints_this_problem: int = 0


@dataclass(frozen=True)
class _KcMastery:
    """The per-KC mastery readout the persistence layer writes (Slice PL.1).

    Computed from the live session's history (the counts the §3.4 rules range over) plus
    the BKT probability and the live confirmed flag — packaged here so ``_persist_turn``
    can hand each to ``upsert_mastery_state`` without the repository knowing how the counts
    were derived (CLAUDE.md §7: counting is service logic, the row shape is the repo's).
    """

    kc: KnowledgeComponentId
    bkt_probability: float
    attempt_count: int
    hint_count: int
    unscaffolded_correct_count: int
    confirmed: bool


def _mastery_rollup(live: _LiveSession) -> list[_KcMastery]:
    """Roll the live session's history up into a per-KC mastery readout for persistence.

    Pure, read-only over the already-settled session — it runs AFTER the response is built
    (invariant 7), never feeds a decision. For each KC the learner has answered, it tallies
    the §3.4 evidence counts straight from the ``Observation`` log:

      - ``attempt_count``               every observation for the KC.
      - ``hint_count``                  observations that used a hint.
      - ``unscaffolded_correct_count``  correct, engaged, NON-hinted attempts — the rule-3
        evidence (mirrors ``mastery_model._has_unscaffolded_correct`` at the row level; we
        re-tally here rather than import private logic, and use the same engagement floor via
        ``Observation.is_low_engagement``).

    ``bkt_probability`` is read from the tutor (the mastery model's value, not re-derived
    here), and ``confirmed`` from the live confirmed-KC set (the S5 probe verdict). KCs with
    no history are skipped — there is nothing to persist for an untouched KC.
    """
    observations: list[Observation] = [t.observation for t in live.tutor.history]
    by_kc: dict[KnowledgeComponentId, list[Observation]] = {}
    for obs in observations:
        by_kc.setdefault(obs.kc, []).append(obs)

    rollup: list[_KcMastery] = []
    for kc, obs_list in by_kc.items():
        hint_count = sum(1 for o in obs_list if o.hinted)
        unscaffolded_correct = sum(
            1 for o in obs_list if o.correct and not o.hinted and not o.is_low_engagement()
        )
        rollup.append(
            _KcMastery(
                kc=kc,
                bkt_probability=live.tutor.mastery_probability(kc),
                attempt_count=len(obs_list),
                hint_count=hint_count,
                unscaffolded_correct_count=unscaffolded_correct,
                confirmed=kc in live.confirmed,
            )
        )
    return rollup


def _persist_turn(
    factory: sessionmaker[OrmSession],
    live: _LiveSession,
    request: TurnRequest,
    response: TurnResponse,
) -> None:
    """Record a just-completed turn + the affected mastery rows — AFTER the response (inv 7).

    Called ONLY once the deterministic verify/mastery/policy decision is already made and the
    ``TurnResponse`` is built, so it can never perturb the turn outcome (the equivalence
    property). It opens its own short-lived session from ``factory``, persists the Turn row
    from the settled response, upserts every touched KC's MasteryState from the history
    rollup, and commits. Any failure is logged and swallowed (invariant 7: persistence never
    breaks a turn) — the caller has already returned the response to the learner in spirit;
    this is the after-write.

    ``db_session_id`` is ``None`` only if ``start`` could not open a Session row (a DB hiccup
    at start that we also swallowed); in that case there is nothing to hang a turn off, so we
    skip — the in-memory turn already succeeded.
    """
    if live.db_session_id is None:
        return
    turn_index = live.persisted_turn_count
    live.persisted_turn_count += 1
    try:
        with factory() as db:
            repo.persist_turn(
                db,
                session_id=live.db_session_id,
                turn_index=turn_index,
                problem_id=request.problem_id,
                action=request.action.value,
                correct=response.correct,
                error_type=response.error_type.value if not response.correct else None,
                surface_state=request.surface_state.value,
                state_transition=live.tutor.last_turn.result.transition.label
                if request.action is ActionType.SUBMIT_ANSWER and live.tutor.last_turn
                else None,
                latency_ms=request.latency_ms,
                hint_used=request.hint_used,
            )
            learner = repo.get_or_create_learner(db, live.learner_session_id)
            db.flush()
            for m in _mastery_rollup(live):
                repo.upsert_mastery_state(
                    db,
                    learner_id=learner.id,
                    kc_id=m.kc.value,
                    bkt_probability=m.bkt_probability,
                    attempt_count=m.attempt_count,
                    hint_count=m.hint_count,
                    unscaffolded_correct_count=m.unscaffolded_correct_count,
                    confirmed=m.confirmed,
                )
            db.commit()
    except Exception:  # noqa: BLE001 — invariant 7: a persistence failure never breaks a turn.
        _log.exception(
            "persistence failed for session %s; turn outcome unaffected", live.db_session_id
        )


@dataclass
class SessionStore:
    """In-memory ``session_id -> _LiveSession`` map — the live-session boundary.

    Runtime state, not deterministic-harness state: a live learner session is
    identified by an opaque id the client echoes onto each turn (TECH_STACK §9 — no
    auth in v1). One store is created per app (``create_app``) and injected into the
    routes, so tests get an isolated store and sessions never leak between apps.

    ``session_factory`` (Slice PL.1) is the optional persistence channel. ``None`` (the
    default, and what every existing test uses) means pure in-memory — no rows written,
    nothing to resume. When present, ``start`` records the Learner + Session rows and each
    ``process_turn`` records the Turn + upserts the affected MasteryState — but always AFTER
    the deterministic response is computed, never on the decision path (ARCHITECTURE.md §14
    invariant 7). Persistence is observe/record-only: a turn's ``TurnResponse`` is identical
    whether or not a factory is wired, and any DB failure is logged and swallowed so it can
    never break a turn.

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

    ``hint_provider`` is the optional LLM backend the escalated ``partial_step`` /
    ``worked_step`` hints rephrase through, behind the SymPy numeric gate (Slice 5.6 pipeline,
    ``build_validated_hint``). ``None`` (the default, and what tests use) makes the pipeline
    return the deterministic canonical worked text — escalation is still real, just not
    LLM-warmed; ``create_app`` injects the Anthropic provider to warm hints live. Distinct
    from ``voice_provider`` because the hint pipeline runs its own LLM rephrase under the
    numeric gate, so escalated hints are NOT also passed through the mascot voice (that would
    bypass the gate).
    """

    predictor: HelpNeedPredictor | None = None
    gate: SustainedHelpNeedGate = field(default_factory=SustainedHelpNeedGate)
    voice_provider: LLMProvider | None = None
    hint_provider: LLMProvider | None = None
    session_factory: sessionmaker[OrmSession] | None = None
    _sessions: dict[str, _LiveSession] = field(default_factory=dict)

    def start(
        self,
        route_key: str,
        *,
        proactive_enabled: bool = False,
        session_id: str | None = None,
    ) -> StartSessionResponse:
        """Start a session from a Turn-0 route key and return its Turn-1 problem (0.D.2).

        Derives everything server-side from the locked routing table: the chosen
        ``RouteOption`` builds a ``TutorSession`` via ``from_route`` (which seeds the
        BKT prior-not-commitment and presents the locked calibration item). The new
        session is stored under a freshly minted opaque id the client threads onto
        every subsequent turn. ``proactive_enabled`` is the session's A/B arm (default
        OFF = observe-only); the Slice 5.4 harness sets it, not the client.

        ``session_id`` is normally minted here (a uuid — runtime identity, not harness
        state). It can be supplied to pin the id (the deterministic-harness/test path):
        because the problem-seed base is derived from the id (Fix A), a fixed id replays
        the identical, reproducible problem walk (PROJECT.md §4.1).

        When a ``session_factory`` is wired (Slice PL.1) we also open the Learner +
        Session rows so turns have something to hang off — best-effort: a DB failure
        here is logged and swallowed (``db_session_id`` stays ``None``) so the live
        session still boots in-memory and the demo runs with no Postgres (invariant 7).
        """
        option = _route_for_key(route_key)
        session_id = session_id if session_id is not None else uuid.uuid4().hex
        live = _LiveSession(
            tutor=TutorSession.from_route(option),
            proactive_enabled=proactive_enabled,
            learner_session_id=session_id,
            seed_base=_seed_base_from_session_id(session_id),
        )
        if self.session_factory is not None:
            live.db_session_id = self._open_persisted_session(session_id, route_key)
        self._sessions[session_id] = live
        return StartSessionResponse(
            session_id=session_id,
            surface_state=live.tutor.surface_state,
            problem=_problem_view(live.tutor.current_problem),
        )

    def start_kc(
        self, kc: KnowledgeComponentId, *, proactive_enabled: bool = False
    ) -> StartSessionResponse:
        """Start a lesson DIRECTLY for a KC (the course-map node launch, Slice CP.A.2/§3.13).

        Unlike ``start`` (a Turn-0 menu route), this begins a session whose goal is ``kc`` and
        presents a generated first problem in the KC's first live representation (the one the
        surface can render+answer — ``live_representations``). Used by the course map so every
        node can launch its own lesson, including KCs that are not Turn-0 routes (subtraction,
        common denominator). Persistence stores ``kc.value`` as the session's ``route_key`` so a
        later ``resume`` re-derives the goal (``_tutor_for_route_key`` handles the KC form).
        Identity/persistence stay off the decision path (invariant 7/8).
        """
        session_id = uuid.uuid4().hex
        surface_format = live_representations(kc)[0]
        # Seed the FIRST problem from the per-session base too (not the fixed seed 0), so every
        # lesson opens with a DIFFERENT easy question instead of always "2/3 on 0–1". The base is
        # derived from the opaque session id, so a brand-new session draws a fresh opening while a
        # pinned id still replays deterministically (PROJECT.md §4.1).
        seed_base = _seed_base_from_session_id(session_id)
        live = _LiveSession(
            tutor=TutorSession.for_goal_kc(kc, surface_format=surface_format, seed=seed_base),
            proactive_enabled=proactive_enabled,
            learner_session_id=session_id,
            seed_base=seed_base,
        )
        if self.session_factory is not None:
            live.db_session_id = self._open_persisted_session(session_id, kc.value)
        self._sessions[session_id] = live
        return StartSessionResponse(
            session_id=session_id,
            surface_state=live.tutor.surface_state,
            problem=_problem_view(live.tutor.current_problem),
        )

    @staticmethod
    def _tutor_for_route_key(route_key: str) -> TutorSession:
        """Rebuild a ``TutorSession`` from a persisted ``route_key`` (for ``resume``).

        A Turn-0 menu key → ``from_route`` (the cold-start calibration path). A bare KC id (a
        course-map ``start_kc`` session, which stores ``kc.value`` as the route_key) → rebuild
        the goal-KC lesson via ``for_goal_kc``. Anything else is genuinely unknown and re-raises
        ``UnknownRouteError`` (CLAUDE.md §8.5 — fail loudly, don't invent a route).
        """
        try:
            return TutorSession.from_route(_route_for_key(route_key))
        except UnknownRouteError:
            try:
                kc = KnowledgeComponentId(route_key)
            except ValueError:
                raise UnknownRouteError(route_key) from None
            return TutorSession.for_goal_kc(kc, surface_format=live_representations(kc)[0])

    def _open_persisted_session(self, session_id: str, route_key: str) -> int | None:
        """Open the Learner + Session rows for a new session; ``None`` on any DB failure.

        Best-effort and OFF the decision path: a missing/unreachable DB must not crash a
        ``start`` (invariant 7 / the live demo boots with no Postgres). The learner is keyed
        by the opaque ``session_id`` (idempotent ``get_or_create_learner``); the Session row
        carries the ``route_key`` so a later ``resume`` can re-derive the goal KC.
        """
        assert self.session_factory is not None
        try:
            with self.session_factory() as db:
                learner = repo.get_or_create_learner(db, session_id)
                db.flush()
                session = repo.create_session(db, learner_id=learner.id, route_key=route_key)
                db.commit()
                return session.id
        except Exception:  # noqa: BLE001 — invariant 7: a DB hiccup at start must not crash.
            _log.exception("could not open persisted session for %s; running in-memory", session_id)
            return None

    def process_turn(self, request: TurnRequest) -> TurnResponse:
        """Process one learner action against its session (the route's entrypoint).

        Looks up the session (``SessionNotFoundError`` if unknown — the route maps it
        to a 404), then dispatches on the action: a hint request returns a nudge
        without advancing; a submitted answer runs the full deterministic turn and
        serves the next problem. All turn-loop composition happens behind this seam so
        the route stays thin (CLAUDE.md §7).

        Persistence happens AFTER the response is computed (Slice PL.1, invariant 7): the
        deterministic verify/mastery/policy decision and the ``TurnResponse`` are fixed
        first, then ``_persist_turn`` records the turn + mastery. Because the write is
        observe-only and its failures are swallowed, the returned response is byte-identical
        to a no-factory run.
        """
        live = self._sessions.get(request.session_id)
        if live is None:
            raise SessionNotFoundError(request.session_id)
        if request.action is ActionType.REQUEST_HINT:
            response = _hint_response(live, self.voice_provider, self.hint_provider)
        else:
            response = _answer_response(
                live, request, self.predictor, self.gate, self.voice_provider
            )
        if self.session_factory is not None:
            _persist_turn(self.session_factory, live, request, response)
        return response

    def ingest_events(self, request: EventBatchRequest) -> int:
        """Record a batch of raw interaction events OFF the turn loop (Slice PL.2, invariant 7).

        The telemetry entrypoint, deliberately INDEPENDENT of ``process_turn``: it never verifies,
        never updates mastery, never chooses a next problem — it only persists what the surface
        observed (ARCHITECTURE.md §14 invariant 7: "telemetry never blocks a turn"). It is LENIENT
        by contract: an unknown ``session_id`` is NOT an error (the route returns 202 either way);
        we link each event to the session/learner rows IF we can resolve them, and otherwise persist
        with NULL foreign keys rather than dropping the data or 404-ing.

        With no ``session_factory`` (the in-memory demo) this is a no-op returning 0. Otherwise it
        resolves the persisted session-row id + learner-row id for the live session (best-effort,
        swallowing any lookup failure), maps the validated wire events to repository ``EventRow``s,
        and delegates to ``app.events.ingest`` — which opens its own short-lived session, commits
        the batch best-effort, and swallows any failure so a telemetry write can never error the
        client. The returned count is "attempted", not a durability guarantee (invariant 7).
        """
        if self.session_factory is None:
            return 0
        session_row_id, learner_id = self._resolve_event_linkage(request.session_id)
        rows = [_event_row(event) for event in request.events]
        return ingest_events(
            self.session_factory,
            session_id=request.session_id,
            events=rows,
            session_row_id=session_row_id,
            learner_id=learner_id,
        )

    def _resolve_event_linkage(self, session_id: str) -> tuple[int | None, int | None]:
        """Best-effort (session-row, learner-row) ids for a batch; ``(None, None)`` if unknown.

        Telemetry is lenient: if the session is live in memory we already hold its persisted
        ``db_session_id`` (set by ``start`` when a factory is wired); we then resolve the learner
        row id by the opaque external key. Either lookup may come up empty — an event for an
        unknown/restarted session still persists with NULL FKs (the §14 invariant-7 leniency) —
        and any DB hiccup during resolution is swallowed so it can never break ``/events``.
        """
        live = self._sessions.get(session_id)
        db_session_id = live.db_session_id if live is not None else None
        learner_key = live.learner_session_id if live is not None else session_id
        learner_id: int | None = None
        if self.session_factory is not None:
            try:
                with self.session_factory() as db:
                    learner = repo.get_learner(db, learner_key)
                    learner_id = learner.id if learner is not None else None
            except Exception:  # noqa: BLE001 — invariant 7: linkage lookup must not break /events.
                _log.exception("could not resolve learner for events on session %s", session_id)
        return db_session_id, learner_id

    def resume(self, session_id: str) -> _LiveSession | None:
        """Rehydrate a live session from an OPEN DB session after the in-memory one is gone.

        The resume contract for Slice PL.1 is MASTERY-LEVEL (PL.1.2): when a server restart
        has dropped the in-memory ``_LiveSession`` but the client still holds its
        ``session_id`` and the DB Session row is still open, we rebuild a working session
        that CARRIES THE LEARNER'S MASTERY FORWARD — per-KC BKT priors and the confirmed-KC
        set are seeded from the persisted ``MasteryState`` rows, so progress is not lost — and
        serve a FRESH problem in the session's route KC.

        Returns the rehydrated ``_LiveSession`` (also re-registered in the store), or ``None``
        when there is no factory, no open session for the id, or the open session has no
        recoverable route. The exact in-progress problem and the full turn-by-turn history are
        deliberately NOT reconstructed (see ``_rehydrate`` — flagged as a known gap, not a
        hack); "continue at the mastery level / start the next problem fresh" is the accepted
        behavior for this slice.

        Idempotent-ish: if the session is already live in memory we return it as-is rather
        than re-reading the DB.
        """
        if session_id in self._sessions:
            return self._sessions[session_id]
        if self.session_factory is None:
            return None
        live = self._rehydrate(session_id)
        if live is not None:
            self._sessions[session_id] = live
        return live

    def _rehydrate(self, session_id: str) -> _LiveSession | None:
        """Build a mastery-level ``_LiveSession`` from the persisted open session, or ``None``.

        MASTERY-LEVEL RESUME (Slice PL.1.2), the deliberate scope of this slice:

          - We re-find the learner by ``session_id`` and load their ``MasteryState`` rows and
            the open Session row (with its persisted ``route_key``).
          - We rebuild a ``TutorSession`` via ``from_route`` (the same path ``start`` uses), so
            the session's goal KC and a valid current problem come from the single-source-of-
            truth routing table — no fragile reconstruction from stored problem ids.
          - We then SEED the rebuilt session's per-KC BKT priors from the persisted
            ``bkt_probability`` and add every ``confirmed`` KC to the live confirmed set, so the
            learner's earned progress carries forward and a confirmed KC is not re-probed.

        WHAT IS NOT RESTORED (known gap, flagged honestly per the slice brief): the EXACT
        in-progress problem and the full turn-by-turn ``history`` are not reconstructed. Doing
        so cleanly would need a ``TutorSession.from_persisted`` constructor that re-hydrates
        the observation log and counters from stored turns — invasive surgery on the tutor's
        internals (its history is built only by ``submit_answer``). Rather than fake a fragile
        history (which would corrupt the §3.6 counters and the mastery evidence), we serve a
        fresh problem in the route KC and carry mastery forward. Follow-up: add
        ``TutorSession.from_persisted`` to restore exact problem + history when PL.2's full
        event stream lands (it will store the per-turn detail this needs).
        """
        assert self.session_factory is not None
        try:
            with self.session_factory() as db:
                learner = repo.get_learner(db, session_id)
                if learner is None:
                    return None
                open_session = repo.load_open_session_for_learner(db, learner.id)
                if open_session is None or open_session.route_key is None:
                    return None
                states = repo.load_mastery_states(db, learner.id)
                # Read everything we need off the rows while the session is open.
                seeded = {KnowledgeComponentId(s.kc_id): s.bkt_probability for s in states}
                confirmed = {KnowledgeComponentId(s.kc_id) for s in states if s.confirmed}
                route_key = open_session.route_key
                db_session_id = open_session.id
                persisted_turns = len(open_session.turns)
        except Exception:  # noqa: BLE001 — a failed rehydrate degrades to "start fresh", never crashes.
            _log.exception("could not rehydrate session %s; client should start fresh", session_id)
            return None

        tutor = self._tutor_for_route_key(route_key)
        tutor.seed_priors(seeded)
        return _LiveSession(
            tutor=tutor,
            learner_session_id=session_id,
            db_session_id=db_session_id,
            persisted_turn_count=persisted_turns,
            confirmed=confirmed,
            seed_base=_seed_base_from_session_id(session_id),
        )

    def mastery_summary_for_learner(self, learner_id: int) -> list[MasterySnapshot]:
        """The carried-forward per-KC mastery for a persisted learner (Slice PL.3, for /me).

        Reads the learner's persisted ``MasteryState`` rows (the PL.1 store) and projects each
        to the wire ``MasterySnapshot`` with ``mastered`` meaning CONFIRMED — the same "earned
        mastery, not bare provisional" contract the live snapshot uses (PROJECT.md §3.4): a row's
        ``confirmed`` flag is the S5-probe verdict that survived persistence. This is the auth
        path's read-only continuity view (the "same login → same state" proof); it is OFF the
        turn loop and never feeds a decision. Returns ``[]`` when there is no factory or the
        learner has no recorded mastery yet.
        """
        if self.session_factory is None:
            return []
        with self.session_factory() as db:
            states = repo.load_mastery_states(db, learner_id)
            return [
                MasterySnapshot(
                    kc_id=KnowledgeComponentId(s.kc_id),
                    probability=s.bkt_probability,
                    mastered=s.confirmed,
                )
                for s in states
            ]

    def _reviewable_skills_for_learner(self, learner_id: int) -> list[ReviewableSkill]:
        """Project a learner's persisted ``MasteryState`` rows → the retention model's inputs.

        Shared by the study planner and the course map (both read the same per-skill state). One
        entry per touched KC; an empty list when there is no factory or no recorded mastery yet.
        """
        if self.session_factory is None:
            return []
        with self.session_factory() as db:
            states = repo.load_mastery_states(db, learner_id)
        return [
            ReviewableSkill(
                kc=KnowledgeComponentId(s.kc_id),
                confirmed=s.confirmed,
                bkt_probability=s.bkt_probability,
                # SQLite returns naive datetimes (PL.1 note); coerce to UTC so the elapsed-time
                # math compares like-with-like against the aware ``now`` the caller passes.
                last_practiced=s.updated_at
                if s.updated_at.tzinfo is not None
                else s.updated_at.replace(tzinfo=UTC),
            )
            for s in states
        ]

    def study_plan_for_learner(self, learner_id: int, now: datetime) -> StudyPlanView:
        """What a returning learner should do next — spaced repetition + prereq sequencing (6.x).

        Reads the learner's persisted ``MasteryState`` rows (PL.1) and runs the study planner:
        confirmed skills whose retention has decayed since ``updated_at`` surface as DUE REVIEWS
        (the cross-session spacing — this is where it actually has effect, a single session has no
        gap), and the next prerequisite-unlocked skill is suggested. Off the turn loop, advisory
        only — identity/sequencing never feeds a turn decision (invariant 8/9). Returns an empty
        plan when there is no factory or no recorded mastery.
        """
        if self.session_factory is None:
            return StudyPlanView()
        plan = plan_study(self._reviewable_skills_for_learner(learner_id), now)
        return StudyPlanView(
            due_reviews=[kc.value for kc in plan.due_reviews],
            unlocked_next=[kc.value for kc in plan.unlocked_next],
            recommended=plan.recommended.value if plan.recommended is not None else None,
        )

    @staticmethod
    def _course_view(skills: list[ReviewableSkill], now: datetime) -> CourseView:
        """Build the wire ``CourseView`` from a learner's per-skill state (Slice CP.A.1).

        Runs the pure ``build_course_map`` and attaches each KC's registry name/description for
        display. Shared by the persisted (signed-in) and the live-session (anonymous demo) maps,
        so the two sources produce the identical shape. Always returns the full catalog.
        """
        nodes = build_course_map(skills, now)
        return CourseView(
            nodes=[
                CourseNodeView(
                    kc_id=node.kc,
                    skill_name=get_kc(node.kc).skill_name,
                    description=get_kc(node.kc).description,
                    status=node.status,
                    prerequisites=list(node.prerequisites),
                    probability=node.probability,
                )
                for node in nodes
            ]
        )

    def course_map_for_learner(self, learner_id: int, now: datetime) -> CourseView:
        """A SIGNED-IN learner's learning path with a status per KC (Slice CP.A.1 — course product).

        The course-product home screen (PROJECT.md §3.13): a pure composition of the existing
        engine — the prerequisite graph + the learner's persisted mastery + the retention model —
        with NO new mastery logic. Reads the same ``MasteryState`` rows the study planner does.
        Always returns the full catalog (even with no factory: a fresh path with the root
        available, the rest locked). Off the turn loop, advisory only (invariant 8/9).
        """
        return self._course_view(self._reviewable_skills_for_learner(learner_id), now)

    def course_map_for_session(self, session_id: str | None, now: datetime) -> CourseView:
        """An ANONYMOUS demo learner's learning path, from their in-memory session (Slice CP.A.2).

        The "Student Demo Free" path has no account, so its progress lives only in the live
        ``_LiveSession`` (the v1 session-id flow, TECH_STACK §9), not in persisted rows. We roll
        that session's history up (``_mastery_rollup`` — the same per-KC BKT + confirmed readout
        the persistence layer uses) and project it into the retention model's inputs, then build
        the same map. An unknown / ``None`` ``session_id`` (a brand-new demo learner who hasn't
        started yet) yields the fresh default path (root available, the rest locked) rather than
        an error — so the home screen always renders.

        ``last_practiced`` is set to ``now``: a single live session has no real time gap to decay
        over, so nothing shows ``due_review`` in-session — honest, and consistent with the
        retention model's "spacing needs a real gap across sessions" note. Read-only, off the turn
        loop; the session identity never feeds a turn decision (invariant 8).
        """
        live = self._sessions.get(session_id) if session_id is not None else None
        if live is None:
            return self._course_view([], now)
        skills = [
            ReviewableSkill(
                kc=row.kc,
                confirmed=row.confirmed,
                bkt_probability=row.bkt_probability,
                last_practiced=now,
            )
            for row in _mastery_rollup(live)
        ]
        return self._course_view(skills, now)

    def _reviewable_skills_for_session(
        self, session_id: str | None, now: datetime
    ) -> list[ReviewableSkill]:
        """Roll an ANONYMOUS demo session's in-memory history up into retention inputs.

        Mirrors the skill construction in :meth:`course_map_for_session`: the demo learner's
        progress lives only in the live ``_LiveSession`` (the v1 session-id flow, TECH_STACK §9),
        so we roll its history up (``_mastery_rollup`` — the same per-KC BKT + confirmed readout
        the persistence layer uses) and project it into the retention model's inputs. An unknown /
        ``None`` ``session_id`` (a brand-new demo learner) yields ``[]`` — the empty/default path.

        ``last_practiced`` is ``now``: a single live session has no real time gap to decay over
        (consistent with the retention model's "spacing needs a real cross-session gap" note).
        """
        live = self._sessions.get(session_id) if session_id is not None else None
        if live is None:
            return []
        return [
            ReviewableSkill(
                kc=row.kc,
                confirmed=row.confirmed,
                bkt_probability=row.bkt_probability,
                last_practiced=now,
            )
            for row in _mastery_rollup(live)
        ]

    # -- units (the unit/lesson shell — Slices DAT.8 / DAT.9 / DAT.10) ----------

    def units_for_learner(self, learner_id: int, now: datetime) -> UnitListView:
        """A SIGNED-IN learner's unit list with rolled-up progress + assignment (DAT.8/DAT.10).

        Derives the unit list from the CATALOG + the course map + ``build_unit_progress`` (NOT
        the DB ``unit`` rows), so it returns the full curriculum even with no DB — exactly like
        :meth:`course_map_for_learner`. The teacher-assigned unit (if any) is resolved via the
        assignment repository and surfaced as ``assigned_unit_slug`` plus ``assigned=True`` on the
        matching unit. A pure composition of existing engine state, no new mastery logic
        (PROJECT.md §3.13); off the turn loop, advisory only (invariant 8/9).
        """
        skills = self._reviewable_skills_for_learner(learner_id)
        assigned_slug = self._assigned_unit_slug(learner_id)
        return self._unit_list_view(skills, now, assigned_slug=assigned_slug)

    def units_for_session(self, session_id: str | None, now: datetime) -> UnitListView:
        """An ANONYMOUS demo learner's unit list, from their in-memory session (DAT.8).

        Mirrors :meth:`course_map_for_session`: the unit list is derived from the catalog + the
        session's rolled-up in-memory mastery. Anonymous callers have no teacher assignment, so
        ``assigned`` is ``False`` on every unit and ``assigned_unit_slug`` is ``None``. An unknown
        / ``None`` ``session_id`` yields the fresh default unit list (so the shell always renders).
        """
        skills = self._reviewable_skills_for_session(session_id, now)
        return self._unit_list_view(skills, now, assigned_slug=None)

    def unit_detail_for_learner(
        self, unit_slug: str, learner_id: int, now: datetime
    ) -> UnitDetailView | None:
        """A SIGNED-IN learner's single-unit detail — lessons + per-lesson progress (DAT.9).

        Same derivation as :meth:`units_for_learner` but for one unit. Returns ``None`` when
        ``unit_slug`` is not in the catalog, so the route can respond with a 404.
        """
        skills = self._reviewable_skills_for_learner(learner_id)
        assigned_slug = self._assigned_unit_slug(learner_id)
        return self._unit_detail_view(unit_slug, skills, now, assigned_slug=assigned_slug)

    def unit_detail_for_session(
        self, unit_slug: str, session_id: str | None, now: datetime
    ) -> UnitDetailView | None:
        """An ANONYMOUS demo learner's single-unit detail, or None (DAT.9).

        Same derivation as :meth:`units_for_session` but for one unit (no assignment). Returns
        ``None`` when ``unit_slug`` is not in the catalog, so the route can respond with a 404.
        """
        skills = self._reviewable_skills_for_session(session_id, now)
        return self._unit_detail_view(unit_slug, skills, now, assigned_slug=None)

    def _assigned_unit_slug(self, learner_id: int) -> str | None:
        """The learner's teacher-assigned unit slug, or ``None`` (DAT.10).

        Reads the assignment via the assignment repository (the ONLY place a DB query lives,
        CLAUDE.md §7) and resolves the assigned ``unit_id`` to the DB ``Unit`` row's slug — that
        slug is the same stable key the catalog uses, so it matches a ``UnitView.unit_slug``.
        Returns ``None`` when there is no session factory (the pure in-memory demo, so no DB to
        read an assignment from), no current assignment, or the assigned unit row is missing.
        """
        if self.session_factory is None:
            return None
        with self.session_factory() as db:
            assignment = repo.get_assigned_unit(db, learner_id)
            if assignment is None:
                return None
            unit = db.get(Unit, assignment.unit_id)
            return unit.slug if unit is not None else None

    @staticmethod
    def _unit_progress(skills: list[ReviewableSkill], now: datetime) -> tuple[UnitProgress, ...]:
        """Derive per-unit progress from the catalog + the course map (DAT.6 bridge).

        Built from the catalog (``all_units``) and the course map (``build_course_map`` over the
        learner's per-skill state), then overlaid by ``build_unit_progress`` — so the unit list
        works for the anonymous demo learner with no DB, exactly like :meth:`_course_view`. The
        confirmed-KC set used for unit gating is the same the course map derives.
        """
        nodes = build_course_map(skills, now)
        confirmed = frozenset(s.kc for s in skills if s.confirmed)
        return build_unit_progress(all_units(), nodes, confirmed)

    def _unit_list_view(
        self,
        skills: list[ReviewableSkill],
        now: datetime,
        *,
        assigned_slug: str | None,
    ) -> UnitListView:
        """Map a learner's per-skill state to the wire ``UnitListView`` (DAT.8).

        Shared by the persisted (signed-in) and the live-session (anonymous) lists, so the two
        sources produce the identical shape. Always returns every catalog unit in teaching order.
        """
        catalog_by_slug = {unit.slug: unit for unit in all_units()}
        units = [
            self._unit_view(up, catalog_by_slug[up.unit_slug], assigned_slug=assigned_slug)
            for up in self._unit_progress(skills, now)
        ]
        return UnitListView(units=units, assigned_unit_slug=assigned_slug)

    def _unit_detail_view(
        self,
        unit_slug: str,
        skills: list[ReviewableSkill],
        now: datetime,
        *,
        assigned_slug: str | None,
    ) -> UnitDetailView | None:
        """Map a learner's per-skill state to one unit's ``UnitDetailView``, or ``None`` (DAT.9).

        Returns ``None`` when ``unit_slug`` is not in the catalog (``get_unit`` raises
        ``KeyError`` for an unknown slug) so the route 404s, and defensively when the slug has no
        matching ``UnitProgress`` entry.
        """
        try:
            catalog_unit = get_unit(unit_slug)
        except KeyError:
            return None
        unit_progress = next(
            (up for up in self._unit_progress(skills, now) if up.unit_slug == unit_slug),
            None,
        )
        if unit_progress is None:
            return None
        return self._unit_detail(unit_progress, catalog_unit, assigned_slug=assigned_slug)

    @staticmethod
    def _unit_view(
        unit_progress: UnitProgress,
        catalog_unit: CatalogUnit,
        *,
        assigned_slug: str | None,
    ) -> UnitView:
        """Project a ``UnitProgress`` + its ``CatalogUnit`` to the wire ``UnitView``.

        Titles / description / cluster codes come from the catalog; ``status`` /
        ``percent_complete`` / ``lesson_count`` from the rolled-up progress. ``percent_complete``
        is scaled from the overlay's ``[0, 1]`` fraction to the wire's ``[0, 100]`` percent.
        """
        return UnitView(
            unit_slug=unit_progress.unit_slug,
            title=catalog_unit.title,
            description=catalog_unit.description,
            order=catalog_unit.order,
            ccss_cluster=catalog_unit.ccss_cluster,
            teks_cluster=catalog_unit.teks_cluster,
            status=unit_progress.status,
            percent_complete=unit_progress.percent_complete * 100.0,
            lesson_count=len(unit_progress.lessons),
            assigned=unit_progress.unit_slug == assigned_slug,
        )

    @staticmethod
    def _unit_detail(
        unit_progress: UnitProgress,
        catalog_unit: CatalogUnit,
        *,
        assigned_slug: str | None,
    ) -> UnitDetailView:
        """Project a ``UnitProgress`` + its ``CatalogUnit`` to the wire ``UnitDetailView``.

        The unit-card fields (as in :meth:`_unit_view`) plus per-lesson ``LessonView``s: lesson
        titles + dual-coverage codes come from the catalog (matched by slug), and per-lesson
        status + probability from the rolled-up ``LessonProgress``. The two are zipped in catalog
        order — ``build_unit_progress`` preserves the catalog's lesson order — so a positional join
        is exact; we still index the catalog by slug to be robust to ordering.
        """
        catalog_lessons = {lesson.slug: lesson for lesson in catalog_unit.lessons}
        lessons = [
            LessonView(
                lesson_slug=lp.lesson_slug,
                title=catalog_lessons[lp.lesson_slug].title,
                kc_id=lp.kc_id,
                ccss_code=catalog_lessons[lp.lesson_slug].ccss_code,
                teks_code=catalog_lessons[lp.lesson_slug].teks_code,
                status=lp.status,
                probability=lp.probability,
            )
            for lp in unit_progress.lessons
        ]
        return UnitDetailView(
            unit_slug=unit_progress.unit_slug,
            title=catalog_unit.title,
            description=catalog_unit.description,
            order=catalog_unit.order,
            ccss_cluster=catalog_unit.ccss_cluster,
            teks_cluster=catalog_unit.teks_cluster,
            status=unit_progress.status,
            percent_complete=unit_progress.percent_complete * 100.0,
            lesson_count=len(unit_progress.lessons),
            assigned=unit_progress.unit_slug == assigned_slug,
            lessons=lessons,
        )

    def prior_for(self, session_id: str, kc: KnowledgeComponentId) -> float | None:
        """The seeded BKT prior for ``kc`` in a live session, or ``None`` if unknown.

        A thin read used by the resume path's callers (and tests) to confirm a rehydrated
        session carried persisted mastery forward, without reaching into ``_LiveSession``.
        """
        live = self._sessions.get(session_id)
        if live is None:
            return None
        return live.tutor.prior_for(kc)


__all__ = [
    "SessionNotFoundError",
    "SessionStore",
    "UnknownRouteError",
    "routing_menu",
]
