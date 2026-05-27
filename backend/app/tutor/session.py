"""The tutor session loop + two-step cold start (Slice 1.7).

This is the tutor scaffolding for Week 1 (PROJECT.md §6): the in-memory session
orchestrator that "walks a hardcoded session correctly". It is a *service* — it
ORCHESTRATES the already-built, already-tested Layer-1 domain and the mastery
model; it never re-implements their jobs (CLAUDE.md §7 boundaries). Concretely:

  - SymPy correctness is the verifier's job, called via ``domain.verifier.verify``
    — there is NO direct SymPy here beyond carrying the ``Rational`` values the
    domain hands back (CLAUDE.md §8.2, ARCHITECTURE.md §14 invariant 2/5);
  - the mastery probability and the §3.4 rules are the mastery model's job, called
    via ``mastery.mastery_model`` — no BKT math is re-derived here;
  - there is NO LLM anywhere on this path (CLAUDE.md §8.1, ARCHITECTURE.md §14
    invariant 1: nothing in the turn loop calls a model provider);
  - there is NO DB persistence — the session lives in memory. Repositories /
    persistence are a deliberately later slice; this orchestrator is pure-ish and
    deterministic so the persona harness can drive it reproducibly (PROJECT.md
    §4.1).

What this slice DOES implement:

  1. **The two-step cold start, locked in decision 0.D.2.** Turn 0 is a
     kid-friendly routing question (three equal-weight KC options + a
     de-emphasized "I'm not sure" default that routes to equivalence). The choice
     seeds a BKT *prior, not a commitment* (via
     ``mastery.initial_prior_from_self_report``). Turn 1 is one calibration
     problem in the chosen route, built from the LOCKED 0.D.2 items. The
     self-report is never echoed to the learner; predicted-vs-actual is logged as
     a metacognitive-calibration signal only and is NOT acted on.
  2. **The session loop, S1 only.** Present a problem in S1 (symbolic focus, the
     default fluent state — ARCHITECTURE.md §7), accept a submitted answer, call
     the domain verifier, build a mastery ``Observation`` from the turn, update
     the in-session mastery view, append the turn to an in-memory history, and
     return a result. The surface stays S1 for the whole week: state TRANSITIONS
     and the reactive policy are Slice 2.4 (PROJECT.md §3.6 NOTE), explicitly out
     of scope here. This module does not import or touch any policy logic.

Determinism: ``TutorSession`` owns all its state (history + per-KC priors); there
is no module-global mutable state. Generated problems are seeded. Same inputs ⇒
same walk (PROJECT.md §4.1, CLAUDE.md §8.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId, Representation, get_kc

# MisconceptionId is owned by misconceptions.py (the verifier re-uses but does not
# re-export it). Importing it from its home keeps the re-export explicit for
# mypy --strict and points the reader at the source of truth.
from app.domain.misconceptions import MisconceptionId
from app.domain.problem_generators import Problem, generate_problem
from app.domain.verifier import ErrorCategory, Submitted, verify
from app.mastery.mastery_model import (
    DEFAULT_BKT_PARAMS,
    BktParams,
    Observation,
    declare_mastery,
    initial_prior_from_self_report,
    kc_mastery_probability,
)

# SurfaceState is the canonical, closed UI-state vocabulary, owned by policy/
# (ARCHITECTURE.md §4, §7 — the adaptation policy's vocabulary). The tutor imports
# it forward (not backward from the API), so it and the API speak the same five
# states. Week 1 only ever uses S1 (no transitions — Slice 2.4).
from app.policy.surface_states import SurfaceState

# The surface this week is always S1 (the default fluent symbolic-focus state,
# ARCHITECTURE.md §7). Naming it once makes the "S1 only, no transitions" scope
# (PROJECT.md §3.6 NOTE) explicit and the day-Slice-2.4 change a single edit.
_WEEK_ONE_SURFACE: SurfaceState = SurfaceState.SYMBOLIC_FOCUS


# ─────────────────── Turn 0: the kid-friendly routing question (0.D.2) ───────────────────


@dataclass(frozen=True)
class RouteOption:
    """One option in the Turn-0 routing question (decision 0.D.2).

    Frozen because the routing menu is fixed configuration, not runtime state. The
    surface renders ``prompt`` (kid-friendly, no curriculum terms, no quiz framing
    — 0.D.2); ``routes_to`` is the KC the option calibrates in at Turn 1.

    ``is_unsure_default`` marks the single de-emphasized "I'm not sure" option. It
    still *routes to* a KC (equivalence) so Turn 1 has a calibration item, but it
    is NOT a self-claim of skill — so it seeds no KC above the unsure default (see
    ``_chosen_kc_for_seeding``). Splitting "where to calibrate" from "what the
    learner claimed to know" is exactly the prior-not-commitment idea: a default
    is not a claim.
    """

    key: str
    prompt: str
    routes_to: KnowledgeComponentId
    is_unsure_default: bool = False


# The three equal-weight KC options + the de-emphasized "I'm not sure" default
# (0.D.2). Prompts are deliberately kid-friendly and free of curriculum terms /
# quiz framing. The three real options span diagnostically distinct KCs the
# calibration items exist for (addition, equivalence, number-line placement); the
# unsure default routes to equivalence (the locked 0.D.2 fallback).
_ADDITION_ROUTE = RouteOption(
    key="combine",
    prompt="Putting two fraction pieces together to see how much you have",
    routes_to=KnowledgeComponentId.ADDITION_UNLIKE,
)
_EQUIVALENCE_ROUTE = RouteOption(
    key="same_amount",
    prompt="Telling when two different-looking fractions are really the same amount",
    routes_to=KnowledgeComponentId.EQUIVALENCE,
)
_NUMBER_LINE_ROUTE = RouteOption(
    key="where_on_line",
    prompt="Finding where a fraction sits on a line between 0 and 1",
    routes_to=KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
)

# The single de-emphasized default. It routes to equivalence for calibration but
# carries no skill claim (0.D.2). Exported so the surface and the tutor agree on
# which option is "I'm not sure" without string-matching.
UNSURE_ROUTE = RouteOption(
    key="not_sure",
    prompt="I'm not sure — just show me something",
    routes_to=KnowledgeComponentId.EQUIVALENCE,
    is_unsure_default=True,
)

_ROUTING_CHOICES: tuple[RouteOption, ...] = (
    _ADDITION_ROUTE,
    _EQUIVALENCE_ROUTE,
    _NUMBER_LINE_ROUTE,
    UNSURE_ROUTE,
)


def routing_choices() -> tuple[RouteOption, ...]:
    """The Turn-0 routing menu: three KC options + the de-emphasized default.

    Returned as data so the surface renders them (and visually de-emphasizes the
    ``is_unsure_default`` one) without the tutor knowing anything about layout
    (0.D.2: no diagnostic/quiz framing — that is a presentation choice, here we
    only supply the options and their KC routing).
    """
    return _ROUTING_CHOICES


# ───────────── Turn 1: the LOCKED calibration problems per route (0.D.2) ─────────────
#
# 0.D.2 names the exact Turn-1 calibration item per route. We construct each as a
# ``Problem`` (the shared domain type) with SymPy-correct values, so the same
# verifier and mastery model handle a calibration turn and any later turn
# identically. These are hand-built (not generator-sampled) precisely because the
# decision LOCKS the specific items — the generator's job is bulk problems, not the
# fixed cold-start probes.


def _addition_calibration() -> Problem:
    """0.D.2 addition route: '1/3 + 1/4'. Correct value 7/12 (SymPy)."""
    first, second = Rational(1, 3), Rational(1, 4)
    return Problem(
        problem_id="CALIB-ADD-1_3+1_4",
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        surface_format=Representation.SYMBOLIC,
        statement="1/3 + 1/4 = ?",
        correct_value=first + second,  # SymPy: 7/12
        representations_available=get_kc(KnowledgeComponentId.ADDITION_UNLIKE).representations,
        operands=(first, second),
    )


def _equivalence_calibration() -> Problem:
    """0.D.2 equivalence route (and the unsure default): 'is 2/3 = 4/6?'.

    The two named fractions are equal, so the correct value is their shared
    magnitude (2/3). Operands carry both fractions in reading order so the
    diagnostic log and any later judgment path can see the pair the item is about.
    """
    first, second = Rational(2, 3), Rational(4, 6)
    return Problem(
        problem_id="CALIB-EQ-2_3=4_6",
        kc=KnowledgeComponentId.EQUIVALENCE,
        surface_format=Representation.SYMBOLIC,
        statement="Is 2/3 the same amount as 4/6?",
        correct_value=first,  # 2/3 == 4/6; the shared magnitude
        representations_available=get_kc(KnowledgeComponentId.EQUIVALENCE).representations,
        operands=(first, second),
    )


def _number_line_calibration() -> Problem:
    """0.D.2 number-line route: place 3/5 on the 0–1 line. Correct value 3/5."""
    target = Rational(3, 5)
    return Problem(
        problem_id="CALIB-NL-3_5",
        kc=KnowledgeComponentId.NUMBER_LINE_PLACEMENT,
        surface_format=Representation.NUMBER_LINE,
        statement="Drag the marker to where 3/5 belongs on the line from 0 to 1.",
        correct_value=target,
        representations_available=get_kc(
            KnowledgeComponentId.NUMBER_LINE_PLACEMENT
        ).representations,
        operands=(target,),
    )


# Map each calibration-target KC to its LOCKED Turn-1 item builder (0.D.2). Only
# the three routable KCs appear; the unsure default routes to equivalence.
_CALIBRATION_BUILDERS = {
    KnowledgeComponentId.ADDITION_UNLIKE: _addition_calibration,
    KnowledgeComponentId.EQUIVALENCE: _equivalence_calibration,
    KnowledgeComponentId.NUMBER_LINE_PLACEMENT: _number_line_calibration,
}


def _calibration_problem(kc: KnowledgeComponentId) -> Problem:
    """The locked Turn-1 calibration ``Problem`` for a routed KC (0.D.2).

    Raises ``KeyError`` (via the dict) on a KC with no locked calibration item —
    the routing menu only ever offers the three that have one, so reaching this
    with another KC is a programming error, not learner input (fail loudly,
    CLAUDE.md §8.5).
    """
    return _CALIBRATION_BUILDERS[kc]()


# ─────────────────── The metacognitive-calibration signal (0.D.2) ───────────────────


@dataclass(frozen=True)
class CalibrationSignal:
    """Predicted-vs-actual at cold start — a logged signal, NEVER acted on (0.D.2).

    0.D.2: "the self-report is never referenced back to the learner;
    predicted-vs-actual is logged as a metacognitive-calibration signal only."
    This record captures exactly that and nothing more — which KC the learner
    routed into (their implicit "prediction" that they can do it) versus whether
    their first calibration attempt was actually correct. The tutor does NOT read
    this back into any decision (no prior adjustment, no transition, no feedback
    text); it exists so a later analysis slice can study learner calibration
    (García et al. 2015/2016, PROJECT.md §8 citation note).

    ``self_reported_kc`` is ``None`` when the learner took the de-emphasized
    "I'm not sure" default — there was no self-claim to calibrate against.
    """

    self_reported_kc: KnowledgeComponentId | None
    first_attempt_correct: bool


# ─────────────────────────── The turn record (in-memory history) ───────────────────────────


@dataclass(frozen=True)
class TurnResult:
    """What one ``submit_answer`` reports back (the loop's per-turn output).

    Mirrors the deterministic outputs the surface needs (cf. the API
    ``TurnResponse`` shape), but is the tutor's own in-process type — the API/
    route mapping is a later slice (CLAUDE.md §7: routes call services, not the
    reverse). Frozen: a turn's verdict is a fact.

    - ``correct`` / ``error_category``  the verifier's verdict (domain decides).
    - ``feedback``                      one-line, label-shaped learner feedback. It
      never echoes the self-report/route (0.D.2). Rich LLM feedback is a later,
      off-path concern (ARCHITECTURE.md §14 invariant 1).
    - ``surface_state``                 the surface AFTER the turn — S1 every time
      this week (no transitions, Slice 2.4).
    - ``matched_misconception``         which named misconception fired, if any
      (passed straight through from the verifier for the diagnostic log).
    - ``mastery_snapshot``              per-KC mastery readout after the update.
    """

    correct: bool
    error_category: ErrorCategory
    feedback: str
    surface_state: SurfaceState
    matched_misconception: MisconceptionId | None
    mastery_snapshot: tuple[MasterySnapshot, ...]


@dataclass(frozen=True)
class MasterySnapshot:
    """A per-KC mastery readout the tutor returns after an update (ARCHITECTURE §6).

    The tutor's in-process snapshot (distinct from the API Pydantic model of the
    same idea — that wiring is a later slice). ``probability`` is the BKT
    probability; ``mastered`` is the mastery model's *declared* mastery (which
    requires far more than the threshold — the §3.4 rules), so the surface can
    show honest progress without re-running the rules itself.
    """

    kc: KnowledgeComponentId
    probability: float
    mastered: bool


@dataclass(frozen=True)
class Turn:
    """One recorded turn in the in-memory session history.

    Holds everything the Week-1 checkpoint needs to "read the log and see expected
    behavior" (PROJECT.md §6): the ``Problem`` presented, the raw answer, the
    mastery ``Observation`` the loop built, the ``TurnResult`` returned, and the
    surface the turn happened in (S1 this week). Frozen — history is append-only.
    """

    problem: Problem
    submitted: Submitted
    observation: Observation
    result: TurnResult
    surface_state: SurfaceState


# ─────────────────────────────── The session orchestrator ───────────────────────────────


@dataclass
class TutorSession:
    """An in-memory, deterministic tutor session (Slice 1.7).

    Owns ALL its state — there is no module-global mutable state, so two sessions
    never interfere and a persona harness can run many in parallel reproducibly
    (PROJECT.md §4.1). State:

    - ``_priors``        per-KC BKT prior P(L0), seeded at cold start from the
      Turn-0 self-report (0.D.2). A prior, not a commitment: a routed KC starts
      modestly higher, everything else at the unsure default, all far below τ.
    - ``current_problem`` the problem currently presented (Turn 1 = the calibration
      item; later turns = whatever ``present_problem`` set).
    - ``surface_state``  always S1 this week (transitions are Slice 2.4).
    - ``_history``       append-only list of completed ``Turn`` records.
    - ``calibration_signal`` the 0.D.2 metacognitive signal, set when the FIRST
      turn after cold start is answered; logged, never acted on.

    Constructed via ``cold_start`` / ``from_route`` (the two-step entry), never by
    hand — the dataclass fields are an implementation detail.
    """

    current_problem: Problem
    _priors: dict[KnowledgeComponentId, float]
    _self_reported_kc: KnowledgeComponentId | None
    _params: BktParams = DEFAULT_BKT_PARAMS
    surface_state: SurfaceState = _WEEK_ONE_SURFACE
    calibration_signal: CalibrationSignal | None = None
    _history: list[Turn] = field(default_factory=list)

    # ── construction: the two-step cold start (0.D.2) ──

    @classmethod
    def cold_start(cls, *, chosen_kc: KnowledgeComponentId | None) -> TutorSession:
        """Begin a session from a Turn-0 routing choice (decision 0.D.2).

        ``chosen_kc`` is the KC the learner routed into, or ``None`` for the
        de-emphasized "I'm not sure" default. We:

          1. seed EVERY KC's BKT prior via the mastery model's
             ``initial_prior_from_self_report`` — the routed KC modestly above the
             unsure default, the rest at the default. This is the prior-not-
             commitment seed (0.D.2); nothing here is at or near τ.
          2. present the LOCKED Turn-1 calibration problem for the route. When
             ``chosen_kc`` is None (unsure default), that is the equivalence
             calibration (0.D.2).

        The surface starts in S1 (the only state this week).
        """
        priors = {
            kc: initial_prior_from_self_report(kc, chosen_kc=chosen_kc)
            for kc in KnowledgeComponentId
        }
        calibration_target = chosen_kc if chosen_kc is not None else UNSURE_ROUTE.routes_to
        return cls(
            current_problem=_calibration_problem(calibration_target),
            _priors=priors,
            _self_reported_kc=chosen_kc,
        )

    @classmethod
    def from_route(cls, option: RouteOption) -> TutorSession:
        """Begin a session from the ``RouteOption`` the surface returned (0.D.2).

        Splits "what KC do we calibrate in" from "what did the learner claim".
        A non-default option is a self-claim, so it seeds that KC's prior up. The
        de-emphasized "I'm not sure" default is NOT a claim, so it seeds nothing
        above the unsure default (``chosen_kc=None``) even though it still routes
        to equivalence for the calibration item. This is the operational meaning of
        prior-not-commitment at the routing boundary.
        """
        chosen_kc = None if option.is_unsure_default else option.routes_to
        session = cls.cold_start(chosen_kc=chosen_kc)
        # The unsure default routes to equivalence for calibration regardless; for a
        # real option the calibration target already matches the chosen KC.
        if option.is_unsure_default:
            session.current_problem = _calibration_problem(option.routes_to)
        return session

    # ── reads ──

    def prior_for(self, kc: KnowledgeComponentId) -> float:
        """The seeded BKT prior P(L0) for ``kc`` (set at cold start; 0.D.2)."""
        return self._priors[kc]

    @property
    def history(self) -> tuple[Turn, ...]:
        """The completed turns, in submission order (append-only, read-only view)."""
        return tuple(self._history)

    @property
    def last_turn(self) -> Turn | None:
        """The most recent completed turn, or ``None`` before any answer is made.

        ``None`` at cold start is also how a caller can assert "no preemptive hint
        / no turn has happened yet" right after presenting the calibration problem.
        """
        return self._history[-1] if self._history else None

    def mastery_probability(self, kc: KnowledgeComponentId) -> float:
        """The current in-session BKT probability for ``kc``.

        Before any observation for ``kc`` exists, this is its seeded prior (the
        cold-start value). Once turns exist, it is the mastery model's BKT run over
        this session's observations for ``kc`` — we delegate the math entirely
        (CLAUDE.md §7: orchestrate, don't re-derive). We thread the seeded prior in
        as the BKT ``p_init`` so the self-report prior actually informs the
        estimate (0.D.2), while still letting evidence override it.
        """
        observations = [t.observation for t in self._history]
        if not any(o.kc == kc for o in observations):
            return self._priors[kc]
        params = self._params_with_prior(kc)
        return kc_mastery_probability(kc, observations, params=params)

    # ── the session loop (S1 only) ──

    def present_problem(
        self,
        *,
        kc: KnowledgeComponentId,
        seed: int,
        surface_format: Representation = Representation.SYMBOLIC,
    ) -> Problem:
        """Present a fresh generated problem for ``kc`` in S1, deterministically.

        Delegates problem construction to the Layer-1 generator (seeded ⇒
        reproducible). The surface stays S1: this slice never changes state
        (transitions are Slice 2.4, PROJECT.md §3.6 NOTE). Returns the problem now
        showing so a caller can read its correct value.
        """
        problem = generate_problem(kc, seed, surface_format)
        self.current_problem = problem
        return problem

    def submit_answer(
        self,
        submitted: Submitted,
        *,
        latency_ms: int,
        hint_used: bool = False,
    ) -> TurnResult:
        """Process one learner answer to the current problem (the turn loop, S1).

        The orchestration, in the order ARCHITECTURE.md §10 prescribes — minus the
        policy/LLM steps that belong to later slices:

          1. **verify** the answer against the current problem with the DOMAIN
             verifier (SymPy decides; this service never judges math — §8.2);
          2. build a mastery **Observation** from the turn (kc, correct,
             representation = the problem's surface format, hinted, latency_ms);
          3. **update the in-session mastery view** by appending the observation to
             history and asking the mastery model for the fresh probability and
             declaration (no BKT re-derivation here — §7);
          4. **append** the completed turn to the in-memory history;
          5. return a ``TurnResult`` — correct?, error category, a one-line
             feedback label, and the per-KC mastery snapshot.

        The surface state returned is S1 (unchanged) every time: NO transition this
        week (Slice 2.4). The feedback never echoes the self-report (0.D.2).

        Side effect besides history: on the FIRST answered turn it records the
        0.D.2 ``calibration_signal`` (predicted-vs-actual) — logged, never acted on.
        """
        problem = self.current_problem
        verdict = verify(problem, submitted)

        observation = Observation(
            kc=problem.kc,
            correct=verdict.is_correct,
            representation=problem.surface_format,
            hinted=hint_used,
            latency_ms=latency_ms,
        )

        # Append BEFORE computing the snapshot so the mastery view reflects this
        # turn (the update step). History is the session's mastery evidence.
        # We build the Turn after the snapshot so it can carry the result.
        provisional_history = [t.observation for t in self._history] + [observation]
        snapshot = self._mastery_snapshot(problem.kc, provisional_history)

        result = TurnResult(
            correct=verdict.is_correct,
            error_category=verdict.error_category,
            feedback=_feedback_line(verdict.is_correct, verdict.error_category),
            surface_state=self.surface_state,  # S1, unchanged (no transitions)
            matched_misconception=verdict.matched_misconception,
            mastery_snapshot=snapshot,
        )

        self._history.append(
            Turn(
                problem=problem,
                submitted=submitted,
                observation=observation,
                result=result,
                surface_state=self.surface_state,
            )
        )

        # 0.D.2 metacognitive signal: set once, on the first answered turn (the
        # Turn-1 calibration attempt). Logged only — never read back into a
        # decision, never echoed to the learner.
        if self.calibration_signal is None:
            self.calibration_signal = CalibrationSignal(
                self_reported_kc=self._self_reported_kc,
                first_attempt_correct=verdict.is_correct,
            )

        return result

    # ── internals ──

    def _params_with_prior(self, kc: KnowledgeComponentId) -> BktParams:
        """The BKT params for ``kc`` with ``p_init`` set to its seeded prior.

        The cold-start self-report seeds P(L0) per KC (0.D.2); BKT consumes the
        prior through ``p_init``. We copy the default params and swap in the
        per-KC seed so the routed KC's elevated prior actually informs its
        estimate, without mutating the shared ``DEFAULT_BKT_PARAMS``.
        """
        base = self._params
        return BktParams(
            p_init=self._priors[kc],
            p_transit=base.p_transit,
            p_slip=base.p_slip,
            p_guess=base.p_guess,
        )

    def _mastery_snapshot(
        self, kc: KnowledgeComponentId, observations: list[Observation]
    ) -> tuple[MasterySnapshot, ...]:
        """Build the per-KC snapshot after an update, for the answered KC.

        We report the answered KC (the one this turn moved). Probability and the
        declaration both come from the mastery model — we only package them. The
        per-KC prior is threaded in as ``p_init`` so the snapshot reflects the
        cold-start seed (0.D.2).
        """
        params = self._params_with_prior(kc)
        probability = kc_mastery_probability(kc, observations, params=params)
        mastered, _reasons = declare_mastery(kc, observations, params=params)
        return (MasterySnapshot(kc=kc, probability=probability, mastered=mastered),)


# ─────────────────────────────── Feedback (S1, non-echoing) ───────────────────────────────


def _feedback_line(correct: bool, error_category: ErrorCategory) -> str:
    """A single-line, learner-facing feedback label for a turn (refuse-rule-4 shape).

    Deliberately plain and short (CLAUDE.md §8.5: write for the reader): the rich,
    LLM-generated surface text is a later, off-the-critical-path concern
    (ARCHITECTURE.md §14 invariant 1). It must NEVER echo the self-report / route
    back to the learner (0.D.2) — so it speaks only about THIS answer, never about
    "the addition route you picked". One line only (no newline), so the surface can
    render it as the transition label.

    The wrong-answer copy is non-judgmental and points at the workspace rather than
    revealing the answer (protects productive struggle, refuse-rule 5). It does not
    name a state change because there is none this week (S1 only).
    """
    if correct:
        return "Correct — nice work."
    if error_category is ErrorCategory.OPERATION:
        return "Not quite — let's look again at how the pieces combine."
    if error_category is ErrorCategory.MAGNITUDE:
        return "Not quite — think about how big this fraction really is."
    return "Not quite — give it another look."


__all__ = [
    "CalibrationSignal",
    "MasterySnapshot",
    "RouteOption",
    "Turn",
    "TurnResult",
    "TutorSession",
    "UNSURE_ROUTE",
    "routing_choices",
]
