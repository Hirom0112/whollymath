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

from app.api.live_adaptation import propose_adaptation_view
from app.api.remediation_view import build_remediation_view
from app.api.schemas import (
    AbsoluteValueView,
    ActionType,
    CourseNodeView,
    CourseView,
    DecimalPlaceValueRowView,
    DecimalPlaceValueView,
    DotPlotStimulusView,
    ErrorType,
    EventBatchRequest,
    ExponentProductView,
    FractionAreaView,
    FractionOperandView,
    FrequencyRowView,
    FrequencyTableStimulusView,
    GcfFactorsView,
    HistogramBinView,
    HistogramStimulusView,
    IntegerJumpView,
    InteractionEventIn,
    InterventionKind,
    InterventionView,
    LessonView,
    MasterySnapshot,
    PercentGridView,
    ProblemView,
    PromptPartsView,
    RatioTableColumnView,
    RatioTableView,
    RouteOptionView,
    SceneView,
    SetModelGroupView,
    SetModelStimulusView,
    SignedPointView,
    SpokenAudio,
    StartSessionResponse,
    StatsStimulusView,
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
from app.domain.decimal_place_value_stimulus import DecimalPlaceValueStimulus
from app.domain.exponent_product_stimulus import ExponentProductStimulus
from app.domain.fraction_area_stimulus import FractionAreaStimulus
from app.domain.gcf_factors_stimulus import GcfFactorsStimulus
from app.domain.integer_line_stimulus import (
    AbsoluteValueStimulus,
    IntegerJumpStimulus,
    SignedPointStimulus,
)
from app.domain.knowledge_components import (
    FOUNDATION_KCS,
    KnowledgeComponentId,
    Representation,
    get_kc,
)
from app.domain.lesson_spec import widget_for_representation
from app.domain.misconceptions import MisconceptionId, get_misconception
from app.domain.percent_grid_stimulus import PercentGridStimulus
from app.domain.problem_generators import Problem
from app.domain.ratio_table_stimulus import RatioTableStimulus
from app.domain.scene import Scene, scene_for
from app.domain.set_model_stimulus import SetModelStimulus, set_model_for
from app.domain.stats_stimulus import (
    DotPlotStimulus,
    FrequencyTableStimulus,
    HistogramStimulus,
    StatsStimulus,
    stimulus_for,
)
from app.domain.verifier import verify
from app.events.ingest import ingest_events
from app.helpneed.events_features import build_episodes
from app.helpneed.live_features import LiveTurn, live_features
from app.helpneed.live_signal_features import compute_live_features
from app.helpneed.predictor import HelpNeedPredictor
from app.llm.provider import LLMProvider
from app.mastery.course_map import build_course_map
from app.mastery.mastery_model import Observation
from app.mastery.progression import plan_study
from app.mastery.retention import ReviewableSkill
from app.mastery.unit_progress import UnitProgress, build_unit_progress
from app.persona_surface.misconception_voice import voice_misconception_nudge
from app.persona_surface.tutor_voice import voice_help
from app.policy.emotion import MomentType, select_emotion
from app.policy.intervention_gate import SustainedHelpNeedGate
from app.policy.mid_problem_help import should_offer_mid_problem_help
from app.policy.remediation_flow import (
    LessonFlow,
    LessonFlowState,
    RemediationCleared,
    RemediationContext,
    RemediationTriggered,
    in_lesson,
)
from app.policy.remediation_flow import (
    apply as apply_remediation,
)
from app.policy.remediation_router import select_remediation_target
from app.policy.scheduler import (
    difficulty_for,
    is_masterable_live,
    live_representations,
    next_spec_after_outcome,
)
from app.policy.state_classifier import classify_state
from app.tts.live_synth import synthesize_live
from app.tts.manifest_lookup import audio_url_for, lookup_audio
from app.tts.provider import Locale
from app.tts.spoken_bank import nudge_string_id
from app.tutor.hints import HintLevel, build_validated_hint, select_nudge
from app.tutor.hints_es import es_mx_text
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


def _stats_stimulus_view(stimulus: StatsStimulus | None) -> StatsStimulusView | None:
    """Project a domain ``StatsStimulus`` to its answer-free wire view, or ``None``.

    A pure shape projection of already-decided data (no SymPy, no answer — §8.2): the domain
    stimulus carries only the data set the prompt already lists, so the wire view does too.
    """
    if stimulus is None:
        return None
    if isinstance(stimulus, DotPlotStimulus):
        return DotPlotStimulusView(values=list(stimulus.values), axis_label=stimulus.axis_label)
    if isinstance(stimulus, FrequencyTableStimulus):
        return FrequencyTableStimulusView(
            rows=[FrequencyRowView(label=label, count=count) for label, count in stimulus.rows],
            category_label=stimulus.category_label,
            count_label=stimulus.count_label,
        )
    if isinstance(stimulus, HistogramStimulus):
        return HistogramStimulusView(
            bins=[HistogramBinView(lo=lo, hi=hi, count=count) for lo, hi, count in stimulus.bins],
            bin_width=stimulus.bin_width,
            axis_label=stimulus.axis_label,
        )
    return None  # pragma: no cover — the union above is exhaustive


def _set_model_view(stimulus: SetModelStimulus | None) -> SetModelStimulusView | None:
    """Project a domain ``SetModelStimulus`` to its answer-free wire view, or ``None``.

    A pure shape projection of already-decided data (no SymPy, no answer — §8.2): the counter
    collection the prompt already names, nothing more.
    """
    if stimulus is None:
        return None
    return SetModelStimulusView(
        groups=[SetModelGroupView(colour=colour, count=count) for colour, count in stimulus.groups],
        asked_colour=stimulus.asked_colour,
    )


def _scene_view(scene: Scene | None) -> SceneView | None:
    """Project a domain ``Scene`` to its answer-free wire view, or ``None``.

    A pure shape projection of already-decided operand data (no SymPy, no answer — §8.2). One arm
    per scene kind, mirroring the domain dataclass field-for-field.
    """
    if scene is None:
        return None
    if isinstance(scene, PercentGridStimulus):
        return PercentGridView(percent=scene.percent, shaded=scene.shaded)
    if isinstance(scene, RatioTableStimulus):
        return RatioTableView(
            top_label=scene.top_label,
            bottom_label=scene.bottom_label,
            columns=[RatioTableColumnView(top=c.top, bottom=c.bottom) for c in scene.columns],
            scale_label=scene.scale_label,
        )
    if isinstance(scene, IntegerJumpStimulus):
        return IntegerJumpView(
            axis_min=scene.axis_min, axis_max=scene.axis_max, start=scene.start, delta=scene.delta
        )
    if isinstance(scene, AbsoluteValueStimulus):
        return AbsoluteValueView(
            axis_min=scene.axis_min, axis_max=scene.axis_max, point=scene.point
        )
    if isinstance(scene, SignedPointStimulus):
        return SignedPointView(
            axis_min=scene.axis_min, axis_max=scene.axis_max, points=list(scene.points)
        )
    if isinstance(scene, FractionAreaStimulus):
        return FractionAreaView(
            op=scene.op,
            first=FractionOperandView(
                numerator=scene.first.numerator, denominator=scene.first.denominator
            ),
            second=FractionOperandView(
                numerator=scene.second.numerator, denominator=scene.second.denominator
            ),
        )
    if isinstance(scene, DecimalPlaceValueStimulus):
        return DecimalPlaceValueView(
            columns=list(scene.columns),
            point_after=scene.point_after,
            rows=[
                DecimalPlaceValueRowView(decimal_text=r.decimal_text, digits=list(r.digits))
                for r in scene.rows
            ],
        )
    if isinstance(scene, GcfFactorsStimulus):
        return GcfFactorsView(
            mode=scene.mode,
            first=scene.first,
            second=scene.second,
            first_factors=list(scene.first_factors),
            second_factors=list(scene.second_factors),
        )
    if isinstance(scene, ExponentProductStimulus):
        return ExponentProductView(
            base=scene.base, exponent=scene.exponent, factors=list(scene.factors)
        )
    return None  # pragma: no cover — the union above is exhaustive


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
        widget_id=widget_for_representation(problem.surface_format, problem.kc).value,
        statement=problem.statement,
        answer_kind=problem.answer_kind,
        yes_no_relation=problem.yes_no_relation,
        tick_segments=int(problem.correct_value.q) if is_number_line else None,
        axis_min=axis_min,
        axis_max=axis_max,
        given_denominator=problem.given_denominator,
        stimulus=_stats_stimulus_view(stimulus_for(problem.kc, problem.operands)),
        set_model=_set_model_view(set_model_for(problem.kc, problem.operands)),
        prompt_parts=(
            PromptPartsView(
                situation=problem.prompt_parts.situation,
                question=problem.prompt_parts.question,
                guiding_rule=problem.prompt_parts.guiding_rule,
            )
            if problem.prompt_parts is not None
            else None
        ),
        scene=_scene_view(scene_for(problem.kc, problem.operands)),
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


def _localized_nudge_text(kc: KnowledgeComponentId, index: int, locale: Locale) -> str:
    """The canonical nudge text for ``kc`` at ``index`` in ``locale`` — English, or its es-MX line.

    The locale seam for help TEXT (Slice 3.6 bilingual scaffold). English ('en') returns the banked
    English nudge (``select_nudge`` — the single source of truth for the text); 'es-MX' returns the
    parallel Mexican-Spanish line keyed by the SAME canonical ``string_id`` (``es_mx_text`` over the
    reviewed es-MX bank, ``tutor/hints_es``). When no es-MX entry exists for the id we fall back to
    the English nudge so a gap voices *something* rather than crashing — mirroring
    ``spoken_bank.text_for_locale``. No LLM/SymPy here: a banked-string lookup (§8.1). The English
    branch is byte-for-byte the pre-Slice-3.6 behavior (locale defaults to 'en')."""
    english = select_nudge(kc, index=index).text
    if locale != "en":
        translated = es_mx_text(nudge_string_id(kc.value, index))
        if translated is not None:
            return translated
    return english


def _nudge_audio(kc_value: str, index: int = 0, *, locale: Locale = "en") -> SpokenAudio | None:
    """Cached audio + lip-sync timing for the canonical nudge at ``index`` of ``kc_value``, or None.

    The canonical-line bridge (Slice AR.3): a help moment selects a banked nudge (``select_nudge``,
    default index 0), and IF that exact canonical line was pre-rendered IN ``locale``
    (``manifest_lookup`` keyed ``<string_id>|<locale>``), the surface can speak it. Returns a
    ``SpokenAudio`` referencing the served mp3 + word timings, or ``None`` when no audio exists for
    the line in that locale (the common case — only a few lines are rendered, and es-MX audio is
    not rendered yet, so 'es-MX' resolves to ``None`` and the existing caption-only fallback holds).

    A caller that attaches this MUST also ship the CANONICAL caption (the banked nudge text in the
    same locale), not an LLM rephrase, so the spoken words and the on-screen words match (the
    SpokenAudio invariant). Off the turn-loop decision path: a single cached-manifest dict lookup,
    no LLM/SymPy/network (§8.1). ``locale`` defaults to 'en' so the English path is unchanged.
    """
    entry = lookup_audio(nudge_string_id(kc_value, index), locale=locale)
    if entry is None:
        return None
    audio_file = entry.get("audio_file")
    words = entry.get("words")
    wtimes = entry.get("wtimes")
    wdurations = entry.get("wdurations")
    # A well-formed manifest row carries all four; a malformed/partial row degrades to silent
    # rather than shipping a broken ref (invariant 4 — voicing never breaks a help moment).
    if (
        not isinstance(audio_file, str)
        or not isinstance(words, list)
        or not isinstance(wtimes, list)
        or not isinstance(wdurations, list)
    ):
        return None
    return SpokenAudio(
        audio_url=audio_url_for(audio_file),
        words=[str(w) for w in words],
        wtimes=[float(t) for t in wtimes],
        wdurations=[float(d) for d in wdurations],
    )


def _live_audio(text: str, locale: Locale) -> SpokenAudio | None:
    """Voice a DYNAMIC help line (no banked clip) via serve-time live synth, or ``None``.

    The fallback that makes LLM-rephrased / number-templated help lines TALK instead of staying
    captions-only (owner 2026-06-04): ``synthesize_live`` voices the EXACT shown ``text`` in
    Hope and content-hash caches it (so a repeat is free), returning a ref this maps onto the
    ``SpokenAudio`` wire model. ``None`` (captions-only) when synth is disabled, keyless, or fails —
    it never raises into the turn (invariant 4). Off the graded loop (§8.1): only called on a help
    moment, after the verdict. The caller passes the verbatim shown text so the mouth matches the
    bubble (the SpokenAudio invariant).
    """
    live = synthesize_live(text, locale=locale)
    if live is None:
        return None
    return SpokenAudio(
        audio_url=live.audio_url,
        words=live.words,
        wtimes=live.wtimes,
        wdurations=live.wdurations,
    )


def _maybe_intervene(
    live: _LiveSession,
    gate: SustainedHelpNeedGate,
    next_problem: Problem,
    voice_provider: LLMProvider | None,
    locale: Locale = "en",
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
    # Tier-2 weak-KC guard (T1_T2_COORDINATION §"Tier-2"): the arm may fire only when the
    # sustained signal trips AND the upcoming problem's KC is one the predictor is validated
    # trustworthy on. On a guarded (weak/unvalidated) KC this returns False and the turn is
    # left to the deterministic reactive layer — we never give a low-confidence proactive
    # nudge. With no trustworthy set configured this is exactly the old window check.
    if not gate.should_intervene_for_kc(live.help_need_history, kc=next_problem.kc.value):
        return None
    # A help moment: voice the pre-written nudge in the mascot's voice (Slice 5.5.2), or
    # return it verbatim if voicing is disabled/fails (invariant 4). The LLM only rephrases
    # an already-decided nudge — it never decides whether to intervene (§8.1).
    nudge_text = _localized_nudge_text(next_problem.kc, 0, locale)
    # If the canonical nudge has cached audio IN THIS LOCALE, speak it — and show the CANONICAL
    # caption (not the LLM rephrase) so the spoken words match the bubble (the SpokenAudio
    # invariant). es-MX audio is not rendered yet, so 'es-MX' resolves to None → captions-only.
    audio = _nudge_audio(next_problem.kc.value, locale=locale)
    # The mascot voices the already-decided nudge in the learner's help-locale: voice_help picks
    # the English or es-MX rephrase prompt deterministically from ``locale`` (Slice 3.4), so the
    # LLM only ever rephrases — never decides language, correctness, or whether to intervene
    # (§8.1/§8.3). With audio present we keep the canonical caption (mouth/bubble match); with no
    # provider the rephrase falls back to the verbatim nudge (invariant 4). es-MX has no rendered
    # audio yet, so it is captions-only.
    voiced = voice_help(
        nudge_text, moment=MomentType.STUCK_NUDGE, provider=voice_provider, locale=locale
    )
    return InterventionView(
        kind=InterventionKind.INLINE_ASSERTION,
        text=nudge_text if audio is not None else voiced.text,
        emotion=voiced.emotion,
        intensity=voiced.intensity,
        audio=audio,
    )


# How many recent turns the live-adaptation representation-diversity read spans (HR.B4 Beat 3).
_ADAPT_REP_WINDOW = 5


def _streak_and_distinct_reps(session: TutorSession) -> tuple[int, int]:
    """The unassisted correct streak + distinct recent representations, from the session history.

    The two session facts the live state classifier (HR.B2) needs beyond the behavioral window —
    they separate fluent-ready (a clean streak across ≥2 representations) from pattern-matching (a
    streak stuck in one). Both read from ``history`` (each turn's ``Observation``), so the
    classifier stays a pure function of values the caller hands it.
    """
    streak = 0
    for turn in reversed(session.history):
        if turn.observation.correct and not turn.observation.hinted:
            streak += 1
        else:
            break
    recent = session.history[-_ADAPT_REP_WINDOW:]
    return streak, len({turn.observation.representation for turn in recent})


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
        # §11.4 hard gate: if this confirmed KC is a NESTED PREREQUISITE lesson (we are in
        # remediation), mastering it CLEARS the gate — resume the paused parent at its paused index
        # instead of finishing (the parent is not done). The remediation panel goes away (flow →
        # IN_LESSON) and the next problem is the parent's. Otherwise this is an ordinary lesson
        # completion (CP.B bounded-lesson terminal state).
        if live.flow.state is LessonFlowState.IN_REMEDIATION:
            resumed = _resume_parent(live)
            return TurnResponse(
                correct=True,
                error_type=ErrorType.NONE,
                next_surface_state=live.tutor.surface_state,
                feedback="Great — basic shored up. Back to where you left off.",
                hint=None,
                mastery=_probe_mastery_view(live.tutor, live, live.tutor.history[0].observation.kc),
                help_need=None,
                intervention=None,
                next_problem=_problem_view(resumed),
            )
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


def _reason_label(prerequisite_kc: KnowledgeComponentId) -> str:
    """The §11.5 on-screen drop label, naming the prerequisite ('shore up a basic first: …').

    Mirrors the labelling discipline of the §3.8 refuse-rule 4 (every adaptation carries a reason)
    and the example in CURRICULUM_STANDARD.md §11.5. Plain, pre-written text — no LLM (§8.1)."""
    return f"Let's shore up a basic first: {get_kc(prerequisite_kc).skill_name}."


def _begin_remediation(
    live: _LiveSession, parent_kc: KnowledgeComponentId, prerequisite_kc: KnowledgeComponentId
) -> Problem:
    """Pause the parent lesson and start the nested prerequisite lesson (CURRICULUM_STANDARD §11).

    Snapshots the ACTIVE (parent) lesson into ``live.paused_parent`` — its tutor, HelpNeed stream,
    S5-probe progress, confirmed set, hint counter, and the resume index (the parent's served
    count) — then resets those fields and swaps in a FRESH ``TutorSession`` for the prerequisite
    KC (the same bounded-lesson construct ``start_kc`` uses; §11.6 item 2). It routes the ``flow``
    to the "R" state via the committed ``remediation_flow.apply`` carrying the resolved context, so
    the surface projection (``build_remediation_view``) lights up. Returns the prereq lesson's first
    problem — what the caller serves in place of the parent's next problem.

    The parent PAUSES, never resets (§11.4): everything needed to resume it exactly is in the
    snapshot. Pure restructuring of in-memory state — no SymPy/LLM/DB on this path (§8.1/§8.2)."""
    paused_at_index = len(live.tutor.history)
    live.paused_parent = _PausedParent(
        tutor=live.tutor,
        help_need_history=live.help_need_history,
        probe_steps=live.probe_steps,
        probe_index=live.probe_index,
        confirmed=live.confirmed,
        probe_cooldown=live.probe_cooldown,
        hints_this_problem=live.hints_this_problem,
        paused_at_index=paused_at_index,
    )
    # Fresh active-lesson state for the nested prereq lesson (started like any goal-KC lesson).
    surface_format = live_representations(prerequisite_kc)[0]
    live.tutor = TutorSession.for_goal_kc(
        prerequisite_kc, surface_format=surface_format, seed=live.seed_base
    )
    live.help_need_history = []
    live.probe_steps = []
    live.probe_index = 0
    live.confirmed = set()
    live.probe_cooldown = 0
    live.hints_this_problem = 0
    context = RemediationContext(
        parent_kc=parent_kc,
        prerequisite_kc=prerequisite_kc,
        paused_at_index=paused_at_index,
        reason=_reason_label(prerequisite_kc),
    )
    live.flow = apply_remediation(live.flow, RemediationTriggered(context=context))
    return live.tutor.current_problem


def _maybe_remediate(
    live: _LiveSession, gate: SustainedHelpNeedGate, served_parent_problem: Problem
) -> Problem | None:
    """If sustained struggle should drop the learner one level, pause and return the prereq problem.

    The §11.2 trigger is the EXISTING §3.7 sustained-help ``gate`` firing on the accumulated
    HelpNeed stream (``live.help_need_history``) — the same signal the proactive arm uses; this
    invents no new trigger and is NOT gated on the proactive A/B arm (remediation is a core
    curriculum behavior, not an experiment). It fires only when ALL of: the gate trips, the learner
    is currently IN_LESSON (one level only — §11.1: a learner already in remediation STAYS and works
    the prereq, no nested drop), and the active lesson's KC has a routed prerequisite the §11.3
    selector picks (terminal foundation KCs return None — no drop). That selector reads the live
    per-KC BKT mastery and the last turn's error category to choose WHICH prereq (error-category
    bias + lowest mastery).

    Returns the prerequisite lesson's first problem (and pauses the parent) when it fires, else None
    (the caller keeps serving ``served_parent_problem``). Off the sub-100ms decision path — it runs
    after the turn is graded and the next problem already chosen, like the proactive read (§8.1)."""
    if live.flow.state is not LessonFlowState.IN_LESSON:
        return None  # one level only (§11.1) — already remediating
    if not gate.should_intervene(live.help_need_history):
        return None
    parent_kc = live.tutor.history[0].observation.kc
    last_error = live.tutor.history[-1].result.error_category
    mastery = {kc: live.tutor.mastery_probability(kc) for kc in KnowledgeComponentId}
    target = select_remediation_target(parent_kc, error_category=last_error, mastery=mastery)
    if target is None:
        return None  # terminal foundation KC — no drop (§11.1)
    return _begin_remediation(live, parent_kc, target)


def _resume_parent(live: _LiveSession) -> Problem:
    """Clear remediation and resume the paused parent lesson where it paused (§11.4 gate passed).

    Called when the nested prerequisite lesson has been MASTERED (its goal KC CONFIRMED by the S5
    probe — the existing "must master to unlock" bar, one level down). Restores the parent-lesson
    snapshot verbatim (tutor, HelpNeed stream, probe progress, confirmed set, hint counter) so the
    parent continues at the exact problem it paused on (§11.4: pauses, never resets), routes the
    ``flow`` back to IN_LESSON via the committed ``RemediationCleared`` edge, and serves the
    parent's NEXT problem via the normal scheduler. Returns that resumed parent problem."""
    snapshot = live.paused_parent
    assert snapshot is not None, "resume requires a paused parent (begin_remediation set it)"
    live.tutor = snapshot.tutor
    live.help_need_history = snapshot.help_need_history
    live.probe_steps = snapshot.probe_steps
    live.probe_index = snapshot.probe_index
    live.confirmed = snapshot.confirmed
    live.probe_cooldown = snapshot.probe_cooldown
    live.hints_this_problem = snapshot.hints_this_problem
    live.paused_parent = None
    live.flow = apply_remediation(live.flow, RemediationCleared())
    return _serve_next(live)


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
    # §11 reactive remediation: with the HelpNeed score now on the stream, the §3.7 sustained gate
    # may trip. If it does (and we are IN_LESSON on a KC with a routed prerequisite), PAUSE the
    # parent and serve the nested prerequisite lesson's first problem instead of the parent's next.
    # Read off the settled turn, like the proactive read — it never perturbs correctness/mastery/
    # surface-state, only swaps which lesson's problem comes next (§8.1 ordering).
    prereq_problem = _maybe_remediate(live, gate, next_problem)
    if prereq_problem is not None:
        return TurnResponse(
            correct=result.correct,
            error_type=result.error_category,
            next_surface_state=live.tutor.surface_state,
            feedback=result.feedback,
            hint=None,
            mastery=_mastery_view(result.mastery_snapshot, live),
            help_need=help_need,
            intervention=None,
            next_problem=_problem_view(prereq_problem),
            remediation=build_remediation_view(live.flow),
        )
    # When the policy routed to S4 (≥2 consecutive errors, §3.6 row 4), serve the worked
    # solution of the problem the learner JUST got stuck on — history[-1] is that answered
    # problem (submit_answer appended it). NOT next_problem: that is the fresh practice item,
    # and revealing its worked solution would hand over its answer (§3.5 S4). Other states
    # leave worked_example empty (the default). Non-buildable stuck problems yield [].
    worked_example: list[WorkedStepView] = []
    if result.surface_state is SurfaceState.WORKED_EXAMPLE:
        worked_example = _worked_example_view(session.history[-1].problem)
    # Beat 2 (explain-after-correct): on a CORRECT answer, surface the worked steps of the problem
    # they JUST SOLVED so the surface can affirm WHY it works before the next problem. Distinct
    # from the stuck-path worked_example (a rescue); mutually exclusive (a correct answer never
    # routes to S4) and empty on a wrong answer or a non-buildable problem.
    explanation = _worked_example_view(session.history[-1].problem) if result.correct else []
    return TurnResponse(
        correct=result.correct,
        error_type=result.error_category,
        next_surface_state=result.surface_state,
        feedback=result.feedback,
        hint=None,
        mastery=_mastery_view(result.mastery_snapshot, live),
        help_need=help_need,
        intervention=_maybe_intervene(live, gate, next_problem, voice_provider, request.locale),
        next_problem=_problem_view(next_problem),
        worked_example=worked_example,
        explanation=explanation,
    )


def _last_matched_misconception(live: _LiveSession) -> MisconceptionId | None:
    """The named misconception the learner's MOST RECENT answer matched, or ``None``.

    Reads the settled verdict off the session history (``Turn.result.matched_misconception`` — the
    verifier already decided this off the turn loop, §8.2); it never re-verifies. Returns ``None``
    when there is no history yet (a hint requested before any answer) or the last answer matched no
    named misconception, so the error-specific nudge only fires when the verifier actually named the
    error. This is a READ of an existing fact, never a new correctness decision (§8.2)."""
    history = live.tutor.history
    if not history:
        return None
    return history[-1].result.matched_misconception


def _hint_response(
    live: _LiveSession,
    voice_provider: LLMProvider | None,
    hint_provider: LLMProvider | None,
    locale: Locale = "en",
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
    # A hint is a STUCK_NUDGE moment: the avatar encourages forward, never celebrates (Slice 1.3).
    # The emotion is chosen deterministically from the moment, independent of which hint level
    # the escalation lands on and independent of the (optional) LLM voicing of the text.
    hint_cue = select_emotion(MomentType.STUCK_NUDGE)
    # Only the first (NUDGE) hint is a banked canonical line that can have cached audio; the
    # escalated partial_step / worked_step hints are number-templated and stay captions-only.
    hint_audio: SpokenAudio | None = None
    if requests_so_far == 0:
        canonical_nudge = _localized_nudge_text(problem.kc, 0, locale)
        hint_audio = _nudge_audio(problem.kc.value, locale=locale)
        if hint_audio is not None:
            # Speak the cached canonical line and caption it verbatim (canonical-line invariant) —
            # the mouth lip-syncs the same words the bubble shows.
            hint_text = canonical_nudge
        else:
            # No cached audio: the mascot rephrases the canonical nudge in the learner's locale.
            # If the learner's LAST wrong answer matched a NAMED misconception (the verifier already
            # decided this, off the turn loop), voice an ERROR-SPECIFIC corrective nudge tailored to
            # that misconception (Slice 1.2) — gated through the SymPy numeric gate + safety filter,
            # with the canonical nudge as the dependable fallback. Otherwise the generic nudge.
            # Either path: the LLM only re-voices an already-decided line; it never decides
            # correctness (§8.2) or sees mastery state (§8.3), and with no provider returns the
            # verbatim canonical nudge (invariant 4). es-MX stays captions-only until audio renders.
            matched = _last_matched_misconception(live)
            if matched is not None:
                hint_text = voice_misconception_nudge(
                    get_misconception(matched),
                    canonical_nudge,
                    provider=voice_provider,
                    locale=locale,
                )
            else:
                hint_text = voice_help(
                    canonical_nudge,
                    moment=MomentType.STUCK_NUDGE,
                    provider=voice_provider,
                    locale=locale,
                ).text
    else:
        level = HintLevel.PARTIAL_STEP if requests_so_far == 1 else HintLevel.WORKED_STEP
        hint_text = build_validated_hint(problem, level, provider=hint_provider).natural_language
    # If no banked clip voiced this line (an LLM-rephrased nudge, a misconception corrective, or a
    # number-templated worked step — and the whole es-MX path until its bank renders), voice the
    # EXACT shown text live in Hope and cache it (owner decision 2026-06-04). Degrades to
    # captions-only when synth is disabled/keyless/failing (invariant 4); off the graded loop.
    if hint_audio is None:
        hint_audio = _live_audio(hint_text, locale)
    live.hints_this_problem += 1
    return TurnResponse(
        correct=False,
        error_type=ErrorType.NONE,
        next_surface_state=live.tutor.surface_state,
        feedback="Here's something to think about.",
        hint=hint_text,
        hint_emotion=hint_cue.emotion,
        hint_intensity=hint_cue.intensity,
        hint_audio=hint_audio,
        mastery=[],
        next_problem=_problem_view(problem),
    )


@dataclass(frozen=True)
class _PausedParent:
    """A snapshot of the PAUSED grade-level lesson taken when remediation fires (Slice P0.4 / §11).

    CURRICULUM_STANDARD.md §11.4: remediation PAUSES the parent lesson, never resets it — on
    completion the learner resumes at the exact problem they paused on. The live loop's per-lesson
    state (the ``TutorSession``, the HelpNeed stream, the S5-probe progress, the confirmed-KC set,
    the per-problem hint counter) all describe the ACTIVE lesson; to run a nested prereq lesson we
    swap fresh ones in and stash the parent's here, frozen, so resume is an exact restore. Session
    IDENTITY/persistence fields (id, db row, seed base, proactive arm) are NOT snapshotted — they
    belong to the session, not the lesson, and carry across the pause unchanged.

    ``paused_at_index`` is the parent's served-problem count at the pause — the §11.5 "filled dots"
    and the resume point the ``RemediationContext`` carries for the surface.
    """

    tutor: TutorSession
    help_need_history: list[float]
    probe_steps: list[Problem]
    probe_index: int
    confirmed: set[KnowledgeComponentId]
    probe_cooldown: int
    hints_this_problem: int
    paused_at_index: int


@dataclass
class _LiveSession:
    """The per-session runtime record behind a ``session_id`` (Slices 4.4/4.5).

    Bundles the ``TutorSession`` with the live-loop state that is an API-layer concern,
    not the tutor's: the accumulated observe-only HelpNeed ``help_need_history`` the §3.7
    gate reads, and ``proactive_enabled`` — this session's A/B arm. The arm defaults OFF
    (observe-only), so a session never sees a proactive intervention unless it was started
    into the proactive arm; the Slice 5.4 A/B is what turns it on per session.

    ``flow`` is the reactive-remediation axis (Slice P0.4, CURRICULUM_STANDARD.md §11): IN_LESSON
    normally, IN_REMEDIATION ("R") while a nested prerequisite lesson runs because the learner
    struggled on the grade-level lesson. ``paused_parent`` holds the frozen snapshot of the paused
    parent lesson while in remediation (``None`` otherwise) — restored verbatim on resume so the
    parent continues where it paused (§11.4: pauses, never resets). The ``tutor`` / probe /
    confirmed / help-need fields below always describe the CURRENTLY-ACTIVE lesson (the parent, or
    the nested prerequisite while remediating); the router swaps them on pause/resume.
    """

    tutor: TutorSession
    proactive_enabled: bool = False
    # The session's HELP-language preference recorded at ``start`` (Slice 3.6 bilingual scaffold,
    # V2_TODO §0.3): 'en' (default) or 'es-MX'. RECORDED for observability/continuity — the live
    # turn loop reads ``TurnRequest.locale`` per turn (the surface sends it each turn, so an
    # anonymous session needs no server-side lookup, §8.1). NEVER on the decision path: locale
    # selects only the spoken help surface, never verify/mastery/policy.
    locale: Locale = "en"
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
    # The problem_id we last offered a MID-PROBLEM proactive nudge for (live loop Beat 1), so the
    # /events stream nudges a struggling learner at most ONCE per problem instead of on every batch.
    mid_problem_nudged_problem_id: str | None = None
    # The reactive-remediation axis (Slice P0.4, CURRICULUM_STANDARD.md §11). ``flow`` is IN_LESSON
    # normally and IN_REMEDIATION ("R") while a nested prerequisite lesson runs; ``paused_parent``
    # holds the frozen parent-lesson snapshot to resume to while in remediation (None otherwise).
    flow: LessonFlow = field(default_factory=in_lesson)
    paused_parent: _PausedParent | None = None


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


@dataclass(frozen=True)
class DemoTeacherHandle:
    """The seeded demo teacher's persistence handle (Slice TCH.B2), HTTP-free.

    Returned by ``SessionStore.provision_demo_teacher`` so the route can shape the wire
    ``DemoLoginResponse`` (including the ``demo:`` bearer token, which is an auth-layer concern
    the store stays out of). Carries only the stable ``learner_id`` and the email label."""

    learner_id: int
    email: str | None


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
        locale: Locale = "en",
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
            locale=locale,
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
        self,
        kc: KnowledgeComponentId,
        *,
        proactive_enabled: bool = False,
        locale: Locale = "en",
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
            locale=locale,
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
            response = _hint_response(live, self.voice_provider, self.hint_provider, request.locale)
        else:
            response = _answer_response(
                live, request, self.predictor, self.gate, self.voice_provider
            )
            # Beat 3: attach the live between-problem adaptation (observe-then-act, gated).
            response = self._with_live_adaptation(live, response)
        # §11.5: keep the remediation panel in sync with the post-turn flow on EVERY turn (practice,
        # probe step, hint) — it shows whenever the learner is in the "R" state, null otherwise.
        # The pause/resume turns already routed the flow; this projects whatever it now is, so a
        # mid-remediation hint or probe-step turn still carries the panel rather than dropping it.
        if response.remediation is None:
            response = response.model_copy(
                update={"remediation": build_remediation_view(live.flow)}
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

    def mid_problem_nudge(self, request: EventBatchRequest) -> InterventionView | None:
        """A proactive, additive nudge for a learner struggling MID-PROBLEM, or ``None`` (Beat 1).

        Reads the live behavioral stream for the in-progress problem and, if the learner is stuck
        RIGHT NOW (sustained idle / many edits going nowhere / a long freeze before first touch),
        returns a gentle pre-written nudge the surface renders inline — never a workspace change
        (refuse-rule 1: an additive hint is the one mid-problem move allowed). Once per problem.

        Gated, like the between-problem intervention, on the session's proactive arm
        (``proactive_enabled``, default OFF) so the live experience is unchanged until the arm is
        turned on. Off the turn loop entirely; any DB hiccup is swallowed (invariant 7). The mascot
        voices the nudge; the LLM never decides whether to offer it (§8.1).
        """
        live = self._sessions.get(request.session_id)
        if (
            live is None
            or not live.proactive_enabled
            or self.session_factory is None
            or live.db_session_id is None
        ):
            return None
        current = live.tutor.current_problem
        if current is None or live.mid_problem_nudged_problem_id == current.problem_id:
            return None

        try:
            with self.session_factory() as db:
                events = repo.load_events_for_session(db, live.db_session_id)
        except Exception:  # noqa: BLE001 — invariant 7: a telemetry read must not break /events.
            _log.exception("could not read events for mid-problem nudge on %s", request.session_id)
            return None

        episodes = build_episodes(events)
        if not episodes or not should_offer_mid_problem_help(compute_live_features(episodes)):
            return None

        # Offer once per problem: record it so subsequent batches on this problem stay quiet.
        live.mid_problem_nudged_problem_id = current.problem_id
        nudge_text = select_nudge(current.kc).text
        voiced = voice_help(nudge_text, moment=MomentType.STUCK_NUDGE, provider=self.voice_provider)
        # Speak the canonical cached line if it exists, captioned verbatim (canonical-line rule).
        audio = _nudge_audio(current.kc.value)
        return InterventionView(
            kind=InterventionKind.INLINE_ASSERTION,
            text=nudge_text if audio is not None else voiced.text,
            emotion=voiced.emotion,
            intensity=voiced.intensity,
            audio=audio,
        )

    def _with_live_adaptation(self, live: _LiveSession, response: TurnResponse) -> TurnResponse:
        """Attach the live-loop between-problem adaptation to an answer response (HR.B4 Beat 3).

        Observe-then-act, AFTER the graded verdict is fixed (so the sub-100ms decision is untouched
        — this only adds to assembling the response, like the existing HelpNeed/intervention reads).
        Gated on the proactive arm (default OFF): reads the session's behavioral stream (HR.B1
        features) + the HelpNeed score + the streak/representation facts, classifies the sustained
        state (HR.B2), and proposes a labeled morph (HR.B3). The result rides on
        ``TurnResponse.adaptation`` (with the morph target on ``to_surface``) — ADVISORY: the
        per-answer routing on ``next_surface_state`` is left intact and the session is not mutated;
        the surface applies the morph. Returns the response unchanged when off, without persistence,
        or when nothing fires. Any DB hiccup is swallowed (invariant 7)."""
        if (
            not live.proactive_enabled
            or self.session_factory is None
            or live.db_session_id is None
            or response.next_problem is None
        ):
            return response
        try:
            with self.session_factory() as db:
                events = repo.load_events_for_session(db, live.db_session_id)
        except Exception:  # noqa: BLE001 — invariant 7: a telemetry read must not break /turn.
            _log.exception(
                "could not read events for live adaptation on session %s", live.db_session_id
            )
            return response

        episodes = build_episodes(events)
        if not episodes:
            return response
        streak, distinct_reps = _streak_and_distinct_reps(live.tutor)
        state = classify_state(
            compute_live_features(episodes),
            helpneed_score=response.help_need or 0.0,
            correct_streak_no_hint=streak,
            distinct_recent_representations=distinct_reps,
        )
        adaptation = propose_adaptation_view(
            state, response.next_problem.kc, response.next_surface_state
        )
        if adaptation is None:
            return response
        return response.model_copy(update={"adaptation": adaptation})

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

    def provision_demo_teacher(self) -> DemoTeacherHandle | None:
        """Seed-or-return the shared demo teacher and its handle (Slice TCH.B2, for demo-login).

        Idempotent (``repo.get_or_create_demo_teacher`` keys on a fixed session id), so clicking
        the one-click "Teacher demo" tab repeatedly maps to ONE teacher row. Commits its own
        short unit of work — the demo teacher must be a durable row so a later request bearing the
        ``demo:`` handle resolves to it. Returns ``None`` when there is no ``session_factory`` (a
        pure in-memory app cannot persist a demo teacher); the route maps that to 503."""
        if self.session_factory is None:
            return None
        with self.session_factory() as db:
            teacher = repo.get_or_create_demo_teacher(db)
            db.commit()
            return DemoTeacherHandle(learner_id=teacher.id, email=teacher.email)

    def set_locale(self, learner_id: int, locale: Locale) -> str | None:
        """Persist a learner's sticky HELP-language preference, or ``None`` if unknown (Slice 3.6).

        The deferred ``Learner.locale`` write (V2_TODO §0.3): records which language the avatar
        SPEAKS for this learner so it survives across sessions/devices. Owns its short unit of work
        like ``provision_demo_teacher`` — opens a session, mutates via the repository (the only
        place a DB query lives, CLAUDE.md §7), and COMMITS so the preference is durable. Returns the
        stored locale on success, or ``None`` when the learner row is unknown so the route can 404.

        ``locale`` is the validated ``Locale`` literal (the route accepts only 'en'/'es-MX'), so the
        allowed-value check happens at the wire boundary, not here. Raises nothing for a missing
        factory — the route checks ``session_factory`` first and 503s (mirroring the other
        persistence-required endpoints). Locale is a rendering preference, never on the turn loop.
        """
        assert self.session_factory is not None  # the route guards this and 503s when absent.
        with self.session_factory() as db:
            learner = repo.set_learner_locale(db, learner_id, locale)
            if learner is None:
                return None
            stored = learner.locale
            db.commit()
            return stored

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
                    is_foundation=node.kc in FOUNDATION_KCS,
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
                description=catalog_lessons[lp.lesson_slug].description,
                kc_id=lp.kc_id,
                ccss_code=catalog_lessons[lp.lesson_slug].ccss_code,
                teks_code=catalog_lessons[lp.lesson_slug].teks_code,
                status=lp.status,
                probability=lp.probability,
                playable=lp.playable,
                concept_only=lp.concept_only,
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

    def current_problem(self, session_id: str) -> Problem | None:
        """The exact problem the learner is looking at in a live session, or ``None``.

        The honest "what is on screen now": during an S5 transfer probe the live item is
        the current probe STEP (``probe_steps[probe_index]``), not ``tutor.current_problem``
        (which still holds the practice item the probe paused on); otherwise it is the
        tutor's current problem. This mirrors exactly how the store itself decides which
        problem becomes the response's ``next_problem``.

        A thin read for callers that must see the un-projected domain ``Problem`` — its
        ``correct_value`` and operands, which ``ProblemView`` deliberately drops (§8.2) —
        without reaching into ``_LiveSession`` (cf. :meth:`prior_for`). The persona-bot
        data runner (``app.personas.student_bots``) uses it to ask the Layer-3 simulator
        for the persona's action on the real served problem. ``None`` when the session is
        unknown (e.g. never started or lost to a restart).
        """
        live = self._sessions.get(session_id)
        if live is None:
            return None
        if live.probe_steps:
            return live.probe_steps[live.probe_index]
        return live.tutor.current_problem


__all__ = [
    "DemoTeacherHandle",
    "SessionNotFoundError",
    "SessionStore",
    "UnknownRouteError",
    "routing_menu",
]
